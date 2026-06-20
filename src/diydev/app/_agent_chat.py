"""Agent 对话面板：结构化消息渲染 + 流式更新。

设计原则（模仿 Hermes TUI）：
- steer.log 解析为结构化消息（user/assistant/system）
- 消息气泡带角色图标 + 时间戳 + markdown 渲染
- 定时轮询 steer.log 变化，模拟流式输出效果
- 运行中显示思考动画 + 工具执行提示
- 自动滚动到底部，用户手动滚动时暂停
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal  # type: ignore[import-untyped]
from PySide6.QtWidgets import (  # type: ignore[import-untyped]
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from diydev.app._app_log import logger as _logger
from diydev.app.agent_bridge import list_agents, steer_read, steer_send

# ═══════════════════════════════════════════════════════
# 色彩常量（Catppuccin Mocha）
# ═══════════════════════════════════════════════════════

_BG = "#1e1e2e"
_BG_DARK = "#181825"
_BG_Surface = "#313244"
_BG_Surface2 = "#45475a"
_TEXT = "#cdd6f4"
_TEXT_DIM = "#a6adc8"
_MAUVE = "#cba6f7"  # 用户角色色
_BLUE = "#89b4fa"  # 助手角色色
_GREEN = "#a6e3a1"  # 成功/完成
_YELLOW = "#f9e2af"  # 警告/思考
_RED = "#f38ba8"  # 错误
_PEACH = "#fab387"  # 工具执行
_TEAL = "#94e2d5"  # 链接/代码
_surface0 = "#585b70"
_surface1 = "#6c7086"
_border = "#313244"

# ═══════════════════════════════════════════════════════
# Steer.log 解析
# ═══════════════════════════════════════════════════════

# 匹配 steer.log 中的消息行开头: [HH:MM:SS] ← 或 [HH:MM:SS] →
_MSG_PATTERN = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\] ([←→]) (.*)$")


@dataclass
class ChatMessage:
    role: str  # "user" | "assistant"
    timestamp: str
    text: str
    _html_cache: str = ""

    def to_html(self) -> str:
        if self._html_cache:
            return self._html_cache
        self._html_cache = _render_markdown(self.text, self.role)
        return self._html_cache


def parse_steer_log(content: str) -> list[ChatMessage]:
    """将 steer.log 文本解析为结构化消息列表。"""
    messages: list[ChatMessage] = []
    current: ChatMessage | None = None

    for line in content.split("\n"):
        m = _MSG_PATTERN.match(line)
        if m:
            ts, arrow, text = m.group(1), m.group(2), m.group(3)
            role = "user" if arrow == "←" else "assistant"
            current = ChatMessage(role=role, timestamp=ts, text=text)
            messages.append(current)
        elif current is not None:
            # 多行消息的续行
            if line.strip():
                current.text += "\n" + line

    return messages


# ═══════════════════════════════════════════════════════
# Markdown → HTML 渲染（轻量级）
# ═══════════════════════════════════════════════════════


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _render_inline(text: str) -> str:
    """渲染行内 markdown：bold, italic, inline code, links。"""
    s = _escape_html(text)
    # bold **text** or __text__
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"__(.+?)__", r"<b>\1</b>", s)
    # italic *text* or _text_ (但不匹配 __bold__)
    s = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", s)
    # inline code `text`
    s = re.sub(
        r"`([^`]+)`",
        rf'<span style="background:{_BG_Surface};color:{_TEAL};padding:1px 4px;border-radius:3px;font-family:monospace;font-size:11px">\1</span>',
        s,
    )
    # links [text](url)
    s = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        rf'<span style="color:{_BLUE};text-decoration:underline">\1</span>',
        s,
    )
    return s


def _render_markdown(text: str, role: str) -> str:
    """将 markdown 文本渲染为 HTML（供 QTextEdit 显示）。"""
    lines = text.split("\n")
    html_parts: list[str] = []
    in_code_block = False
    code_lines: list[str] = []

    for line in lines:
        # 代码块处理
        if line.strip().startswith("```"):
            if in_code_block:
                # 结束代码块
                code_content = _escape_html("\n".join(code_lines))
                html_parts.append(
                    f'<pre style="background:{_BG_DARK};color:{_TEXT_DIM};'
                    f"padding:8px 12px;border-radius:6px;border:1px solid {_border};"
                    f'margin:4px 0;font-family:monospace;font-size:11px;line-height:1.4">'
                    f"{code_content}</pre>"
                )
                code_lines = []
                in_code_block = False
            else:
                # 开始代码块
                in_code_block = True
            continue

        if in_code_block:
            code_lines.append(line)
            continue

        stripped = line.strip()

        # 空行
        if not stripped:
            html_parts.append("<br>")
            continue

        # 标题
        if stripped.startswith("# "):
            html_parts.append(
                f'<div style="color:{_TEXT};font-weight:bold;font-size:14px;margin:6px 0 2px 0">'
                f"{_render_inline(stripped[2:])}</div>"
            )
            continue
        if stripped.startswith("## "):
            html_parts.append(
                f'<div style="color:{_TEXT};font-weight:bold;font-size:13px;margin:4px 0 2px 0">'
                f"{_render_inline(stripped[3:])}</div>"
            )
            continue
        if stripped.startswith("### "):
            html_parts.append(
                f'<div style="color:{_TEXT_DIM};font-weight:bold;font-size:12px;margin:3px 0 1px 0">'
                f"{_render_inline(stripped[4:])}</div>"
            )
            continue

        # 分隔线
        if stripped in ("---", "***", "___"):
            html_parts.append(
                f'<div style="border-top:1px solid {_border};margin:6px 0"></div>'
            )
            continue

        # 列表项
        if re.match(r"^[-*]\s+", stripped):
            content = _render_inline(re.sub(r"^[-*]\s+", "", stripped))
            html_parts.append(
                f'<div style="color:{_TEXT};margin:1px 0;padding-left:12px">'
                f'<span style="color:{_MAUVE}">•</span> {content}</div>'
            )
            continue

        # 有序列表
        m_ol = re.match(r"^(\d+)\.\s+(.+)", stripped)
        if m_ol:
            num, content = m_ol.group(1), m_ol.group(2)
            html_parts.append(
                f'<div style="color:{_TEXT};margin:1px 0;padding-left:12px">'
                f'<span style="color:{_MAUVE}">{num}.</span> {_render_inline(content)}</div>'
            )
            continue

        # 表格行（简化处理）
        if stripped.startswith("|") and stripped.endswith("|"):
            # 跳过分隔行 |---|---|
            if re.match(r"^\|[\s\-:|]+\|$", stripped):
                continue
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            cell_html = " &nbsp;│&nbsp; ".join(
                f'<span style="color:{_TEAL}">{_escape_html(c)}</span>' for c in cells
            )
            html_parts.append(
                f'<div style="color:{_TEXT};font-family:monospace;font-size:11px;margin:1px 0;padding:2px 8px;'
                f'background:{_BG_DARK};border-radius:3px">{cell_html}</div>'
            )
            continue

        # 引用
        if stripped.startswith("> "):
            content = _render_inline(stripped[2:])
            html_parts.append(
                f'<div style="color:{_TEXT_DIM};border-left:3px solid {_MAUVE};'
                f'padding-left:8px;margin:2px 0;font-style:italic">{content}</div>'
            )
            continue

        # 普通段落
        html_parts.append(
            f'<div style="color:{_TEXT};margin:1px 0;line-height:1.5">{_render_inline(stripped)}</div>'
        )

    return "\n".join(html_parts)


# ═══════════════════════════════════════════════════════
# 单条消息组件
# ═══════════════════════════════════════════════════════


class ChatMessageWidget(QFrame):
    """单条消息的渲染组件。"""

    def __init__(self, msg: ChatMessage, parent=None):
        super().__init__(parent)
        self._msg = msg
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("background: transparent;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        is_user = self._msg.role == "user"

        # ── 角色图标 ──
        icon = QLabel("✦" if is_user else "◈")
        icon_color = _MAUVE if is_user else _BLUE
        icon.setStyleSheet(
            f"color: {icon_color}; font-size: 14px; font-weight: bold; "
            f"background: transparent; padding-top: 2px;"
        )
        icon.setFixedWidth(20)
        icon.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(icon)

        # ── 消息内容区 ──
        content_widget = QWidget()
        content_widget.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(2)

        # 头部：角色名 + 时间
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)

        role_label = QLabel("You" if is_user else "Agent")
        role_color = _MAUVE if is_user else _BLUE
        role_label.setStyleSheet(
            f"color: {role_color}; font-weight: bold; font-size: 11px; "
            f"background: transparent;"
        )
        header.addWidget(role_label)

        ts_label = QLabel(self._msg.timestamp)
        ts_label.setStyleSheet(
            f"color: {_TEXT_DIM}; font-size: 10px; background: transparent;"
        )
        header.addWidget(ts_label)

        header.addStretch()
        content_layout.addLayout(header)

        # 消息体（markdown 渲染）
        body = QTextEdit()
        body.setReadOnly(True)
        body.setHtml(self._msg.to_html())
        body.setStyleSheet(
            f"QTextEdit {{ background: transparent; color: {_TEXT}; border: none; "
            f"padding: 0; font-size: 12px; selection-background-color: {_BG_Surface2}; }}"
        )
        # 自适应高度
        doc = body.document()
        doc.setTextWidth(500)  # 近似宽度
        body.setMaximumHeight(max(60, int(doc.size().height()) + 16))
        content_layout.addWidget(body)

        layout.addWidget(content_widget, 1)


# ═══════════════════════════════════════════════════════
# 思考 / 工具提示组件
# ═══════════════════════════════════════════════════════


class ThinkingIndicator(QWidget):
    """思考中的动画指示器。"""

    _FRAMES = ["( ◕‿◕)", "( ◕__◕)", "( ◕﹏◕)", "( ◕__◕)"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._frame_idx = 0
        self._setup_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._timer.start(400)

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 4, 8, 4)
        layout.setSpacing(6)

        self._icon = QLabel("◈")
        self._icon.setStyleSheet(
            f"color: {_BLUE}; font-size: 14px; font-weight: bold; background: transparent;"
        )
        self._icon.setFixedWidth(20)
        layout.addWidget(self._icon)

        self._text = QLabel(self._FRAMES[0])
        self._text.setStyleSheet(
            f"color: {_YELLOW}; font-size: 11px; background: transparent; font-style: italic;"
        )
        layout.addWidget(self._text)
        layout.addStretch()

    def _advance(self) -> None:
        self._frame_idx = (self._frame_idx + 1) % len(self._FRAMES)
        self._text.setText(self._FRAMES[self._frame_idx])

    def set_thinking_text(self, text: str) -> None:
        """更新思考提示文本。"""
        if text:
            self._text.setText(f"思考中... {text}")
        else:
            self._text.setText(self._FRAMES[self._frame_idx])


class ToolIndicator(QWidget):
    """工具执行中的提示组件。"""

    def __init__(self, tool_name: str = "", parent=None):
        super().__init__(parent)
        self._tool_name = tool_name
        self._elapsed_start = time.time()
        self._setup_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_elapsed)
        self._timer.start(1000)

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 2, 8, 2)
        layout.setSpacing(6)

        self._icon = QLabel("⚙")
        self._icon.setStyleSheet(
            f"color: {_PEACH}; font-size: 12px; background: transparent;"
        )
        self._icon.setFixedWidth(20)
        layout.addWidget(self._icon)

        label = f"执行中: {self._tool_name}" if self._tool_name else "执行中..."
        self._text = QLabel(label)
        self._text.setStyleSheet(
            f"color: {_PEACH}; font-size: 11px; background: transparent;"
        )
        layout.addWidget(self._text)

        self._time_label = QLabel("0s")
        self._time_label.setStyleSheet(
            f"color: {_TEXT_DIM}; font-size: 10px; background: transparent;"
        )
        layout.addWidget(self._time_label)
        layout.addStretch()

    def _update_elapsed(self) -> None:
        elapsed = time.time() - self._elapsed_start
        if elapsed < 10:
            self._time_label.setText(f"{elapsed:.1f}s")
        else:
            self._time_label.setText(f"{elapsed:.0f}s")

    def set_tool_name(self, name: str) -> None:
        self._tool_name = name
        label = f"执行中: {name}" if name else "执行中..."
        self._text.setText(label)


# ═══════════════════════════════════════════════════════
# 主面板
# ═══════════════════════════════════════════════════════

# Session 状态图标映射
_SESSION_ICONS = {
    "running": "●",
    "idle": "○",
    "done": "✓",
    "failed": "✗",
    "killed": "⊘",
    "interrupted": "◉",
    "waiting_input": "💬",
    "waiting_approval": "🔒",
    "": "○",
}

_PLACEHOLDER_KEY = "placeholder"
_PLUS_KEY = "plus"


def _session_icon(state: str) -> str:
    return _SESSION_ICONS.get(state, "○")


def _list_sessions_for_task(task_uri: str) -> list[dict]:
    agents = list_agents()
    return [a.to_dict() for a in agents if a.task_id == task_uri]


def _spawn_agent(task_uri: str, message: str) -> str | None:
    import socket as _sock

    agentd_sock = str(Path.home() / ".diy" / "agentd.sock")
    cmd = f"spawn --task={task_uri} --message={message}\n"
    try:
        s = _sock.socket(_sock.AF_UNIX, _sock.SOCK_STREAM)
        s.settimeout(5.0)
        s.connect(agentd_sock)
        s.sendall(cmd.encode("utf-8"))
        s.shutdown(_sock.SHUT_WR)
        buf = b""
        while True:
            data = s.recv(4096)
            if not data:
                break
            buf += data
        s.close()
        resp = buf.decode("utf-8").strip()
        _logger.info("[agent] 启动 session: %s → %s", task_uri, resp)
        return resp
    except Exception as exc:
        _logger.error("[agent] 启动失败: %s", exc)
        return None


class AgentChatPanel(QWidget):
    """Agent 对话面板 —— 模仿 Hermes TUI 的消息渲染风格。"""

    title_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._task_uri: str | None = None
        self._sessions: list[dict] = []
        self._selected_idx: int | None = None
        self._placeholder_row: int | None = None
        self._last_steer_content: str = ""
        self._message_widgets: list[ChatMessageWidget] = []
        self._thinking_indicator: ThinkingIndicator | None = None
        self._auto_scroll = True
        self._streaming_text: str = ""

        self._setup_ui()
        self._setup_timers()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Session 列表 ──
        self._session_list = QListWidget()
        self._session_list.setFrameShape(QFrame.Shape.NoFrame)
        self._session_list.setMaximumHeight(100)
        self._session_list.setMinimumHeight(50)
        self._session_list.setStyleSheet(
            f"QListWidget {{ background: {_BG_DARK}; border-bottom: 1px solid {_border}; }}"
            f"QListWidget::item {{ padding: 3px 8px; color: {_TEXT}; font-size: 11px; }}"
            f"QListWidget::item:selected {{ background: {_BG_Surface}; border-radius: 4px; }}"
        )
        self._session_list.currentRowChanged.connect(self._on_session_selected)
        layout.addWidget(self._session_list)

        # ── 消息区（ScrollArea 包裹） ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            f"QScrollArea {{ background: {_BG}; border: none; }}"
            f"QScrollBar:vertical {{ background: {_BG_DARK}; width: 6px; }}"
            f"QScrollBar::handle:vertical {{ background: {_surface0}; border-radius: 3px; min-height: 20px; }}"
            f"QScrollBar::handle:vertical:hover {{ background: {_surface1}; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
        )
        scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)

        self._messages_container = QWidget()
        self._messages_container.setStyleSheet(f"background: {_BG};")
        self._messages_layout = QVBoxLayout(self._messages_container)
        self._messages_layout.setContentsMargins(0, 4, 0, 4)
        self._messages_layout.setSpacing(2)
        self._messages_layout.addStretch()  # 底部弹簧

        scroll.setWidget(self._messages_container)
        self._scroll_area = scroll
        layout.addWidget(scroll, 1)

        # ── 底部输入区 ──
        bottom = QWidget()
        bottom.setStyleSheet(
            f"background: {_BG_DARK}; border-top: 1px solid {_border};"
        )
        bottom_lay = QVBoxLayout(bottom)
        bottom_lay.setContentsMargins(8, 6, 8, 6)
        bottom_lay.setSpacing(4)

        input_row = QHBoxLayout()
        input_row.setSpacing(6)

        self._input = QLineEdit()
        self._input.setPlaceholderText("输入消息开始新对话...")
        self._input.returnPressed.connect(self._send)
        self._input.setStyleSheet(
            f"QLineEdit {{ background: {_BG_Surface}; color: {_TEXT}; "
            f"border: 1px solid {_BG_Surface2}; border-radius: 6px; "
            f"padding: 6px 10px; font-size: 12px; }}"
            f"QLineEdit:focus {{ border-color: {_MAUVE}; }}"
        )
        input_row.addWidget(self._input)

        self._send_btn = QPushButton("发送")
        self._send_btn.setFixedHeight(30)
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.setStyleSheet(
            f"QPushButton {{ background: {_MAUVE}; color: {_BG_DARK}; border: none; "
            f"border-radius: 6px; padding: 2px 14px; font-size: 11px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: {_BLUE}; }}"
            f"QPushButton:pressed {{ background: {_surface0}; }}"
        )
        self._send_btn.clicked.connect(self._send)
        input_row.addWidget(self._send_btn)

        bottom_lay.addLayout(input_row)
        layout.addWidget(bottom)

    def _setup_timers(self) -> None:
        # Session 列表刷新（3s）
        self._session_timer = QTimer(self)
        self._session_timer.timeout.connect(self._refresh_sessions)
        self._session_timer.start(3000)

        # Steer.log 轮询（800ms，模拟流式）
        self._steer_timer = QTimer(self)
        self._steer_timer.timeout.connect(self._poll_steer_log)
        self._steer_timer.start(800)

    # ═══════════════════════════════════════════════════
    # 滚动控制
    # ═══════════════════════════════════════════════════

    def _on_scroll(self, value: int) -> None:
        sb = self._scroll_area.verticalScrollBar()
        # 接近底部时开启自动滚动
        self._auto_scroll = value >= sb.maximum() - 30

    def _scroll_to_bottom(self) -> None:
        if self._auto_scroll:
            sb = self._scroll_area.verticalScrollBar()
            sb.setValue(sb.maximum())

    # ═══════════════════════════════════════════════════
    # Steer.log 轮询 + 增量渲染
    # ═══════════════════════════════════════════════════

    def _poll_steer_log(self) -> None:
        """轮询 steer.log，增量添加新消息。"""
        if not self._task_uri:
            return

        content = steer_read(self._task_uri)
        if content == self._last_steer_content:
            return  # 无变化

        self._last_steer_content = content
        messages = parse_steer_log(content)
        self._render_messages_incremental(messages)

    def _render_messages_incremental(self, messages: list[ChatMessage]) -> None:
        """增量渲染：只添加新消息，不重建已有消息。"""
        existing_count = len(self._message_widgets)

        if existing_count == 0:
            # 全量渲染
            for msg in messages:
                self._add_message_widget(msg)
        else:
            # 增量添加
            for msg in messages[existing_count:]:
                self._add_message_widget(msg)

        self._scroll_to_bottom()

    def _add_message_widget(self, msg: ChatMessage) -> None:
        """在消息区添加一条消息组件。"""
        widget = ChatMessageWidget(msg)
        self._message_widgets.append(widget)
        # 插入到 stretch 之前
        self._messages_layout.insertWidget(self._messages_layout.count() - 1, widget)

    # ═══════════════════════════════════════════════════
    # 思考/工具指示器
    # ═══════════════════════════════════════════════════

    def _show_thinking(self) -> None:
        if self._thinking_indicator is not None:
            return
        self._thinking_indicator = ThinkingIndicator()
        self._messages_layout.insertWidget(
            self._messages_layout.count() - 1, self._thinking_indicator
        )
        self._scroll_to_bottom()

    def _hide_thinking(self) -> None:
        if self._thinking_indicator is None:
            return
        self._messages_layout.removeWidget(self._thinking_indicator)
        self._thinking_indicator.deleteLater()
        self._thinking_indicator = None

    def _show_tool_indicator(self, tool_name: str = "") -> None:
        indicator = ToolIndicator(tool_name)
        self._messages_layout.insertWidget(self._messages_layout.count() - 1, indicator)
        self._scroll_to_bottom()
        # 3 秒后自动移除
        QTimer.singleShot(3000, lambda: self._remove_tool_indicator(indicator))

    def _remove_tool_indicator(self, indicator: ToolIndicator) -> None:
        self._messages_layout.removeWidget(indicator)
        indicator.deleteLater()

    # ═══════════════════════════════════════════════════
    # Session 列表
    # ═══════════════════════════════════════════════════

    def _rebuild_list(self, sessions: list[dict]) -> None:
        self._session_list.blockSignals(True)
        self._session_list.clear()

        for s in sessions:
            icon = _session_icon(s.get("state", ""))
            sid = s.get("agent_id", s.get("id", "?"))
            item = QListWidgetItem(f"{icon} {sid}")
            item.setData(Qt.ItemDataRole.UserRole, s)
            item.setToolTip(s.get("state", ""))
            self._session_list.addItem(item)

        plus_item = QListWidgetItem("[+ 新会话]")
        plus_item.setData(Qt.ItemDataRole.UserRole, _PLUS_KEY)
        plus_item.setForeground(Qt.GlobalColor.gray)
        plus_item.setToolTip("点击后可输入新消息创建会话")
        self._session_list.addItem(plus_item)

        self._session_list.blockSignals(False)

    def _add_placeholder(self) -> None:
        if self._placeholder_row is not None:
            return
        item = QListWidgetItem("⏳ 新会话...")
        item.setData(Qt.ItemDataRole.UserRole, _PLACEHOLDER_KEY)
        item.setForeground(Qt.GlobalColor.yellow)
        plus_row = self._session_list.count() - 1
        self._session_list.blockSignals(True)
        self._session_list.insertItem(plus_row, item)
        self._session_list.blockSignals(False)
        self._placeholder_row = plus_row

    def _remove_placeholder(self) -> None:
        if self._placeholder_row is None:
            return
        row = self._placeholder_row
        self._placeholder_row = None
        if 0 <= row < self._session_list.count():
            item = self._session_list.item(row)
            if item and item.data(Qt.ItemDataRole.UserRole) == _PLACEHOLDER_KEY:
                self._session_list.blockSignals(True)
                self._session_list.takeItem(row)
                self._session_list.blockSignals(False)

    def _refresh_sessions(self) -> None:
        if self._task_uri is None:
            return

        sessions = _list_sessions_for_task(self._task_uri)
        if sessions == self._sessions:
            return

        self._remove_placeholder()
        self._sessions = sessions
        self._rebuild_list(sessions)

        has_active = any(s.get("state") == "running" for s in sessions)

        if not sessions:
            self._update_mode("idle")
        elif has_active:
            active_idx = next(
                i for i, s in enumerate(sessions) if s.get("state") == "running"
            )
            self._session_list.setCurrentRow(active_idx)
            self._update_mode("active")
            self._show_thinking()
        else:
            self._update_mode("idle")
            self._hide_thinking()
            if sessions:
                self._session_list.setCurrentRow(len(sessions) - 1)

    def _on_session_selected(self, row: int) -> None:
        if 0 <= row < self._session_list.count():
            item = self._session_list.item(row)
            if item and item.data(Qt.ItemDataRole.UserRole) == _PLUS_KEY:
                self._clear_messages()
                self._input.setFocus()
                self._input.setPlaceholderText("输入消息开始新对话...")
                return

        self._selected_idx = row
        if row < 0 or row >= len(self._sessions):
            return

        # 切换 session 时重新加载消息
        self._reload_messages()

    def _reload_messages(self) -> None:
        """重新加载当前 task 的所有消息。"""
        if not self._task_uri:
            return

        content = steer_read(self._task_uri)
        self._last_steer_content = content
        messages = parse_steer_log(content)

        self._clear_messages()
        for msg in messages:
            self._add_message_widget(msg)
        self._scroll_to_bottom()

    def _clear_messages(self) -> None:
        """清空所有消息组件。"""
        for w in self._message_widgets:
            self._messages_layout.removeWidget(w)
            w.deleteLater()
        self._message_widgets.clear()
        self._hide_thinking()

    # ═══════════════════════════════════════════════════
    # 模式切换
    # ═══════════════════════════════════════════════════

    def _update_mode(self, mode: str) -> None:
        if mode == "active":
            self._input.setPlaceholderText("输入消息...")
        else:
            self._input.setPlaceholderText("输入新消息创建新对话...")

    # ═══════════════════════════════════════════════════
    # 公开接口
    # ═══════════════════════════════════════════════════

    def set_task(self, uri: str) -> None:
        self._task_uri = uri
        self.title_changed.emit(f"Agent — {uri}")
        self._placeholder_row = None
        self._clear_messages()
        self._reload_messages()
        self._refresh_sessions()

        # 自动选中最后 session
        count = self._session_list.count()
        if count > 0:
            last = count - 1
            item = self._session_list.item(last)
            if item and item.data(Qt.ItemDataRole.UserRole) == _PLUS_KEY:
                last -= 1
            if last >= 0:
                self._session_list.setCurrentRow(last)

    def set_compact(self, compact: bool) -> None:
        if compact:
            self._session_list.setMaximumHeight(100)
            self._session_list.setMinimumHeight(50)

    def send_text(self, text: str) -> None:
        self._send_text(text)

    # ═══════════════════════════════════════════════════
    # 发送消息
    # ═══════════════════════════════════════════════════

    def _send_text(self, text: str) -> None:
        if not text or self._task_uri is None:
            return

        sessions = self._sessions
        has_active = any(s.get("state") == "running" for s in sessions)

        from datetime import datetime

        ts = datetime.now().strftime("%H:%M:%S")

        if not has_active:
            # 无活跃 session → 即时显示用户消息 + 思考指示 + 后台 spawn
            self._add_message_widget(ChatMessage(role="user", timestamp=ts, text=text))
            self._show_thinking()
            self._add_placeholder()
            steer_send(self._task_uri, text)
            self._input.clear()

            import threading

            threading.Thread(
                target=_spawn_agent,
                args=(self._task_uri, text),
                daemon=True,
            ).start()
        else:
            # 有活跃 → 直接发
            steer_send(self._task_uri, text)
            self._add_message_widget(ChatMessage(role="user", timestamp=ts, text=text))
            self._input.clear()
            self._show_thinking()

        self._auto_scroll = True
        self._scroll_to_bottom()
        QTimer.singleShot(1500, self._refresh_sessions)

    def _send(self) -> None:
        text = self._input.text().strip()
        self._send_text(text)

    # ═══════════════════════════════════════════════════
    # Probe 接口
    # ═══════════════════════════════════════════════════

    def ui_state(self) -> dict:
        sessions_info = []
        for s in self._sessions:
            entry = {
                "id": s.get("agent_id", s.get("id", "?")),
                "state": s.get("state", ""),
            }
            if s.get("task_id"):
                entry["task"] = s["task_id"]
            sessions_info.append(entry)

        has_active = any(s.get("state") == "running" for s in self._sessions)
        mode = "active" if has_active else "idle"

        return {
            "task_uri": self._task_uri,
            "mode": mode,
            "session_count": len(self._sessions),
            "sessions": sessions_info,
            "selected_idx": self._selected_idx,
            "has_placeholder": self._placeholder_row is not None,
            "input_text": self._input.text(),
            "message_count": len(self._message_widgets),
        }

    def ui_chat_log(self) -> str:
        """探针用：当前对话文本。"""
        return self._last_steer_content
