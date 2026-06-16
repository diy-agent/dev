"""LogPanel — VSCode Output Panel 风格的日志视图。

用法:
  panel = LogPanel()
  some_tab_widget.addTab(panel, "输出")
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt  # type: ignore[import-untyped]
from PySide6.QtGui import QFont, QTextCursor  # type: ignore[import-untyped]
from PySide6.QtWidgets import (  # type: ignore[import-untyped]
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from diydev.app._app_log import get_qt_handler, logger

_LOG_LEVELS = [
    ("ALL", 0),
    ("ERROR", 40),
    ("WARN ", 30),
    ("INFO ", 20),
    ("DEBUG", 10),
]

_CLASSIC = QFont("Menlo", 11)


class LogPanel(QWidget):
    """日志输出视图，实时显示 app 日志，可过滤级别。"""

    MAX_LINES = 5000

    def __init__(self, parent=None):
        super().__init__(parent)

        # ── 控件 ──
        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setFont(_CLASSIC)
        self._text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._text.setMaximumBlockCount(self.MAX_LINES)
        self._text.setStyleSheet("""
            QPlainTextEdit {
                background: #1e1e2e;
                color: #cdd6f4;
                selection-background-color: #45475a;
            }
        """)

        # 过滤
        self._filter = QComboBox()
        for label, lvl in _LOG_LEVELS:
            self._filter.addItem(label, lvl)
        self._filter.currentIndexChanged.connect(self._apply_filter)

        # 自动滚
        self._auto_scroll = QCheckBox("自动滚动")
        self._auto_scroll.setChecked(True)

        # 清空
        clear_btn = QPushButton("清空")
        clear_btn.clicked.connect(self._text.clear)

        # ── Toolbar ──
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(4, 2, 4, 2)
        toolbar.addWidget(self._filter)
        toolbar.addWidget(self._auto_scroll)
        toolbar.addStretch()
        toolbar.addWidget(clear_btn)

        # ── 布局 ──
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(toolbar)
        layout.addWidget(self._text)

        # ── 连接 QtLogHandler → GUI（回放缓存 + 实时接收） ──
        qt_handler = get_qt_handler()
        if qt_handler:
            qt_handler.connect_listener(self._on_record)

    # ── slots ──

    def _on_record(self, _name: str, levelno: int, message: str) -> None:
        """从 QtLogHandler 接收日志记录（跨线程安全）。"""
        min_level = self._filter.currentData()
        if min_level and levelno < min_level:
            return

        color = _level_color(levelno)
        html = f'<pre style="color:{color};margin:0;font-family:Menlo;font-size:11px;">{_esc_html(message)}</pre>'
        self._text.appendHtml(html)

        if self._auto_scroll.isChecked():
            cursor = self._text.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self._text.setTextCursor(cursor)

    def _apply_filter(self) -> None:
        min_level = self._filter.currentData()
        logger.debug("过滤切换至 level=%s", min_level)

    def append_log(self, message: str) -> None:
        """手动追加一条日志（供外部直接调用）。"""
        self._on_record("", 20, message)


def _level_color(levelno: int) -> str:
    if levelno >= logging.ERROR:
        return "#f38ba8"
    if levelno >= logging.WARNING:
        return "#fab387"
    if levelno >= logging.INFO:
        return "#a6e3a1"
    return "#6c7086"


def _esc_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
