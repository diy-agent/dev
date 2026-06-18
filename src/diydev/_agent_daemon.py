"""Agent Daemon — 后台进程，管理 AIAgent 实例。

作为子进程运行（使用 Hermes venv 的 Python 解释器），
通过 Unix socket 接收命令。CLI 通过 socket 与之通信。

启动:
  /path/to/hermes/python -m diydev._agent_daemon
  
注意: 这是一个 standalone 模块，不依赖 diydev 包的 __init__.py。
直接通过 PYTHONPATH 确保 src/ 在 sys.path 上即可。
"""

from __future__ import annotations

import json
import logging
import os
import socketserver
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# 直接导入 _agent_pool，不走 diydev.__init__
_pool_dir = str(Path(__file__).resolve().parent)
if _pool_dir not in sys.path:
    sys.path.insert(0, _pool_dir)
import _agent_pool  # noqa: E402
AgentStatus = _agent_pool.AgentStatus
DaemonCommand = _agent_pool.DaemonCommand
DaemonResponse = _agent_pool.DaemonResponse
TaskAgentConfig = _agent_pool.TaskAgentConfig

logger = logging.getLogger("agentd")

_SOCKET_PATH = Path.home() / ".diy" / "agentd.sock"


# ════════════════════════════════════════════════════════════════
# Hermes 导入（只在 daemon 进程中执行）
# ════════════════════════════════════════════════════════════════

def _import_hermes():
    """Import Hermes AIAgent."""
    try:
        from run_agent import AIAgent
        return AIAgent
    except ImportError:
        # 尝试添加 Hermes 项目根到 sys.path
        hermes_home = Path.home() / ".hermes" / "hermes-agent"
        if hermes_home.exists():
            sys.path.insert(0, str(hermes_home))
        from run_agent import AIAgent  # noqa: F811
        return AIAgent


# ════════════════════════════════════════════════════════════════
# 默认配置
# ════════════════════════════════════════════════════════════════

DEFAULT_CONFIG = TaskAgentConfig(
    model="",
    enabled_toolsets=["terminal", "file"],
    max_iterations=50,
    skip_context_files=True,
    skip_memory=True,
)


# ════════════════════════════════════════════════════════════════
# SessionPool — 管理所有 TaskAgent
# ════════════════════════════════════════════════════════════════

