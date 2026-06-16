"""state.yaml 全局状态系统

~/.diy/state.yaml 是 diy 生态全局状态真相源。

结构:
  手改区: profiles（人直接编辑）
  机器区: spaces（dai 维护，人只读）

任务数据存储在 ~/.diy/tasks/<id>/AGENTS.md（YAML frontmatter + markdown body）。
"""

from __future__ import annotations

import fcntl
import os
import shutil
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
# 加载 / 保存（state.yaml — 仅 profiles + spaces）
# ════════════════════════════════════════════════════════════════


def load_state() -> dict[str, Any]:
    """加载 state.yaml。文件不存在时返回默认值。"""
    path = _state_path()
    if path.exists():
        with open(path, encoding="utf-8") as fh:
            data: dict[str, Any] = yaml.safe_load(fh) or {}
    else:
        data = {}

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
# 锁操作（空间锁 — state.yaml）
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
    """申请锁。如已锁则抛出 RuntimeError。"""
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
# 任务存储 — ~/.diy/tasks/<id>/
# ════════════════════════════════════════════════════════════════

_FRONT_MATTER_SEP = "---"


def _tasks_root() -> Path:
    """~/.diy/tasks/（可通过 DIY_HOME 覆盖，和 state.yaml 同级）"""
    return _state_path().parent / "tasks"


def _task_dir(task_id: int) -> Path:
    return _tasks_root() / str(task_id)


def _agents_md(task_id: int) -> Path:
    return _task_dir(task_id) / "AGENTS.md"


def _read_frontmatter(path: Path) -> dict[str, Any] | None:
    """解析 AGENTS.md 的 YAML frontmatter。无文件/格式错返回 None。"""
    if not path.exists():
        return None
    content = path.read_text(encoding="utf-8")
    return _parse_frontmatter(content)


def _parse_frontmatter(content: str) -> dict[str, Any] | None:
    """从 AGENTS.md 内容解析 YAML frontmatter"""
    lines = content.split("\n")
    if not lines or lines[0].strip() != _FRONT_MATTER_SEP:
        return None
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == _FRONT_MATTER_SEP:
            end = i
            break
    if end is None:
        return None
    fm_text = "\n".join(lines[1:end])
    try:
        return yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        return None


def _make_frontmatter(meta: dict[str, Any]) -> str:
    """将 dict 渲染为 YAML frontmatter 块"""
    fm = yaml.dump(
        meta, allow_unicode=True, default_flow_style=False, sort_keys=False
    ).strip()
    return f"{_FRONT_MATTER_SEP}\n{fm}\n{_FRONT_MATTER_SEP}\n"


def _write_agents_md(task_id: int, meta: dict[str, Any], body: str = "") -> None:
    """写 AGENTS.md（frontmatter + body）"""
    d = _task_dir(task_id)
    d.mkdir(parents=True, exist_ok=True)
    content = _make_frontmatter(meta)
    if body:
        content += body.strip() + "\n"
    (_agents_md(task_id)).write_text(content, encoding="utf-8")


def _meta_to_task_dict(task_id: int, meta: dict[str, Any]) -> dict[str, Any]:
    """将 frontmatter meta 转为与 get_task 返回一致的 dict"""
    result: dict[str, Any] = {}
    for key in ("title", "state", "subject", "detail", "parent", "created", "updated"):
        if key in meta:
            result[key] = meta[key]
    # 确保默认字段存在
    result.setdefault("title", "")
    result.setdefault("state", meta.get("state", "pending"))
    result.setdefault("subject", meta.get("subject", ""))
    return result


def _counter_path() -> Path:
    return _tasks_root() / ".counter"


def _lock_path() -> Path:
    return _tasks_root() / ".lock"


def _next_task_id() -> int:
    """fcntl 保护的 ID 自增。"""
    root = _tasks_root()
    root.mkdir(parents=True, exist_ok=True)

    lock_path = _lock_path()
    counter_path = _counter_path()

    with open(lock_path, "w") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            if counter_path.exists():
                current = int(counter_path.read_text().strip())
            else:
                current = 1
            counter_path.write_text(str(current + 1))
            return current
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


# ════════════════════════════════════════════════════════════════
# 任务 CRUD 函数（签名不变，供 CLI / task_tree 调用）
# ════════════════════════════════════════════════════════════════


def get_task(task_id: int) -> dict[str, Any] | None:
    """获取任务信息。从 ~/.diy/tasks/<id>/AGENTS.md 读取。"""
    md = _agents_md(task_id)
    meta = _read_frontmatter(md)
    if meta is None:
        return None
    return _meta_to_task_dict(task_id, meta)


def create_task(
    title: str,
    subject: str,
    parent: int | None = None,
    state_val: str = "pending",
    detail: str | None = None,
) -> int:
    """创建任务，返回自增 int ID。先分配 ID 再写文件。"""
    if parent is not None and get_task(parent) is None:
        raise ValueError(f"parent {parent} 不存在")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    task_id = _next_task_id()

    meta: dict[str, Any] = {
        "id": task_id,
        "title": title,
        "state": state_val,
        "subject": subject,
        "created": now,
        "updated": now,
    }
    if detail is not None:
        meta["detail"] = detail
    if parent is not None:
        meta["parent"] = parent

    _write_agents_md(task_id, meta)
    return task_id


def update_task_field(task_id: int, **fields: Any) -> dict[str, Any]:
    """更新任务字段，返回更新后的完整任务。"""
    md = _agents_md(task_id)
    meta = _read_frontmatter(md)
    if meta is None:
        raise KeyError(f"Task {task_id} 不存在")

    # parent 验证
    if "parent" in fields:
        p = fields["parent"]
        if p is not None:
            if get_task(p) is None:
                raise KeyError(f"parent {p} 不存在")
            fields["parent"] = int(p) if not isinstance(p, int) else p
        else:
            fields["parent"] = None

    meta.update(fields)
    meta["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 保留已有的 body 内容
    body = _read_body(md)
    _write_agents_md(task_id, meta, body)
    return _meta_to_task_dict(task_id, meta)


def _read_body(path: Path) -> str:
    """读取 frontmatter 之后的 body 内容"""
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8")
    lines = content.split("\n")
    if not lines or lines[0].strip() != _FRONT_MATTER_SEP:
        return content
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == _FRONT_MATTER_SEP:
            end = i
            break
    if end is None:
        return ""
    return "\n".join(lines[end + 1:]).strip()


def delete_task(task_id: int) -> None:
    """删除任务目录。不存在时静默成功。"""
    d = _task_dir(task_id)
    if d.exists():
        shutil.rmtree(d)


def list_tasks() -> dict[str, Any]:
    """列出所有任务。扫描 ~/.diy/tasks/*/AGENTS.md。"""
    root = _tasks_root()
    if not root.exists():
        return {}
    result: dict[str, dict[str, Any]] = {}
    for d in sorted(root.iterdir(), key=lambda p: p.name):
        if not d.is_dir():
            continue
        try:
            tid = int(d.name)
        except ValueError:
            continue
        task = get_task(tid)
        if task is not None:
            result[str(tid)] = task
    return result


def get_task_spaces(task_id: int) -> list[str]:
    """获取任务声明的 spaces。"""
    task = get_task(task_id)
    if not task:
        return []
    return task.get("spaces", [])
