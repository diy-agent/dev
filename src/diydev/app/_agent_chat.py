"""Agent 对话面板：session 列表 + 聊天区。

设计原则：
- 输入框始终可用，placeholder 随状态变化
- 无活跃 session 时输入即创建新 session（即时反馈）
- session 列表底部固定 [+] 入口
- 只有 active / idle 两态，无复杂状态机
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal  # type: ignore[import-untyped]
from PySide6.QtWidgets import (  # type: ignore[import-untyped]
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from diydev.app._app_log import logger as _logger
from diydev.app.agent_bridge import list_agents, steer_read, steer_send

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

# 占位 item 的 UserRole data key
_PLACEHOLDER_KEY = "placeholder"
_PLUS_KEY = "plus"


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
        _logger.info("[agent] 启动 session: %s → %s", task_uri, resp)
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
        self._placeholder_row: int | None = None  # ⏳ 占位行号

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

        # ── 底部操作区（始终可见） ──
        bottom = QWidget()
        bottom_lay = QVBoxLayout(bottom)
        bottom_lay.setContentsMargins(4, 2, 4, 4)
        bottom_lay.setSpacing(4)

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
        self._update_mode("idle")

    # ── 模式切换 ──

    def _update_mode(self, mode: str) -> None:
        """切换模式：active（有活跃）/ idle（无活跃）。输入框始终可见。"""
        if mode == "active":
            self._input.setPlaceholderText("输入消息...")
        else:
            self._input.setPlaceholderText("输入新消息创建新对话...")

    # ── 公开接口 ──

    def set_task(self, uri: str) -> None:
        self._task_uri = uri
        self.title_changed.emit(f"Agent — {uri}")
        self._placeholder_row = None
        self._refresh_sessions()
        # 自动选中最后 session
        count = self._session_list.count()
        if count > 0:
            # 跳过 [+] 固定 item（在最底部）
            last = count - 1
            item = self._session_list.item(last)
            if item and item.data(Qt.ItemDataRole.UserRole) == _PLUS_KEY:
                last -= 1
            if last >= 0:
                self._session_list.setCurrentRow(last)

    def set_compact(self, compact: bool) -> None:
        if compact:
            self._session_list.setMaximumHeight(120)
            self._session_list.setMinimumHeight(60)

    def send_text(self, text: str) -> None:
        """编程发送文本（外部调用，如右键启动 agent）。"""
        self._send_text(text)

    # ── Session 列表 ──

    def _rebuild_list(self, sessions: list[dict]) -> None:
        """重建 session 列表（不含 [+] 固定 item）。"""
        self._session_list.blockSignals(True)
        self._session_list.clear()

        for _i, s in enumerate(sessions):
            icon = _session_icon(s.get("state", ""))
            sid = s.get("agent_id", s.get("id", "?"))
            item = QListWidgetItem(f"{icon} {sid}")
            item.setData(Qt.ItemDataRole.UserRole, s)
            item.setToolTip(s.get("state", ""))
            self._session_list.addItem(item)

        # 固定 [+] item 在最底部
        plus_item = QListWidgetItem("[+ 新会话]")
        plus_item.setData(Qt.ItemDataRole.UserRole, _PLUS_KEY)
        plus_item.setForeground(Qt.GlobalColor.gray)
        plus_item.setToolTip("点击后可输入新消息创建会话")
        self._session_list.addItem(plus_item)

        self._session_list.blockSignals(False)

    def _add_placeholder(self) -> None:
        """即时添加 ⏳ 占位 item（用户按 Enter 后立即显示）。"""
        if self._placeholder_row is not None:
            return  # 已有占位
        item = QListWidgetItem("⏳ 新会话...")
        item.setData(Qt.ItemDataRole.UserRole, _PLACEHOLDER_KEY)
        item.setForeground(Qt.GlobalColor.yellow)
        # 插入到 [+] item 之前
        plus_row = self._session_list.count() - 1
        self._session_list.blockSignals(True)
        self._session_list.insertItem(plus_row, item)
        self._session_list.blockSignals(False)
        self._placeholder_row = plus_row  # 插入后的位置

    def _remove_placeholder(self) -> None:
        """移除 ⏳ 占位 item。"""
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
        """刷新 session 列表并更新 UI 模式。"""
        if self._task_uri is None:
            return

        sessions = _list_sessions_for_task(self._task_uri)
        if sessions == self._sessions:
            return  # 无变化

        # agent 数据变了，占位 item 已无意义
        self._remove_placeholder()

        self._sessions = sessions

        self._rebuild_list(sessions)

        # 决定模式
        has_active = any(s.get("state") == "running" for s in sessions)

        if not sessions:
            self._update_mode("idle")
            self._log.clear()
        elif has_active:
            # 有活跃 session → 自动选中第一个活跃的
            active_idx = next(
                i for i, s in enumerate(sessions) if s.get("state") == "running"
            )
            self._session_list.setCurrentRow(active_idx)
            self._update_mode("active")
        else:
            # 只有历史 session → 选最后一个
            self._update_mode("idle")
            if sessions:
                self._session_list.setCurrentRow(len(sessions) - 1)

    def _on_session_selected(self, row: int) -> None:
        """选中 session → 加载对话。"""
        # [+] item 被点击 → 清空 log，聚焦输入框
        if 0 <= row < self._session_list.count():
            item = self._session_list.item(row)
            if item and item.data(Qt.ItemDataRole.UserRole) == _PLUS_KEY:
                self._log.clear()
                self._input.setFocus()
                self._input.setPlaceholderText("输入消息开始新对话...")
                return

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
            self._update_mode("idle")

    # ── 发送 / 新对话 ──

    def _send_text(self, text: str) -> None:
        if not text or self._task_uri is None:
            return

        sessions = self._sessions
        has_active = any(s.get("state") == "running" for s in sessions)
        from datetime import datetime

        ts = datetime.now().strftime("%H:%M:%S")
        user_line = f"[{ts}] ← {text}"

        if not has_active:
            # 无活跃 session → 即时添加 ⏳ 占位 + 后台 spawn
            self._add_placeholder()
            steer_send(self._task_uri, text)
            self._log.append(user_line)
            self._input.clear()
            # 后台 spawn（不阻塞 UI 线程）
            import threading

            threading.Thread(
                target=_spawn_agent,
                args=(self._task_uri, text),
                daemon=True,
            ).start()
        else:
            # 有活跃 → 直接发
            steer_send(self._task_uri, text)
            self._log.append(user_line)
            self._input.clear()

        QTimer.singleShot(1500, self._refresh_sessions)

    def _send(self) -> None:
        text = self._input.text().strip()
        self._send_text(text)

    # ── Probe 接口 ──

    def ui_state(self) -> dict:
        """探针用：当前面板状态转 dict。"""
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
        }

    def ui_chat_log(self) -> str:
        """探针用：当前对话文本。"""
        return self._log.toPlainText()
