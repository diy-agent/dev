"""ActivityBar — VSCode 风格左侧活动栏。

垂直按钮条，每个按钮对应一个视图区域:
  ─────────────────
  📁  主侧边栏（任务树）
  💬  副侧边栏（Agent 通信）
  📋  面板（日志/输出）
  ─────────────────

点击切换对应 dock 的显隐，按钮高亮状态跟 dock 可见性同步。
"""

from __future__ import annotations

from PySide6.QtCore import Qt  # type: ignore[import-untyped]
from PySide6.QtWidgets import (  # type: ignore[import-untyped]
    QHBoxLayout,
    QToolButton,
    QToolBar,
    QWidget,
)


class ActivityBar(QToolBar):
    """左侧活动栏。"""

    def __init__(self, parent=None):
        super().__init__("活动", parent)

        from PySide6.QtCore import QSize  # type: ignore[import-untyped]

        self.setMovable(False)
        self.setOrientation(Qt.Orientation.Vertical)
        self.setIconSize(QSize(24, 24))
        self.setFixedWidth(48)

        self.setStyleSheet("""
            QToolBar {
                background: #181825;
                border: none;
                spacing: 2px;
                padding: 4px 0;
            }
        """)

        # 每个按钮: (label, icon_text, tooltip, dock_ref_fn)
        # dock_ref_fn 在 MainWindow 中设置
        self._buttons: list[QToolButton] = []
        self._docks: list[QWidget | None] = [None, None, None]

        self._add_button("📁", "任务树", 0)
        self._add_separator()
        self._add_button("💬", "Agent 通信", 1)
        self._add_separator()
        self._add_button("📋", "输出", 2)

        # tight top margin
        self.layout().setContentsMargins(0, 4, 0, 0)

    def _add_button(self, icon_text: str, tooltip: str, idx: int) -> None:
        btn = QToolButton(self)
        btn.setText(icon_text)
        btn.setToolTip(tooltip)
        btn.setCheckable(True)
        btn.setChecked(False)
        btn.setFixedSize(40, 40)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda: self._toggle(idx))
        btn.setStyleSheet("""
            QToolButton {
                font-size: 18px;
                background: transparent;
                border: none;
                border-radius: 6px;
                color: #6c7086;
            }
            QToolButton:hover {
                background: #313244;
                color: #cdd6f4;
            }
            QToolButton:checked {
                background: #313244;
                color: #89b4fa;
                border-left: 3px solid #89b4fa;
                border-radius: 0 6px 6px 0;
            }
        """)
        self.addWidget(btn)
        self._buttons.append(btn)

    def _add_separator(self) -> None:
        sep = QWidget()
        sep.setFixedSize(24, 1)
        sep.setStyleSheet("background: #313244; margin: 4px 8px;")
        # wrap in a container to centre the line
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(sep)
        self.addWidget(container)

    def _toggle(self, idx: int) -> None:
        btns = self._buttons
        dock = self._docks[idx]
        if dock is None:
            return
        # Toggle the dock visibility
        dock.setVisible(not dock.isVisible())

    def set_dock(self, idx: int, dock: QWidget) -> None:
        """关联 dock 控件并同步初始状态。"""
        self._docks[idx] = dock
        dock.visibilityChanged.connect(lambda visible, i=idx: self._sync_btn(i, visible))

    def _sync_btn(self, idx: int, visible: bool) -> None:
        if idx < len(self._buttons):
            self._buttons[idx].setChecked(visible)
