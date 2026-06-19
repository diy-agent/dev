"""轻量内存指标存储，设计参考 OpenTelemetry。

- counter: 单调递增计数（如健康检查次数、命令调用次数）
- gauge: 瞬时值（如 agent 数量、自检通过/失败）
- history: gauge 时间序列，保留最近 1000 条
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any


class MetricsStore:
    """进程内指标存储。"""

    def __init__(self, max_history: int = 1000):
        self._counters: dict[str, int] = {}
        self._gauges: dict[str, float] = {}
        self._histories: dict[str, list[tuple[float, float]]] = {}
        self._max_history = max_history

    # ── 增删改 ──

    def counter(self, name: str, delta: int = 1) -> None:
        """递增计数器。"""
        self._counters[name] = self._counters.get(name, 0) + delta

    def gauge(self, name: str, value: float) -> None:
        """设 gauge 值，同时记录时间序列。"""
        self._gauges[name] = value
        if name not in self._histories:
            self._histories[name] = []
        self._histories[name].append((time.time(), value))
        # 保留最近 N 条
        h = self._histories[name]
        if len(h) > self._max_history:
            self._histories[name] = h[-self._max_history :]

    def snapshot(self) -> dict[str, Any]:
        """返回当前指标快照（可序列化成 YAML/JSON）。"""
        return {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histories": {
                k: [{"t": ts, "v": v} for ts, v in entries[-100:]]
                for k, entries in self._histories.items()
            },
        }

    # ── 快捷读取 ──

    def get_counter(self, name: str, default: int = 0) -> int:
        return self._counters.get(name, default)

    def get_gauge(self, name: str, default: float = 0.0) -> float:
        return self._gauges.get(name, default)

    def get_history(
        self, name: str, default: None = None
    ) -> list[tuple[float, float]] | None:
        return self._histories.get(name, default)

    def format_doctor_section(self) -> str:
        """格式化成 dai doctor 可读的文本。"""
        lines: list[str] = []

        counts: list[str] = []
        for k, v in sorted(self._counters.items()):
            counts.append(f"  {k}: {v}")
        if counts:
            lines.append("📊 计数器:")
            lines.extend(counts)

        gauges: list[str] = []
        for k, v in sorted(self._gauges.items()):
            gauges.append(f"  {k}: {v}")
        if gauges:
            lines.append("📈 瞬时值:")
            lines.extend(gauges)

        return "\n".join(lines) if lines else "（无指标数据）"
