"""Agent Daemon — 后台进程，管理 AIAgent 实例。

作为子进程运行（使用 Hermes venv 的 Python 解释器），
通过 Unix socket 接收文本命令。CLI 通过 socket 与之通信。

协议: 纯文本，一行一个命令，shlex 解析
  spawn --task <uri> --message <msg> [--model <m>] [--toolsets <t1,t2>] [--reasoning <n>]
  send --task <uri> --message <msg>
  kill --task <uri>
  show --task <uri>
  list
  config
  shutdown

输出: 纯文本行，首行是状态行，后续是数据。
  成功: OK <状态描述>
  失败: ERROR <错误信息>
  数据行: <json> 或普通文本

启动:
  /path/to/hermes/python -m diydev._agent_daemon
  
注意: 这是一个 standalone 模块，不依赖 diydev 包的 __init__.py。
直接通过 PYTHONPATH 确保 src/ 在 sys.path 上即可。
"""

from __future__ import annotations

import io
import json
import logging
import os
import shlex
import socketserver
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# 直接导入 _agent_pool，不走 diydev.__init__
_pool_dir = str(Path(__file__).resolve().parent)
if _pool_dir not in sys.path:
    sys.path.insert(0, _pool_dir)
import _agent_pool  # noqa: E402
AgentStatus = _agent_pool.AgentStatus
TaskAgentConfig = _agent_pool.TaskAgentConfig

# 导入 steer_reply 用于写入 steer.log
_app_dir = str(Path(__file__).resolve().parent / "app")
if _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)  # FIXME 临时设置sys.path
from agent_bridge import steer_reply  # noqa: E402

logger = logging.getLogger("agentd")

def _diy_home() -> Path:
    """获取 DIY 数据根目录。独立实现，避免循环导入。"""
    if home := os.environ.get("DIY_HOME"):
        return Path(home)
    return Path(os.path.expanduser("~/.diy"))

