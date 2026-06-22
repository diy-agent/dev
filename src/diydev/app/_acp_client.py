"""
ACP Client — 通过 ACP 协议与 Hermes ACP 服务通信，将实时事件桥接到 Qt 信号。

ACP（Agent Client Protocol）是基于 JSON-RPC 2.0 的 stdio 协议。
Hermes 通过 ``hermes acp`` 启动 ACP server，我们的 Client 通过子进程 stdin/stdout 与之通信。

架构：
    GUI 进程（主线程，QtAsyncio event loop）
      │
      ├── AcpManager          — 子进程生命周期 + 连接管理
      │     └── asyncio:     spawn_agent_process → hermes acp
      │                       ClientSideConnection → ACP JSON-RPC
      │
      ├── AcpChatClient(QObject)
      │     └── session_update() → Qt Signal → AgentChatPanel 实时渲染
      │
      └── Hermes state.db     — 仅 session 结束后冷启动读取历史

数据流（活跃 session）：
    prompt(text)
      → asyncio 写 JSON-RPC request → hermes acp stdin
      → hermes acp 执行 AIAgent
      → callback → ACP session_update → hermes acp stdout
      → asyncio 读 JSON-RPC notification
      → AcpChatClient.session_update() → emit Qt Signal
      → AgentChatPanel 渲染

Python 版本注意事项：
    - PySide6 6.8.x 内置 QtAsyncio（QAsyncioEventLoopPolicy），零额外依赖
    - Python 3.12+ 废弃 asyncio.AbstractChildWatcher（QAsyncioEventLoopPolicy 已标记 DeprecationWarning）
    - Python 3.15 将移除 asyncio.set_event_loop_policy()，届时需改用 asyncio.run() + loop factory
      （参考 https://discuss.python.org/t/removing-the-asyncio-policy-system/37553）
    - Windows: ProactorEventLoop（Python 3.8+ 默认）的 subprocess pipe 与 QtAsyncio 可能冲突，
      需要显式切换为 WindowsSelectorEventLoopPolicy
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal  # type: ignore[import-untyped]

# 使用 app 的日志系统（diy.app 才有 handler，__name__ 会丢日志）
from diydev.app._app_log import get_logger as _get_app_logger

logger = _get_app_logger("acp")

from acp import (
    PROTOCOL_VERSION,
    Client,
    RequestError,
    text_block,
)
from acp.schema import (
    AgentMessageChunk,
    AgentThoughtChunk,
    AudioContentBlock,
    ClientCapabilities,
    EmbeddedResourceContentBlock,
    ImageContentBlock,
    Implementation,
    PermissionOption,
    PromptResponse,
    ReadTextFileResponse,
    ReleaseTerminalResponse,
    RequestPermissionResponse,
    ResourceContentBlock,
    TerminalOutputResponse,
    TextContentBlock,
    ToolCallProgress,
    ToolCallStart,
    UsageUpdate,
    WriteTextFileResponse,
    CreateTerminalResponse,
    KillTerminalResponse,
    WaitForTerminalExitResponse,
)


# =========================================================================
# ACP Client — 将 ACP 协议事件转换为 Qt 信号
# =========================================================================


class AcpChatClient(QObject):
    """ACP Client 实现：接收 Hermes ACP server 的实时事件，emit Qt Signal。

    实现 acp.Client 协议（duck typing，不直接继承 Protocol 以免 QObject 元类冲突）。
    所有回调由 ACP 协议栈在 asyncio event loop 上异步调用。
    由于 QtAsyncio 将 Qt event loop 作为 asyncio event loop，
    这些回调与 Qt 主线程在同一线程上，emit Signal 天然安全。

    Signal 概览：
        delta_received      — 流式文本（AgentMessageChunk）
        reasoning_received  — 推理过程（AgentThoughtChunk）
        tool_started        — 工具开始执行（ToolCallStart）
        session_ready       — 新 session 创建成功
        finished            — 当前 prompt 执行完毕
        error_occurred      — 错误
    """

    # ── 实时事件信号 ──
    delta_received = Signal(str)                    # 流式文本 token
    reasoning_received = Signal(str)                # 推理过程
    tool_started = Signal(str, str, dict)           # (name, tool_call_id, args)
    session_ready = Signal(str)                     # (session_id)
    finished = Signal(str)                          # (stop_reason)
    error_occurred = Signal(str)                    # (error_message)

    def __init__(self, parent: QObject | None = None) -> None:
        QObject.__init__(self, parent)
        self._conn: Client | None = None

    # ── ACP Client 接口 ──

    async def session_update(
        self,
        session_id: str,
        update: AgentMessageChunk
        | AgentThoughtChunk
        | ToolCallStart
        | ToolCallProgress
        | UsageUpdate
        | Any,
        **kwargs: Any,
    ) -> None:
        """ACP 实时事件回调——由 ACP SDK 在收到 JSON-RPC notification 时调用。

        根据 update 类型分发到不同 Signal：
            AgentMessageChunk → delta_received（流式文本）
            AgentThoughtChunk → reasoning_received（推理）
            ToolCallStart     → tool_started（工具调用）
            ToolCallProgress  → tool_started（工具进度更新）
            UsageUpdate       → 日志记录，不 emit
        """
        if isinstance(update, AgentMessageChunk):
            content = update.content
            if isinstance(content, TextContentBlock):
                self.delta_received.emit(content.text)
            elif isinstance(content, str):
                self.delta_received.emit(content)

        elif isinstance(update, AgentThoughtChunk):
            thought = update.thought
            if thought and thought.content:
                self.reasoning_received.emit(thought.content)

        elif isinstance(update, ToolCallStart):
            name = update.tool_call.name if hasattr(update, "tool_call") and update.tool_call else ""
            tc_id = update.tool_call.id if hasattr(update, "tool_call") and update.tool_call else ""
            args = {}
            if hasattr(update, "tool_call") and update.tool_call and hasattr(update.tool_call, "arguments"):
                args = update.tool_call.arguments if isinstance(update.tool_call.arguments, dict) else {}
            self.tool_started.emit(name, tc_id, args)

        elif isinstance(update, ToolCallProgress):
            tc = update.tool_call if hasattr(update, "tool_call") else None
            name = tc.name if tc and hasattr(tc, "name") else ""
            tc_id = tc.id if tc and hasattr(tc, "id") else ""
            args = tc.arguments if tc and hasattr(tc, "arguments") and isinstance(tc.arguments, dict) else {}
            self.tool_started.emit(name, tc_id, args)

        elif isinstance(update, UsageUpdate):
            logger.debug(
                "[acp] usage: input=%s output=%s",
                update.input_tokens if hasattr(update, "input_tokens") else "?",
                update.output_tokens if hasattr(update, "output_tokens") else "?",
            )

    # ── 以下 acp.Client 必需但本场景暂不使用的接口 ──

    async def request_permission(
        self, options: list[PermissionOption], session_id: str,
        tool_call: ToolCallProgress | ToolCallStart, **kwargs: Any,
    ) -> RequestPermissionResponse:
        raise RequestError.method_not_found("session/request_permission")

    async def write_text_file(self, content: str, path: str, session_id: str, **kwargs: Any) -> WriteTextFileResponse | None:
        raise RequestError.method_not_found("fs/write_text_file")

    async def read_text_file(self, path: str, session_id: str, limit: int | None = None, line: int | None = None, **kwargs: Any) -> ReadTextFileResponse:
        raise RequestError.method_not_found("fs/read_text_file")

    async def create_terminal(self, command: str, session_id: str, args: list[str] | None = None, cwd: str | None = None, env: list[Any] | None = None, output_byte_limit: int | None = None, **kwargs: Any) -> CreateTerminalResponse:
        raise RequestError.method_not_found("terminal/create")

    async def terminal_output(self, session_id: str, terminal_id: str, **kwargs: Any) -> TerminalOutputResponse:
        raise RequestError.method_not_found("terminal/output")

    async def release_terminal(self, session_id: str, terminal_id: str, **kwargs: Any) -> ReleaseTerminalResponse | None:
        raise RequestError.method_not_found("terminal/release")

    async def wait_for_terminal_exit(self, session_id: str, terminal_id: str, **kwargs: Any) -> WaitForTerminalExitResponse:
        raise RequestError.method_not_found("terminal/wait_for_exit")

    async def kill_terminal(self, session_id: str, terminal_id: str, **kwargs: Any) -> KillTerminalResponse | None:
        raise RequestError.method_not_found("terminal/kill")

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        raise RequestError.method_not_found(method)

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        raise RequestError.method_not_found(method)

    def on_connect(self, conn: Client) -> None:
        """ACP 握手成功后回调——保存连接对象供后续 prompt() 等调用。"""
        self._conn = conn

    @property
    def conn(self) -> Client | None:
        return self._conn


# =========================================================================
# ACP 连接管理器 — 子进程生命周期 + ACP 会话管理
# =========================================================================


class AcpManager(QObject):
    """管理 Hermes ACP 子进程的完整生命周期。

    职责：
        1. 启动 ``hermes acp`` 子进程（__init__ 或 start 时）
        2. ACP protocol 握手（initialize）
        3. 会话管理（new_session / prompt / cancel）
        4. 退出时清理子进程

    Signal（透传 self._client 的信号）：
        delta_received, reasoning_received, tool_started, ...
        直接绑定 AgentChatPanel 的槽函数。
    """

    # 透传 AcpChatClient 的信号
    delta_received = Signal(str)
    reasoning_received = Signal(str)
    tool_started = Signal(str, str, dict)
    finished = Signal(str)
    error_occurred = Signal(str)

    # Hermes acp 的可执行路径查找顺序
    _HERMES_BIN_CANDIDATES = [
        "hermes",
        str(Path.home() / ".local" / "bin" / "hermes"),
        str(Path.home() / ".hermes" / "hermes-agent" / "venv" / "bin" / "hermes"),
    ]

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._client = AcpChatClient(self)
        self._proc: asyncio.subprocess.Process | None = None
        self._session_id: str | None = None
        self._transport_ctx = None
        self._conn = None
        # 跨线程同步：threading.Event 而非 asyncio.Event（不同 event loop 间不兼容）
        self._acp_ready = threading.Event()
        self._acp_error: Exception | None = None

        # 透传 client 信号
        self._client.delta_received.connect(self.delta_received)
        self._client.reasoning_received.connect(self.reasoning_received)
        self._client.tool_started.connect(self.tool_started)
        self._client.finished.connect(self.finished)
        self._client.error_occurred.connect(self.error_occurred)

    @staticmethod
    def _find_hermes() -> str:
        """查找 hermes 可执行路径。"""
        for candidate in AcpManager._HERMES_BIN_CANDIDATES:
            if "/" not in candidate:
                import shutil
                if shutil.which(candidate):
                    return candidate
                continue
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        return "hermes"

    async def start(self) -> None:
        """启动 ``hermes acp`` 子进程并完成 ACP 握手。

        QAsyncioEventLoop 不支持 subprocess_exec()，所以子进程管理
        在独立线程的 asyncio loop 上运行，ACP 事件通过 Qt Signal 跨线程桥接。
        """
        hermes_bin = self._find_hermes()
        logger.info("[acp] 启动: %s acp", hermes_bin)

        # 独立线程：子进程 I/O + ACP 协议
        self._acp_ready.clear()
        self._acp_error = None

        async def _run() -> None:
            try:
                import subprocess as _sp
                from acp.client.connection import ClientSideConnection  # noqa: PLC0415
                from acp.stdio import _WritePipeProtocol  # noqa: PLC0415

                logger.info("[acp] 手动 spawn 子进程...")
                proc = _sp.Popen(
                    [hermes_bin, "acp"],
                    stdin=_sp.PIPE,
                    stdout=_sp.PIPE,
                    stderr=_sp.PIPE,
                )

                loop = asyncio.get_running_loop()
                reader = asyncio.StreamReader()
                rp = asyncio.StreamReaderProtocol(reader)
                await loop.connect_read_pipe(lambda: rp, proc.stdout)
                wt, wp = await loop.connect_write_pipe(
                    lambda: _WritePipeProtocol(), proc.stdin,
                )
                writer = asyncio.StreamWriter(wt, wp, None, loop)

                conn = ClientSideConnection(self._client, input_stream=writer, output_stream=reader)
                self._conn = conn
                self._proc = proc
                self._acp_ready.set()
                logger.info("[acp] 子进程就绪 pid=%d", proc.pid)

                # 协议握手
                result = await conn.initialize(
                    protocol_version=PROTOCOL_VERSION,
                    client_capabilities=ClientCapabilities(),
                    client_info=Implementation(name="diy-app", version="0.1.0"),
                )
                logger.info(
                    "[acp] 握手完成 — agent=%s v=%s  pver=%s",
                    result.agent_info.name if result.agent_info else "?",
                    result.agent_info.version if result.agent_info else "?",
                    result.protocol_version,
                )
                # 创建默认 session
                await self.new_session()
                # 阻塞直到连接关闭（子进程退出）
                await asyncio.get_running_loop().run_in_executor(None, proc.wait)
            except Exception as exc:
                self._acp_error = exc
                self._acp_ready.set()
                raise

        def _thread_main() -> None:
            # 不能用 QAsyncioEventLoopPolicy（全局策略），它不支持 subprocess_exec
            loop = asyncio.SelectorEventLoop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(_run())
            finally:
                loop.close()

        t = threading.Thread(target=_thread_main, daemon=True, name="acp-io")
        t.start()

        # 等待连接就绪或出错（超时 15s）—— 非阻塞 polling 避免卡 Qt 主线程
        try:
            await asyncio.wait_for(
                self._wait_for_ready(),
                timeout=15.0,
            )
        except asyncio.TimeoutError:
            raise RuntimeError("ACP 连接超时（15s）")
        if self._acp_error:
            raise self._acp_error  # type: ignore[misc]

    async def _wait_for_ready(self) -> None:
        """轮询 _acp_ready（threading.Event），不阻塞 Qt 主线程。"""
        while not self._acp_ready.is_set():
            await asyncio.sleep(0.05)

    async def _pipe_stderr(self) -> None:
        """读取 stderr 避免 pipe buffer 满阻塞。"""
        try:
            while self._proc and self._proc.stderr and not self._proc.stderr.at_eof():
                line = await self._proc.stderr.readline()
                if line:
                    logger.info("[hermes] %s", line.decode("utf-8", errors="replace").rstrip())
        except Exception as exc:
            logger.debug("[acp] stderr 结束: %s", exc)

    async def new_session(self, cwd: str | None = None) -> str:
        """创建 ACP session，返回 session_id。"""
        if not self._conn:
            raise RuntimeError("ACP 未初始化")
        result = await self._conn.new_session(cwd=cwd or os.getcwd(), mcp_servers=[])
        self._session_id = result.session_id
        self._client.session_ready.emit(self._session_id)
        logger.info("[acp] session: %s", self._session_id)
        return self._session_id

    async def prompt(self, text: str) -> PromptResponse | None:
        """发送用户消息，实时事件通过信号推送。"""
        if not self._conn or not self._session_id:
            self.error_occurred.emit("ACP 未连接")
            return None
        result = await self._conn.prompt(
            session_id=self._session_id,
            prompt=[text_block(text)],
        )
        self._client.finished.emit(result.stop_reason if result else "unknown")
        return result

    async def cancel(self) -> None:
        """取消当前 prompt。"""
        if not self._conn or not self._session_id:
            return
        await self._conn.cancel(session_id=self._session_id)
        logger.info("[acp] 已取消")

    async def stop(self) -> None:
        """关闭连接并终止子进程。"""
        self._conn = None
        if self._proc is not None:
            try:
                if self._proc.returncode is None:
                    self._proc.terminate()
                    try:
                        await asyncio.get_event_loop().run_in_executor(
                            None, self._proc.wait, 3.0,
                        )
                    except asyncio.TimeoutError:
                        self._proc.kill()
            except ProcessLookupError:
                pass
            self._proc = None
        logger.info("[acp] 已关闭")
