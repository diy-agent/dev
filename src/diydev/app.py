"""dai 管控台 — diy UI app.

Usage:
    uv run python -m diydev.app       # dev mode (autoreload)
    uv run panel serve --dev src/diydev/app.py
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pandas as pd
import panel as pn

pn.extension("tabulator")

import diy.ui.providers.panel as diypn

from diydev._state import load_state, save_state

_STATE_PATH = Path(os.environ.get("DIY_HOME", Path.home() / ".diy")) / "state.yaml"


def _state_mtime() -> float:
    try:
        return _STATE_PATH.stat().st_mtime
    except OSError:
        return 0.0


def _build_subject_rows(data: dict) -> list[dict]:
    rows: list[dict] = []
    for path, info in sorted(data.get("subjects", {}).items()):
        depth = path.count("/")
        is_git = os.path.isdir(os.path.join(os.path.expanduser(path), ".git"))
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
        rows.append({
            "id": int(tid_str),
            "title": info.get("title", ""),
            "state": info.get("state", ""),
            "subject": info.get("subject", ""),
        })
    return rows


def _delete_subject(subject_path: str) -> None:
    """删除 subject 及其关联 tasks。"""
    data = load_state()
    data["subjects"].pop(subject_path, None)
    data["tasks"] = {
        tid: t for tid, t in data["tasks"].items()
        if t.get("subject") != subject_path
    }
    save_state(data)


def _refresh_tables() -> None:
    """刷新两个表格。"""
    data = load_state()
    _subject_tabulator.value = pd.DataFrame(_build_subject_rows(data))
    _task_tabulator.value = pd.DataFrame(_build_task_rows(data))


# ── app ──

app = diypn.PanelApp()

# ── tick 驱动周期刷新 ──

tick = app.signal(0)

# ── 删除确认弹窗 ──

_pending_delete: str = ""

_subject_path_text = pn.pane.Markdown("")
_confirm_btn = pn.widgets.Button(name="确认删除", button_type="danger")
_cancel_btn = pn.widgets.Button(name="取消", button_type="default")

_confirm_modal = pn.Modal(
    pn.pane.Markdown("## 确认删除"),
    _subject_path_text,
    pn.pane.Markdown("删除 subject 后，关联的 tasks 也会一并删除。**此操作不可撤销。**"),
    pn.Row(_confirm_btn, _cancel_btn),
    show_close_button=False,
    background_close=False,
    margin=20,
)


def _on_confirm_delete(event):
    global _pending_delete
    if _pending_delete:
        _delete_subject(_pending_delete)
        _pending_delete = ""
        _refresh_tables()
    _confirm_modal.hide()


def _on_cancel_delete(event):
    global _pending_delete
    _pending_delete = ""
    _confirm_modal.hide()


_confirm_btn.on_click(_on_confirm_delete)
_cancel_btn.on_click(_on_cancel_delete)

# ── 布局 ──

app.pane.markdown("# diy 管控台")

with app.layout.row():
    # ── 左栏：Subject 树 ──
    with app.layout.column(sizing_mode="stretch_width"):
        app.pane.markdown("## Subject 树")

        _subject_tabulator = app.widgets.tabulator(
            value=pd.DataFrame(_build_subject_rows(load_state())),
            pagination=None,
            sizing_mode="stretch_width",
            height=360,
            show_index=False,
            hidden_columns=["_path"],
            selectable=True,
        )

        _selected_info = app.pane.markdown("选中一行后点击删除")

        def _on_select(event):
            if not event.new:
                _selected_info.object = "选中一行后点击删除"
                return
            row = event.new[0]
            df = _subject_tabulator.value
            path = df.iloc[row]["_path"]
            _selected_info.object = f"已选中: **{path}**"

        _subject_tabulator.param.watch(_on_select, "selection")

        def _on_delete_click(event):
            sel = _subject_tabulator.selection
            if not sel:
                _selected_info.object = "⚠️ 请先选中一行"
                return
            global _pending_delete
            df = _subject_tabulator.value
            _pending_delete = df.iloc[sel[0]]["_path"]
            _subject_path_text.object = f"**{_pending_delete}**"
            _confirm_modal.show()

        _delete_btn = app.widgets.button(name="🗑 删除选中", button_type="danger")
        _delete_btn.on_click(_on_delete_click)

    # ── 右栏：任务列表 ──
    with app.layout.column(sizing_mode="stretch_width"):
        app.pane.markdown("## 任务列表")

        _task_tabulator = app.widgets.tabulator(
            value=pd.DataFrame(_build_task_rows(load_state())),
            pagination=None,
            sizing_mode="stretch_width",
            height=400,
            show_index=False,
        )

# ── 后台轮询 cell ──

_last_mtime = _state_mtime()


@app.layout.column().cell()
async def _(node: diypn.layout.Column):
    """轮询 state.yaml mtime，变化时更新表格。"""
    global _last_mtime
    while True:
        yield pn.indicators.LoadingSpinner(
            value=True, width=20, height=20, visible=False
        )
        await asyncio.sleep(2.0)
        mtime = _state_mtime()
        if mtime != _last_mtime:
            _last_mtime = mtime
            _refresh_tables()


# ── 注入 CSS：允许文字选择 ──
# Bokeh 3.x 用 shadow DOM 渲染，外部 CSS 穿透不了
# 在 session 创建后注入 JS 到所有 shadow root


def _inject_selectable():
    """浏览器端 JS: 向所有 shadow root 写入 :host { user-select: text }"""
    code = """document.querySelectorAll('[data-root-id]').forEach(function(el){
if(el.shadowRoot&&!el.shadowRoot.querySelector('.diy-sel')){
var s=document.createElement('style');s.className='diy-sel';
s.textContent=':host{user-select:text!important;-webkit-user-select:text!important}';
el.shadowRoot.appendChild(s);}});"""
    pn.state.execute(code)


def _on_session_created(_event):
    """session 创建后注入 CSS，并定时重试（后续 shadow root）"""
    _inject_selectable()
    pn.state.add_periodic_callback(_inject_selectable, period=5000)


pn.state.on_session_created(_on_session_created)

app.servable()

if __name__ == "__main__":
    pn.serve(__file__, autoreload=True, port=5006)
