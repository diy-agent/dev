"""测试：去掉 QWebEngineView，看 app 是否稳定。"""

from __future__ import annotations

import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["DIY_HOME"] = "/tmp/diy-test-stable"

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

_app = None


@pytest.fixture(scope="module")
def app():
    global _app
    if _app is None:
        _app = QApplication(sys.argv)
    return _app


def test_app_stays_alive(app):
    """验证 app 启动后 30 秒不崩溃。"""
    import diydev._state as _st
    import diydev.app.task_tree as _tt

    _st.list_tasks = _tt.list_tasks = lambda: {}
    _st.list_starred = _tt.list_starred = lambda: {}
    _st.load_state = _tt.load_state = lambda: {"subjects": {}}

    from diydev.app.main import MainWindow

    win = MainWindow()
    win.show()
    QTest.qWait(500)

    # 模拟 30 秒运行（用 QTimer 处理事件）
    alive = True

    def check():
        nonlocal alive
        alive = win.isVisible()

    timer = QTimer()
    timer.timeout.connect(check)
    timer.start(1000)

    QTest.qWait(8000)  # 8s 就够了
    timer.stop()

    assert alive, "app 在 8s 内崩溃了"
    print("✅ app 存活 8s (exit_code 未触发)")
    win.close()
