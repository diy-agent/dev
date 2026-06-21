"""state.yaml 全局状态系统

~/.diy/state.yaml 是 diy 生态全局状态真相源。

结构:
  手改区: profiles（人直接编辑）
  机器区: spaces（dai 维护，人只读）

任务数据存储在 ~/.diy/task/<uri-path>/AGENTS.md（YAML frontmatter + markdown body）。
每个任务对应一个 URI，URI 也是文件系统路径和身份标识。

star/unstar 替代了归档：取消关注后 symlink 删除，数据保留在原位。
"""

from __future__ import annotations

import fcntl
import os
import shutil
from datetime import datetime
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


def diy_home() -> Path:
    """获取 DIY 数据根目录（可通过 DIY_HOME 环境变量覆盖）。"""
    if home := os.environ.get("DIY_HOME"):
        return Path(home)
    return Path(os.path.expanduser("~/.diy"))


def _state_path() -> Path:
    """state.yaml 路径。"""
    return diy_home() / "state.yaml"


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
        "since": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
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
# 数据根 — ~/.diy/task/
# ════════════════════════════════════════════════════════════════

_FRONT_MATTER_SEP = "---"


def _data_root() -> Path:
    """~/.diy/task/（可通过 DIY_HOME 覆盖），自动从 ~/.diy/d/ 迁移。"""
    task_root = diy_home() / "task"
    d_root = diy_home() / "d"

    # 自动迁移：d/ 存在且 task/ 不存在 → 改名并更新 star/ symlink
    if d_root.exists() and not task_root.exists():
        _migrate_d_to_task(d_root, task_root)

    task_root.mkdir(parents=True, exist_ok=True)
    return task_root


def _migrate_d_to_task(src: Path, dst: Path) -> None:
    """将 d/ 迁移到 task/，同时更新 star/ symlink 目标路径。"""
    import logging
    logger = logging.getLogger("diy.app.state")
    logger.warning("迁移 ~/.diy/d/ → ~/.diy/task/")

    shutil.move(str(src), str(dst))

    # 更新 star/ symlink：指向 d/ 的改为指向 task/
    star_root = _star_root()
    if star_root.exists():
        src_str = str(src)
        for sym in sorted(star_root.rglob("*")):
            if not sym.is_symlink():
                continue
            try:
                target = os.readlink(str(sym))
                if target.startswith(src_str):
                    new_target = target.replace(src_str, str(dst), 1)
                    os.unlink(str(sym))
                    sym.symlink_to(new_target)
                    logger.debug("  更新 symlink: %s → %s", sym, new_target)
            except OSError:
                pass


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
# Star 视图 — ~/.diy/star/
# ════════════════════════════════════════════════════════════════

def _star_root() -> Path:
    """~/.diy/star/（可通过 DIY_HOME 覆盖）"""
    return diy_home() / "star"


def star_task(uri: str) -> None:
    """star 任务：创建 symlink 到 ~/.diy/star/<uri>。"""
    src = _uri_to_path(uri).parent  # ~/.diy/d/<uri>
    if not src.exists():
        raise FileNotFoundError(f"任务 {uri} 不存在")

    dst = _star_root() / uri
    if dst.exists() or dst.is_symlink():
        return  # 幂等：已 star

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.symlink_to(src)


def unstar_task(uri: str) -> None:
    """unstar 任务：删除 symlink，数据不动。"""
    dst = _star_root() / uri
    if dst.is_symlink():
        dst.unlink()
    elif dst.exists():
        dst.rmdir()  # 非 symlink 目录，清理


def is_starred(uri: str) -> bool:
    """检查任务是否 starred。"""
    return (_star_root() / uri).is_symlink()


def list_starred() -> dict[str, dict[str, Any]]:
    """列出所有 starred 任务。"""
    root = _star_root()
    if not root.exists():
        return {}
    result: dict[str, dict[str, Any]] = {}
    for d in sorted(root.rglob("*")):
        if not d.is_symlink():
            continue
        # 从 symlink 反推 URI
        try:
            rel = d.relative_to(root)
            uri = str(rel)
        except ValueError:
            continue
        task = get_task(uri)
        if task is not None:
            result[uri] = task
    return result


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
    """获取任务信息。通过 URI 读取。返回 dict 包含 body 字段。"""
    md = _uri_to_path(uri)
    meta = _read_frontmatter(md)
    if meta is None:
        return None
    result = _meta_to_task_dict(uri, meta)
    result["body"] = _read_body(md)
    return result


def create_task(
    title: str,
    subject: str,
    source_type: str = "local",
    source_uri: str | None = None,
    parent: str | None = None,
    state_val: str = "pending",
    detail: str | None = None,
    body: str = "",
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

    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

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

    _write_agents_md(uri, meta, body)
    return uri


def update_task_field(uri: str, **fields: Any) -> dict[str, Any]:
    """更新任务字段，返回更新后的完整任务。

    特殊字段 'body' 写入 markdown body 而非 frontmatter。
    """
    md = _uri_to_path(uri)
    meta = _read_frontmatter(md)
    if meta is None:
        raise KeyError(f"Task {uri} 不存在")

    # parent 验证
    if "parent" in fields:
        p = fields["parent"]
        if p is not None and get_task(p) is None:
            raise KeyError(f"parent {p} 不存在")

    body = fields.pop("body", None)
    if body is None:
        body = _read_body(md)

    meta.update(fields)
    meta["updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    _write_agents_md(uri, meta, body)
    return _meta_to_task_dict(uri, meta)


def delete_task(uri: str) -> None:
    """删除任务目录。不存在时静默成功。"""
    d = _uri_to_path(uri).parent
    if d.exists():
        shutil.rmtree(d)


def _archive_root() -> Path:
    """~/.diy/archive/data/（已废弃，archive 被 unstar 替代）。"""
    return diy_home() / "archive" / "data"


def archive_task(uri: str) -> Path:
    """归档任务（已废弃 — 请用 unstar 替代）。

    此函数保留以支持已有数据迁移。
    归档后自动取消关注（unstar），数据移入 archive/。
    返回归档后的路径。
    """
    import logging
    logger = logging.getLogger("diy.app.state")
    logger.warning("archive_task 已废弃，请用 unstar 替代")

    src = _uri_to_path(uri).parent
    if not src.exists():
        raise FileNotFoundError(f"任务 {uri} 不存在")

    dst_base = _archive_root() / uri
    now = datetime.now()

    # 尝试 base.20260618-074801，同秒碰撞则递增
    stamp = now.strftime("%Y%m%d-%H%M%S")
    counter = 0
    while True:
        suffix = f".{stamp}" if counter == 0 else f".{stamp}.{counter}"
        dst = dst_base.with_name(f"{dst_base.name}{suffix}")
        if not dst.exists():
            break
        counter += 1

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))

    # 归档后自动取消关注
    unstar_task(uri)

    return dst


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
        task_dict = _meta_to_task_dict(uri, meta)
        task_dict["body"] = _read_body(md)
        result[uri] = task_dict
    return result


def get_task_spaces(task_uri: str) -> list[str]:
    """获取任务声明的 spaces。"""
    task = get_task(task_uri)
    if not task:
        return []
    return task.get("spaces", [])
