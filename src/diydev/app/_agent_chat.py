"""Agent 对话面板：session 列表 + 聊天区。

流程：
- 无 session      → 显示"新对话"按钮 + 空 input（首条消息即创建 session）
- 有活跃 session → 自动选中，input 可发消息
- 只有历史 session → 列表 + "新对话"按钮
- 点击历史 session → 只读查看对话
- 双击 session    → （未来：恢复对话）
"""

from __future__ import annotations

import time
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
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from diydev.app._app_log import logger as _logger
from diydev.app.agent_bridge import steer_read, steer_send, list_agents

# ── 状态图标映射 ──

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


def _session_icon(state: str) -> str:
    return _SESSION_ICONS.get(state, "○")


def _list_sessions_for_task(task_uri: str) -> list[dict]:
    """列出某个 task 的所有 agent session。"""
    agents = list_agents()
    return [a.to_dict() for a in agents if a.task_id == task_uri]


def _spawn_agent(task_uri: str, message: str) -> str | None:
    """启动一个新 agent session。通过 agentd socket 发送 spawn 命令。"""
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
        _logger.info("[agent] 启动 session: %s for %s → %s", task_uri, task_uri, resp)
        return resp
    except Exception as exc:
        _logger.error("[agent] 启动失败: %s", exc)
        return None