class _ManagedAgent:
    """单个 task agent — 包装 AIAgent + 执行线程。"""

    def __init__(self, task_uri: str, config: TaskAgentConfig, agent_class):
        import threading as _t

        self.task_uri = task_uri
        self.config = config
        self.status = AgentStatus(
            task_uri=task_uri,
            state="idle",
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        self.agent = None  # AIAgent 实例（懒创建）
        self._lock = threading.Lock()
        self._agent_class = agent_class
        self._messages: list[dict] = None
        self._output_buf: list[str] = []  # 流式输出累积
        self._output_chunks: list[str] = []  # 单个 delta
        self._exec_thread: threading.Thread | None = None
        self._interrupt_event = threading.Event()
        self._bridge_dir = Path.home() / ".diy" / "agents" / task_uri

    def _write_bridge_status(self):
        """写 status.json / progress.log，让 GUI agent_bridge 能读到。"""
        import json
        try:
            self._bridge_dir.mkdir(parents=True, exist_ok=True)

            # status.json
            pid = os.getpid()
            status = {
                "agent_id": f"agentd-{self.task_uri}",
                "task_id": self.task_uri,
                "state": self.status.state,
                "pid": pid,
                "model": self.status.model or (self.config.model or ""),
                "started_at": self.status.started_at,
            }
            tmp = self._bridge_dir / "status.json.tmp"
            with open(tmp, "w") as fh:
                json.dump(status, fh, indent=2)
            tmp.replace(self._bridge_dir / "status.json")

            # progress.log — 追加最新输出
            if self._output_chunks:
                text = "".join(self._output_chunks)
                # 只写新内容（尚未写入文件的）
                written = getattr(self, "_bridge_bytes_written", 0)
                new_text = text[written:]
                if new_text:
                    with open(self._bridge_dir / "progress.log", "a") as fh:
                        fh.write(new_text)
                    self._bridge_bytes_written = len(text.encode("utf-8"))
        except Exception:
            pass  # bridge 文件写失败不阻塞 agent

    def build_agent(self):
        """创建 AIAgent 实例。"""
        kwargs: dict[str, Any] = {
            "quiet_mode": True,
            "session_id": f"agent-{self.task_uri}",
            "stream_delta_callback": self._on_stream,
            "tool_progress_callback": self._on_tool_progress,
        }

        if self.config.model:
            kwargs["model"] = self.config.model
        if self.config.provider:
            kwargs["provider"] = self.config.provider
        if self.config.enabled_toolsets is not None:
            kwargs["enabled_toolsets"] = self.config.enabled_toolsets
        if self.config.max_iterations is not None:
            kwargs["max_iterations"] = self.config.max_iterations
        if self.config.skip_context_files is not None:
            kwargs["skip_context_files"] = self.config.skip_context_files
        if self.config.skip_memory is not None:
            kwargs["skip_memory"] = self.config.skip_memory
        if self.config.reasoning_budget is not None:
            kwargs["reasoning_config"] = {"budget_tokens": self.config.reasoning_budget}
        if self.config.checkpoints:
            kwargs["checkpoints_enabled"] = True

        self.agent = self._agent_class(**kwargs)
        return self.agent

    def _on_stream(self, text: str | None):
        if text is not None:
            self._output_chunks.append(text)
            self._output_buf.extend(text.split("\n"))
            # 每收到流式数据就写 progress.log（GUI 实时显示）
            self._write_bridge_status()

    @property
    def output_text(self) -> str:
        return "".join(self._output_chunks)

    def _on_tool_progress(self, *args, **kwargs):
        pass

    def spawn(self, prompt: str) -> str:
        """在后台线程启动 agent。"""
        if self.status.state == "running":
            return "agent 已在运行"

        if self.agent is None:
            self.build_agent()

        self.status.state = "running"
        self.status.last_message = prompt[:200]
        self._write_bridge_status()
        self._exec_thread = threading.Thread(
            target=self._run,
            args=(prompt,),
            daemon=True,
        )
        self._exec_thread.start()
        return "ok"

    def _run(self, prompt: str):
        """线程入口 — 执行 run_conversation。"""
        try:
            result = self.agent.run_conversation(
                prompt,
                conversation_history=self._messages,
            )
            self._messages = result.get("messages")
            if result.get("interrupted"):
                self.status.state = "interrupted"
            elif result.get("failed"):
                self.status.state = "failed"
                self.status.error = "agent 执行失败"
            else:
                self.status.state = "done"
            self.status.last_message = (result.get("final_response") or "")[:200]
        except Exception as exc:
            logger.exception("agent %s 执行异常", self.task_uri)
            self.status.state = "failed"
            self.status.error = str(exc)
        finally:
            self._write_bridge_status()

    def send(self, message: str) -> str:
        """向 agent 发送消息（如果正在运行则注入 steer）。"""
        if self.status.state == "running":
            # agent 正在执行 — 通过 steer 注入
            if self.agent is not None:
                try:
                    self.agent._pending_steer = message
                    self.status.last_message = f"[steer] {message[:200]}"
                    return "steer 已发送"
                except Exception as exc:
                    return f"steer 失败: {exc}"
            return "agent 未初始化"

        if self.agent is None:
            self.build_agent()

        # agent 空闲 — 启动新对话
        self.spawn(message)
        return "ok"

    def kill(self):
        """终止 agent。"""
        if self.agent is not None:
            try:
                self.agent.interrupt("用户终止")
            except Exception:
                pass
        self.status.state = "killed"
        self._write_bridge_status()

    @property
    def output_tail(self) -> list[str]:
        lines = [l for l in self._output_buf if l]
        return lines[-20:]


class SessionPool:
    """管理所有 task agent 实例。"""

    def __init__(self):
        self._agents: dict[str, _ManagedAgent] = {}
        self._lock = threading.Lock()
        self._AIAgent = _import_hermes()

    def spawn(self, task_uri: str, prompt: str, config: dict | None = None) -> AgentStatus:
        agent_config = TaskAgentConfig.from_dict(config or {})
        with self._lock:
            agent = self._agents.get(task_uri)
            if agent is None:
                agent = _ManagedAgent(task_uri, agent_config, self._AIAgent)
                self._agents[task_uri] = agent
            elif agent.status.state == "running":
                return agent.status
        msg = agent.spawn(prompt)
        return agent.status

    def send(self, task_uri: str, message: str) -> AgentStatus:
        with self._lock:
            agent = self._agents.get(task_uri)
        if agent is None:
            raise ValueError(f"agent {task_uri} 不存在")
        agent.send(message)
        return agent.status

    def kill(self, task_uri: str) -> AgentStatus:
        with self._lock:
            agent = self._agents.get(task_uri)
        if agent is None:
            raise ValueError(f"agent {task_uri} 不存在")
        agent.kill()
        return agent.status

    def show(self, task_uri: str) -> AgentStatus | None:
        with self._lock:
            agent = self._agents.get(task_uri)
        if agent is None:
            return None
        s = agent.status
        s.output_tail = agent.output_tail
        return s

    def list(self) -> list[AgentStatus]:
        with self._lock:
            agents = list(self._agents.values())
        return [a.status for a in agents]

    def cleanup(self):
        for agent in self._agents.values():
            agent.kill()


# ════════════════════════════════════════════════════════════════
# Socket 服务器
# ════════════════════════════════════════════════════════════════

_pool: SessionPool | None = None


class AgentDaemonHandler(socketserver.BaseRequestHandler):
    """处理 CLI 发来的命令。"""

    def handle(self):
        raw = self.request.recv(65536)
        if not raw:
            return
        try:
            cmd = DaemonCommand.from_dict(json.loads(raw.decode("utf-8")))
        except (json.JSONDecodeError, Exception) as exc:
            resp = DaemonResponse(ok=False, error=f"解析失败: {exc}")
            self.request.sendall(json.dumps(resp.to_dict()).encode("utf-8"))
            return

        try:
            resp = self._dispatch(cmd)
        except Exception as exc:
            logger.exception("dispatch error")
            resp = DaemonResponse(ok=False, error=str(exc))

        self.request.sendall(json.dumps(resp.to_dict()).encode("utf-8"))

    def _dispatch(self, cmd: DaemonCommand) -> DaemonResponse:
        pool = _pool
        if pool is None:
            return DaemonResponse(ok=False, error="agentd 未初始化")

        if cmd.action == "spawn":
            status = pool.spawn(cmd.task_uri, cmd.message, cmd.config)
            return DaemonResponse(data=status.to_dict())

        elif cmd.action == "send":
            status = pool.send(cmd.task_uri, cmd.message)
            return DaemonResponse(data=status.to_dict())

        elif cmd.action == "kill":
            status = pool.kill(cmd.task_uri)
            return DaemonResponse(data=status.to_dict())

        elif cmd.action == "show":
            status = pool.show(cmd.task_uri)
            if status is None:
                return DaemonResponse(ok=False, error=f"agent {cmd.task_uri} 不存在")
            return DaemonResponse(data=status.to_dict())

        elif cmd.action == "list":
            agents = pool.list()
            return DaemonResponse(data=[a.to_dict() for a in agents])

        elif cmd.action == "config":
            # 目前 daemon 不支持运行时改默认配置
            return DaemonResponse(data={"default": DEFAULT_CONFIG.to_dict()})

        else:
            return DaemonResponse(ok=False, error=f"未知 action: {cmd.action}")


class _ThreadedUnixServer(socketserver.ThreadingUnixStreamServer):
    allow_reuse_address = True
    daemon_threads = True


def run_daemon():
    """启动 agent daemon（单实例，socket 锁检测）。"""
    global _pool

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    # ── Socket 锁检查：连接成功说明有活实例 ──
    import socket as _sock
    try:
        s = _sock.socket(_sock.AF_UNIX, _sock.SOCK_STREAM)
        s.settimeout(0.5)
        s.connect(str(_SOCKET_PATH))
        s.close()
        print(f"错误: 已有运行中的 agentd (socket: {_SOCKET_PATH})", file=sys.stderr)
        sys.exit(1)
    except (OSError, _sock.timeout):
        pass  # 连不上 → 残留或不存在

    # ── 清理残留 socket ──
    if _SOCKET_PATH.exists():
        _SOCKET_PATH.unlink()

    _pool = SessionPool()
    logger.info("SessionPool 已创建 (Hermes AIAgent: %s)", _pool._AIAgent.__name__)

    server = _ThreadedUnixServer(str(_SOCKET_PATH), AgentDaemonHandler)
    logger.info("agentd 监听 %s", _SOCKET_PATH)

    # ── 记下 socket 文件身份，用于自检 ──
    _sock_dev = _sock_ino = None
    try:
        st = os.stat(_SOCKET_PATH)
        _sock_dev, _sock_ino = st.st_dev, st.st_ino
    except OSError:
        pass

    # ── 心跳线程：检测 socket 文件是否异常 ──
    def _health_beat():
        while True:
            time.sleep(5)
            try:
                st = os.stat(_SOCKET_PATH)
            except FileNotFoundError:
                logger.critical("agentd socket 文件被删除，退出")
                os._exit(1)
            if (st.st_dev, st.st_ino) != (_sock_dev, _sock_ino):
                logger.critical("agentd socket 文件被替换，退出")
                os._exit(1)

    t = threading.Thread(target=_health_beat, daemon=True)
    t.start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("正在关闭...")
    finally:
        _pool.cleanup()
        _SOCKET_PATH.unlink(missing_ok=True)


# ════════════════════════════════════════════════════════════════
# 入口
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    run_daemon()