_SOCKET_PATH = _diy_home() / "agentd.sock"


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
    model="deepseek-v4-flash-202605",
    provider="diy-tencent-tokenhub",
    enabled_toolsets=[],
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
            started_at=datetime.now().isoformat(),
        )
        self.agent = None  # AIAgent 实例（懒创建）
        self._lock = threading.Lock()
        self._agent_class = agent_class
        self._messages: list[dict] = None
        self._output_buf: list[str] = []  # 流式输出累积
        self._output_chunks: list[str] = []  # 单个 delta
        self._exec_thread: threading.Thread | None = None
        self._interrupt_event = threading.Event()
        self._bridge_dir = _diy_home() / "agents" / task_uri

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

        # 回退到 DEFAULT_CONFIG（在 spawn 无 CLI 参数时生效）
        model = self.config.model or DEFAULT_CONFIG.model
        provider = self.config.provider or DEFAULT_CONFIG.provider
        if model:
            kwargs["model"] = model
        if provider:
            kwargs["provider"] = provider
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

    def _on_tool_progress(self, event: str, *args, **kwargs):
        """工具进度回调 — 写入 tool_events.jsonl 供 GUI 实时显示。

        事件类型:
          tool.started   — args: (name, preview, full_args)
          tool.completed — args: (name, None, None), kwargs: duration, is_error, result
          _thinking      — args: (first_line,)
          reasoning.available — args: ("_thinking", text, None)
        """
        import json as _json
        try:
            self._bridge_dir.mkdir(parents=True, exist_ok=True)
            entry = {"event": event, "ts": datetime.now().strftime("%H:%M:%S")}
            if event == "tool.started" and len(args) >= 2:
                entry["tool"] = args[0]
                entry["preview"] = args[1] or ""
            elif event == "tool.completed" and len(args) >= 1:
                entry["tool"] = args[0]
                entry["duration"] = kwargs.get("duration", 0)
                entry["is_error"] = kwargs.get("is_error", False)
            elif event in ("_thinking", "reasoning.available"):
                entry["text"] = args[0] if args else ""
            else:
                entry["args"] = [str(a) for a in args]
            with open(self._bridge_dir / "tool_events.jsonl", "a") as fh:
                fh.write(_json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass  # 写失败不阻塞 agent

    def spawn(self, prompt: str) -> str:
        """在后台线程启动 agent。"""
        if self.status.state == "running":
            return "agent 已在运行"

        # Fix: interrupt 或 killed 后重新 spawn 要重建实例
        if self.status.state in ("interrupted", "killed", "failed"):
            self.agent = None
            self._messages = None
            self._output_buf = []
            self._output_chunks = []
            self._exec_thread = None
            self.status.error = ""  # Fix: 重置 error

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
            final_response = result.get("final_response") or ""
            self.status.last_message = final_response[:200]
            # 写入 steer.log 让 GUI 能读到回复（仅 done 状态）
            if self.status.state == "done" and final_response:
                steer_reply(self.task_uri, final_response)
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
        """终止 agent。

        Fix: kill 后 error 字段重置。
        """
        if self.agent is not None:
            try:
                self.agent.interrupt("用户终止")
            except Exception:
                pass
        self.status.state = "killed"
        self.status.error = ""  # Fix: 重置 error
        self._write_bridge_status()

    @property
    def output_tail(self) -> list[str]:
        lines = [l for l in self._output_buf if l]
        return lines[-20:]

    def _format_status_block(self) -> str:
        """将 AgentStatus 格式化为可读文本块。"""
        s = self.status
        lines = [
            f"状态: {s.state}",
            f"模型: {s.model or self.config.model or ''}",
            f"启动: {s.started_at}",
            f"最后消息: {s.last_message[:200]}",
        ]
        if s.error:
            lines.append(f"错误: {s.error}")
        tail = self.output_tail
        if tail:
            lines.append("--- 输出 ---")
            lines.extend(tail)
        return "\n".join(lines)


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
            else:
                # Fix: re-spawn 时更新 config（替换旧的，不保留已存在的 agent.config）
                agent.config = agent_config
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
# 文本协议解析器
# ════════════════════════════════════════════════════════════════

def _parse_bool(val: str) -> bool:
    return val.lower() in ("true", "1", "yes")


def _parse_config_from_args(
    args: dict[str, str],
) -> dict[str, Any]:
    """从 args dict 提取 agent config 参数。"""
    config: dict[str, Any] = {}
    if args.get("model"):
        config["model"] = args["model"]
    if args.get("provider"):
        config["provider"] = args["provider"]
    if args.get("toolsets"):
        config["enabled_toolsets"] = [t.strip() for t in args["toolsets"].split(",")]
    if args.get("max_iterations"):
        config["max_iterations"] = int(args["max_iterations"])
    if args.get("skip_context_files"):
        config["skip_context_files"] = _parse_bool(args["skip_context_files"])
    if args.get("skip_memory"):
        config["skip_memory"] = _parse_bool(args["skip_memory"])
    if args.get("reasoning"):
        config["reasoning_budget"] = int(args["reasoning"])
    if args.get("checkpoints"):
        config["checkpoints"] = _parse_bool(args["checkpoints"])
    return config


def _dispatch_text(cmd_line: str, out: io.TextIOBase) -> None:
    """解析一行文本命令，执行操作，输出结果到 out。

    输出流式 flush，每行独立。
    """
    global _pool
    pool = _pool

    tokens = shlex.split(cmd_line)
    if not tokens:
        out.write("ERROR 空命令\n")
        out.flush()
        return

    action = tokens[0]

    # 解析 --key value 或 --key=value 参数
    args: dict[str, str] = {}
    i = 1
    while i < len(tokens):
        token = tokens[i]
        if token.startswith("--"):
            key = token[2:]
            # 支持 --key=value 语法
            if "=" in key:
                k, v = key.split("=", 1)
                args[k] = v
            elif i + 1 < len(tokens) and not tokens[i + 1].startswith("--"):
                i += 1
                args[key] = tokens[i]
            else:
                args[key] = "true"
        i += 1

    if pool is None:
        out.write("ERROR agentd 未初始化\n")
        out.flush()
        return

    try:
        if action == "spawn":
            task_uri = args.get("task")
            message = args.get("message")
            if not task_uri or not message:
                out.write("ERROR spawn 需要 --task 和 --message\n")
                out.flush()
                return
            config = _parse_config_from_args(args)
            status = pool.spawn(task_uri, message, config)
            out.write(f"OK {status.state}\n")
            out.flush()

        elif action == "send":
            task_uri = args.get("task")
            message = args.get("message")
            if not task_uri or not message:
                out.write("ERROR send 需要 --task 和 --message\n")
                out.flush()
                return
            status = pool.send(task_uri, message)
            out.write(f"OK {status.state}\n")
            out.flush()

        elif action == "kill":
            task_uri = args.get("task")
            if not task_uri:
                out.write("ERROR kill 需要 --task\n")
                out.flush()
                return
            status = pool.kill(task_uri)
            out.write(f"OK killed\n")
            out.flush()

        elif action == "show":
            task_uri = args.get("task")
            if not task_uri:
                out.write("ERROR show 需要 --task\n")
                out.flush()
                return
            status = pool.show(task_uri)
            if status is None:
                out.write(f"ERROR agent {task_uri} 不存在\n")
                out.flush()
                return
            # 输出状态块
            agent = pool._agents.get(task_uri)
            if agent:
                out.write(agent._format_status_block() + "\n")
            else:
                out.write(f"状态: {status.state}\n")
            out.flush()

        elif action == "list":
            agents = pool.list()
            if not agents:
                out.write("(无活跃 agent)\n")
                out.flush()
                return
            for a in agents:
                out.write(f"{a.task_uri:30s} {a.state:10s} {a.model or ''}\n")
            out.flush()

        elif action == "config":
            out.write(json.dumps({"default": DEFAULT_CONFIG.to_dict()}, indent=2) + "\n")
            out.flush()

        elif action == "shutdown":
            out.write("OK shutdown\n")
            out.flush()
            # 在后台线程执行 shutdown，避免 socket write 被截断
            import _thread
            _thread.interrupt_main()

        else:
            out.write(f"ERROR 未知命令: {action}\n")
            out.flush()

    except Exception as exc:
        logger.exception("dispatch error: %s", action)
        out.write(f"ERROR {exc}\n")
        out.flush()


# ════════════════════════════════════════════════════════════════
# Socket 服务器
# ════════════════════════════════════════════════════════════════

_pool: SessionPool | None = None


class AgentDaemonHandler(socketserver.StreamRequestHandler):
    """处理 CLI 发来的文本命令。"""

    def handle(self):
        # 使用 rfile 按行读取，支持流式
        data = self.rfile.readline()
        if not data:
            return
        cmd_line = data.decode("utf-8").strip()

        # 文本输出到 wfile（二进制流 → TextIOWrapper）
        text_out = io.TextIOWrapper(
            self.wfile, encoding="utf-8", write_through=True
        )
        _dispatch_text(cmd_line, text_out)


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
