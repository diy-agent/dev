"""diy 管控台 v2 — 主入口。

启动 PySide6 窗口，渲染任务树 + agent 监控。
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, Qt, QTimer  # type: ignore[import-untyped]
from PySide6.QtGui import QStandardItem, QStandardItemModel  # type: ignore[import-untyped]
from PySide6.QtWidgets import (  # type: ignore[import-untyped]
    QApplication,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSplitter,
    QTextEdit,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from diydev.app.agent_bridge import (
    AgentStatus,
    list_agents,
    read_progress,
    steer_read,
    steer_send,
)
from diydev.app.task_tree import TaskNode, load_task_tree

# ═══════════════════════════════════════════════════════
# 自定义 data roles
# ═══════════════════════════════════════════════════════

ROLE_TASK_ID = Qt.ItemDataRole.UserRole + 1
ROLE_KIND = Qt.ItemDataRole.UserRole + 2
ROLE_STATE = Qt.ItemDataRole.UserRole + 3
ROLE_SUBJECT = Qt.ItemDataRole.UserRole + 4


def build_model(nodes: list[TaskNode]) -> QStandardItemModel:
    """从 TaskNode 树构建 QStandardItemModel。"""
    model = QStandardItemModel()
    model.setHorizontalHeaderLabels(["任务"])
    for node in nodes:
        _add_node(model, node)
    return model


def _add_node(
    parent: QStandardItemModel | QStandardItem,
    node: TaskNode,
) -> None:
    from PySide6.QtGui import QColor  # type: ignore[import-untyped]

    if node.kind == "subject":
        expanded = Path(node.key).expanduser()
        is_git = expanded.joinpath(".git").is_dir()
        icon = "📦" if is_git else "📁"
        text = f"{icon} {node.key}"
    else:
        icon = node.state_icon
        text = f"{icon} #{node.task_id} {node.title}" if node.title else f"{icon} #{node.task_id}"

    if node.agents:
        running = [a for a in node.agents if a.state == "running"]
        if running:
            text += f"  [🤖×{len(running)}]"

    item = QStandardItem(text)
    item.setData(node.task_id, ROLE_TASK_ID)
    item.setData(node.kind, ROLE_KIND)
    item.setData(node.state, ROLE_STATE)
    item.setData(node.subject_path, ROLE_SUBJECT)

    colors = {
        "done": QColor("#2e7d32"), "closed": QColor("#2e7d32"),
        "active": QColor("#1565c0"), "open": QColor("#1565c0"),
        "blocked": QColor("#c62828"), "cancelled": QColor("#6d4c41"),
    }
    if node.state in colors:
        item.setForeground(colors[node.state])

    parent.appendRow(item)
    for child in node.children:
        _add_node(item, child)


# ═══════════════════════════════════════════════════════
# 边界防护 — 所有外部入口统一兜底
# ═══════════════════════════════════════════════════════


def safe_call(fn, *args, _context="", _on_error="return", **kwargs):
    """所有边界调用的防护层。

    _on_error="return" → 返回错误字符串（socket 边界）
    _on_error="silent" → 吞异常，返回 None（定时器/监控回调）
    """
    try:
        return fn(*args, **kwargs)
    except Exception:
        tb = traceback.format_exc()
        print(f"[diy] 边界异常 [{_context}]\n{tb}", file=sys.stderr, flush=True)
        if _on_error == "return":
            return f"内部错误 (context={_context})"
        return None


def guarded(context: str):
    """装饰器：为 Qt slot / 回调加防护边界。"""
    import functools

    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return safe_call(fn, *args, _context=context, _on_error="silent", **kwargs)
        return wrapper
    return deco


# ═══════════════════════════════════════════════════════
# Steer Panel
# ═══════════════════════════════════════════════════════

class SteerPanel(QDockWidget):
    """Dock widget 用于 /steer 与 agent 通信。"""

    def __init__(self, parent=None):
        super().__init__("Agent 通信", parent)
        self._task_id: int | None = None

        central = QWidget()
        layout = QVBoxLayout(central)

        # 只读对话区
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        layout.addWidget(self._log)

        # 输入区
        input_row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("输入 /steer 消息...")
        self._input.returnPressed.connect(self._send)
        input_row.addWidget(self._input)

        send_btn = QPushButton("发送")
        send_btn.clicked.connect(self._send)
        input_row.addWidget(send_btn)

        layout.addLayout(input_row)
        self.setWidget(central)

        # 定时刷新对话
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_log)
        self._timer.start(3000)

    def set_task(self, task_id: int) -> None:
        self._task_id = task_id
        self.setWindowTitle(f"Agent 通信 — #{task_id}")
        self._refresh_log()

    @guarded("steer.send")
    def _send(self) -> None:
        text = self._input.text().strip()
        if not text or self._task_id is None:
            return
        steer_send(self._task_id, text)
        self._input.clear()
        self._refresh_log()

    @guarded("steer.timer")
    def _refresh_log(self) -> None:
        if self._task_id is None:
            return
        self._log.setPlainText(steer_read(self._task_id) or "(无对话)")


# ═══════════════════════════════════════════════════════
# 主窗口
# ═══════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("diy 管控台")
        self.resize(1000, 650)

        self._started_at = time.time()
        self._last_reload = self._started_at

        # ── AppProbe（Unix socket 探针） ──
        self._probe = AppProbe(self)
        self._probe.start()

        # ── 树视图 ──
        self._tree = QTreeView()
        self._tree.setHeaderHidden(True)
        self._tree.setAnimated(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setExpandsOnDoubleClick(True)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)

        # ── 详情面板 ──
        self._detail = QWidget()
        detail_layout = QVBoxLayout(self._detail)
        self._detail_label = QLabel("选择任务查看详情")
        self._detail_label.setWordWrap(True)
        self._detail_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        detail_layout.addWidget(self._detail_label)

        # ── Steer Panel (dock) ──
        self._steer = SteerPanel(self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._steer)
        self._steer.hide()

        # ── 布局 ──
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._tree)
        splitter.addWidget(self._detail)
        splitter.setSizes([400, 600])
        self.setCentralWidget(splitter)

        # ── 数据 ──
        self._nodes: list[TaskNode] = []
        self._load()

        # ── 信号 ──
        self._tree.selectionModel().selectionChanged.connect(self._on_select)
        self._tree.doubleClicked.connect(self._on_double_click)

        # ── 文件监控 ──
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._on_agent_dir_changed)
        self._watcher.fileChanged.connect(self._on_file_changed)
        self._setup_agent_watcher()

        # state.yaml 变化 → 自动 reload
        state_path = str(Path.home() / ".diy" / "state.yaml")
        self._watcher.addPath(state_path)

        # ── 定时刷新（agent 状态 5s） ──
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_agents)
        self._refresh_timer.start(5000)

    def _load(self) -> None:
        self._nodes = load_task_tree()
        self._last_reload = time.time()
        self._refresh_agents()
        self._render_tree()

    def _render_tree(self) -> None:
        model = build_model(self._nodes)
        self._tree.setModel(model)
        self._tree.expandAll()

    @guarded("timer.refresh")
    def _refresh_agents(self) -> None:
        """从文件系统读取 agent 状态并挂到任务节点上。"""
        agents = list_agents()
        by_task: dict[int, list[AgentStatus]] = {}
        for a in agents:
            by_task.setdefault(a.task_id, []).append(a)

        changed = False
        for n in self._iter_nodes(self._nodes):
            new_agents = [
                AgentInfo(a.agent_id, a.state, a.pid)
                for a in by_task.get(n.task_id or 0, [])
            ]
            if n.agents != new_agents:
                n.agents = new_agents
                changed = True

        if changed:
            self._render_tree()

    def _iter_nodes(self, nodes: list[TaskNode]):
        for n in nodes:
            yield n
            yield from self._iter_nodes(n.children)

    # ── Agent 文件监控 ──
    def _setup_agent_watcher(self) -> None:
        agents_dir = str(Path.home() / ".diy" / "agents")
        os.makedirs(agents_dir, exist_ok=True)
        if agents_dir not in self._watcher.directories():
            self._watcher.addPath(agents_dir)

    @guarded("watcher.agent")
    def _on_agent_dir_changed(self, _path: str) -> None:
        self._refresh_agents()

    @guarded("watcher.file")
    def _on_file_changed(self, path: str) -> None:
        if path.endswith("state.yaml"):
            # macOS: yaml 写入可能换 inode，重新 watch
            self._watcher.removePath(path)
            self._watcher.addPath(path)
            self._load()
        else:
            self._refresh_agents()

    # ── 右键菜单 ──
    @guarded("ctxmenu")
    def _on_context_menu(self, pos):
        from PySide6.QtWidgets import QMenu  # type: ignore[import-untyped]

        index = self._tree.indexAt(pos)
        if not index.isValid():
            return

        kind = index.data(ROLE_KIND)
        task_id = index.data(ROLE_TASK_ID)
        state = index.data(ROLE_STATE)

        menu = QMenu(self)

        if kind == "task" and task_id:
            menu.addAction(f"#{task_id} — {state}").setEnabled(False)
            menu.addSeparator()

            state_menu = menu.addMenu("更改状态")
            for s, label in [("pending", "⏳ Pending"), ("active", "🔄 Active"),
                             ("done", "✅ Done"), ("blocked", "🚫 Blocked"),
                             ("cancelled", "❌ Cancelled")]:
                if s != state:
                    act = state_menu.addAction(label)
                    act.triggered.connect(lambda checked, t=task_id, ns=s: self._set_state(t, ns))

            menu.addSeparator()

            steer_act = menu.addAction("💬 /steer 通信")
            steer_act.triggered.connect(lambda checked, t=task_id: self._open_steer(t))

            del_act = menu.addAction("🗑 删除任务")
            del_act.triggered.connect(lambda checked, t=task_id: self._delete_task(t))

        menu.addSeparator()
        refresh_act = menu.addAction("🔄 刷新")
        refresh_act.triggered.connect(self._load)

        menu.exec(self._tree.viewport().mapToGlobal(pos))

    # ── 操作 ──
    @guarded("action.state")
    def _set_state(self, task_id: int, new_state: str) -> None:
        import subprocess
        subprocess.run(
            ["dai", "task", "edit", str(task_id), "--state", new_state],
            capture_output=True,
        )
        self._load()

    @guarded("action.delete")
    def _delete_task(self, task_id: int) -> None:
        import subprocess
        subprocess.run(
            ["dai", "task", "delete", str(task_id)],
            capture_output=True,
        )
        self._load()

    @guarded("action.steer")
    def _open_steer(self, task_id: int) -> None:
        self._steer.set_task(task_id)
        self._steer.show()

    # ── 选中 / 双击 ──
    @guarded("tree.select")
    def _on_select(self):
        indexes = self._tree.selectionModel().selectedIndexes()
        if not indexes:
            return

        index = indexes[0]
        kind = index.data(ROLE_KIND)
        task_id = index.data(ROLE_TASK_ID)
        state = index.data(ROLE_STATE)
        subject = index.data(ROLE_SUBJECT)

        lines = []
        if kind == "subject":
            lines.append(f"**Subject:** `{subject or index.data(Qt.ItemDataRole.DisplayRole)}`")
        elif kind == "task" and task_id:
            lines.append(f"**#{task_id}** — {state}")

        node = self._find_node(task_id) if task_id else None
        if node:
            if node.title:
                lines.append(f"标题: {node.title}")
            if node.subject_path:
                lines.append(f"Subject: `{node.subject_path}`")
            if node.parent_id:
                lines.append(f"父任务: #{node.parent_id}")
            if node.agents:
                lines.append("")
                lines.append("**Agent:**")
                for a in node.agents:
                    icon = {"running": "🤖", "done": "✅", "blocked": "🚫"}.get(a.state, "⏳")
                    progress = read_progress(node.task_id or 0, tail=5).strip()
                    lines.append(f"  {icon} {a.agent_id} ({a.state})")
                    if progress:
                        for pline in progress.split("\n")[-3:]:
                            lines.append(f"    {pline}")

        self._detail_label.setText("\n".join(lines) if lines else "选择任务查看详情")

    @guarded("tree.double")
    def _on_double_click(self, index):
        task_id = index.data(ROLE_TASK_ID)
        if task_id:
            self._open_steer(task_id)

    def _find_node(self, task_id: int) -> TaskNode | None:
        def _search(nodes: list[TaskNode]) -> TaskNode | None:
            for n in nodes:
                if n.task_id == task_id:
                    return n
                r = _search(n.children)
                if r:
                    return r
            return None
        return _search(self._nodes)

    # ── AppProbe 序列化 ──

    def format_tree(self) -> str:
        """遍历 QStandardItemModel，直接读 DisplayRole — 和 UI 完全一致。"""
        model = self._tree.model()
        if model is None:
            return "(空)"
        lines: list[str] = []
        self._dump_model_rows(model, None, lines, 0)
        return "\n".join(lines) if lines else "(空)"

    def format_status(self) -> str:
        """app 运行状态快照（类似 Docker healthcheck）。"""
        now = time.time()
        geom = self.geometry()

        def _count(nodes):
            s = t = 0
            for n in nodes:
                if n.kind == "subject":
                    s += 1
                else:
                    t += 1
                cs, ct = _count(n.children)
                s += cs; t += ct
            return s, t

        subjects, tasks = _count(self._nodes)
        model = self._tree.model()
        model_rows = model.rowCount() if model else 0

        state_path = str(Path.home() / ".diy" / "state.yaml")
        state_exists = os.path.isfile(state_path)

        return "\n".join([
            f"pid:       {os.getpid()}",
            f"uptime:    {now - self._started_at:.0f}s",
            f"reload:    {now - self._last_reload:.0f}s ago",
            f"window:    {geom.width()}×{geom.height()} @ ({geom.x()},{geom.y()}) "
            f"{'hidden' if self.isHidden() else 'visible'}"
            f"{' minimized' if self.isMinimized() else ''}",
            f"tree:      {subjects} subjects + {tasks} tasks = {subjects + tasks} nodes "
            f"(model rows: {model_rows})",
            f"state:     {state_path} {'✅' if state_exists else '❌ missing'}",
            f"socket:    {self._probe._path} {'✅' if self._probe._server else '❌'}",
            f"watchers:  {len(self._watcher.files()) + len(self._watcher.directories())} paths",
            f"timers:    refresh={self._refresh_timer.interval()}ms "
            f"steer={self._steer._timer.interval()}ms",
            f"qt:        {'running' if QApplication.instance() else 'stopped'}",
        ])

    @staticmethod
    def _dump_model_rows(
        model, parent: QStandardItem | None, lines: list[str], depth: int
    ) -> None:
        """递归遍历 model 的行，读 DisplayRole 拼缩进。"""
        prefix = "  " * depth
        item = model.invisibleRootItem() if parent is None else parent
        for row in range(item.rowCount()):
            child = item.child(row)
            text = child.data(Qt.ItemDataRole.DisplayRole) or ""
            lines.append(f"{prefix}{text}")
            MainWindow._dump_model_rows(model, child, lines, depth + 1)

    def format_node(self, task_id: int) -> str:
        """序列化指定任务节点详情（含 agent 状态）。"""
        node = self._find_node(task_id)
        if node is None:
            return f"未找到任务 #{task_id}"
        lines = [
            f"#{node.task_id} {node.title}",
            f"  kind:    {node.kind}",
            f"  state:   {node.state} {node.state_icon}",
            f"  subject: {node.subject_path or '(无)'}",
            f"  parent:  {f'#{node.parent_id}' if node.parent_id else '(无)'}",
            f"  depth:   {node.depth}",
            f"  children: {len(node.children)}",
        ]
        if node.children:
            lines.append("  child_list:")
            for c in node.children:
                lines.append(f"    #{c.task_id} {c.title} [{c.state}]")
        if node.agents:
            lines.append("  agents:")
            for a in node.agents:
                icon = {"running": "🤖", "done": "✅", "blocked": "🚫"}.get(a.state, "⏳")
                lines.append(f"    {icon} {a.agent_id} (pid={a.pid}, state={a.state})")
        return "\n".join(lines)

    def format_agents(self) -> str:
        """序列化当前 agent 列表。"""
        lines: list[str] = []
        for n in self._iter_nodes(self._nodes):
            for a in n.agents:
                lines.append(f"#{n.task_id} {a.agent_id} pid={a.pid} state={a.state}")
        return "\n".join(lines) if lines else "(无 agent)"

    def closeEvent(self, event):
        self._probe.stop()
        super().closeEvent(event)


# ═══════════════════════════════════════════════════════
# AppProbe — Unix socket 探针（agent 实时探测/操纵）
# ═══════════════════════════════════════════════════════

import socket
import socketserver
import threading

from cyclopts import App as CycloptsApp
from PySide6.QtCore import QObject  # type: ignore[import-untyped]


class ProbeCLI:
    """Socket 协议层 — 用 cyclopts 解析命令，输出为纯文本。"""

    def __init__(self, window: "MainWindow"):
        self._window = window
        self._app = CycloptsApp(name="probe")

        @self._app.command
        def tree():
            """完整任务树（和 UI 一致）"""
            return self._window.format_tree()

        @self._app.command
        def status():
            """健康检查（pid/窗口/树/定时器）"""
            return self._window.format_status()

        @self._app.command
        def agents():
            """agent 列表"""
            return self._window.format_agents()

        @self._app.command
        def reload():
            """热重载 state.yaml"""
            from PySide6.QtCore import QMetaObject, Qt as QtCore
            QMetaObject.invokeMethod(
                self._window, "_load", QtCore.ConnectionType.QueuedConnection)
            return "OK"

        @self._app.command
        def node(task_id: int):
            """<id> 任务节点详情"""
            return self._window.format_node(task_id)

        @self._app.default
        def unknown(*tokens: str):
            return f"未知命令: {' '.join(tokens)!r}  试试 --help"

    def dispatch(self, line: str) -> str:
        tokens = line.split() if line else ["--help"]

        # --help / -h → 手动构建帮助（避免 cyclopts console 兼容问题）
        if set(tokens) & {"--help", "-h"} or not tokens:
            lines = ["命令:"]
            for name, sub in sorted(self._app.meta._registered_commands.items()):
                help_text = (sub.default_command.__doc__ or "").strip()
                lines.append(f"  {name:<10s} {help_text}")
            return "\n".join(lines)

        try:
            command, bound, _ = self._app.parse_args(tokens)
            return str(command(*bound.args, **bound.kwargs))
        except SystemExit:
            return "错误: 命令解析失败"


class AppProbe(QObject):
    """Unix domain socket server，允许外部进程查询/操纵 app 运行状态。

    协议: 纯文本，cyclopts 解析:
      tree         → 完整任务树
      node <id>    → 任务详情
      status       → 健康检查
      agents       → agent 列表
      reload       → 重载 state.yaml
      --help       → 帮助
    """

    def __init__(self, window: "MainWindow", socket_path: str = "~/.diy/app.sock"):
        super().__init__(window)
        self._window = window
        self._path = os.path.expanduser(socket_path)
        self._server: socketserver.UnixStreamServer | None = None
        self._thread: threading.Thread | None = None
        self._cli = ProbeCLI(window)

    def start(self) -> None:
        # 检查是否有活实例
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect(self._path)
            s.close()
            return  # 有活实例，不启动
        except (OSError, socket.timeout):
            pass  # 连不上 → 残留或不存在

        # 清理残留
        try:
            os.unlink(self._path)
        except OSError:
            pass

        self._server = socketserver.UnixStreamServer(self._path, _make_handler(self))
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
        try:
            os.unlink(self._path)
        except OSError:
            pass


def _make_handler(probe: AppProbe):
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            data = self.rfile.readline()
            if not data:
                return
            cmd = data.decode("utf-8").strip()
            result = safe_call(
                probe._cli.dispatch, cmd,
                _context="socket",
                _on_error="return",
            )
            self.wfile.write((result + "\n").encode("utf-8"))
    return Handler


# ═══════════════════════════════════════════════════════
# AgentInfo (简化 dataclass，避免循环导入)
# ═══════════════════════════════════════════════════════

class AgentInfo:
    def __init__(self, agent_id: str, state: str = "unknown", pid: int | None = None):
        self.agent_id = agent_id
        self.state = state
        self.pid = pid

    def __eq__(self, other):
        if not isinstance(other, AgentInfo):
            return False
        return self.agent_id == other.agent_id and self.state == other.state


# ═══════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════

def main():
    import signal

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Ctrl+C 两次退出（调试模式下 Qt event loop 会吞 SIGINT）
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
