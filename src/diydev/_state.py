"""state.yaml 全局状态系统

~/.diy/state.yaml 是 diy 生态全局状态真相源。

结构:
  手改区: profiles（人直接编辑）
  机器区: spaces（dai 维护，人只读）

任务数据存储在 ~/.diy/d/<uri-path>/AGENTS.md（YAML frontmatter + markdown body）。
每个任务对应一个 URI，URI 也是文件系统路径和身份标识。
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
    task_uri: str,
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
        "by": task_uri,
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
# 数据根 — ~/.diy/d/
# ════════════════════════════════════════════════════════════════

_FRONT_MATTER_SEP = "---"


def _data_root() -> Path:
    """~/.diy/d/（可通过 DIY_HOME 覆盖，和 state.yaml 同级）"""
    return _state_path().parent / "d"


def _uri_to_path(uri: str) -> Path:
    """将任务 URI 映射为 AGENTS.md 路径。

    local/task/23 → ~/.diy/d/local/task/23/AGENTS.md
    github.com/diy-agent/diy/issues/58 → ~/.diy/d/github.com/diy-agent/diy/issues/58/AGENTS.md
    """
    return _data_root() / uri / "AGENTS.md"


def _path_to_uri(path: Path) -> str | None:
    """从 AGENTS.md 路径反推 URI。"""
    root = _data_root()
    try:
        rel = path.parent.relative_to(root)
        return str(rel)
    except ValueError:
        return None


# ════════════════════════════════════════════════════════════════
# 本地任务 ID 自增
# ════════════════════════════════════════════════════════════════

_LOCAL_COUNTER_DIR = "local/task"


def _local_counter_dir() -> Path:
    return _data_root() / _LOCAL_COUNTER_DIR


def _local_counter_file() -> Path:
    return _local_counter_dir() / ".counter"


def _local_lock_file() -> Path:
    return _local_counter_dir() / ".lock"


def _next_local_task_num() -> int:
    """fcntl 保护的本地任务编号自增。"""
    d = _local_counter_dir()
    d.mkdir(parents=True, exist_ok=True)

    lock_path = _local_lock_file()
    counter_path = _local_counter_file()

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
# Frontmatter 解析与渲染
# ════════════════════════════════════════════════════════════════


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


def _write_agents_md(uri: str, meta: dict[str, Any], body: str = "") -> None:
    """写 AGENTS.md（frontmatter + body）。自动创建目录。"""
    path = _uri_to_path(uri)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = _make_frontmatter(meta)
    if body:
        content += body.strip() + "\n"
    path.write_text(content, encoding="utf-8")


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


def _meta_to_task_dict(uri: str, meta: dict[str, Any]) -> dict[str, Any]:
    """将 frontmatter meta 转为与 get_task 返回一致的 dict"""
    result: dict[str, Any] = {"uri": uri}
    for key in ("title", "state", "subject", "detail", "parent", "created", "updated", "source"):
        if key in meta:
            result[key] = meta[key]
    # 确保默认字段存在
    result.setdefault("title", "")
    result.setdefault("state", meta.get("state", "pending"))
    result.setdefault("subject", meta.get("subject", ""))
    result.setdefault("source", meta.get("source", {"type": "local", "uri": uri}))
    return result


# ════════════════════════════════════════════════════════════════
# 任务 CRUD 函数
# ════════════════════════════════════════════════════════════════


def get_task(uri: str) -> dict[str, Any] | None:
    """获取任务信息。通过 URI 读取。"""
    md = _uri_to_path(uri)
    meta = _read_frontmatter(md)
    if meta is None:
        return None
    return _meta_to_task_dict(uri, meta)


def create_task(
    title: str,
    subject: str,
    source_type: str = "local",
    source_uri: str | None = None,
    parent: str | None = None,
    state_val: str = "pending",
    detail: str | None = None,
) -> str:
    """创建任务，返回任务 URI。

    本地任务：source_type="local" 且 source_uri 为 None → 自动生成 local/task/<n>
    外部任务：source_type="github_issue" 等，source_uri 必填
    """
    if parent is not None and get_task(parent) is None:
        raise ValueError(f"parent {parent} 不存在")

    # 生成 URI
    if source_type == "local" and source_uri is None:
        num = _next_local_task_num()
        uri = f"local/task/{num}"
    elif source_uri:
        uri = source_uri
    else:
        raise ValueError("source_uri 必须提供（非 local 类型）")

    # 检查 URI 是否已存在
    if _uri_to_path(uri).parent.exists():
        raise ValueError(f"URI 已存在: {uri}")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    meta: dict[str, Any] = {
        "title": title,
        "state": state_val,
        "subject": subject,
        "source": {"type": source_type, "uri": uri},
        "created": now,
        "updated": now,
    }
    if detail is not None:
        meta["detail"] = detail
    if parent is not None:
        meta["parent"] = parent

    _write_agents_md(uri, meta)
    return uri


def update_task_field(uri: str, **fields: Any) -> dict[str, Any]:
    """更新任务字段，返回更新后的完整任务。"""
    md = _uri_to_path(uri)
    meta = _read_frontmatter(md)
    if meta is None:
        raise KeyError(f"Task {uri} 不存在")

    # parent 验证
    if "parent" in fields:
        p = fields["parent"]
        if p is not None and get_task(p) is None:
            raise KeyError(f"parent {p} 不存在")

    meta.update(fields)
    meta["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 保留已有的 body 内容
    body = _read_body(md)
    _write_agents_md(uri, meta, body)
    return _meta_to_task_dict(uri, meta)


def delete_task(uri: str) -> None:
    """删除任务目录。不存在时静默成功。"""
    d = _uri_to_path(uri).parent
    if d.exists():
        shutil.rmtree(d)


def list_tasks() -> dict[str, dict[str, Any]]:
    """列出所有任务。递归扫描 ~/.diy/d/ 下所有目录。"""
    root = _data_root()
    if not root.exists():
        return {}
    result: dict[str, dict[str, Any]] = {}
    for d in sorted(root.rglob("*")):
        if not d.is_dir():
            continue
        md = d / "AGENTS.md"
        if not md.exists():
            continue
        meta = _read_frontmatter(md)
        if meta is None:
            continue
        uri = _path_to_uri(md)
        if uri is None:
            continue
        result[uri] = _meta_to_task_dict(uri, meta)
    return result


def get_task_spaces(task_uri: str) -> list[str]:
    """获取任务声明的 spaces。"""
    task = get_task(task_uri)
    if not task:
        return []
    return task.get("spaces", [])
