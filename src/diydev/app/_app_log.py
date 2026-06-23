"""diy 管控台日志基础设施。

三路输出，格式按用途分离:
  1. 文件 → ~/.diy/app.log（JSONL，RotatingFileHandler 5MB×3，可 jq/grep 查询）
  2. stderr → 终端（纯文本，含 [category] 前缀）
  3. Qt Signal → GUI LogPanel（纯文本，可过滤级别 + 来源）

QtLogHandler 自动缓存前 200 条记录，LogPanel 连接时回放。

分类前缀约定（消息首词 [xxx]）:
  [watcher] — 文件系统监控触发刷新
  [timer]   — 定时器触发刷新
  [probe]   — Socket 命令触发刷新
  [health]  — 健康自检
  [main]    — 全量重载
  [panel]   — LogPanel 操作

用法:
  from diydev.app._app_log import setup_app_logger, get_logger, logger

  setup_app_logger()
  logger.info("[watcher] 文件变化 → reload")     # 统一 logger
  sub = get_logger("probe")                       # 子 logger → diy.app.probe
  sub.debug("socket 连接已建立")

文件端查询示例:
  jq 'select(.c == "watcher")' ~/.diy/app.log
  grep '"c":"watcher"' ~/.diy/app.log
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import re
from collections import deque
from pathlib import Path
from diydev._state import diy_home

from PySide6.QtCore import QObject, Signal  # type: ignore[import-untyped]

if __name__ != "__main__":
    from typing import TYPE_CHECKING
    if TYPE_CHECKING:
        from diydev.app._metrics import MetricsStore

__all__ = ["setup_app_logger", "logger", "QtLogHandler", "get_logger"]

# 模块级 logger — logging.getLogger() 在 setup_app_logger 调用前返回安全空 logger
logger: logging.Logger = logging.getLogger("diy.app")

# 所有 handler 共享的格式（含时间戳、logger 名，三路一致）
_SHARED_FMT = logging.Formatter(
    "%(asctime)s [%(levelname)-5s] [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)

# 从消息中提取 [category] 前缀
_RE_CATEGORY = re.compile(r"^\[([\w-]+)\]")


class JsonlFormatter(logging.Formatter):
    """JSONL formatter — 每行一个 JSON 对象，适合 jq/grep 查询。

    字段:
      t — 时间 (HH:MM:SS)
      l — 级别 (DEBUG/INFO/WARNING/ERROR)
      n — logger 名称
      c — 分类前缀（如 watcher/timer/probe）
      m — 消息正文（不含前缀）
    """

    def format(self, record: logging.LogRecord) -> str:
        msg = record.getMessage()
        cat = ""
        body = msg
        m = _RE_CATEGORY.match(msg)
        if m:
            cat = m.group(1)
            body = msg[m.end():].strip()
        return json.dumps(
            {
                "t": self.formatTime(record, "%H:%M:%S"),
                "l": record.levelname,
                "n": record.name,
                "c": cat,
                "m": body,
            },
            ensure_ascii=False,
        )


def get_logger(name: str) -> logging.Logger:
    """创建 diy.app 下的子 logger。

    用法:
        logger = get_logger("main")    → diy.app.main
        logger = get_logger("probe")   → diy.app.probe
        logger.watcher()/info()/debug() 同标准 logging
    """
    return logging.getLogger(f"diy.app.{name}")


class QtLogHandler(logging.Handler):
    """将 LogRecord 通过 Qt Signal 桥接到主线程。

    特性:
    - 缓存前 MAX_BUF 条记录，LogPanel 连接时回放（解决初始化窗口前日志丢失）
    - 所有 handler 使用相同格式（含时间戳）
    - 跨线程安全
    """

    MAX_BUF = 200

    class _Signals(QObject):
        record = Signal(str, int, str)  # logger_name, levelno, formatted_message

    def __init__(self) -> None:
        super().__init__()
        self._buffer: deque[tuple[str, int, str]] = deque(maxlen=self.MAX_BUF)
        self._signals: QtLogHandler._Signals | None = None

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            entry = (record.name, record.levelno, msg)
            self._buffer.append(entry)
            sigs = self._signals
            if sigs is not None:
                sigs.record.emit(*entry)
        except Exception:
            self.handleError(record)

    def connect_listener(self, slot) -> None:
        """创建 QObject 信号桥，连接 slot，并回放缓存。

        必须在创建 QApplication 之后调用。
        """
        sigs = self._Signals()
        sigs.record.connect(slot)
        self._signals = sigs

        # 回放历史记录
        for entry in self._buffer:
            slot(*entry)


# 保存引用以便 LogPanel 连接
_qt_handler: QtLogHandler | None = None


def _install_qt_msg_handler() -> None:
    """拦截 Qt 原生 C++ 消息，路由到 Python logger。

    Qt 消息级别映射:
      QtFatalMsg (4)   → CRITICAL
      QtCriticalMsg (3)→ ERROR
      QtWarningMsg (2) → WARNING
      QtInfoMsg (1)    → INFO
      QtDebugMsg (0)   → DEBUG

    消息前缀 [Qt] 标示来源，三路输出（文件/stderr/LogPanel）一致。
    """
    from PySide6.QtCore import qInstallMessageHandler  # type: ignore[import-untyped]

    _LEVEL_MAP = {4: 50, 3: 40, 2: 30, 1: 20, 0: 10}  # Qt mode → logging levelno

    def handler(mode, context, message):
        py_level = _LEVEL_MAP.get(mode, logging.WARNING)
        logger.log(py_level, "[Qt] %s", message)

    qInstallMessageHandler(handler)


class MetricsLogHandler(logging.Handler):
    """拦截 WARNING/ERROR 日志，按模块分类记 metrics counter。

    setup_app_logger 时注册，MainWindow 初始化后注入 MetricsStore。
    """

    def __init__(self) -> None:
        super().__init__()
        self.setLevel(logging.WARNING)
        self._store: Any | None = None  # MetricsStore | None

    def set_store(self, store: Any) -> None:
        """注入 MetricsStore（MainWindow 初始化后调用）。"""
        self._store = store

    def emit(self, record: logging.LogRecord) -> None:
        if self._store is None:
            return
        try:
            msg = record.getMessage()
            m = _RE_CATEGORY.match(msg)
            category = m.group(1) if m else record.name.rsplit(".", 1)[-1]
            level_name = record.levelname.lower()
            self._store.counter(f"log.{level_name}.{category}", 1)
        except Exception:
            self.handleError(record)


_metrics_handler: MetricsLogHandler | None = None


def get_metrics_handler() -> MetricsLogHandler | None:
    """返回 MetricsLogHandler，供 MainWindow 注入 MetricsStore。"""
    return _metrics_handler


def setup_app_logger(
    level: int = logging.DEBUG,
    file_path: str | None = None,
) -> logging.Logger:
    """初始化 diy.app logger。

    可在 main() 最开头调用，也可在子进程中再次调用（会先清理旧 handler）。
    """
    global _qt_handler, _metrics_handler

    log_path = Path(file_path or (
        diy_home() / "app.log"
    ))
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("diy.app")
    root.setLevel(level)

    # 避免重复添加 handler（多次调用 setup 时）
    root.handlers.clear()

    # ── Qt 原生消息拦截（过滤 keymapper 等噪音） ──
    _install_qt_msg_handler()

    # ── 文件（5MB×3 轮转，JSONL 格式） ──
    fh = logging.handlers.RotatingFileHandler(
        str(log_path),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(JsonlFormatter())
    root.addHandler(fh)

    # ── stderr（终端模式可见） ──
    sh = logging.StreamHandler()
    sh.setLevel(logging.DEBUG)
    sh.setFormatter(_SHARED_FMT)
    root.addHandler(sh)

    # ── Qt Signal（GUI LogPanel） ──
    _qt_handler = QtLogHandler()
    _qt_handler.setLevel(logging.DEBUG)
    _qt_handler.setFormatter(_SHARED_FMT)
    root.addHandler(_qt_handler)

    # ── Metrics（WARNING/ERROR → counter） ──
    _metrics_handler = MetricsLogHandler()
    root.addHandler(_metrics_handler)

    logger.info("日志初始化完成 → %s", log_path)
    return root


def get_qt_handler() -> QtLogHandler | None:
    """返回 QtLogHandler 实例，供 LogPanel 连接 signal。"""
    return _qt_handler
