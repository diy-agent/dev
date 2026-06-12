"""dai 管控台 — Panel GUI app.

Usage:
    uv run python -m diydev.app       # dev mode (autoreload)
    uv run panel serve --dev src/diydev/app.py
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import panel as pn

from ._state import load_state

_STATE_PATH = Path(os.environ.get("DIY_HOME", Path.home() / ".diy")) / "state.yaml"

pn.extension("tabulator", sizing_mode="stretch_width")


def _state_mtime() -> float:
    try:
        return _STATE_PATH.stat().st_mtime
    except OSError:
        return 0.0


_last_mtime = _state_mtime()


def _refresh() -> None:
    global _last_mtime
    mtime = _state_mtime()
    if mtime == _last_mtime:
        return
    _last_mtime = mtime
    data = load_state()
    _subject_tabulator.value = _build_subject_rows(data)
    _task_tabulator.value = _build_task_rows(data)


def _build_subject_rows(data: dict) -> list[dict]:
    rows: list[dict] = []
    for path, info in sorted(data.get("subjects", {}).items()):
        is_git = os.path.isdir(os.path.join(os.path.expanduser(path), ".git"))
        rows.append({
            "path": path,
            "description": info.get("description", ""),
            "is_git": "✓" if is_git else "",
        })
    return rows


def _build_task_rows(data: dict) -> list[dict]:
    rows: list[dict] = []
    for tid_str, info in sorted(data.get("tasks", {}).items(), key=lambda x: int(x[0])):
        rows.append({
            "id": int(tid_str),
            "title": info.get("title", ""),
            "state": info.get("state", ""),
            "subject": info.get("subject", ""),
        })
    return rows


# ── widgets ──

_subject_tabulator = pn.widgets.Tabulator(
    value=_build_subject_rows(load_state()),
    pagination=None,
    sizing_mode="stretch_width",
    height=400,
    formatters={"is_git": {"type": "tickcross"}},
)

_task_tabulator = pn.widgets.Tabulator(
    value=_build_task_rows(load_state()),
    pagination=None,
    sizing_mode="stretch_width",
    height=400,
)

# ── 定时轮询 ──

pn.state.add_periodic_callback(
    _refresh, period=2000,
)


# ── 布局 ──

pn.template.FastListTemplate(
    title="diy 管控台",
    accent="#0072B5",
    main=[
        pn.Row(
            pn.Column(
                "## Subject 树",
                _subject_tabulator,
                sizing_mode="stretch_width",
            ),
            pn.Column(
                "## 任务列表",
                _task_tabulator,
                sizing_mode="stretch_width",
            ),
            sizing_mode="stretch_width",
        ),
    ],
).servable()


if __name__ == "__main__":
    pn.serve(__file__, autoreload=True, port=5006)