class AgentChatPanel(QWidget):
    """Agent 对话面板，嵌入任务详情右侧栏。"""

    title_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._task_uri: str | None = None
        self._sessions: list[dict] = []
        self._selected_idx: int | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # ── Session 列表 ──
        self._session_list = QListWidget()
        self._session_list.setFrameShape(QFrame.Shape.NoFrame)
        self._session_list.setStyleSheet(
            "QListWidget { background: transparent; border: none; }"
            "QListWidget::item { padding: 4px 8px; color: #cdd6f4; font-size: 12px; }"
            "QListWidget::item:selected { background: #45475a; border-radius: 4px; }"
        )
        self._session_list.currentRowChanged.connect(self._on_session_selected)
        layout.addWidget(self._session_list)

        # ── 聊天区 ──
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setStyleSheet(
            "QTextEdit { background: #1e1e2e; color: #cdd6f4; border: none;"
            " border-top: 1px solid #313244; padding: 6px; font-size: 12px; }"
        )
        layout.addWidget(self._log, 1)

        # ── 底部操作区 ──
        bottom = QWidget()
        bottom_lay = QVBoxLayout(bottom)
        bottom_lay.setContentsMargins(4, 2, 4, 4)
        bottom_lay.setSpacing(4)

        # 新对话按钮（无活跃 session 时显示）
        self._new_btn = QPushButton("➕ 新对话")
        self._new_btn.setFixedHeight(28)
        self._new_btn.setStyleSheet(
            "QPushButton { background: #89b4fa; color: #1e1e2e; border: none;"
            " border-radius: 4px; padding: 4px 12px; font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { background: #74c7ec; }"
        )
        self._new_btn.clicked.connect(self._start_new_session)
        bottom_lay.addWidget(self._new_btn)

        # 输入行
        input_row = QHBoxLayout()
        input_row.setSpacing(4)

        self._input = QLineEdit()
        self._input.setPlaceholderText("输入消息开始新对话...")
        self._input.returnPressed.connect(self._send)
        self._input.setStyleSheet(
            "QLineEdit { background: #313244; color: #cdd6f4; border: 1px solid #45475a;"
            " border-radius: 4px; padding: 4px 8px; font-size: 12px; }"
        )
        input_row.addWidget(self._input)

        self._send_btn = QPushButton("发送")
        self._send_btn.setFixedHeight(24)
        self._send_btn.setStyleSheet(
            "QPushButton { background: #45475a; color: #cdd6f4; border: none;"
            " border-radius: 4px; padding: 2px 10px; font-size: 11px; }"
            "QPushButton:hover { background: #585b70; }"
        )
        self._send_btn.clicked.connect(self._send)
        input_row.addWidget(self._send_btn)

        bottom_lay.addLayout(input_row)
        layout.addWidget(bottom)

        # ── 定时刷新 ──
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_sessions)
        self._timer.start(3000)

        # ── 初始状态 ──
        self._update_mode("empty")

    # ── 模式切换 ──

    def _update_mode(self, mode: str) -> None:
        """切换底部操作区模式。"""
        if mode == "empty":           # 无 session，可输入首条消息
            self._new_btn.hide()
            self._input.show()
            self._send_btn.show()
            self._input.setPlaceholderText("输入消息开始新对话...")
            self._input.setEnabled(True)
            self._send_btn.setEnabled(True)
        elif mode == "active":        # 有活跃 session，可输入
            self._new_btn.hide()
            self._input.show()
            self._send_btn.show()
            self._input.setPlaceholderText("输入消息...")
            self._input.setEnabled(True)
            self._send_btn.setEnabled(True)
        elif mode == "history":       # 只有历史 session，看对话
            self._new_btn.show()
            self._input.hide()
            self._send_btn.hide()
        elif mode == "history_view":  # 正在查看历史对话
            self._new_btn.show()
            self._input.hide()
            self._send_btn.hide()

    # ── 公开接口 ──

    def set_task(self, uri: str) -> None:
        self._task_uri = uri
        self.title_changed.emit(f"Agent — {uri}")
        self._refresh_sessions()

    def set_compact(self, compact: bool) -> None:
        if compact:
            self._session_list.setMaximumHeight(120)
            self._session_list.setMinimumHeight(60)

    def send_text(self, text: str) -> None:
        """编程发送文本（外部调用，如右键启动 agent）。"""
        self._send_text(text)

    # ── Session 列表 ──

    def _refresh_sessions(self) -> None:
        """刷新 session 列表并更新 UI 模式。"""
        if self._task_uri is None:
            return

        sessions = _list_sessions_for_task(self._task_uri)
        if sessions == self._sessions:
            return  # 无变化

        self._sessions = sessions
        old_row = self._session_list.currentRow()

        self._session_list.blockSignals(True)
        self._session_list.clear()
        for s in sessions:
            icon = _session_icon(s.get("state", ""))
            sid = s.get("agent_id", s.get("id", "?"))
            item = QListWidgetItem(f"{icon} {sid}")
            item.setData(Qt.ItemDataRole.UserRole, s)
            item.setToolTip(s.get("state", ""))
            self._session_list.addItem(item)
        self._session_list.blockSignals(False)

        # 决定模式
        has_active = any(s.get("state") == "running" for s in sessions)

        if not sessions:
            # 无 session → 新对话模式
            self._update_mode("empty")
            self._log.clear()
        elif has_active:
            # 有活跃 session → 自动选中第一个活跃的
            active_idx = next(i for i, s in enumerate(sessions) if s.get("state") == "running")
            self._session_list.setCurrentRow(active_idx)
            self._update_mode("active")
        else:
            # 只有历史 session
            self._update_mode("history")
            # 如果之前已有选中，保留；否则清空 log
            if old_row >= 0 and old_row < self._session_list.count():
                pass  # 保持选中
            else:
                self._log.clear()

    def _on_session_selected(self, row: int) -> None:
        """选中 session → 加载对话。"""
        self._selected_idx = row
        if row < 0 or row >= len(self._sessions):
            return
        s = self._sessions[row]
        state = s.get("state", "")
        is_active = state == "running"

        # 加载对话
        if self._task_uri:
            chat = steer_read(self._task_uri)
            self._log.setPlainText(chat or "(无对话)")

        # 切换模式
        if is_active:
            self._update_mode("active")
        else:
            self._update_mode("history_view")

    # ── 发送 / 新对话 ──

    def _send_text(self, text: str) -> None:
        if not text or self._task_uri is None:
            return

        sessions = self._sessions
        has_active = any(s.get("state") == "running" for s in sessions)

        if not has_active:
            # 无活跃 session → 首条消息创建新 session
            steer_send(self._task_uri, text)
            _spawn_agent(self._task_uri, text)
            self._input.clear()
        else:
            # 有活跃 → 直接发
            steer_send(self._task_uri, text)
            self._input.clear()

        # 立即刷新
        import time as _time
        _time.sleep(0.2)
        self._refresh_sessions()

    def _send(self) -> None:
        text = self._input.text().strip()
        self._send_text(text)

    def _start_new_session(self) -> None:
        """点击"新对话"按钮 → 切换到输入模式。"""
        self._update_mode("empty")
        self._input.show()
        self._send_btn.show()
        self._new_btn.hide()
        self._input.setFocus()
        self._input.setPlaceholderText("输入第一条消息...")
