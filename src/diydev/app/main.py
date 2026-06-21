"""diy 管控台 v2 — 主入口。

启动 PySide6 窗口，渲染任务树 + agent 监控。
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

from PySide6.QtCore import (  # type: ignore[import-untyped]
    QEvent,
    QFileSystemWatcher,
    QItemSelectionModel,
    QSortFilterProxyModel,
    Qt,
    QTimer,
    Slot,
    Signal,
)
from PySide6.QtGui import QAction, QFont, QStandardItem, QStandardItemModel  # type: ignore[import-untyped]
from PySide6.QtWebEngineWidgets import QWebEngineView  # type: ignore[import-untyped]
from PySide6.QtWidgets import (  # type: ignore[import-untyped]
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QToolButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from diydev.app._activity_bar import ActivityBar
from diydev.app._agent_chat import AgentChatPanel
from diydev.app._app_log import get_logger, logger, setup_app_logger
from diydev.app._log_panel import LogPanel
from diydev.app.agent_bridge import (
    AgentStatus,
    list_agents,
)
from diydev.app.task_tree import TaskNode, load_task_tree
from diydev.app._doctor import HealthIssue, is_locked, run_check, set_locked
from diydev.app._metrics import MetricsStore
from diydev._state import diy_home

# ═══════════════════════════════════════════════════════
# 自定义 data roles
# ═══════════════════════════════════════════════════════

ROLE_TASK_URI = Qt.ItemDataRole.UserRole + 1
ROLE_KIND = Qt.ItemDataRole.UserRole + 2
ROLE_STATE = Qt.ItemDataRole.UserRole + 3
ROLE_SUBJECT = Qt.ItemDataRole.UserRole + 4


# ═══════════════════════════════════════════════════════
# Material3 暗色主题 — 语义化颜色系统
# ═══════════════════════════════════════════════════════

import os as _os
import pwd as _pwd


def _detect_sandbox() -> tuple[bool, str]:
    """检测是否在隔离模式下运行（测试/调试/多实例）。

    判定条件：
    1. $HOME ≠ 真实 HOME（临时目录模式）
    2. $DIY_HOME 已设置（项目级隔离模式）

    Returns:
        (is_sandbox, data_path) — data_path 是数据目录路径
    """
    # 检查是否设置了 DIY_HOME（非默认值）
    if _os.environ.get("DIY_HOME"):
        return True, str(diy_home())

    # 检查 HOME 是否被覆盖
    real_home = _pwd.getpwuid(_os.getuid()).pw_dir
    current_home = _os.path.expanduser("~")
    if current_home != real_home:
        return True, current_home

    return False, str(diy_home())


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

    # 调试/沙箱模式 — 暖色替代蓝
    sandbox_bg = "#e5c07b"      # 琥珀色（替代 active_bg 的蓝）
    sandbox_fg = "#1e1e2e"

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


def _icons_dir() -> Path:
    """返回 app/icons 目录路径（pkg 内打包）。"""
    return Path(__file__).resolve().parent / "icons"


def _app_stylesheet(sandbox: bool = False) -> str:
    """全局 Material3 暗色主题 QSS。

    sandbox=True 时用琥珀色替代蓝色作为强调色，区分调试/生产环境。
    """
    accent = Theme.sandbox_bg if sandbox else Theme.active_bg
    dock_bg = Theme.sandbox_bg if sandbox else Theme.surface_alt
    tab_bg = Theme.sandbox_bg if sandbox else Theme.surface
    btn_hover = Theme.sandbox_bg if sandbox else "#585b70"
    return f"""
        QMainWindow {{ background: {Theme.surface}; }}
        QDockWidget {{ background: {Theme.surface}; color: {Theme.on_surface};
                       border: 1px solid {Theme.outline}; titlebar-close-icon: none; }}
        QDockWidget::title {{ background: {dock_bg};
                              padding: 4px 8px; text-align: left; }}
        QTreeView {{ background: {Theme.surface}; color: {Theme.on_surface};
                     border: none; font-size: 13px;
                     outline: none; }}
        QTreeView::item {{ padding: 2px 4px; border-radius: 4px; }}
        QTreeView::item:selected {{ background: #45475a; color: #cdd6f4; }}
        QTreeView::item:hover {{ background: #313244; }}
        QTreeView::branch {{ background: {Theme.surface}; }}
        QTreeView::branch:has-children:closed {{ image: url({_icons_dir() / "branch-closed.png"}); }}
        QTreeView::branch:has-children:open {{ image: url({_icons_dir() / "branch-open.png"}); }}
        QTextBrowser {{ background: {Theme.surface}; color: {Theme.on_surface};
                        border: none; font-size: 14px; padding: 8px; }}
        QPlainTextEdit {{ background: {Theme.surface_alt}; color: {Theme.on_surface};
                          border: none; font-size: 12px; }}
        QLineEdit {{ background: {Theme.surface_alt}; color: {Theme.on_surface};
                     border: 1px solid {Theme.outline}; border-radius: 4px;
                     padding: 4px 8px; }}
        QLineEdit:focus {{ border: 1px solid {accent}; }}
        QPushButton {{ background: #45475a; color: {Theme.on_surface};
                       border: none; border-radius: 4px; padding: 4px 12px; }}
        QPushButton:hover {{ background: {btn_hover}; }}
        QTabWidget::pane {{ background: {Theme.surface}; border: 1px solid {Theme.outline}; }}
        QTabBar::tab {{ background: {Theme.surface_alt}; color: {Theme.on_surface_variant};
                       padding: 4px 12px; border: none; }}
        QTabBar::tab:selected {{ background: {tab_bg}; color: {Theme.on_surface};
                                 border-bottom: 2px solid {accent}; }}
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
# DetailView — HTML 元数据 + WebEngine body
# ═══════════════════════════════════════════════════════

class DetailView(QWidget):
    """详情面板：查看/编辑任务。GitHub/Jira 风格的两栏布局。"""

    task_saved = Signal(str)  # task_uri

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── 顶栏：URI + state + 按钮 ──
        self._toolbar = QWidget()
        self._toolbar.setFixedHeight(32)
        tb_lay = QHBoxLayout(self._toolbar)
        tb_lay.setContentsMargins(8, 2, 8, 2)
        tb_lay.setSpacing(6)

        self._uri_label = QLabel()
        self._uri_label.setStyleSheet("color: #cdd6f4; font-size: 12px; font-weight: bold;")

        self._state_label = QLabel()
        self._state_label.setStyleSheet("color: #a6adc8; font-size: 11px;")

        tb_lay.addWidget(self._uri_label)
        tb_lay.addWidget(self._state_label)
        tb_lay.addStretch()

        self._edit_btn = QPushButton("✏️ 编辑")
        self._edit_btn.setFixedHeight(24)
        self._edit_btn.setStyleSheet(
            "QPushButton { background: #45475a; color: #cdd6f4; border: none;"
            " border-radius: 4px; padding: 2px 10px; font-size: 11px; }"
            "QPushButton:hover { background: #585b70; }"
        )
        self._edit_btn.clicked.connect(self._toggle_edit)

        self._save_btn = QPushButton("💾 保存")
        self._save_btn.setFixedHeight(24)
        self._save_btn.setStyleSheet(
            "QPushButton { background: #a6e3a1; color: #1e1e2e; border: none;"
            " border-radius: 4px; padding: 2px 10px; font-size: 11px; font-weight: bold; }"
            "QPushButton:hover { background: #94e2d5; }"
        )
        self._save_btn.clicked.connect(self._save_task)
        self._save_btn.hide()

        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.setFixedHeight(24)
        self._cancel_btn.setStyleSheet(
            "QPushButton { background: #45475a; color: #cdd6f4; border: none;"
            " border-radius: 4px; padding: 2px 10px; font-size: 11px; }"
            "QPushButton:hover { background: #585b70; }"
        )
        self._cancel_btn.clicked.connect(self._cancel_edit)
        self._cancel_btn.hide()

        tb_lay.addWidget(self._edit_btn)
        tb_lay.addWidget(self._save_btn)
        tb_lay.addWidget(self._cancel_btn)

        layout.addWidget(self._toolbar)

        # ── 内容区：QSplitter 两栏布局（查看模式） ──
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(self._splitter)

        # 左侧：body（view / edit 切换）
        self._stack = QStackedWidget()
        self._splitter.addWidget(self._stack)

        # view 页 — body 区
        self.view = QWebEngineView()
        self._stack.addWidget(self.view)

        # edit 页
        edit_page = QWidget()
        ed_lay = QVBoxLayout(edit_page)
        ed_lay.setContentsMargins(8, 8, 8, 8)
        ed_lay.setSpacing(6)

        ed_lay.addWidget(QLabel("标题"))
        self._edit_title = QLineEdit()
        self._edit_title.setStyleSheet(
            "QLineEdit { background: #313244; color: #cdd6f4; border: 1px solid #45475a;"
            " border-radius: 4px; padding: 6px 8px; font-size: 14px; }"
        )
        ed_lay.addWidget(self._edit_title)

        ed_lay.addWidget(QLabel("文档 (Markdown)"))
        self._edit_body = QPlainTextEdit()
        self._edit_body.setStyleSheet(
            "QPlainTextEdit { background: #1e1e2e; color: #cdd6f4; border: 1px solid #45475a;"
            " border-radius: 4px; padding: 6px; font-size: 13px;"
            " font-family: 'SF Mono', monospace; }"
        )
        ed_lay.addWidget(self._edit_body)

        self._stack.addWidget(edit_page)

        # 右侧：侧边栏（属性 + Agent Chat）
        self._sidebar = QWidget()
        self._sidebar.setMinimumWidth(240)
        self._sidebar.setMaximumWidth(400)
        side_lay = QVBoxLayout(self._sidebar)
        side_lay.setContentsMargins(0, 0, 0, 0)
        side_lay.setSpacing(0)

        # ─ 属性面板 ─
        self._attr_widget = QWidget()
        self._attr_widget.setStyleSheet(
            "QWidget { background: #181825; }"
            "QLabel { color: #a6adc8; font-size: 11px; padding: 2px 8px; }"
        )
        attr_lay = QVBoxLayout(self._attr_widget)
        attr_lay.setContentsMargins(0, 4, 0, 4)
        attr_lay.setSpacing(0)

        self._attr_subject = QLabel()
        self._attr_parent = QLabel()
        self._attr_detail = QLabel()
        self._attr_detail.setWordWrap(True)

        attr_lay.addWidget(QLabel("属性"))
        attr_lay.addWidget(self._attr_subject)
        attr_lay.addWidget(self._attr_parent)
        attr_lay.addWidget(self._attr_detail)
        attr_lay.addStretch()

        side_lay.addWidget(self._attr_widget)

        # ─ 分隔线 ─
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #313244;")
        side_lay.addWidget(sep)

        # ─ Agent Chat ─
        self._chat = AgentChatPanel(self)
        self._chat.set_compact(True)
        side_lay.addWidget(self._chat, 1)  # stretch=1, 占剩余空间

        self._splitter.addWidget(self._sidebar)

        # ── 当前状态 ──
        self._current_task_uri: str | None = None
        self._current_node: TaskNode | None = None
        self._current_task_uri_for_chat: str | None = None

    # ── 公开接口 ──

    def show_task(self, uri: str, node: TaskNode | None, html: str) -> None:
        """进入查看模式，显示任务详情。"""
        self._current_task_uri = uri
        self._current_node = node
        self._stack.setCurrentIndex(0)
        self._edit_btn.show()
        self._save_btn.hide()
        self._cancel_btn.hide()
        self._uri_label.setText(uri)
        state = node.state if node else ""
        self._state_label.setText(state)
        self.view.setHtml(html)

        # 更新侧边栏
        self._update_sidebar(uri, node)

        # 关联 Agent Chat
        if uri != self._current_task_uri_for_chat:
            self._chat.set_task(uri)
            self._current_task_uri_for_chat = uri
            self._splitter.setSizes([400, 260])  # 初始比例

    def show_placeholder(self, html: str) -> None:
        """显示占位信息（无任务选中）。"""
        self._current_task_uri = None
        self._current_node = None
        self._stack.setCurrentIndex(0)
        self._edit_btn.hide()
        self._save_btn.hide()
        self._cancel_btn.hide()
        self._uri_label.clear()
        self._state_label.clear()
        self._current_task_uri_for_chat = None
        self.view.setHtml(html)
        self._clear_sidebar()

    # ── 侧边栏 ──

    def _update_sidebar(self, uri: str, node: TaskNode | None) -> None:
        if not node:
            self._clear_sidebar()
            return
        parts = []
        if node.subject_path:
            parts.append(f"📂 {_esc_html(node.subject_path)}")
        if node.parent_uri:
            parts.append(f"⬆ 父任务 {node.parent_uri}")
        if node.detail:
            parts.append(f"📝 {_esc_html(node.detail)}")
        self._attr_subject.setText(parts[0] if len(parts) > 0 else "")
        self._attr_parent.setText(parts[1] if len(parts) > 1 else "")
        self._attr_detail.setText(parts[2] if len(parts) > 2 else "")
        self._attr_widget.setVisible(len(parts) > 0)

    def _clear_sidebar(self) -> None:
        self._attr_subject.clear()
        self._attr_parent.clear()
        self._attr_detail.clear()
        self._attr_widget.hide()

    # ── 编辑模式 ──

    def _toggle_edit(self) -> None:
        """切换到编辑模式。"""
        if not self._current_node:
            return
        self._edit_title.setText(self._current_node.title or "")
        self._edit_body.setPlainText(self._current_node.body or "")
        self._edit_btn.hide()
        self._save_btn.show()
        self._cancel_btn.show()
        # 编辑模式隐藏侧边栏
        self._sidebar.hide()

    def _cancel_edit(self) -> None:
        """取消编辑，返回查看模式。"""
        self._sidebar.show()
        self._stack.setCurrentIndex(0)
        self._edit_btn.show()
        self._save_btn.hide()
        self._cancel_btn.hide()

    def _save_task(self) -> None:
        """保存任务修改。"""
        uri = self._current_task_uri
        if not uri:
            return
        new_title = self._edit_title.text().strip()
        new_body = self._edit_body.toPlainText()
        from ._state import update_task_field  # noqa: PLC0415
        if new_title != (self._current_node.title or "") if self._current_node else True:
            update_task_field(uri, title=new_title)
        if new_body != (self._current_node.body or "") if self._current_node else True:
            update_task_field(uri, body=new_body)
        self._cancel_edit()
        self.task_saved.emit(uri)


# ═══════════════════════════════════════════════════════
# 主窗口
# ═══════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # ── 沙箱检测（调试/测试/多实例模式） ──
        self._sandbox, self._sandbox_path = _detect_sandbox()
        if self._sandbox:
            self.setWindowTitle(
                f"🧪 diy 管控台 [测试: {self._sandbox_path}]"
            )
        else:
            self.setWindowTitle(f"diy 管控台 [{self._sandbox_path}]")
        self.resize(1000, 650)

        self._started_at = time.time()
        self._last_reload = self._started_at

        # ── Gateway（Unix socket 入口） ──
        self._gateway = Gateway(self)

        # ── Activity Bar（左侧活动栏） ──
        self._activity_bar = ActivityBar(self)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, self._activity_bar)

        # ── 过滤栏（搜索 + 状态过滤） ──
        self._filter_text = QLineEdit()
        self._filter_text.setPlaceholderText("搜索任务...")
        self._filter_text.setClearButtonEnabled(True)

        self._filter_state = QComboBox()
        self._filter_state.addItems(["所有状态", "pending", "active", "done", "blocked", "cancelled"])

        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(4, 4, 4, 0)
        filter_row.setSpacing(4)
        filter_row.addWidget(self._filter_text, 3)
        filter_row.addWidget(self._filter_state, 2)

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

        # ── 树头部栏（标题 + 刷新按钮） ──
        tree_header = QWidget()
        tree_header_lay = QHBoxLayout(tree_header)
        tree_header_lay.setContentsMargins(8, 4, 4, 4)
        tree_header_lay.setSpacing(0)
        tree_header_label = QLabel("任务树")
        tree_header_label.setStyleSheet(
            f"color: {Theme.on_surface}; font-size: 11px; font-weight: bold;"
        )
        tree_header_lay.addWidget(tree_header_label)
        tree_header_lay.addStretch()
        self._refresh_btn = QToolButton()
        self._refresh_btn.setText("🔄")
        self._refresh_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._refresh_btn.setFixedSize(22, 22)
        self._refresh_btn.setToolTip("刷新任务树")
        self._refresh_btn.setStyleSheet(
            "QToolButton { background: transparent; border: none;"
            " font-size: 13px; border-radius: 4px; }"
            "QToolButton:hover { background: #45475a; }"
        )
        self._refresh_btn.clicked.connect(self._load)
        tree_header_lay.addWidget(self._refresh_btn)

        # ── 展开/折叠切换按钮 ──
        self._expand_all = True  # 当前状态：已展开
        self._expand_btn = QToolButton()
        self._expand_btn.setText("▼")
        self._expand_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._expand_btn.setFixedSize(22, 22)
        self._expand_btn.setToolTip("折叠所有")
        self._expand_btn.setStyleSheet(
            "QToolButton { background: transparent; border: none;"
            " font-size: 11px; border-radius: 4px; }"
            "QToolButton:hover { background: #45475a; }"
        )
        self._expand_btn.clicked.connect(self._toggle_expand)
        tree_header_lay.addWidget(self._expand_btn)

        tree_container = QWidget()
        tree_layout = QVBoxLayout(tree_container)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        tree_layout.setSpacing(0)
        tree_layout.addWidget(tree_header)
        tree_layout.addLayout(filter_row)
        tree_layout.addWidget(self._tree)

        self._primary_sidebar = QDockWidget("任务树", self)
        self._primary_sidebar.setObjectName("PrimarySidebar")
        self._primary_sidebar.setWidget(tree_container)
        self._primary_sidebar.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._primary_sidebar)

        # ── 详情面板（中央 Editor） ──
        self._detail = DetailView()
        self._detail.task_saved.connect(self._on_task_saved)
        self.setCentralWidget(self._detail)

        # _detail 就绪后再启动 socket（防止 GatewayCLI 命令在 _detail 未创建时到达）
        self._gateway.start()

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
        self._activity_bar.set_dock(2, self._panel_dock)          # 📋

        # ── 菜单栏 ──
        self._setup_menu()

        # ── 数据 ──
        self._metrics = MetricsStore()
        self._nodes: list[TaskNode] = []
        self._load()

        # ── 过滤信号（必须在 _load 之后，否则 proxy 未创建） ──
        self._filter_text.textChanged.connect(self._filter_tree)
        self._filter_state.currentTextChanged.connect(self._filter_tree)

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

        # ── 健康自检（10s，启动后 30s 才开始） ──
        self._health_timer = QTimer(self)
        self._health_timer.timeout.connect(self._on_health_check)
        QTimer.singleShot(30000, lambda: self._health_timer.start(10000))

        logger.info("MainWindow 初始化完成, pid=%s", os.getpid())

    def event(self, evt: QEvent | None) -> bool:
        """处理跨线程 _InvokeEvent。"""
        if evt and isinstance(evt, _InvokeEvent):
            evt.execute()
            return True
        return super().event(evt)

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

    @guarded("task_saved")
    def _on_task_saved(self, uri: str) -> None:
        """任务编辑保存后刷新数据并触发重渲染。"""
        self._nodes = load_task_tree()
        self._render_tree()
        # 保存后重新选中该任务 — 在 source model 中搜索
        source = self._proxy.sourceModel()
        if source is None:
            return

        def _walk(item):
            for row in range(item.rowCount()):
                child = item.child(row)
                if child.data(ROLE_TASK_URI) == uri:
                    return child
                found = _walk(child)
                if found is not None:
                    return found
            return None

        target = _walk(source.invisibleRootItem())
        if target is not None:
            idx = self._proxy.mapFromSource(target.index())
            self._tree.selectionModel().select(
                idx, QItemSelectionModel.SelectionFlag.Select
            )
            self._tree.scrollTo(idx)

    def _load(self) -> None:
        self._nodes = load_task_tree()
        self._last_reload = time.time()
        self._refresh_agents()
        self._render_tree()
        subjects = sum(1 for n in self._iter_nodes(self._nodes) if n.kind == "subject")
        tasks = sum(1 for n in self._iter_nodes(self._nodes) if n.kind == "task")
        logger.debug("[main] 重载完成 — %d subject, %d task, %d root", subjects, tasks, len(self._nodes))

    def _render_tree(self) -> None:
        source = build_model(self._nodes)
        self._proxy = TaskFilterProxy(self)
        self._proxy.setSourceModel(source)
        self._proxy.setRecursiveFilteringEnabled(True)
        self._tree.setModel(self._proxy)
        self._tree.expandAll()
        self._expand_all = True
        self._expand_btn.setText("▼")
        self._expand_btn.setToolTip("折叠所有")
        self._expand_subjects()
        # setModel() 会重建 selectionModel，重新连接信号
        self._tree.selectionModel().selectionChanged.connect(self._on_select)

    def _toggle_expand(self) -> None:
        """切换全部展开/折叠。"""
        if self._expand_all:
            self._tree.collapseAll()
            self._expand_subjects()
            self._expand_all = False
            self._expand_btn.setText("▶")
            self._expand_btn.setToolTip("展开所有")
        else:
            self._tree.expandAll()
            self._expand_all = True
            self._expand_btn.setText("▼")
            self._expand_btn.setToolTip("折叠所有")

    def _expand_subjects(self) -> None:
        """展开所有 subject 节点。"""
        model = self._tree.model()
        if model is None:
            return
        for row in range(model.rowCount()):
            idx = model.index(row, 0)
            kind = model.data(idx.sibling(row, 0), ROLE_KIND)
            if kind == "subject":
                self._tree.expand(idx)

    @guarded("filter")
    def _filter_tree(self) -> None:
        """根据过滤栏筛选树节点。"""
        self._proxy.invalidateFilter()
        self._tree.expandAll()

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
            self._metrics.counter("agent.changes")
            logger.debug("[timer] agent 状态变化 → 重绘树 (%d agent)", len(agents))
            self._render_tree()
        self._metrics.gauge("agent.count", len(agents))
        self._metrics.counter("agent.refresh")

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
        if _path == tasks_dir or _path.startswith(tasks_dir + "/"):
            logger.info("[watcher] ~/.diy/d/ 目录变化 → 全量重载")
            self._load()
        else:
            logger.info("[watcher] agents/ 目录变化 → 刷新 agent 状态")
            self._refresh_agents()

    @guarded("watcher.file")
    def _on_file_changed(self, path: str) -> None:
        if path.endswith("state.yaml"):
            logger.info("[watcher] state.yaml 变化 → 全量重载")
            # macOS: yaml 写入可能换 inode，重新 watch
            self._watcher.removePath(path)
            self._watcher.addPath(path)
            self._load()
        else:
            logger.debug("[watcher] 其他文件变化 → 刷新 agent 状态")
            self._refresh_agents()

    # ── 健康自检 ──
    @guarded("health")
    def _on_health_check(self) -> None:
        sock_dev = getattr(self._gateway, '_sock_dev', None)
        sock_ino = getattr(self._gateway, '_sock_ino', None)
        critical = [i for i in run_check(sock_dev, sock_ino) if i.severity == "critical"]
        self._metrics.gauge("health.critical", len(critical))
        self._metrics.counter("health.checks")
        if critical:
            self._metrics.counter("health.crashes")
            logger.warning("[health] 发现 %d 个严重问题, 退出", len(critical))
            # ... 退出逻辑不变
            for iss in critical:
                logger.warning("[health]   [%s] %s — %s", iss.code, iss.message, iss.detail[:200])
            self._health_timer.stop()
            # 直接退出，不留错误面板
            QApplication.instance().quit()
            return

    def _enter_lockdown(self, issues: list[HealthIssue]) -> None:
        """严重故障 → 锁定界面并显示告示。"""
        # 隐藏所有 dock（副作用：无法交互）
        for dock in self.findChildren(QDockWidget):
            dock.hide()

        self.menuBar().setEnabled(False)

        html = """<style>
          body { background: #1e1e2e; color: #cdd6f4; font-family: -apple-system, sans-serif;
                 display: flex; justify-content: center; align-items: center;
                 height: 100vh; margin: 0; }
          .card { max-width: 600px; padding: 40px; text-align: center; }
          .icon-warn { font-size: 48px; margin-bottom: 12px; }
          h1 { color: #f7768e; font-size: 20px; margin-bottom: 16px; }
          .issue { background: #313244; border-radius: 8px; padding: 12px 16px;
                   margin: 8px 0; text-align: left; font-size: 13px; line-height: 1.6; }
          .issue code { background: #45475a; color: #f5c2e7; padding: 1px 4px; border-radius: 3px; }
          .issue .msg { font-weight: bold; color: #f7768e; }
          .hint { margin-top: 20px; font-size: 13px; color: #a6adc8; }
        </style>
        <div class="card">
          <div class="icon-warn">⚠️</div>
          <h1>严重故障 — 应用已锁定</h1>
        """
        for iss in issues:
            html += (
                f'<div class="issue">'
                f'<div class="msg">[{iss.code}] {iss.message}</div>'
                f'<div>{self._esc_html(iss.detail)}</div>'
                f'</div>'
            )
        html += (
            '<div class="hint">'
            '建议：关闭本窗口 → kill 残留进程 → 重新启动'
            '</div></div>'
        )
        self._detail.show_placeholder(html)
        self.setCentralWidget(self._detail)
        self.setWindowTitle("⚠️ 应用故障")

    # ── 右键菜单 ──
    @guarded("ctxmenu")
    def _on_context_menu(self, pos):
        from PySide6.QtWidgets import QMenu  # type: ignore[import-untyped]

        index = self._tree.indexAt(pos)
        if not index.isValid():
            return

        kind = index.data(ROLE_KIND)
        task_uri = index.data(ROLE_TASK_URI)
        subject_path = index.data(ROLE_SUBJECT)
        state = index.data(ROLE_STATE)

        menu = QMenu(self)

        # 所有节点都可以创建子任务
        new_act = menu.addAction("✨ 新建任务")
        if kind == "task":
            new_act.triggered.connect(lambda checked, t=task_uri: self._open_create_task(parent_uri=t))
        elif kind == "subject":
            subj = index.data(ROLE_SUBJECT) or next(
                (k for k, v in _subjects_from_state().items()
                 if k == subject_path or k == index.data(Qt.ItemDataRole.DisplayRole)),
                None
            )
            new_act.triggered.connect(lambda checked, s=subj or subject_path: self._open_create_task(subject=s))
        else:
            new_act.triggered.connect(lambda: self._open_create_task())

        menu.addSeparator()

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

            spawn_act = menu.addAction("🤖 启动 agent")
            spawn_act.triggered.connect(lambda checked, t=task_uri: self._spawn_agent(t))

            steer_act = menu.addAction("💬 /steer 通信")
            steer_act.triggered.connect(lambda checked, t=task_uri: self._open_steer(t))

            del_act = menu.addAction("📦 归档任务")
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
        """归档任务（替代删除）"""
        from diydev._state import get_task, archive_task
        task = get_task(uri)
        if not task:
            return
        archive_task(uri)
        self._load()

    @guarded("action.spawn")
    def _spawn_agent(self, uri: str) -> None:
        """启动 agent for 一个 task。"""
        # 通过 Gateway 发送 diy agent spawn 命令
        from diydev._state import get_task
        task = get_task(uri)
        if not task:
            return
        title = task.get("title", uri)
        prompt = f"请完成以下任务：{title}"
        self._detail._chat._send_text(prompt)

    @guarded("action.create")
    def _open_create_task(self, parent_uri: str | None = None, subject: str | None = None) -> None:
        """打开创建任务对话框。"""
        dlg = _CreateTaskDialog(self, parent_uri=parent_uri, initial_subject=subject)
        if dlg.exec():
            self._load()

    @guarded("action.steer")
    def _open_steer(self, uri: str) -> None:
        self._detail._chat.set_task(uri)

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
            html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  body {{ background: #1e1e2e; color: #cdd6f4; font-family: -apple-system, sans-serif; padding: 12px; }}
  .header {{ font-size: 14px; font-weight: bold; color: #cdd6f4; }}
  .title {{ font-size: 18px; font-weight: bold; color: #fff; margin-top: 8px; }}
</style></head><body>
<div class="header">📁 Subject</div>
<div class="title">{_esc_html(display)}</div>
</body></html>"""
            self._detail.show_placeholder(html)
            return

        if kind != "task" or not task_uri:
            self._detail.show_placeholder(f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  body {{ background: #1e1e2e; color: #a6adc8; font-family: -apple-system, sans-serif; font-size: 14px; padding: 20px; }}
</style></head><body>
<div>选择任务查看详情</div>
</body></html>""")
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

        # Body（markdown 文档）— 渲染后嵌入同一 HTML
        full_body_html: str | None = None
        if node and node.body:
            from markdown_it import MarkdownIt
            md = MarkdownIt("gfm-like", {"breaks": True, "html": True})
            md.disable("linkify")  # 不依赖 linkify-it-py
            rendered = md.render(node.body)
            full_body_html = f"""<hr><div class="section-title">📄 文档</div><div class="md-body">{rendered}</div>"""

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

        # —— 合成完整 HTML ——
        header_html = "".join(parts)
        if full_body_html:
            header_html += full_body_html

        html_doc = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  body {{ background: #1e1e2e; color: #cdd6f4; font-family: -apple-system, sans-serif; font-size: 14px; padding: 12px; line-height: 1.7; }}
  .card {{ font-family: -apple-system, "Segoe UI", sans-serif; padding: 12px; }}
  .placeholder {{ font-family: -apple-system, "Segoe UI", sans-serif; color: #a6adc8; font-size: 14px; padding: 20px; }}
  .header {{ font-size: 14px; font-weight: bold; color: #cdd6f4; margin-bottom: 8px; }}
  .title {{ font-size: 18px; font-weight: bold; color: #ffffff; margin-bottom: 10px; }}
  .detail {{ font-size: 13px; color: #bac2de; line-height: 1.6; margin: 8px 0 12px 0; white-space: pre-wrap; }}
  .meta {{ margin: 8px 0 4px 0; }}
  .tag {{ display: inline-block; background: #45475a; color: #cdd6f4; font-size: 12px; padding: 2px 8px; border-radius: 4px; margin-right: 6px; }}
  .section-title {{ font-size: 13px; font-weight: bold; color: #a6adc8; margin: 4px 0; }}
  .agent {{ font-size: 12px; color: #bac2de; margin: 2px 0; }}
  .agent code {{ background: #1e1e2e; color: #f5c2e7; padding: 1px 4px; border-radius: 3px; }}
  .hint {{ font-size: 12px; color: #585b70; margin-top: 4px; }}
  .badge {{ display: inline-block; font-size: 11px; font-weight: 600; padding: 2px 10px; border-radius: 10px; color: #1e1e2e; }}
  hr {{ border: none; border-top: 1px solid #45475a; margin: 12px 0; }}
  .md-body {{ font-size: 13px; color: #bac2de; line-height: 1.7; }}
  .md-body h1 {{ color: #fff; font-size: 20px; border-bottom: 1px solid #45475a; padding-bottom: 4px; }}
  .md-body h2 {{ color: #cdd6f4; font-size: 17px; }} .md-body h3 {{ color: #a6adc8; font-size: 15px; }}
  .md-body table {{ border-collapse: collapse; margin: 12px 0; width: 100%; }}
  .md-body th {{ background: #313244; color: #cdd6f4; padding: 8px 12px; text-align: left; font-weight: 600; border: 1px solid #45475a; }}
  .md-body td {{ padding: 6px 12px; border: 1px solid #313244; }}
  .md-body tr:nth-child(even) {{ background: #181825; }}
  .md-body code {{ background: #1e1e2e; color: #f5c2e7; padding: 1px 5px; border-radius: 3px; }}
  .md-body pre {{ background: #181825; padding: 10px 14px; border-radius: 6px; overflow-x: auto; }}
  .md-body blockquote {{ border-left: 3px solid #45475a; padding-left: 12px; color: #a6adc8; }}
  .md-body a {{ color: #89b4fa; }}
  .md-body strong {{ color: #cdd6f4; }} .md-body em {{ color: #a6e3a1; }}
</style></head><body>{header_html}<script>
  document.addEventListener('click', function(e) {{
    var t = e.target; while (t && t.tagName !== 'A') t = t.parentElement;
    if (t && t.href && t.getAttribute('target') === '_blank') {{
      e.preventDefault(); window.location.href = t.href;
    }}
  }});
</script></body></html>"""

        self._detail.show_task(task_uri, node, html_doc)

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

    # ── Gateway 序列化 ──

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
            f"socket:    {self._gateway._path} {'✅' if self._gateway._server else '❌'}",
            f"watchers:  {len(self._watcher.files()) + len(self._watcher.directories())} paths",
            f"timers:    refresh={self._refresh_timer.interval()}ms",
            f"qt:        {'running' if QApplication.instance() else 'stopped'}",
            f"sandbox:   {'⚡ ' + self._sandbox_path if self._sandbox else 'no'}",
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
        if node.body:
            # 探针输出 body 第一行 + ... 提示
            body_preview = node.body.split("\n")[0]
            lines.append(f"  body:    {body_preview}{' ...' if len(node.body.splitlines()) > 1 else ''}")
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
        if lines:
            return "\n".join(lines)
        # 兜底：直接从 ~/.diy/agents/ 读
        from diydev.app.agent_bridge import list_agents
        all_agents = list_agents()
        if all_agents:
            lines = []
            for a in all_agents:
                lines.append(f"{a.task_id} agentd pid={a.pid} state={a.state}")
            return "\n".join(lines)
        return "(无 agent)"

    def closeEvent(self, event):
        self._gateway.stop()
        super().closeEvent(event)


# ═══════════════════════════════════════════════════════
# Gateway — Unix socket 入口
# ═══════════════════════════════════════════════════════

import fcntl
import socket
import socketserver
import threading
from typing import Callable, TypeVar

from cyclopts import App as CycloptsApp
from cyclopts.exceptions import UnknownCommandError
from PySide6.QtCore import QMetaObject, Qt as QtCore, Q_ARG, QTimer  # type: ignore[import-untyped]
from PySide6.QtCore import QObject  # type: ignore[import-untyped]


T = TypeVar("T")


class _InvokeEvent(QEvent):
    """跨线程调用 QEvent — 用 threading.Event 可靠信令。"""

    _EVENT_TYPE = QEvent.Type(QEvent.registerEventType())

    def __init__(self, fn: Callable[[], T], ret: list[T], done: threading.Event):
        super().__init__(self._EVENT_TYPE)
        self.fn = fn
        self.ret = ret
        self.done = done

    def execute(self) -> None:
        try:
            self.ret.append(self.fn())
        except Exception as e:
            self.ret.append(e)
        self.done.set()

    @classmethod
    def create(cls, fn: Callable[[], T], ret: list[T], done: threading.Event) -> "_InvokeEvent":
        return cls(fn, ret, done)


class MainThread:
    """安全地在 Qt 主线程执行操作，调用者不关心线程跳转。

    用法:
        mt = MainThread(window)
        tree = mt.invoke(window.format_tree)    # 返回 str
        node = mt.invoke(lambda: window.format_node(42))  # 带参数
    """

    def __init__(self, window: QObject):
        self._window = window

    def invoke(self, fn: Callable[[], T], timeout: float = 20.0) -> T:
        """阻塞等待 fn 在 Qt 主线程执行完毕，返回结果。

        用 QApplication.postEvent + threading.Event 的跨线程方案，
        timeout 超时后抛出 TimeoutError。
        """
        import threading
        ret: list[T] = []
        done = threading.Event()
        evt = _InvokeEvent.create(fn, ret, done)
        QApplication.instance().postEvent(self._window, evt)
        if not done.wait(timeout=timeout):
            raise TimeoutError(f"UI 操作超时（{timeout}s）")
        if isinstance(ret[0], Exception):
            raise ret[0]
        return ret[0]


class GatewayCLI:
    """Socket 协议层 — 用 cyclopts 解析命令，输出为纯文本。

    协议前缀:
      diy <cmd>   — v1 协议
    """

    def __init__(self, window: "MainWindow"):
        self._window = window
        self._main = MainThread(window)
        self._app = CycloptsApp(name="gateway")

        # ── diy 子应用（协议 v1） ──
        diy = CycloptsApp(name="diy", help="diy protocol v1")

        @diy.command
        def tree():
            """完整任务树（和 UI 一致）"""
            return self._main.invoke(self._window.format_tree)

        @diy.command
        def status():
            """健康检查（pid/窗口/树/定时器）"""
            return self._main.invoke(self._window.format_status)

        @diy.command
        def agents():
            """agent 列表"""
            return self._main.invoke(self._window.format_agents)

        @diy.command
        def reload():
            """热重载 state.yaml"""
            logger.info("[gateway] diy reload 收到 → 全量重载")
            self._main.invoke(self._window._load)
            return "OK"

        @diy.command
        def node(uri: str):
            """<uri> 任务节点详情"""
            return self._main.invoke(lambda: self._window.format_node(uri))

        @diy.command
        def doctor():
            """分层健康自检 — app 状态 / socket 健康 / 多实例 / state.yaml"""
            from diydev.app._doctor import format_report, run_check
            gw = self._window._gateway
            sock_dev = getattr(gw, '_sock_dev', None)
            sock_ino = getattr(gw, '_sock_ino', None)
            return format_report(run_check(sock_dev, sock_ino))

        # ── ui ── 聊天面板交互 ──
        ui_app = CycloptsApp(name="ui", help="UI 视图操纵")

        chat_app = CycloptsApp(name="chat", help="AgentChatPanel 交互")

        @chat_app.command
        def state() -> str:
            """当前 AgentChatPanel 状态（task_uri, mode, sessions）。"""
            import yaml as _yaml
            panel = self._window._detail._chat if hasattr(self._window, "_detail") and self._window._detail else None
            if panel is None:
                return "error: UI 尚未初始化"
            panel_state = self._main.invoke(panel.ui_state)
            import io as _io
            buf = _io.StringIO()
            _yaml.dump(panel_state, buf, allow_unicode=True, default_flow_style=False, sort_keys=False)
            return buf.getvalue()

        @chat_app.command
        def sessions() -> str:
            """当前 task 的 session 列表。"""
            import yaml as _yaml
            import io as _io
            panel = self._window._detail._chat if hasattr(self._window, "_detail") and self._window._detail else None
            if panel is None:
                return "error: UI 尚未初始化"
            panel_state = self._main.invoke(panel.ui_state)
            sessions_list = panel_state.get("sessions", [])
            if not sessions_list:
                return "sessions: []"
            buf = _io.StringIO()
            _yaml.dump({"sessions": sessions_list, "count": len(sessions_list)}, buf, allow_unicode=True, default_flow_style=False, sort_keys=False)
            return buf.getvalue()

        @chat_app.command
        def read(task: str | None = None):
            """读取当前对话文本（UI 层 _log）。"""
            panel = self._window._detail._chat if hasattr(self._window, "_detail") and self._window._detail else None
            if panel is None:
                return "error: UI 尚未初始化"
            text = self._main.invoke(panel.ui_chat_log)
            return text or "(无对话)"

        @chat_app.command
        def wait(task: str | None = None, timeout: int = 60):
            """等待 agent 完成，轮询 UI 层 _log 文本。"""
            import time as _time
            panel = self._window._detail._chat if hasattr(self._window, "_detail") and self._window._detail else None
            if panel is None:
                return "error: UI 尚未初始化"
            out = getattr(self, "_stream_out", None)
            deadline = _time.time() + timeout
            last_text = ""
            while _time.time() < deadline:
                cur = self._main.invoke(panel.ui_chat_log) or ""
                if cur != last_text:
                    delta = cur[len(last_text):]
                    last_text = cur
                    if out:
                        out.write(delta)
                        out.flush()
                    else:
                        return delta  # 非流式模式，只返回增量
                # 检查 session 是否已完成
                state = self._main.invoke(panel.ui_state)
                sessions = state.get("sessions", [])
                all_done = all(s.get("state") in ("done", "failed") for s in sessions)
                if sessions and all_done:
                    if out:
                        out.write("\n[done]\n")
                        out.flush()
                    return
                _time.sleep(2)
            return f"[timeout] agent 未在 {timeout}s 内完成"

        @chat_app.command
        def select(task_uri: str):
            """选中任务，显示其 AgentChatPanel。"""
            panel = self._window._detail._chat if hasattr(self._window, "_detail") and self._window._detail else None
            if panel is None:
                return "error: UI 尚未初始化"
            self._main.invoke(lambda: panel.set_task(task_uri))
            return f"OK: chat set to {task_uri}"

        @chat_app.command
        def send(text: str, task: str | None = None):
            """向 task 发送消息（走 UI 层）。"""
            panel = self._window._detail._chat if hasattr(self._window, "_detail") and self._window._detail else None
            if panel is None:
                return "error: UI 尚未初始化"
            if task:
                self._main.invoke(lambda: panel.set_task(task))
            self._main.invoke(lambda: panel.send_text(text))
            return "OK: 已发送"

        ui_app.command(chat_app)
        diy.command(ui_app)

        # ═══════════════════════════════════════════
        # AI 子命令：task / subject / state / scan / profile / agent
        # 从 _dai_cli 导入逻辑函数，注册为 cyclopts 子 App
        # ═══════════════════════════════════════════

        # ── state ──
        @diy.command
        def state(
            json_output: bool = False,
            set_path: list[str] | None = None,
            free: bool = False,
        ):
            """输出/修改 state.yaml"""
            from diydev._state import load_state, save_state
            if free:
                data = load_state()
                spaces = data.get("spaces", {})
                free_paths = [p for p, cfg in spaces.items() if not cfg or cfg.get("lock") is None]
                return "\n".join(sorted(free_paths))
            if set_path is not None:
                if len(set_path) != 2:
                    return "错误: --set 需要 <path> <value> 两个参数"
                path, raw_value = set_path
                import json as _json
                parsed = _json.loads(raw_value) if raw_value.lower() not in ("true", "false") else raw_value.lower() == "true"
                try:
                    parsed = int(raw_value)
                except ValueError:
                    pass
                data = load_state()
                parts = path.split(".")
                section, key, field = parts[0], ".".join(parts[1:-1]), parts[-1]
                section_data = data.setdefault(section, {})
                entry = section_data.setdefault(key, {})
                entry[field] = parsed
                save_state(data)
                return "OK"
            import io as _io
            import yaml as _yaml
            _buf = _io.StringIO()
            _yaml.dump(load_state(), _buf, allow_unicode=True, default_flow_style=False, sort_keys=False)
            return _buf.getvalue()

        # ── scan ──
        @diy.command
        def scan(
            path: str | None = None,
            json_output: bool = False,
        ):
            """扫描 workspace 与 spaces"""
            from diydev._dai_scan import find_spaces, find_workspace_root
            import os as _os
            start = _os.path.realpath(path) if path else _os.path.realpath(_os.getcwd())
            ws = find_workspace_root(start)
            if ws is None:
                return "错误: 未找到 diy.yaml"
            spaces = find_spaces(ws)
            import yaml as _yaml
            import json as _json
            result = {"workspace": ws, "spaces": spaces}
            if json_output:
                return _json.dumps(result, indent=2, ensure_ascii=False)
            import io as _io
            _buf = _io.StringIO()
            _yaml.dump(result, _buf, allow_unicode=True, default_flow_style=False, sort_keys=False)
            return _buf.getvalue()

        # ── ai profile ──
        profile_app = CycloptsApp(name="profile", help="查询 state.yaml 中的 profile 预设")

        @profile_app.command(name="list")
        def profile_list(json_output: bool = False):
            """列出所有 profile"""
            from diydev._state import load_state
            import json as _json
            profiles = load_state().get("profiles", {})
            if json_output:
                return _json.dumps(profiles, indent=2, ensure_ascii=False)
            import io as _io
            import yaml as _yaml
            _buf = _io.StringIO()
            _yaml.dump(profiles, _buf, allow_unicode=True, default_flow_style=False, sort_keys=False)
            return _buf.getvalue()

        @profile_app.command
        def profile_show(name: str, json_output: bool = False):
            """查看单个 profile"""
            from diydev._state import load_state
            import yaml as _yaml, json as _json
            profiles = load_state().get("profiles", {})
            if name not in profiles:
                return f"错误: profile {name} 不存在"
            if json_output:
                return _json.dumps(profiles[name], indent=2, ensure_ascii=False)
            import io as _io
            import yaml as _yaml
            _buf = _io.StringIO()
            _yaml.dump(profiles[name], _buf, allow_unicode=True, default_flow_style=False, sort_keys=False)
            return _buf.getvalue()

        diy.command(profile_app)

        # ── subject ──
        subject_app = CycloptsApp(name="subject", help="Subject 树管理")

        def _norm(path: str) -> str:
            import os as _os
            home = _os.path.expanduser("~")
            expanded = _os.path.abspath(_os.path.expanduser(path))
            if expanded.startswith(home + "/"):
                return "~" + expanded[len(home):]
            if expanded == home:
                return "~"
            return expanded

        def _subject_is_git(path: str) -> bool:
            import os as _os
            full = _os.path.expanduser(path)
            return _os.path.isdir(_os.path.join(full, ".git")) or _os.path.isfile(_os.path.join(full, ".git"))

        @subject_app.command(name="add")
        def subject_add(
            path: str,
            desc: str | None = None,
            json_output: bool = False,
        ):
            """注册 subject"""
            from diydev._state import load_state, save_state
            path_n = _norm(path)
            data = load_state()
            subjects = data.setdefault("subjects", {})
            if path_n in subjects:
                return f"错误: subject {path_n} 已存在"
            entry: dict = {}
            if desc:
                entry["description"] = desc
            subjects[path_n] = entry
            save_state(data)
            import json as _json, io as _io
            result = {"status": "success", "data": {"path": path_n, **entry}}
            if json_output:
                return _json.dumps(result, indent=2, ensure_ascii=False)
            import yaml as _yaml
            _buf = _io.StringIO()
            _yaml.dump(result, _buf, allow_unicode=True, default_flow_style=False, sort_keys=False)
            return _buf.getvalue()

        @subject_app.command(name="list")
        def subject_list(json_output: bool = False):
            """扁平列表"""
            from diydev._state import load_state
            import yaml as _yaml, json as _json, io as _io
            data = load_state()
            subjects = data.get("subjects", {})
            enriched = {p: {**entry, "is_git": _subject_is_git(p)} for p, entry in subjects.items()}
            if json_output:
                return _json.dumps(enriched, indent=2, ensure_ascii=False)
            _buf = _io.StringIO()
            _yaml.dump(enriched, _buf, allow_unicode=True, default_flow_style=False, sort_keys=False)
            return _buf.getvalue()

        @subject_app.command(name="remove")
        def subject_remove(path: str, json_output: bool = False):
            """删除 subject"""
            from diydev._state import load_state, save_state
            import json as _json, io as _io
            path_n = _norm(path)
            data = load_state()
            subjects = data.get("subjects", {})
            if path_n not in subjects:
                return f"错误: subject {path_n} 不存在"
            to_delete = [p for p in subjects if p == path_n or p.startswith(path_n + "/")]
            for p in to_delete:
                del subjects[p]
            save_state(data)
            result = {"status": "success", "data": {"path": path_n, "removed": len(to_delete)}}
            if json_output:
                return _json.dumps(result, indent=2, ensure_ascii=False)
            import yaml as _yaml
            _buf = _io.StringIO()
            _yaml.dump(result, _buf, allow_unicode=True, default_flow_style=False, sort_keys=False)
            return _buf.getvalue()

        @subject_app.command(name="show")
        def subject_show(path: str, json_output: bool = False):
            """查看单个 subject（含实时 is_git 检测）"""
            from diydev._state import load_state
            import yaml as _yaml, json as _json, io as _io
            path_n = _norm(path)
            data = load_state()
            subjects = data.get("subjects", {})
            if path_n not in subjects:
                return f"subject {path_n} 不存在"
            entry = dict(subjects[path_n])
            entry["is_git"] = _subject_is_git(path_n)
            if json_output:
                return _json.dumps(entry, indent=2, ensure_ascii=False)
            _buf = _io.StringIO()
            _yaml.dump(entry, _buf, allow_unicode=True, default_flow_style=False, sort_keys=False)
            return _buf.getvalue()

        @subject_app.command(name="tree")
        def subject_tree(json_output: bool = False):
            """树状展示 subject（实时 is_git 检测）"""
            from diydev._state import load_state
            from diydev._dai_cli import _build_subject_tree
            import yaml as _yaml, json as _json, io as _io
            data = load_state()
            subjects = data.get("subjects", {})
            enriched = {p: {**entry, "is_git": _subject_is_git(p)} for p, entry in subjects.items()}
            tree = _build_subject_tree(enriched)
            if json_output:
                return _json.dumps(tree, indent=2, ensure_ascii=False)
            _buf = _io.StringIO()
            _yaml.dump(tree, _buf, allow_unicode=True, default_flow_style=False, sort_keys=False)
            return _buf.getvalue()

        @subject_app.command(name="scan")
        def subject_scan(root: str, json_output: bool = False):
            """扫描文件系统，发现 git 仓库作为 subject"""
            import os as _os
            from diydev._state import load_state, save_state
            import yaml as _yaml, json as _json, io as _io
            root_path = _os.path.abspath(_os.path.expanduser(root))
            if not _os.path.isdir(root_path):
                return f"错误: 目录不存在 {root}"
            found: dict[str, dict] = {}
            for dirpath, dirs, _ in _os.walk(root_path):
                if _os.path.isdir(_os.path.join(dirpath, ".git")) or _os.path.isfile(_os.path.join(dirpath, ".git")):
                    found[_norm(dirpath)] = {}
                    dirs.clear()
            data = load_state()
            subjects = data.setdefault("subjects", {})
            subjects.update(found)
            save_state(data)
            result = {"status": "success", "data": {"found": len(found)}}
            if json_output:
                return _json.dumps(result, indent=2, ensure_ascii=False)
            _buf = _io.StringIO()
            _yaml.dump(result, _buf, allow_unicode=True, default_flow_style=False, sort_keys=False)
            return _buf.getvalue()

        diy.command(subject_app)

        # ── task ──
        task_app = CycloptsApp(name="task", help="任务管理")

        @task_app.command(name="star")
        def task_star(uri: str, json_output: bool = False):
            """star 任务（创建 symlink）"""
            from diydev._state import get_task, star_task
            import yaml as _yaml, json as _json, io as _io
            task = get_task(uri)
            if task is None:
                return f"错误: 任务 {uri} 不存在"
            star_task(uri)
            result = {"status": "success", "data": {"uri": uri, "starred": True}}
            if json_output:
                return _json.dumps(result, indent=2, ensure_ascii=False)
            _buf = _io.StringIO()
            _yaml.dump(result, _buf, allow_unicode=True, default_flow_style=False, sort_keys=False)
            return _buf.getvalue()

        @task_app.command(name="unstar")
        def task_unstar(uri: str, json_output: bool = False):
            """unstar 任务（删除 symlink）"""
            from diydev._state import get_task, unstar_task
            import yaml as _yaml, json as _json, io as _io
            task = get_task(uri)
            if task is None:
                return f"错误: 任务 {uri} 不存在"
            unstar_task(uri)
            result = {"status": "success", "data": {"uri": uri, "starred": False}}
            if json_output:
                return _json.dumps(result, indent=2, ensure_ascii=False)
            _buf = _io.StringIO()
            _yaml.dump(result, _buf, allow_unicode=True, default_flow_style=False, sort_keys=False)
            return _buf.getvalue()

        @task_app.command(name="list")
        def task_list(json_output: bool = False):
            """列出所有任务"""
            from diydev._state import list_tasks
            import yaml as _yaml, json as _json, io as _io
            tasks = dict(list_tasks())
            if json_output:
                return _json.dumps({"tasks": tasks}, indent=2, ensure_ascii=False)
            _buf = _io.StringIO()
            _yaml.dump({"tasks": tasks}, _buf, allow_unicode=True, default_flow_style=False, sort_keys=False)
            return _buf.getvalue()

        @task_app.command(name="show")
        def task_show(uri: str, json_output: bool = False):
            """查看单个任务"""
            from diydev._state import get_task
            import yaml as _yaml, json as _json, sys as _sys
            task = get_task(uri)
            if task is None:
                return f"错误: 任务 {uri} 不存在"
            body = task.pop("body", "") if not json_output else task.get("body", "")
            if json_output:
                return _json.dumps(task, indent=2, ensure_ascii=False)
            import io as _io
            import yaml as _yaml
            _buf = _io.StringIO()
            _yaml.dump(task, _buf, allow_unicode=True, default_flow_style=False, sort_keys=False)
            result = _buf.getvalue()
            if body:
                result += "\n" + body
            return result

        @task_app.command(name="create")
        def task_create(
            title: str,
            subject: str,
            parent: str | None = None,
            detail: str | None = None,
            body_file: str | None = None,
            source_type: str = "local",
            source_uri: str | None = None,
            json_output: bool = False,
        ):
            """创建任务"""
            from diydev._state import load_state, get_task, create_task
            import yaml as _yaml, json as _json, sys as _sys
            subject_n = _norm(subject)
            data = load_state()
            if subject_n not in data.get("subjects", {}):
                return f"错误: subject {subject_n} 未注册"
            if parent is not None and get_task(parent) is None:
                return f"错误: parent {parent} 不存在"
            body = ""
            if body_file:
                try:
                    from pathlib import Path
                    body = Path(body_file).read_text(encoding="utf-8")
                except OSError as exc:
                    return f"错误: 无法读取 body 文件: {exc}"
            try:
                uri = create_task(title=title, subject=subject_n, parent=parent, detail=detail,
                                  source_type=source_type, source_uri=source_uri, body=body)
            except ValueError as exc:
                return f"错误: {exc}"
            task = get_task(uri) or {}
            result = {"status": "success", "data": task}
            if json_output:
                return _json.dumps(result, indent=2, ensure_ascii=False)
            import io as _io
            import yaml as _yaml
            _buf = _io.StringIO()
            _yaml.dump(result, _buf, allow_unicode=True, default_flow_style=False, sort_keys=False)
            return _buf.getvalue()

        @task_app.command(name="edit")
        def task_edit(
            uri: str,
            title: str | None = None,
            state: str | None = None,
            subject: str | None = None,
            parent: str | None = None,
            detail: str | None = None,
            body_file: str | None = None,
            json_output: bool = False,
        ):
            """编辑任务"""
            from diydev._state import get_task, update_task_field
            import yaml as _yaml, json as _json, sys as _sys
            if get_task(uri) is None:
                return f"错误: 任务 {uri} 不存在"
            fields: dict = {}
            if title is not None:
                fields["title"] = title
            if state is not None:
                fields["state"] = state
            if subject is not None:
                fields["subject"] = _norm(subject)
            if parent is not None:
                if get_task(parent) is None:
                    return f"错误: parent {parent} 不存在"
                fields["parent"] = parent
            if detail is not None:
                fields["detail"] = detail
            if body_file is not None:
                try:
                    from pathlib import Path
                    fields["body"] = Path(body_file).read_text(encoding="utf-8")
                except OSError as exc:
                    return f"错误: 无法读取 body 文件: {exc}"
            task = update_task_field(uri, **fields)
            result = {"status": "success", "data": task}
            if json_output:
                return _json.dumps(result, indent=2, ensure_ascii=False)
            import io as _io
            import yaml as _yaml
            _buf = _io.StringIO()
            _yaml.dump(result, _buf, allow_unicode=True, default_flow_style=False, sort_keys=False)
            return _buf.getvalue()

        @task_app.command(name="delete")
        def task_delete(uri: str, json_output: bool = False):
            """删除本地任务"""
            from diydev._state import get_task, delete_task
            import json as _json
            task = get_task(uri)
            if task is None:
                return f"错误: 任务 {uri} 不存在"
            src = task.get("source", {})
            if src.get("type") != "local":
                return f"错误: {uri} 是外部任务，请用 unlink"
            delete_task(uri)
            result = {"status": "success"}
            if json_output:
                return _json.dumps(result, indent=2, ensure_ascii=False)
            return "已删除"

        @task_app.command(name="link")
        def task_link(
            title: str,
            subject: str,
            source_uri: str,
            parent: str | None = None,
            detail: str | None = None,
            json_output: bool = False,
        ):
            """链接外部任务（GitHub issue / PR 等）。不修改远端，仅建立本地引用。"""
            from diydev._state import load_state, get_task, create_task
            import yaml as _yaml, json as _json, io as _io
            if not source_uri:
                return "错误: --source-uri 必填"
            if "github.com" in source_uri:
                source_type = "github_pr" if "/pull/" in source_uri else "github_issue"
            else:
                source_type = "external"
            subject_n = _norm(subject)
            data = load_state()
            if subject_n not in data.get("subjects", {}):
                return f"错误: subject {subject_n} 未注册"
            if parent is not None and get_task(parent) is None:
                return f"错误: parent {parent} 不存在"
            try:
                uri = create_task(
                    title=title, subject=subject_n, parent=parent, detail=detail,
                    source_type=source_type, source_uri=source_uri,
                )
            except ValueError as exc:
                return f"错误: {exc}"
            task = get_task(uri) or {}
            result = {"status": "success", "data": task}
            if json_output:
                return _json.dumps(result, indent=2, ensure_ascii=False)
            _buf = _io.StringIO()
            _yaml.dump(result, _buf, allow_unicode=True, default_flow_style=False, sort_keys=False)
            return _buf.getvalue()

        @task_app.command(name="archive")
        def task_archive(uri: str, json_output: bool = False):
            """归档任务：从 ~/.diy/d/ 移到 ~/.diy/archive/data/。"""
            from diydev._state import get_task, archive_task
            import json as _json
            task = get_task(uri)
            if task is None:
                return f"错误: 任务 {uri} 不存在"
            try:
                archive_path = archive_task(uri)
            except FileNotFoundError:
                return f"错误: 任务文件不存在: {uri}"
            except OSError as exc:
                return f"错误: 归档失败: {exc}"
            result = {"status": "success", "data": {"uri": uri, "archive_path": str(archive_path)}}
            if json_output:
                return _json.dumps(result, indent=2, ensure_ascii=False)
            return f"已归档: {archive_path}"

        @task_app.command(name="unlink")
        def task_unlink(uri: str, json_output: bool = False):
            """解绑外部任务引用。不删除远端 issue，仅移除本地记录。"""
            from diydev._state import get_task, delete_task
            import json as _json
            task = get_task(uri)
            if task is None:
                return f"错误: 任务 {uri} 不存在"
            src = task.get("source", {})
            if src.get("type") == "local":
                return f"错误: {uri} 是本地任务，请用 delete"
            delete_task(uri)
            result = {"status": "success"}
            if json_output:
                return _json.dumps(result, indent=2, ensure_ascii=False)
            return "已解绑"

        @task_app.command(name="sync")
        def task_sync(
            uri: str | None = None,
            all: bool = False,
            json_output: bool = False,
        ):
            """同步外部任务内容到本地（目前支持：GitHub issue）。"""
            from diydev._state import get_task, list_tasks, update_task_field, archive_task
            import json as _json, subprocess, re as _re, yaml as _yaml, io as _io

            if not uri and not all:
                return "错误: 请指定任务 URI 或使用 --all 同步全部"

            _GH_STATE_MAP = {"OPEN": "active", "CLOSED": "done", "MERGED": "done"}

            def _gh_parse(source_uri: str):
                m = _re.match(r"github\.com/([^/]+)/([^/]+)/issues/(\d+)", source_uri)
                if not m:
                    return None
                return m.group(1), m.group(2), m.group(3)

            def _sync_one(t_uri: str, t_data: dict) -> dict | str:
                src = t_data.get("source", {})
                source_uri = src.get("uri", t_uri)
                parsed = _gh_parse(source_uri)
                if not parsed:
                    return f"无法解析 GitHub URI: {source_uri}"
                owner, repo, number = parsed
                try:
                    r = subprocess.run(
                        ["gh", "issue", "view", number, "--repo", f"{owner}/{repo}",
                         "--json", "title,body,state,updatedAt"],
                        capture_output=True, text=True, timeout=15,
                    )
                except FileNotFoundError:
                    return "gh CLI 未安装"
                except subprocess.TimeoutExpired:
                    return f"请求 {owner}/{repo}#{number} 超时"
                if r.returncode != 0:
                    err = r.stderr.strip()
                    if "not found" in err.lower():
                        try:
                            ap = archive_task(t_uri)
                            return f"GitHub issue 已不存在，已归档至 {ap}"
                        except FileNotFoundError:
                            return "GitHub issue 已不存在（已移除）"
                    return f"gh 调用失败: {err}"
                try:
                    data = _json.loads(r.stdout)
                except _json.JSONDecodeError:
                    return f"gh 返回非 JSON: {r.stdout[:200]}"
                title = data.get("title", t_data.get("title", ""))
                body = data.get("body", "") or ""
                gh_state = _GH_STATE_MAP.get(data.get("state", ""), "active")
                return update_task_field(t_uri, title=title, state=gh_state, body=body)

            if all:
                tasks = list_tasks()
                results: dict[str, dict | str] = {}
                total = 0
                for t_uri, t_data in sorted(tasks.items()):
                    src = t_data.get("source", {})
                    src_type = src.get("type", "")
                    if src_type not in ("github_issue",):
                        continue
                    total += 1
                    results[t_uri] = _sync_one(t_uri, t_data)
                ok = sum(1 for v in results.values() if isinstance(v, dict))
                fail = sum(1 for v in results.values() if isinstance(v, str))
                if json_output:
                    return _json.dumps({"synced": ok, "failed": fail, "results": results, "total": total},
                                       indent=2, ensure_ascii=False)
                return f"同步完成: {ok} 更新, {fail} 失败, 共 {total} 个外部任务"
            # 单个同步
            task = get_task(uri)
            if task is None:
                return f"错误: 任务 {uri} 不存在"
            src = task.get("source", {})
            src_type = src.get("type", "")
            if src_type != "github_issue":
                return f"错误: {uri} 的类型 {src_type} 暂不支持同步"
            result = _sync_one(uri, task)
            if isinstance(result, str):
                return f"错误: {result}"
            if json_output:
                return _json.dumps({"status": "success", "data": result}, indent=2, ensure_ascii=False)
            _buf = _io.StringIO()
            _yaml.dump({"status": "success", "data": result}, _buf, allow_unicode=True, default_flow_style=False, sort_keys=False)
            return _buf.getvalue()

        diy.command(task_app)

        # ── agent ──
        agent_app = CycloptsApp(name="agent", help="子 agent 管理 — 文本协议")

        import socket as _sock
        _AGENT_SOCKET = str(diy_home() / "agentd.sock")

        def _agent_send_text(cmd_line: str, retries: int = 10) -> str:
            """向 agentd socket 发送一行文本命令，返回全部响应文本。"""
            for attempt in range(retries):
                try:
                    s = _sock.socket(_sock.AF_UNIX, _sock.SOCK_STREAM)
                    s.settimeout(10)
                    s.connect(_AGENT_SOCKET)
                    s.sendall((cmd_line + "\n").encode("utf-8"))
                    s.shutdown(_sock.SHUT_WR)
                    buf: list[bytes] = []
                    while True:
                        data = s.recv(4096)
                        if not data:
                            break
                        buf.append(data)
                    s.close()
                    return b"".join(buf).decode("utf-8")
                except FileNotFoundError:
                    if attempt < retries - 1:
                        import time as _time
                        _time.sleep(0.5)
                        continue
                    raise
                except OSError:
                    if attempt < retries - 1:
                        import time as _time
                        _time.sleep(0.5)
                        continue
                    raise
            return ""

        def _check_agent_ok(resp: str) -> str | None:
            """检查响应首行是否为 OK，返回状态描述或错误信息。"""
            first = resp.split("\n")[0].strip()
            if first.startswith("ERROR"):
                return first[6:].strip()
            if first.startswith("OK"):
                return first[3:].strip()
            return None

        @agent_app.command
        def agent_spawn(
            task_uri: str,
            message: str,
            model: str | None = None,
            toolsets: str | None = None,
            reasoning_budget: int | None = None,
        ):
            """为一个 task 创建并启动 agent"""
            parts = ["spawn", f"--task={task_uri}", f"--message={message}"]
            if model:
                parts.append(f"--model={model}")
            if toolsets:
                parts.append(f"--toolsets={toolsets}")
            if reasoning_budget is not None:
                parts.append(f"--reasoning={reasoning_budget}")
            cmd = " ".join(parts)
            resp = _agent_send_text(cmd)
            err = _check_agent_ok(resp)
            if err is not None:
                return f"agent {task_uri}: {err}"
            return f"agent {task_uri}: 已启动"

        @agent_app.command
        def agent_send(
            task_uri: str,
            message: str,
        ):
            """向 agent 发送消息"""
            cmd = f"send --task={task_uri} --message={message}"
            resp = _agent_send_text(cmd)
            err = _check_agent_ok(resp)
            if err is not None:
                return f"agent {task_uri}: {err}"
            return f"agent {task_uri}: 消息已发送"

        @agent_app.command
        def agent_kill(task_uri: str):
            """终止 agent"""
            cmd = f"kill --task={task_uri}"
            resp = _agent_send_text(cmd)
            err = _check_agent_ok(resp)
            if err is not None:
                return f"agent {task_uri}: {err}"
            return f"agent {task_uri}: 已终止"

        @agent_app.command
        def agent_list():
            """列出所有活跃 agent"""
            resp = _agent_send_text("list")
            if resp.startswith("(") or not resp.strip():
                return "(无活跃 agent)"
            return resp

        @agent_app.command
        def agent_show(task_uri: str):
            """查看 agent 状态和输出"""
            cmd = f"show --task={task_uri}"
            resp = _agent_send_text(cmd)
            if resp.startswith("ERROR"):
                return resp
            return resp

        diy.command(agent_app)

        # ── notify / title（通用，AI 和人类都能用） ──
        @diy.command
        def notify(*message: str):
            """<消息...> 弹通知 — 窗口右上角弹出"""
            text = " ".join(message)
            QMetaObject.invokeMethod(
                self._window, "show_notification",
                QtCore.ConnectionType.QueuedConnection,
                Q_ARG(str, text))
            return "OK"

        @diy.command
        def title(*text: str):
            """<文本...> 改窗口标题"""
            title_text = " ".join(text)
            if not title_text:
                return "错误: 缺少参数，用法: diy title <文本...>"
            QMetaObject.invokeMethod(
                self._window, "setWindowTitle",
                QtCore.ConnectionType.QueuedConnection,
                Q_ARG(str, title_text))
            return f"标题已改为: {title_text}"

        @diy.command
        def metrics():
            """返回当前指标快照（YAML）。"""
            import yaml  # type: ignore[import-untyped]  # noqa: PLC0415
            # 去除 YAML 颜色标记
            raw = yaml.dump(self._window._metrics.snapshot(), default_flow_style=False, sort_keys=False, allow_unicode=True)
            import re  # noqa: PLC0415
            return re.sub(r"\x1b\[\d+(;\d+)*m", "", raw)

        @diy.command
        def shutdown():
            """关闭管控台。app 退出后下次 dai 命令会自动启动。"""
            # QApp.quit() 线程安全 — 直接调用，不经过 QTimer
            QApplication.instance().quit()
            return "OK app 正在退出"

        # ── 注册 diy 组 ──
        self._app.command(diy)

        @self._app.default
        def unknown(*tokens: str):
            return f"未知命令: {' '.join(tokens)!r}  试试 --help"

    def dispatch(self, line: str, out: _io.TextIOWrapper) -> None:
        """流式输出 — 直接写 out，不缓冲。"""
        import io
        import shlex
        from rich.console import Console

        tokens = shlex.split(line) if line else ["--help"]
        console = Console(file=out, force_terminal=True, width=80)

        # 保存 stream_out 供流式命令（如 wait）使用
        self._stream_out = out

        # cyclopts 错误写入 stderr，重定向到 out
        old_stderr = sys.stderr
        err_buf = io.StringIO()
        sys.stderr = err_buf
        try:
            self._app(tokens, console=console, exit_on_error=False)
        except SystemExit:
            pass
        except UnknownCommandError:
            pass
        except Exception as exc:
            logger.error("dispatch 异常: %s\n%s", exc, traceback.format_exc())
            out.write(f"\n内部错误: {exc}\n")
        finally:
            sys.stderr = old_stderr
            self._stream_out = None

        err_text = err_buf.getvalue()
        if err_text:
            out.write(err_text)
        out.flush()


# ═══════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════


def _subjects_from_state() -> dict:
    """从 state.yaml 读取 subject 列表。"""
    from diydev._state import load_state
    return load_state().get("subjects", {})


# ═══════════════════════════════════════════════════════
# 创建任务对话框
# ═══════════════════════════════════════════════════════

class _CreateTaskDialog(QDialog):
    """创建任务弹窗。"""

    def __init__(self, parent=None, parent_uri: str | None = None,
                 initial_subject: str | None = None):
        super().__init__(parent)
        self.setWindowTitle("✨ 新建任务")
        self.resize(480, 400)

        self._parent_uri = parent_uri
        self._result_uri: str | None = None

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 标题
        layout.addWidget(QLabel("标题"))
        self._title = QLineEdit()
        self._title.setPlaceholderText("任务标题...")
        layout.addWidget(self._title)

        # Subject 选择
        layout.addWidget(QLabel("Subject"))
        self._subject = QComboBox()
        subjects = _subjects_from_state()
        self._subject.addItem("(无)", "")
        for s in sorted(subjects.keys()):
            self._subject.addItem(s, s)
        if initial_subject and initial_subject in subjects:
            self._subject.setCurrentText(initial_subject)
        layout.addWidget(self._subject)

        # 父任务（只读显示）
        if parent_uri:
            from diydev._state import get_task
            pt = get_task(parent_uri)
            pt_label = pt.get("title", parent_uri) if pt else parent_uri
            info = QLabel(f"父任务: {parent_uri} — {pt_label}")
            info.setStyleSheet("color: #a6adc8; font-size: 12px;")
            info.setWordWrap(True)
            layout.addWidget(info)

        # 详情
        layout.addWidget(QLabel("详情（可选）"))
        self._detail = QTextEdit()
        self._detail.setPlaceholderText("任务描述...")
        self._detail.setMaximumHeight(120)
        layout.addWidget(self._detail)

        layout.addStretch()

        # 按钮
        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        create_btn = QPushButton("创建")
        create_btn.setDefault(True)
        create_btn.clicked.connect(self._on_create)
        btn_row.addWidget(create_btn)
        layout.addLayout(btn_row)

        # 暗色样式
        self.setStyleSheet("""
            QDialog {
                background: #1e1e2e; color: #cdd6f4;
                font-size: 13px;
            }
            QLabel {
                color: #a6adc8; font-size: 12px;
            }
            QLineEdit, QTextEdit, QComboBox {
                background: #313244; color: #cdd6f4;
                border: 1px solid #45475a; border-radius: 4px;
                padding: 6px 8px; font-size: 13px;
            }
            QLineEdit:focus, QTextEdit:focus, QComboBox:focus {
                border: 1px solid #7aa2f7;
            }
            QComboBox::drop-down {
                border: none; width: 20px;
            }
            QComboBox QAbstractItemView {
                background: #313244; color: #cdd6f4;
                selection-background-color: #45475a;
            }
            QPushButton {
                background: #45475a; color: #cdd6f4;
                border: none; border-radius: 4px;
                padding: 6px 16px;
            }
            QPushButton:hover {
                background: #585b70;
            }
            QPushButton[pressed=true] {
                background: #7aa2f7;
            }
        """)

    def _on_create(self) -> None:
        title = self._title.text().strip()
        if not title:
            self._title.setFocus()
            return
        subject = self._subject.currentData() or ""
        detail = self._detail.toPlainText().strip() or None

        from diydev._state import create_task
        try:
            uri = create_task(
                title=title,
                subject=subject,
                parent=self._parent_uri,
                detail=detail,
            )
        except ValueError as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "创建失败", str(e))
            return

        self._result_uri = uri
        self.accept()


class Gateway(QObject):
    """Unix domain socket server — diy 协议入口。

    协议: 纯文本，cyclopts 解析。
    命令前缀 diy = 协议 v1。
    """

    def __init__(self, window: "MainWindow", socket_path: str | None = None):
        super().__init__(window)
        self._window = window
        if socket_path:
            self._path = os.path.expanduser(socket_path)
        else:
            self._path = str(diy_home() / "app.sock")
        self._server: socketserver.UnixStreamServer | None = None
        self._thread: threading.Thread | None = None
        self._cli = GatewayCLI(window)

    def start(self) -> None:
        _LOCK_PATH = os.path.join(os.path.dirname(self._path), "app.lock")
        os.makedirs(os.path.dirname(_LOCK_PATH), exist_ok=True)
        lock_fd = os.open(_LOCK_PATH, os.O_RDWR | os.O_CREAT, 0o644)

        # Acquire exclusive lock — serializes startup with _forward.py
        try:
            fcntl.fcntl(lock_fd, fcntl.LOCK_EX)
        except OSError:
            os.close(lock_fd)
            raise ConnectionError("无法获取 app.lock")

        try:
            # 1) Socket 锁检查 — 连接成功说明有活实例（锁下重新检查）
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.settimeout(0.5)
                s.connect(self._path)
                s.close()
                raise ConnectionError(
                    f"已有运行中的管控台实例 (socket: {self._path})"
                )
            except (OSError, socket.timeout):
                pass  # 连不上 → 残留或不存在

            # 2) 清理残留 socket + 绑定（仍持有锁）
            try:
                os.unlink(self._path)
            except OSError:
                pass

            self._server = socketserver.UnixStreamServer(
                self._path, _make_handler(self)
            )
            self._thread = threading.Thread(
                target=self._server.serve_forever, daemon=True
            )
            self._thread.start()

            # 记下 socket 文件身份
            self._sock_dev: int | None = None
            self._sock_ino: int | None = None
            try:
                st = os.stat(self._path)
                self._sock_dev = st.st_dev
                self._sock_ino = st.st_ino
            except OSError:
                pass

            logger.info(
                "Gateway socket ready → %s  pid=%d",
                self._path,
                os.getpid(),
            )
        finally:
            # Release lock — socket is bound, others can detect it
            os.close(lock_fd)

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
        try:
            os.unlink(self._path)
        except OSError:
            pass


def _make_handler(gateway: Gateway):
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
                gateway._cli.dispatch(cmd, text_out)
            except Exception:
                import traceback
                text_out.write(f"\n内部错误: {traceback.format_exc()}")
                text_out.flush()
    return Handler


# ═══════════════════════════════════════════════════════
# AgentInfo (简化 dataclass，避免循环导入)
# ═══════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════
# 任务树过滤器
# ═══════════════════════════════════════════════════════

class TaskFilterProxy(QSortFilterProxyModel):
    """按文本 + 状态过滤任务树。"""

    def __init__(self, window: "MainWindow"):
        super().__init__(window)
        self._window = window
        self.setRecursiveFilteringEnabled(True)

    def filterAcceptsRow(self, source_row: int, source_parent) -> bool:
        model = self.sourceModel()
        if model is None:
            return True
        index = model.index(source_row, 0, source_parent)
        if not index.isValid():
            return True

        text = self._window._filter_text.text().strip().lower()
        state_filter = self._window._filter_state.currentText()

        display = (index.data(Qt.ItemDataRole.DisplayRole) or "").lower()
        uri = index.data(ROLE_TASK_URI) or ""
        item_state = index.data(ROLE_STATE) or ""

        # 文本匹配
        text_ok = not text or text in display or text in uri.lower()

        # 状态匹配
        state_ok = state_filter == "所有状态" or item_state == state_filter

        return text_ok and state_ok


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
    import socket
    import subprocess

    # 日志系统必须先初始化（MainWindow.__init__ 中 guarded 方法可能立即触发）
    setup_app_logger()
    logger.info("=" * 50)
    logger.info("diy 管控台启动")

    # ── 连接 agentd（已有则复用，没有则启动） ──
    hermes_python = os.path.expanduser("~/.hermes/hermes-agent/venv/bin/python3")
    _agentd_proc = None
    agentd_sock = str(diy_home() / "agentd.sock")

    # 先试试能不能连上已存在的 agentd
    _agentd_alive = False
    if os.path.exists(agentd_sock):
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect(agentd_sock)
            s.close()
            _agentd_alive = True
            logger.info("agentd 已在运行，复用")
        except OSError:
            pass  # socket 残留，需要启动新的

    if not _agentd_alive and os.path.exists(hermes_python):
        srcdir = os.path.dirname(os.path.abspath(__file__))  # diydev/app/
        src_parent = os.path.dirname(os.path.dirname(srcdir))  # src/<zipper>
        env = os.environ.copy()
        env["PYTHONPATH"] = src_parent
        _agentd_proc = subprocess.Popen(
            [hermes_python, "-m", "diydev._agent_daemon"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )
        logger.info("agentd 已启动 (pid=%s)", _agentd_proc.pid)
    elif not _agentd_alive:
        logger.warning("找不到 Hermes Python，agentd 未启动")

    sandbox, sandbox_path = _detect_sandbox()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(_app_stylesheet(sandbox))

    # Ctrl+C 两次退出（调试模式下 Qt event loop 会吞 SIGINT）
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    try:
        window = MainWindow()
    except ConnectionError as e:
        logger.error(str(e))
        return

    window.show()
    ret = app.exec()

    # ── 退出时杀 agentd ──
    if _agentd_proc and _agentd_proc.poll() is None:
        _agentd_proc.terminate()
        try:
            _agentd_proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            _agentd_proc.kill()
        logger.info("agentd 已停止")

    sys.exit(ret)


if __name__ == "__main__":
    main()
