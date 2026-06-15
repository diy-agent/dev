"""diy 管控台 — 纯观察面板。

展示 state.yaml 全部数据：subject 树、任务列表（状态色）、profile、spaces/locks。
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pandas as pd
import panel as pn

pn.extension("tabulator")

from diydev._state import load_state

_STATE_PATH = Path(os.environ.get("DIY_HOME", Path.home() / ".diy")) / "state.yaml"

# ── 状态图标映射 ──
_STATE_ICON = {
    "pending":   "⏳",
    "active":    "🔄",
    "open":      "🔄",
    "done":      "✅",
    "closed":    "✅",
    "cancelled": "❌",
    "blocked":   "🚫",
    "shelved":   "⏸",
    "new":       "🆕",
}

_STATE_ORDER = {"done": 1, "active": 2, "open": 3, "pending": 4, "blocked": 5, "cancelled": 6, "shelved": 7, "new": 8}


# ═══════════════════════════════════════════════════════
# 数据构建
# ═══════════════════════════════════════════════════════

def _state_mtime() -> float:
    try:
        return _STATE_PATH.stat().st_mtime
    except OSError:
        return 0.0


def _build_subject_rows(data: dict) -> list[dict]:
    rows: list[dict] = []
    for path, info in sorted(data.get("subjects", {}).items()):
        depth = path.count("/")
        expanded = os.path.expanduser(path)
        is_git = os.path.isdir(os.path.join(expanded, ".git")) or os.path.isfile(os.path.join(expanded, ".git"))
        icon = "📦" if is_git else "📁"
        rows.append({
            "_path": path,
            "path": "\u00a0\u00a0" * depth + f"{icon}\u00a0" + path,
            "description": info.get("description", ""),
        })
    return rows


def _build_task_rows(data: dict) -> list[dict]:
    rows: list[dict] = []
    for tid_str, info in sorted(data.get("tasks", {}).items(), key=lambda x: int(x[0])):
        state = info.get("state", "pending")
        icon = _STATE_ICON.get(state, "⏳")
        parent = info.get("parent", "")
        parent_str = f" ← #{parent}" if parent else ""
        rows.append({
            "id": int(tid_str),
            "title": f"{icon}\u00a0{info.get('title', '')}{parent_str}",
            "state": state,
            "subject": info.get("subject", ""),
            "_sort": _STATE_ORDER.get(state, 99),
        })
    rows.sort(key=lambda r: r["_sort"])
    return rows


def _build_space_rows(data: dict) -> list[dict]:
    rows: list[dict] = []
    for path, cfg in sorted(data.get("spaces", {}).items()):
        lock = cfg.get("lock") if cfg else None
        if lock:
            status = f"🔒 #{lock.get('by', '?')}"
        else:
            status = "🟢 空闲"
        rows.append({"path": path, "status": status})
    return rows


def _build_profile_rows(data: dict) -> list[dict]:
    rows: list[dict] = []
    for name, cfg in data.get("profiles", {}).items():
        rows.append({
            "name": name,
            "area": cfg.get("area", "?"),
            "merge": cfg.get("merge", "?"),
            "approval": str(cfg.get("approval", "—")),
        })
    return rows


# ═══════════════════════════════════════════════════════
# 组件
# ═══════════════════════════════════════════════════════

initial_state = load_state()

# ── Subject 树表 ──
_subject_tab = pn.widgets.Tabulator(
    value=pd.DataFrame(_build_subject_rows(initial_state)),
    pagination=None,
    sizing_mode="stretch_width",
    height=300,
    show_index=False,
    hidden_columns=["_path"],
    selectable=True,
)

_subject_info = pn.pane.Markdown("*选中一行查看详情*")
_subject_desc = pn.pane.Markdown("")

def _on_subject_select(event):
    if not event.new:
        _subject_info.object = "*选中一行查看详情*"
        _subject_desc.object = ""
        return
    row = event.new[0]
    df = _subject_tab.value
    path = df.iloc[row]["_path"]
    desc = df.iloc[row].get("description", "")
    _subject_info.object = f"**{path}**"
    _subject_desc.object = desc if desc else "*无描述*"

_subject_tab.param.watch(_on_subject_select, "selection")

# ── 任务列表表 ──
_task_tab = pn.widgets.Tabulator(
    value=pd.DataFrame(_build_task_rows(initial_state)),
    pagination=None,
    sizing_mode="stretch_width",
    height=300,
    show_index=False,
    hidden_columns=["_sort"],
    selectable=True,
)

_task_info = pn.pane.Markdown("*选中一行查看详情*")

def _on_task_select(event):
    if not event.new:
        _task_info.object = "*选中一行查看详情*"
        return
    row = event.new[0]
    df = _task_tab.value
    tid = df.iloc[row]["id"]
    state = df.iloc[row]["state"]
    subject = df.iloc[row].get("subject", "")
    _task_info.object = f"**#{tid}** — {state} — subject: `{subject}`"

_task_tab.param.watch(_on_task_select, "selection")

# ── Profiles 表 ──
_profile_tab = pn.widgets.Tabulator(
    value=pd.DataFrame(_build_profile_rows(initial_state)),
    pagination=None,
    sizing_mode="stretch_width",
    height=160,
    show_index=False,
)

# ── Spaces 表 ──
_space_tab = pn.widgets.Tabulator(
    value=pd.DataFrame(_build_space_rows(initial_state)),
    pagination=None,
    sizing_mode="stretch_width",
    height=160,
    show_index=False,
)

# ── 刷新 ──
def _refresh_all(data: dict) -> None:
    _subject_tab.value = pd.DataFrame(_build_subject_rows(data))
    _task_tab.value = pd.DataFrame(_build_task_rows(data))
    _profile_tab.value = pd.DataFrame(_build_profile_rows(data))
    _space_tab.value = pd.DataFrame(_build_space_rows(data))


_last_mtime = _state_mtime()

async def _poll():
    global _last_mtime
    mtime = _state_mtime()
    if mtime != _last_mtime:
        _last_mtime = mtime
        _refresh_all(load_state())

pn.state.add_periodic_callback(_poll, period=2000)

# ═══════════════════════════════════════════════════════
# 布局
# ═══════════════════════════════════════════════════════

layout = pn.Column(
    pn.pane.Markdown("# diy 管控台"),
    pn.Row(
        pn.Column(
            pn.pane.Markdown("## Subject 树"),
            _subject_tab,
            _subject_info,
            _subject_desc,
            sizing_mode="stretch_width",
        ),
        pn.Column(
            pn.pane.Markdown("## 任务列表"),
            _task_tab,
            _task_info,
            sizing_mode="stretch_width",
        ),
    ),
    pn.Row(
        pn.Column(
            pn.pane.Markdown("## Profiles"),
            _profile_tab,
            sizing_mode="stretch_width",
        ),
        pn.Column(
            pn.pane.Markdown("## Spaces / Locks"),
            _space_tab,
            sizing_mode="stretch_width",
        ),
    ),
    sizing_mode="stretch_width",
)

layout.servable()

if __name__ == "__main__":
    pn.serve(__file__, autoreload=True, port=5006)
