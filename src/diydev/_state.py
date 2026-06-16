"""state.yaml 全局状态系统

~/.diy/state.yaml 是 diy 生态全局状态真相源。

结构:
  手改区: profiles + tasks（人直接编辑）
  机器区: spaces（dai 维护，人只读）
"""

from __future__ import annotations

import fcntl
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
    "next_task_id": 1,
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
    """加载 state.yaml。文件不存在时返回默认值。

    首次加载时自动迁移 next_task_id（根据已有任务计算）。
    """
    path = _state_path()
    if path.exists():
        with open(path, encoding="utf-8") as fh:
            data: dict[str, Any] = yaml.safe_load(fh) or {}
    else:
        data = {}

    # 合并默认值（确保顶层 key 都存在）
    merged = dict(DEFAULT_STATE)
    merged.update(data)

    # 迁移：已有任务但缺 next_task_id → 从已有任务计算
    if "next_task_id" not in data and merged.get("tasks"):
        existing_ids = [int(k) for k in merged["tasks"] if k.isdigit()]
        merged["next_task_id"] = max(existing_ids) + 1 if existing_ids else 1

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
    task_id: int,
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
            f"Space {space_path} 已被 {existing['by']} 锁定 "
            f"(area={existing.get('area', '?')}, since={existing.get('since', '?')})"
        )

    lock = {
        "by": task_id,
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


def _lock_path() -> Path:
    return _state_path().with_suffix(".lock")


def get_task(task_id: int) -> dict[str, Any] | None:
    """获取任务信息。"""
    state = load_state()
    entry = state["tasks"].get(str(task_id))
    return dict(entry) if entry else None


def create_task(
    title: str,
    subject: str,
    parent: int | None = None,
    state_val: str = "pending",
) -> int:
    """创建任务，返回自增 int ID。

    使用 fcntl.flock 保护 next_task_id 自增的读-改-写窗口。
    """
    lock_path = _lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with open(lock_path, "w") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            state_data = load_state()
            task_id: int = state_data["next_task_id"]
            state_data["next_task_id"] = task_id + 1

            # 解析 parent（内联，避免死锁）
            resolved_parent: int | None = None
            if parent is not None:
                pkey = str(parent)
                if pkey not in state_data.get("tasks", {}):
                    raise ValueError(f"parent {parent} 不存在")
                resolved_parent = parent

            entry: dict[str, Any] = {
                "title": title,
                "state": state_val,
                "subject": subject,
            }
            if resolved_parent is not None:
                entry["parent"] = resolved_parent

            state_data["tasks"][str(task_id)] = entry
            save_state(state_data)
            return task_id
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


def update_task_field(task_id: int, **fields: Any) -> dict[str, Any]:
    """更新任务字段，返回更新后的完整任务。"""
    state_data = load_state()
    key = str(task_id)
    if key not in state_data["tasks"]:
        raise KeyError(f"Task {task_id} 不存在")

    # parent 字段统一存 int
    if "parent" in fields:
        p = fields["parent"]
        if p is not None:
            pkey = str(p)
            if pkey not in state_data["tasks"]:
                raise KeyError(f"parent {p} 不存在")
            fields["parent"] = int(p) if not isinstance(p, int) else p
        else:
            fields["parent"] = None

    state_data["tasks"][key].update(fields)
    save_state(state_data)
    return dict(state_data["tasks"][key])


def delete_task(task_id: int) -> None:
    """删除任务。不存在时静默成功。"""
    state_data = load_state()
    key = str(task_id)
    if key in state_data["tasks"]:
        del state_data["tasks"][key]
        save_state(state_data)


def list_tasks() -> dict[str, Any]:
    """列出所有任务。"""
    return load_state()["tasks"]


def get_task_spaces(task_id: int) -> list[str]:
    """获取任务声明的 spaces。"""
    task = get_task(task_id)
    if not task:
        return []
    return task.get("spaces", [])
