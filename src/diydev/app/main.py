"""diy 管控台 v2 — 主入口。

启动 PySide6 窗口，渲染任务树 + agent 监控。
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, Qt, QTimer, Slot, Signal  # type: ignore[import-untyped]
from PySide6.QtGui import QAction, QStandardItem, QStandardItemModel  # type: ignore[import-untyped]
from PySide6.QtWidgets import (  # type: ignore[import-untyped]
    QAbstractItemView,
    QApplication,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from diydev.app._activity_bar import ActivityBar
from diydev.app._app_log import logger, setup_app_logger
from diydev.app._log_panel import LogPanel
from diydev.app.agent_bridge import (
    AgentStatus,
    list_agents,
    steer_read,
    steer_send,
)
from diydev.app.task_tree import TaskNode, load_task_tree

# ═══════════════════════════════════════════════════════
# 自定义 data roles
# ═══════════════════════════════════════════════════════

ROLE_TASK_URI = Qt.ItemDataRole.UserRole + 1
ROLE_KIND = Qt.ItemDataRole.UserRole + 2
ROLE_STATE = Qt.ItemDataRole.UserRole + 3
ROLE_SUBJECT = Qt.ItemDataRole.UserRole + 4

# ═══════════════════════════════════════════════════════
# 详情面板样式
# ═══════════════════════════════════════════════════════

_STYLE = """<style>
  .card { font-family: -apple-system, "Segoe UI", sans-serif; padding: 12px; }
  .placeholder { font-family: -apple-system, "Segoe UI", sans-serif; color: #a6adc8; font-size: 14px; padding: 20px; }
  .header { font-size: 14px; font-weight: bold; color: #cdd6f4; margin-bottom: 8px; }
  .title { font-size: 18px; font-weight: bold; color: #ffffff; margin-bottom: 10px; }
  .detail { font-size: 13px; color: #bac2de; line-height: 1.6; margin: 8px 0 12px 0; white-space: pre-wrap; }
  .meta { margin: 8px 0 4px 0; }
  .tag { display: inline-block; background: #45475a; color: #cdd6f4; font-size: 12px; padding: 2px 8px; border-radius: 4px; margin-right: 6px; }
  .section-title { font-size: 13px; font-weight: bold; color: #a6adc8; margin: 4px 0; }
  .agent { font-size: 12px; color: #bac2de; margin: 2px 0; }
  .agent code { background: #1e1e2e; color: #f5c2e7; padding: 1px 4px; border-radius: 3px; }
  .hint { font-size: 12px; color: #585b70; margin-top: 4px; }
  .badge { display: inline-block; font-size: 11px; font-weight: 600; padding: 2px 10px; border-radius: 10px; color: #1e1e2e; }
  hr { border: none; border-top: 1px solid #45475a; margin: 12px 0; }
</style>"""


# ═══════════════════════════════════════════════════════
# Material3 暗色主题 — 语义化颜色系统
# ═══════════════════════════════════════════════════════

class Theme:
    """语义化颜色令牌 — 高对比度暗色主题"""

    # 基色
    surface = "#1e1e2e"        # 主背景
    surface_alt = "#181825"    # 侧栏/面板背景
    on_surface = "#cdd6f4"     # 主文本
    on_surface_variant = "#a6adc8"  # 次要文本
    outline = "#45475a"        # 分隔线

    # 状态色 — 高对比度版本
    pending_bg = "#e5c07b"     # 琥珀黄背景
    pending_fg = "#1e1e2e"     # 琥珀上文本（深色）
    active_bg = "#7aa2f7"      # 明亮蓝
    active_fg = "#1e1e2e"
    done_bg = "#9ece6a"        # 明亮绿
    done_fg = "#1e1e2e"
    cancelled_bg = "#565f89"   # 灰紫
    cancelled_fg = "#cdd6f4"
    blocked_bg = "#f7768e"     # 明亮红
    blocked_fg = "#1e1e2e"
    shelved_bg = "#e0af68"     # 橙
    shelved_fg = "#1e1e2e"
    new_bg = "#73daca"         # 青
    new_fg = "#1e1e2e"

    @classmethod
    def state_bg(cls, state: str) -> str:
        return {
            "pending": cls.pending_bg, "active": cls.active_bg,
            "open": cls.active_bg, "done": cls.done_bg,
            "closed": cls.done_bg, "cancelled": cls.cancelled_bg,
            "blocked": cls.blocked_bg, "shelved": cls.shelved_bg,
            "new": cls.new_bg,
        }.get(state, cls.cancelled_bg)

    @classmethod
    def state_fg(cls, state: str) -> str:
        return {
            "pending": cls.pending_fg, "active": cls.active_fg,
            "open": cls.active_fg, "done": cls.done_fg,
            "closed": cls.done_fg, "cancelled": cls.cancelled_fg,
            "blocked": cls.blocked_fg, "shelved": cls.shelved_fg,
            "new": cls.new_fg,
        }.get(state, cls.on_surface)


def _app_stylesheet() -> str:
    """全局 Material3 暗色主题 QSS。"""
    return f"""
        QMainWindow {{ background: {Theme.surface}; }}
        QDockWidget {{ background: {Theme.surface}; color: {Theme.on_surface};
                       border: 1px solid {Theme.outline}; titlebar-close-icon: none; }}
        QDockWidget::title {{ background: {Theme.surface_alt};
                              padding: 4px 8px; text-align: left; }}
        QTreeView {{ background: {Theme.surface}; color: {Theme.on_surface};
                     border: none; font-size: 13px;
                     outline: none; }}
        QTreeView::item {{ padding: 2px 4px; border-radius: 4px; }}
        QTreeView::item:selected {{ background: #45475a; color: #cdd6f4; }}
        QTreeView::item:hover {{ background: #313244; }}
        QTreeView::branch {{ background: {Theme.surface}; }}
        QTextBrowser {{ background: {Theme.surface}; color: {Theme.on_surface};
                        border: none; font-size: 14px; padding: 8px; }}
        QPlainTextEdit {{ background: {Theme.surface_alt}; color: {Theme.on_surface};
                          border: none; font-size: 12px; }}
        QLineEdit {{ background: {Theme.surface_alt}; color: {Theme.on_surface};
                     border: 1px solid {Theme.outline}; border-radius: 4px;
                     padding: 4px 8px; }}
        QLineEdit:focus {{ border: 1px solid {Theme.active_bg}; }}
        QPushButton {{ background: #45475a; color: {Theme.on_surface};
                       border: none; border-radius: 4px; padding: 4px 12px; }}
        QPushButton:hover {{ background: #585b70; }}
        QTabWidget::pane {{ background: {Theme.surface}; border: 1px solid {Theme.outline}; }}
        QTabBar::tab {{ background: {Theme.surface_alt}; color: {Theme.on_surface_variant};
                       padding: 4px 12px; border: none; }}
        QTabBar::tab:selected {{ background: {Theme.surface}; color: {Theme.on_surface};
                                 border-bottom: 2px solid {Theme.active_bg}; }}
        QScrollBar:vertical {{ background: {Theme.surface_alt}; width: 10px;
                               border: none; }}
        QScrollBar::handle:vertical {{ background: #45475a; border-radius: 4px;
                                       min-height: 20px; }}
        QScrollBar::handle:vertical:hover {{ background: #585b70; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical
          {{ height: 0; background: none; border: none; }}
        QToolTip {{ background: {Theme.surface_alt}; color: {Theme.on_surface};
                    border: 1px solid {Theme.outline}; font-size: 12px; }}
    """


def _esc_html(text: str) -> str:
    """转义 HTML 特殊字符"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _short_uri(uri: str) -> str:
    """URI 短显示：local/task/58 → local#58, github.com/.../58 → github#58"""
    if uri.startswith("local/"):
        num = uri.rstrip("/").rsplit("/", 1)[-1]
        return f"local#{num}"
    if "github.com" in uri:
        num = uri.rstrip("/").rsplit("/", 1)[-1]
        return f"github#{num}"
    return uri


def _state_badge(state: str) -> str:
    bg = Theme.state_bg(state)
    fg = Theme.state_fg(state)
    return f'<span class="badge" style="background:{bg};color:{fg};">{state}</span>'


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
        text = f"{icon} {node.label or node.key}"
    else:
        icon = node.state_icon
        display_uri = _short_uri(node.uri or "")
        text = f"{icon} {display_uri} {node.title}" if node.title else f"{icon} {display_uri}"

    if node.agents:
        running = [a for a in node.agents if a.state == "running"]
        if running:
            text += f"  [🤖×{len(running)}]"

    item = QStandardItem(text)
    item.setData(node.uri, ROLE_TASK_URI)
    item.setData(node.kind, ROLE_KIND)
    item.setData(node.state, ROLE_STATE)
    item.setData(node.subject_path, ROLE_SUBJECT)

    # 树节点用列表文本色，不用 badge 色
    item.setForeground(QColor(Theme.on_surface))

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
        logger.error("[%s] 边界异常\n%s", _context, tb.rstrip())
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

class SteerPanel(QWidget):
    """用于 /steer 与 agent 通信。"""

    title_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._task_uri: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

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

        # 定时刷新对话
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_log)
        self._timer.start(3000)

    def set_task(self, uri: str) -> None:
        self._task_uri = uri
        self.title_changed.emit(f"Agent 通信 — {uri}")
        self._refresh_log()

    @guarded("steer.send")
    def _send(self) -> None:
        text = self._input.text().strip()
        if not text or self._task_uri is None:
            return
        steer_send(self._task_uri, text)
        self._input.clear()
        self._refresh_log()

    @guarded("steer.timer")
    def _refresh_log(self) -> None:
        if self._task_uri is None:
            return
        self._log.setPlainText(steer_read(self._task_uri) or "(无对话)")


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

        # ── Activity Bar（左侧活动栏） ──
        self._activity_bar = ActivityBar(self)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, self._activity_bar)

        # ── 树视图（主侧边栏） ──
        self._tree = QTreeView()
        self._tree.setHeaderHidden(True)
        self._tree.setAnimated(True)
        self._tree.setIndentation(14)  # 缩进减半
        self._tree.setRootIsDecorated(True)
        self._tree.setExpandsOnDoubleClick(True)
        self._tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)

        self._primary_sidebar = QDockWidget("任务树", self)
        self._primary_sidebar.setObjectName("PrimarySidebar")
        self._primary_sidebar.setWidget(self._tree)
        self._primary_sidebar.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._primary_sidebar)

        # ── 详情面板（中央 Editor） ──
        self._detail = QTextBrowser()
        self._detail.setOpenExternalLinks(True)
        self._detail.setPlaceholderText("选择任务查看详情")
        self.setCentralWidget(self._detail)

        # ── Steer Panel（副侧边栏） ──
        self._steer = SteerPanel(self)
        self._steer.title_changed.connect(self._on_steer_title)

        self._secondary_sidebar = QDockWidget("Agent 通信", self)
        self._secondary_sidebar.setObjectName("SecondarySidebar")
        self._secondary_sidebar.setWidget(self._steer)
        self._secondary_sidebar.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._secondary_sidebar)
        self._secondary_sidebar.hide()

        # ── 底部面板（输出 / Agent 列表等） ──
        self._log_panel = LogPanel(self)

        self._agent_panel = QPlainTextEdit()
        self._agent_panel.setReadOnly(True)
        self._agent_panel.setPlaceholderText("运行中的 agent 将显示在这里")

        self._panel_tabs = QTabWidget()
        self._panel_tabs.addTab(self._log_panel, "输出")
        self._panel_tabs.addTab(self._agent_panel, "Agent")

        self._panel_dock = QDockWidget("面板", self)
        self._panel_dock.setObjectName("Panel")
        self._panel_dock.setWidget(self._panel_tabs)
        self._panel_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._panel_dock)
        self._panel_dock.hide()

        # ── ActivityBar → Dock 绑定 ──
        self._activity_bar.set_dock(0, self._primary_sidebar)   # 📁
        self._activity_bar.set_dock(1, self._secondary_sidebar)  # 💬
        self._activity_bar.set_dock(2, self._panel_dock)          # 📋

        # ── 菜单栏 ──
        self._setup_menu()

        # ── 数据 ──
        self._nodes: list[TaskNode] = []
        self._load()

        # ── 信号 ──
        self._tree.clicked.connect(self._on_select)
        self._tree.doubleClicked.connect(self._on_double_click)

        # ── 文件监控 ──
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._on_agent_dir_changed)
        self._watcher.fileChanged.connect(self._on_file_changed)
        self._setup_agent_watcher()

        # state.yaml 变化 → 自动 reload
        state_path = str(Path.home() / ".diy" / "state.yaml")
        self._watcher.addPath(state_path)
        # ~/.diy/d/ 目录变化（CLI 创建/删除任务）→ 自动 reload
        data_path = str(Path.home() / ".diy" / "d")
        os.makedirs(data_path, exist_ok=True)
        self._watcher.addPath(data_path)

        # ── 定时刷新（agent 状态 5s） ──
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_agents)
        self._refresh_timer.start(5000)

        logger.info("MainWindow 初始化完成, pid=%s", os.getpid())

    def _setup_menu(self):
        """构建菜单栏。"""
        menubar = self.menuBar()

        # ── 视图菜单 ──
        view_menu = menubar.addMenu("视图")

        toggle_sidebar = QAction("任务树", self, checkable=True)
        toggle_sidebar.setChecked(True)
        toggle_sidebar.setShortcut("Ctrl+B")
        toggle_sidebar.triggered.connect(self._primary_sidebar.setVisible)
        self._primary_sidebar.visibilityChanged.connect(toggle_sidebar.setChecked)
        view_menu.addAction(toggle_sidebar)

        toggle_steer = QAction("Agent 通信", self, checkable=True)
        toggle_steer.setChecked(False)
        toggle_steer.triggered.connect(self._secondary_sidebar.setVisible)
        self._secondary_sidebar.visibilityChanged.connect(toggle_steer.setChecked)
        view_menu.addAction(toggle_steer)

        view_menu.addSeparator()

        toggle_output = QAction("输出", self, checkable=True)
        toggle_output.setChecked(False)
        toggle_output.setShortcut("Ctrl+`")
        toggle_output.triggered.connect(lambda v: self._toggle_panel(v, 0))
        self._panel_dock.visibilityChanged.connect(toggle_output.setChecked)
        view_menu.addAction(toggle_output)

    def _toggle_panel(self, visible: bool, tab_index: int = 0) -> None:
        self._panel_dock.setVisible(visible)
        if visible:
            self._panel_tabs.setCurrentIndex(tab_index)
            self._panel_dock.raise_()

    def _on_steer_title(self, title: str) -> None:
        self._secondary_sidebar.setWindowTitle(title)

    def _load(self) -> None:
        self._nodes = load_task_tree()
        self._last_reload = time.time()
        self._refresh_agents()
        self._render_tree()
        subjects = sum(1 for n in self._iter_nodes(self._nodes) if n.kind == "subject")
        tasks = sum(1 for n in self._iter_nodes(self._nodes) if n.kind == "task")
        logger.info("reload — %d subject(s), %d task(s), %d root(s)", subjects, tasks, len(self._nodes))

    def _render_tree(self) -> None:
        model = build_model(self._nodes)
        self._tree.setModel(model)
        self._tree.expandAll()
        # setModel() 会重建 selectionModel，重新连接信号
        self._tree.selectionModel().selectionChanged.connect(self._on_select)

    @guarded("timer.refresh")
    def _refresh_agents(self) -> None:
        """从文件系统读取 agent 状态并挂到任务节点上。"""
        agents = list_agents()
        by_task: dict[str, list[AgentStatus]] = {}
        for a in agents:
            by_task.setdefault(a.task_id, []).append(a)

        changed = False
        for n in self._iter_nodes(self._nodes):
            new_agents = [
                AgentInfo(a.agent_id, a.state, a.pid)
                for a in by_task.get(n.uri or "", [])
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
        # 启动 3 秒内不响应目录变化（macOS 初始化会触发一次）
        if time.time() - self._started_at < 3.0:
            return
        tasks_dir = str(Path.home() / ".diy" / "d")
        if _path == tasks_dir:
            # tasks/ 目录变化（CLI 创建/删除任务）→ reload 树
            self._load()
        else:
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
        task_uri = index.data(ROLE_TASK_URI)
        state = index.data(ROLE_STATE)

        menu = QMenu(self)

        if kind == "task" and task_uri:
            menu.addAction(f"{task_uri} — {state}").setEnabled(False)
            menu.addSeparator()

            state_menu = menu.addMenu("更改状态")
            for s, label in [("pending", "⏳ Pending"), ("active", "🔄 Active"),
                             ("done", "✅ Done"), ("blocked", "🚫 Blocked"),
                             ("cancelled", "❌ Cancelled")]:
                if s != state:
                    act = state_menu.addAction(label)
                    act.triggered.connect(lambda checked, t=task_uri, ns=s: self._set_state(t, ns))

            menu.addSeparator()

            steer_act = menu.addAction("💬 /steer 通信")
            steer_act.triggered.connect(lambda checked, t=task_uri: self._open_steer(t))

            del_act = menu.addAction("🗑 删除任务")
            del_act.triggered.connect(lambda checked, t=task_uri: self._delete_task(t))

        menu.addSeparator()
        refresh_act = menu.addAction("🔄 刷新")
        refresh_act.triggered.connect(self._load)

        menu.exec(self._tree.viewport().mapToGlobal(pos))

    # ── 操作 ──
    @guarded("action.state")
    def _set_state(self, uri: str, new_state: str) -> None:
        import subprocess
        subprocess.run(
            ["dai", "task", "edit", uri, "--state", new_state],
            capture_output=True,
        )
        self._load()

    @guarded("action.delete")
    def _delete_task(self, uri: str) -> None:
        import subprocess
        subprocess.run(
            ["dai", "task", "delete", uri],
            capture_output=True,
        )
        self._load()

    @guarded("action.steer")
    def _open_steer(self, uri: str) -> None:
        self._steer.set_task(uri)
        self._secondary_sidebar.show()

    # ── 选中 / 双击 ──
    @guarded("tree.select")
    def _on_select(self, _selected=None, _deselected=None):
        indexes = self._tree.selectionModel().selectedIndexes()
        if not indexes:
            return

        index = indexes[0]
        kind = index.data(ROLE_KIND)
        task_uri = index.data(ROLE_TASK_URI)
        state = index.data(ROLE_STATE)

        if kind == "subject":
            display = index.data(Qt.ItemDataRole.DisplayRole) or ""
            html = f"""<div class="card">
  <div class="header">📁 Subject</div>
  <div class="title">{_esc_html(display)}</div>
</div>"""
            self._detail.setHtml(_STYLE + html)
            return

        if kind != "task" or not task_uri:
            self._detail.setHtml(_STYLE + """<div class="placeholder">选择任务查看详情</div>""")
            return

        node = self._find_node(task_uri)

        # —— 拼 HTML ——
        parts: list[str] = []

        # URI + state badge
        state_badge = _state_badge(state)
        parts.append(f"""<div class="header">{task_uri} {state_badge}</div>""")

        # Title
        if node and node.title:
            parts.append(f"""<div class="title">{_esc_html(node.title)}</div>""")

        # Detail
        if node and node.detail:
            detail_html = _esc_html(node.detail).replace("\n", "<br>")
            parts.append(f"""<div class="detail">{detail_html}</div>""")

        # Metadata row
        meta: list[str] = []
        if node and node.subject_path:
            meta.append(f"""<span class="tag">📂 {_esc_html(node.subject_path)}</span>""")
        if node and node.parent_uri:
            meta.append(f"""<span class="tag">⬆ 父任务 {node.parent_uri}</span>""")
        if meta:
            parts.append(f"""<div class="meta">{' '.join(meta)}</div>""")

        # Divider
        parts.append("<hr>")

        # Agent section
        if node and node.agents:
            parts.append("""<div class="section-title">🤖 Agent</div>""")
            for a in node.agents:
                icons = {"running": "🟢", "done": "✅", "blocked": "🔴"}
                icon = icons.get(a.state, "⏳")
                parts.append(f"""<div class="agent">{icon} <code>{_esc_html(a.agent_id)}</code> — {a.state}</div>""")
        else:
            parts.append("""<div class="hint">无运行中的 agent</div>""")

        self._detail.setHtml(_STYLE + "".join(parts))

    @guarded("tree.double")
    def _on_double_click(self, index):
        task_uri = index.data(ROLE_TASK_URI)
        if task_uri:
            self._open_steer(task_uri)

    def _find_node(self, uri: str) -> TaskNode | None:
        def _search(nodes: list[TaskNode]) -> TaskNode | None:
            for n in nodes:
                if n.uri == uri:
                    return n
                r = _search(n.children)
                if r:
                    return r
            return None
        return _search(self._nodes)

    # ── 通知弹窗 ──

    @Slot(str)
    def show_notification(self, message: str) -> None:
        """在窗口右上角弹出通知，3 秒自动消失。"""
        from PySide6.QtCore import QPropertyAnimation  # type: ignore[import-untyped]

        popup = QLabel(message, self)
        popup.setStyleSheet("""
            QLabel {
                background: #1e1e2e; color: #cdd6f4;
                border: 1px solid #45475a; border-radius: 8px;
                padding: 10px 16px; font-size: 13px;
            }
        """)
        popup.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.ToolTip)
        popup.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        popup.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        popup.adjustSize()

        # 定位：窗口右上角
        geom = self.geometry()
        popup.move(geom.right() - popup.width() - 20, geom.top() + 40)
        popup.show()

        # 3 秒后淡出
        anim = QPropertyAnimation(popup, b"windowOpacity")
        anim.setDuration(800)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(popup.deleteLater)
        QTimer.singleShot(3000, anim.start)

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

    def format_node(self, uri: str) -> str:
        """序列化指定任务节点详情（含 agent 状态）。"""
        node = self._find_node(uri)
        if node is None:
            return f"未找到任务 {uri}"
        lines = [
            f"{node.uri} {node.title}",
            f"  kind:    {node.kind}",
            f"  state:   {node.state} {node.state_icon}",
            f"  subject: {node.subject_path or '(无)'}",
            f"  parent:  {node.parent_uri if node.parent_uri else '(无)'}",
            f"  depth:   {node.depth}",
            f"  children: {len(node.children)}",
        ]
        if node.detail:
            lines.append(f"  detail:  {node.detail}")
        if node.children:
            lines.append("  child_list:")
            for c in node.children:
                lines.append(f"    {c.uri} {c.title} [{c.state}]")
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
                lines.append(f"{n.uri} {a.agent_id} pid={a.pid} state={a.state}")
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
from typing import Callable, TypeVar

from cyclopts import App as CycloptsApp
from PySide6.QtCore import QEventLoop, QMetaObject, Qt as QtCore, Q_ARG, QTimer  # type: ignore[import-untyped]
from PySide6.QtCore import QObject  # type: ignore[import-untyped]


T = TypeVar("T")


class MainThread:
    """安全地在 Qt 主线程执行操作，调用者不关心线程跳转。

    用法:
        mt = MainThread(window)
        tree = mt.invoke(window.format_tree)    # 返回 str
        node = mt.invoke(lambda: window.format_node(42))  # 带参数
    """

    def __init__(self, window: QObject):
        self._window = window

    def invoke(self, fn: Callable[[], T]) -> T:
        """阻塞等待 fn 在 Qt 主线程执行完毕，返回结果。

        PySide6 6.8 兼容：QTimer.singleShot + QEventLoop，
        代替 QMetaObject.invokeMethod(obj, callable, conn_type)（6.9+ 才支持）。
        """
        ret: list[T] = []
        loop = QEventLoop()
        QTimer.singleShot(0, lambda: [ret.append(fn()), loop.quit()])
        loop.exec()
        return ret[0]


class ProbeCLI:
    """Socket 协议层 — 用 cyclopts 解析命令，输出为纯文本。

    命令分两组:
      ai <cmd>    — AI/agent 接口，无交互，纯数据
      hum <cmd>   — 人类接口，通知/操控
    """

    def __init__(self, window: "MainWindow"):
        self._window = window
        self._main = MainThread(window)
        self._app = CycloptsApp(name="probe")

        # ── AI 子应用 ──
        ai = CycloptsApp(name="ai", help="AI/agent 接口")
        @ai.command
        def tree():
            """完整任务树（和 UI 一致）"""
            return self._main.invoke(self._window.format_tree)

        @ai.command
        def status():
            """健康检查（pid/窗口/树/定时器）"""
            return self._main.invoke(self._window.format_status)

        @ai.command
        def agents():
            """agent 列表"""
            return self._main.invoke(self._window.format_agents)

        @ai.command
        def reload():
            """热重载 state.yaml"""
            self._main.invoke(self._window._load)
            return "OK"

        @ai.command
        def node(uri: str):
            """<uri> 任务节点详情"""
            return self._main.invoke(lambda: self._window.format_node(uri))

        self._app.command(ai)

        # ── 人类子应用 ──
        hum = CycloptsApp(name="human", help="人类接口")
        @hum.command
        def notify(*message: str):
            """<消息...> 弹通知 — 窗口右上角弹出"""
            text = " ".join(message)
            QMetaObject.invokeMethod(
                self._window, "show_notification",
                QtCore.ConnectionType.QueuedConnection,
                Q_ARG(str, text))
            return "OK"

        @hum.command
        def title(*text: str):
            """<文本...> 改窗口标题"""
            title_text = " ".join(text)
            if not title_text:
                return "错误: 缺少参数，用法: human title <文本...>"
            QMetaObject.invokeMethod(
                self._window, "setWindowTitle",
                QtCore.ConnectionType.QueuedConnection,
                Q_ARG(str, title_text))
            return f"标题已改为: {title_text}"

        self._app.command(hum)

        @self._app.default
        def unknown(*tokens: str):
            return f"未知命令: {' '.join(tokens)!r}  试试 --help"

    def dispatch(self, line: str, out) -> None:
        """流式输出 — 直接写 out，不缓冲。"""
        import io
        from rich.console import Console

        tokens = line.split() if line else ["--help"]
        console = Console(file=out, force_terminal=True, width=80)

        # cyclopts 错误写入 stderr，重定向到 out
        old_stderr = sys.stderr
        err_buf = io.StringIO()
        sys.stderr = err_buf
        try:
            self._app(tokens, console=console, exit_on_error=False)
        except SystemExit:
            pass
        except Exception as exc:
            logger.error("dispatch 异常: %s\n%s", exc, traceback.format_exc())
            out.write(f"\n内部错误: {exc}\n")
        finally:
            sys.stderr = old_stderr

        err_text = err_buf.getvalue()
        if err_text:
            out.write(err_text)
        out.flush()


class AppProbeError(Exception):
    """已有运行中的管控台实例。"""


_PID_PATH = os.path.expanduser("~/.diy/app.pid")


def _is_pid_alive(pid: int) -> bool:
    """检查 PID 是否存活。"""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


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
        # 1) PID 锁检查 — 即使 socket 文件被误删也能拦截
        if os.path.exists(_PID_PATH):
            try:
                with open(_PID_PATH) as fh:
                    pid = int(fh.read().strip())
                if _is_pid_alive(pid):
                    raise AppProbeError(
                        f"已有运行中的管控台实例 (pid={pid})"
                    )
                logger.warning("PID 文件残留 pid=%d，清理", pid)
            except (OSError, ValueError):
                pass
            try:
                os.unlink(_PID_PATH)
            except OSError:
                pass

        # 2) Socket 锁检查
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect(self._path)
            s.close()
            raise AppProbeError(
                f"已有运行中的管控台实例 (socket: {self._path})"
            )
        except (OSError, socket.timeout):
            pass  # 连不上 → 残留或不存在

        # 3) 清理残留 socket + 绑定
        try:
            os.unlink(self._path)
        except OSError:
            pass

        self._server = socketserver.UnixStreamServer(self._path, _make_handler(self))
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

        # 4) 写入 PID 锁
        try:
            with open(_PID_PATH, "w") as fh:
                fh.write(str(os.getpid()))
        except OSError:
            pass

        logger.info("AppProbe socket ready → %s  pid=%d", self._path, os.getpid())

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
        try:
            os.unlink(self._path)
        except OSError:
            pass
        try:
            os.unlink(_PID_PATH)
        except OSError:
            pass


def _make_handler(probe: AppProbe):
    import io as _io

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            data = self.rfile.readline()
            if not data:
                return
            cmd = data.decode("utf-8").strip()
            # wfile 是 binary，包成 text mode 给 rich
            text_out = _io.TextIOWrapper(self.wfile, encoding="utf-8", write_through=True)
            try:
                probe._cli.dispatch(cmd, text_out)
            except Exception:
                import traceback
                text_out.write(f"\n内部错误: {traceback.format_exc()}")
                text_out.flush()
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

    # 日志系统必须先初始化（MainWindow.__init__ 中 guarded 方法可能立即触发）
    setup_app_logger()
    logger.info("=" * 50)
    logger.info("diy 管控台启动")

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(_app_stylesheet())

    # Ctrl+C 两次退出（调试模式下 Qt event loop 会吞 SIGINT）
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    try:
        window = MainWindow()
    except AppProbeError as e:
        logger.error(str(e))
        return

    window.show()
    logger.info("窗口已显示")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
