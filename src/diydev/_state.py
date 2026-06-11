"""state.yaml 全局状态系统

~/.diy/state.yaml 是 diy 生态全局状态真相源。

结构:
  手改区: profiles + tasks（人直接编辑）
  机器区: spaces（dai 维护，人只读）
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

# ════════════════════════════════════════════════════════════════
# 默认值
# ════════════════════════════════════════════════════════════════

DEFAULT_PROFILES: dict[str, dict[str, Any]] = {
    "quick": {"area": "main", "merge": "direct", "approval": None},
    "standard": {"area": "branch", "merge": "pr", "approval": "self"},
    "reviewed": {"area": "worktree", "merge": "pr", "approval": "human"},
}

DEFAULT_STATE: dict[str, Any] = {
    "profiles": dict(DEFAULT_PROFILES),
    "tasks": {},
    "spaces": {},
}


def _state_path() -> Path:
    """~/.diy/state.yaml（可通过 DIY_HOME 环境变量覆盖目录，供测试用）"""
    if home := os.environ.get("DIY_HOME"):
        return Path(home) / "state.yaml"
    return Path(os.path.expanduser("~/.diy/state.yaml"))


# ════════════════════════════════════════════════════════════════
# 加载 / 保存
# ════════════════════════════════════════════════════════════════


def load_state() -> dict[str, Any]:
    """加载 state.yaml。文件不存在时返回默认值。"""
    path = _state_path()
    if path.exists():
        with open(path, encoding="utf-8") as fh:
            data: dict[str, Any] = yaml.safe_load(fh) or {}
    else:
        data = {}

    # 合并默认值（确保顶层 key 都存在）
    merged = dict(DEFAULT_STATE)
    merged.update(data)
    return merged


def save_state(data: dict[str, Any]) -> None:
    """保存 state.yaml。自动创建目录。"""
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    # 先写临时文件再替换，保证原子性
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh, allow_unicode=True, default_flow_style=False, sort_keys=False)
    tmp.replace(path)


# ════════════════════════════════════════════════════════════════
# 锁操作
# ════════════════════════════════════════════════════════════════


def get_lock(space_path: str) -> dict[str, Any] | None:
    """获取 space 当前锁状态。无锁返回 None。"""
    state = load_state()
    space = state["spaces"].get(space_path)
    if space and space.get("lock"):
        return space["lock"]
    return None


def acquire_lock(
    space_path: str,
    task_num: int,
    area: str = "branch",
) -> dict[str, Any]:
    """申请锁。如已锁则抛出 RuntimeError。

    Returns:
        新建的 lock dict
    """
    state = load_state()
    space = state["spaces"].setdefault(space_path, {"lock": None})

    existing = space.get("lock")
    if existing:
        raise RuntimeError(
            f"Space {space_path} 已被 #{existing['by']} 锁定 "
            f"(area={existing.get('area', '?')}, since={existing.get('since', '?')})"
        )

    lock = {
        "by": task_num,
        "area": area,
        "since": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    space["lock"] = lock
    save_state(state)
    return lock


def release_lock(space_path: str) -> None:
    """释放锁。无锁时静默成功。"""
    state = load_state()
    if space_path in state["spaces"]:
        state["spaces"][space_path]["lock"] = None
        save_state(state)


# ════════════════════════════════════════════════════════════════
# 任务操作
# ════════════════════════════════════════════════════════════════


def get_task(task_num: int) -> dict[str, Any] | None:
    """获取任务信息。"""
    state = load_state()
    return state["tasks"].get(str(task_num))


def get_task_spaces(task_num: int) -> list[str]:
    """获取任务声明的 spaces。"""
    task = get_task(task_num)
    if not task:
        return []
    return task.get("spaces", [])


def register_task(
    task_num: int,
    title: str,
    spaces: list[str] | None = None,
    parent: int | None = None,
    state_val: str = "pending",
) -> None:
    """注册或更新任务。"""
    state_data = load_state()
    key = str(task_num)
    entry: dict[str, Any] = {"title": title, "state": state_val}
    if parent is not None:
        entry["parent"] = parent
    if spaces:
        entry["spaces"] = spaces

    # 保留已有字段
    existing = state_data["tasks"].get(key, {})
    existing.update(entry)
    state_data["tasks"][key] = existing
    save_state(state_data)


def update_task_state(task_num: int, new_state: str) -> None:
    """更新任务状态字段。"""
    state_data = load_state()
    key = str(task_num)
    if key not in state_data["tasks"]:
        raise KeyError(f"Task #{task_num} 未注册")
    state_data["tasks"][key]["state"] = new_state
    save_state(state_data)


def list_tasks() -> dict[str, Any]:
    """列出所有任务。"""
    return load_state()["tasks"]
