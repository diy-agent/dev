"""dai CLI — diy agent 接口

命令:
  dai state          全量输出 state.yaml（YAML，默认）
  dai state --json   全量输出 state.yaml（JSON）
  dai tree --sync    注入 AGENTS.md json block
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from contextlib import suppress
from typing import Annotated

import yaml
from cyclopts import App, Parameter

from ._log import VerboseFlag, set_verbosity
from ._state import load_state, save_state

app = App(
    name="dai",
    help="diy agent 接口 — state 查询与同步",
    version_flags=[],
)

_BEGIN_MARKER = "<!-- diy:tree:begin -->"
_END_MARKER = "<!-- diy:tree:end -->"


# ════════════════════════════════════════════════════════════════
# dai state
# ════════════════════════════════════════════════════════════════


@app.command
def state(
    json_output: Annotated[
        bool,
        Parameter(name=["--json"], help="JSON 格式输出"),
    ] = False,
    set_path: Annotated[
        list[str] | None,
        Parameter(
            name=["--set"],
            help="设置值: --set <path> <value>（如 --set tasks.73.title 新标题）",
            consume_multiple=2,
        ),
    ] = None,
    free: Annotated[
        bool,
        Parameter(name=["--free"], help="列出 lock 为 null 或未注册的 space"),
    ] = False,
):
    """输出/修改 state.yaml。"""
    # ── --free ──
    if free:
        data = load_state()
        spaces = data.get("spaces", {})
        free_paths = [
            p for p, cfg in spaces.items()
            if not cfg or cfg.get("lock") is None
        ]
        for p in sorted(free_paths):
            print(p)
        return

    # ── --set ──
    if set_path is not None:
        if len(set_path) != 2:
            print(
                "错误: --set 需要 <path> <value> 两个参数",
                file=sys.stderr,
            )
            sys.exit(1)

        path, raw_value = set_path
        try:
            section, key, field = _parse_path(path)
        except ValueError as e:
            print(f"错误: {e}", file=sys.stderr)
            sys.exit(1)

        if section not in ("profiles", "tasks", "spaces"):
            print(
                f"错误: section 必须是 profiles/tasks/spaces，"
                f"收到 {shlex.quote(section)}",
                file=sys.stderr,
            )
            sys.exit(1)

        # 类型转换：布尔 / 整数 / JSON 列表 / 字符串
        parsed: object = _parse_value(raw_value)

        data = load_state()
        section_data = data.setdefault(section, {})
        entry: dict[str, object] = section_data.setdefault(key, {})
        if not isinstance(entry, dict):
            print(
                f"错误: {shlex.quote(path)} 的目标不是 dict 类型",
                file=sys.stderr,
            )
            sys.exit(1)
        entry[field] = parsed
        save_state(data)
        return

    # ── 默认：全量输出 ──
    data = load_state()
    if json_output:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        yaml.dump(
            data,
            sys.stdout,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            explicit_start=True,
        )


# ════════════════════════════════════════════════════════════════
# dai tree --sync
# ════════════════════════════════════════════════════════════════


def _find_agents_md() -> str | None:
    """在项目根目录查找 AGENTS.md"""
    cwd = os.getcwd()
    for candidate in [
        os.path.join(cwd, "AGENTS.md"),
    ]:
        if os.path.isfile(candidate):
            return candidate
    return None


def _build_tree_json(state_data: dict) -> str:
    """从 state.yaml 构建注入到 AGENTS.md 的 JSON block。"""
    tasks_data = state_data.get("tasks", {})
    spaces_data = state_data.get("spaces", {})

    # 构建简化的任务树
    task_list = []
    for num, task in sorted(tasks_data.items(), key=lambda x: int(x[0])):
        entry = {
            "number": int(num),
            "title": task.get("title", ""),
            "state": task.get("state", "pending"),
        }
        if task.get("parent"):
            entry["parent"] = task["parent"]
        if task.get("spaces"):
            entry["spaces"] = task["spaces"]
        task_list.append(entry)

    # 构建空间锁状态
    lock_map = {}
    for path, cfg in sorted(spaces_data.items()):
        lock = cfg.get("lock") if cfg else None
        lock_map[path] = lock

    tree = {
        "tasks": task_list,
        "locks": lock_map,
    }
    return json.dumps(tree, indent=2, ensure_ascii=False)


@app.command
def tree(
    sync: Annotated[
        bool,
        Parameter(name=["--sync"], help="注入 AGENTS.md json block"),
    ] = True,
    verbose: VerboseFlag = 0,
):
    """注入 AGENTS.md json block。

    在 AGENTS.md 中查找 <!-- diy:tree:begin --> / <!-- diy:tree:end -->
    之间的区域，替换为当前 state.yaml 的 JSON 投影。
    """
    set_verbosity(verbose)

    agents_path = _find_agents_md()
    if not agents_path:
        print("错误: 当前目录未找到 AGENTS.md", file=sys.stderr)
        sys.exit(1)

    with open(agents_path, encoding="utf-8") as fh:
        content = fh.read()

    state_data = load_state()
    tree_json = _build_tree_json(state_data)

    # 构建替换 block
    block = f"{_BEGIN_MARKER}\n```json\n{tree_json}\n```\n{_END_MARKER}"

    pattern = re.compile(
        rf"{re.escape(_BEGIN_MARKER)}.*?{re.escape(_END_MARKER)}",
        re.DOTALL,
    )

    if pattern.search(content):
        new_content = pattern.sub(block, content)
    else:
        # 追加到文件末尾
        new_content = content.rstrip("\n") + "\n\n" + block + "\n"

    with open(agents_path, "w", encoding="utf-8") as fh:
        fh.write(new_content)

    print(f"已同步: {agents_path}")


# ════════════════════════════════════════════════════════════════
# 辅助
# ════════════════════════════════════════════════════════════════


def _parse_path(raw: str) -> tuple[str, str, str]:
    """解析 --set path 为 (section, key, field)。

    path 格式：<section>.<key>.<field>，从右边第二个 . 分割。
    section=第一个.之前，field=最后一个.之后，key=中间部分。
    """
    parts = raw.split(".")
    if len(parts) < 3:
        raise ValueError(
            f"path 格式必须为 <section>.<key>.<field>，收到 {raw!r}"
        )
    return parts[0], ".".join(parts[1:-1]), parts[-1]


def _parse_value(raw: str) -> object:
    """智能解析 --set-val 值：JSON → int → bool → 字符串。"""
    # 试 JSON（列表、字典、数字、布尔、null）
    with suppress(ValueError):
        return json.loads(raw)
    # 试整数
    with suppress(ValueError):
        return int(raw)
    # 试布尔关键字
    if raw.lower() in ("true", "false"):
        return raw.lower() == "true"
    # 兜底字符串
    return raw


# ════════════════════════════════════════════════════════════════
# 入口
# ════════════════════════════════════════════════════════════════


def main():
    try:
        app(sys.argv[1:] if len(sys.argv) > 1 else ["--help"])
    except SystemExit:
        raise
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
