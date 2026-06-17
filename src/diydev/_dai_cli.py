"""dai CLI — diy agent 接口

命令:
  dai state          全量输出 state.yaml（YAML，默认）
  dai state --json   全量输出 state.yaml（JSON）
  dai tree --sync    注入 AGENTS.md json block
  dai doctor         健康自检（Socket/多实例/state.yaml）
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import sys
from contextlib import suppress
from typing import Annotated, Any

import yaml
from cyclopts import App, Parameter

from ._dai_scan import find_spaces, find_workspace_root
from ._log import VerboseFlag, set_verbosity
from ._state import create_task, delete_task, get_task, list_tasks, load_state, save_state, update_task_field

app = App(
    name="dai",
    help="diy agent 接口 — state 查询与同步\n\n  子命令 dai app ... → 管控台探针（透传到 app socket）",
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
# dai scan
# ════════════════════════════════════════════════════════════════


@app.command
def scan(
    json_output: Annotated[
        bool,
        Parameter(name=["--json"], help="JSON 格式输出"),
    ] = False,
    path: Annotated[
        str | None,
        Parameter(help="扫描起始目录（默认当前工作目录）"),
    ] = None,
):
    """扫描 workspace 与 spaces — 向上查找 diy.yaml，向下发现 .git。"""
    start = os.path.realpath(path) if path else os.path.realpath(os.getcwd())

    workspace_root = find_workspace_root(start)
    if workspace_root is None:
        print("错误: 未找到 diy.yaml（向上扫描到 $HOME 为止）", file=sys.stderr)
        sys.exit(1)

    spaces = find_spaces(workspace_root)

    result: dict = {
        "workspace": workspace_root,
        "spaces": spaces,
    }

    if json_output:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        yaml.dump(
            result,
            sys.stdout,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            explicit_start=True,
        )


# ════════════════════════════════════════════════════════════════
# dai profile
# ════════════════════════════════════════════════════════════════

profile_app = App(
    name="profile",
    help="查询 state.yaml 中的 profile 预设",
)


@profile_app.command(name="list")
def list_profiles(
    json_output: Annotated[
        bool,
        Parameter(name=["--json"], help="JSON 格式输出"),
    ] = False,
):
    """列出所有 profile（YAML 默认，--json 切 JSON）。"""
    data = load_state()
    profiles = data.get("profiles", {})
    if json_output:
        print(json.dumps(profiles, indent=2, ensure_ascii=False))
    else:
        yaml.dump(
            profiles,
            sys.stdout,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            explicit_start=True,
        )


@profile_app.command
def show(
    name: Annotated[str, Parameter(help="profile 名称")],
    json_output: Annotated[
        bool,
        Parameter(name=["--json"], help="JSON 格式输出"),
    ] = False,
):
    """查看单个 profile。"""
    data = load_state()
    profiles = data.get("profiles", {})
    if name not in profiles:
        print(f"错误: profile {shlex.quote(name)} 不存在", file=sys.stderr)
        sys.exit(1)
    profile_data = profiles[name]
    if json_output:
        print(json.dumps(profile_data, indent=2, ensure_ascii=False))
    else:
        yaml.dump(
            profile_data,
            sys.stdout,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            explicit_start=True,
        )


app.command(profile_app)


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
    """从 state.yaml + ~/.diy/d/ 任务数据构建注入到 AGENTS.md 的 JSON block。"""
    # 从任务目录加载，而非 state.yaml
    tasks_data = list_tasks()
    spaces_data = state_data.get("spaces", {})

    # 构建简化的任务树
    task_list = []
    # local task 先按编号排，再按 URI 排
    for uri, task in sorted(tasks_data.items()):
        entry = {
            "uri": uri,
            "title": task.get("title", ""),
            "state": task.get("state", "pending"),
        }
        src = task.get("source", {})
        entry["source"] = src
        if task.get("parent"):
            entry["parent"] = task["parent"]
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
# dai subject
# ════════════════════════════════════════════════════════════════

subject_app = App(name="subject", help="Subject 树管理")

_HOME = os.path.expanduser("~")


def _norm(path: str) -> str:
    """把路径统一为 ~/... 格式存储。"""
    expanded = os.path.abspath(os.path.expanduser(path))
    if expanded.startswith(_HOME + "/"):
        return "~" + expanded[len(_HOME):]
    if expanded == _HOME:
        return "~"
    return expanded


def _subject_is_git(path: str) -> bool:
    """实时检测 subject 目录是否为 git 仓库。"""
    full = os.path.expanduser(path)
    return os.path.isdir(os.path.join(full, ".git")) or os.path.isfile(os.path.join(full, ".git"))


def _enrich(subjects: dict[str, dict]) -> dict[str, dict]:
    """给 subject 条目添加实时检测的 is_git 字段。"""
    return {
        p: {**entry, "is_git": _subject_is_git(p)}
        for p, entry in subjects.items()
    }


@subject_app.command(name="add")
def subject_add(
    path: Annotated[str, Parameter(help="subject 路径（如 ~/git/diy/_diy）")],
    desc: Annotated[str | None, Parameter(name="--desc", help="描述")] = None,
    json_output: Annotated[
        bool, Parameter(name=["--json"], help="JSON 格式输出")
    ] = False,
):
    """注册 subject。自动检测是否为 git 仓库。"""
    path_n = _norm(path)
    data = load_state()
    subjects = data.setdefault("subjects", {})

    if path_n in subjects:
        print(f"错误: subject {shlex.quote(path_n)} 已存在", file=sys.stderr)
        sys.exit(1)

    entry: dict[str, object] = {}
    if desc:
        entry["description"] = desc
    subjects[path_n] = entry
    save_state(data)

    result = {"status": "success", "data": {"path": path_n, **entry}}
    if json_output:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        yaml.dump(result, sys.stdout, allow_unicode=True, default_flow_style=False, sort_keys=False)


@subject_app.command(name="list")
def subject_list(
    json_output: Annotated[
        bool, Parameter(name=["--json"], help="JSON 格式输出")
    ] = False,
):
    """扁平列表（实时 is_git 检测）。"""
    data = load_state()
    subjects = _enrich(data.get("subjects", {}))
    if json_output:
        print(json.dumps(subjects, indent=2, ensure_ascii=False))
    else:
        yaml.dump(subjects, sys.stdout, allow_unicode=True, default_flow_style=False, sort_keys=False)


@subject_app.command(name="tree")
def subject_tree(
    json_output: Annotated[
        bool, Parameter(name=["--json"], help="JSON 格式输出")
    ] = False,
):
    """树状展示（实时 is_git 检测）。"""
    data = load_state()
    subjects = _enrich(data.get("subjects", {}))

    tree = _build_subject_tree(subjects)
    if json_output:
        print(json.dumps(tree, indent=2, ensure_ascii=False))
    else:
        yaml.dump(tree, sys.stdout, allow_unicode=True, default_flow_style=False, sort_keys=False)


@subject_app.command(name="show")
def subject_show(
    path: Annotated[str, Parameter(help="subject 路径")],
    json_output: Annotated[
        bool, Parameter(name=["--json"], help="JSON 格式输出")
    ] = False,
):
    """查看单个 subject（含实时 is_git 检测）。"""
    path_n = _norm(path)
    data = load_state()
    subjects = data.get("subjects", {})
    if path_n not in subjects:
        print(f"subject {shlex.quote(path_n)} 不存在", file=sys.stderr)
        sys.exit(1)
    entry = dict(subjects[path_n])
    entry["is_git"] = _subject_is_git(path_n)
    if json_output:
        print(json.dumps(entry, indent=2, ensure_ascii=False))
    else:
        yaml.dump(entry, sys.stdout, allow_unicode=True, default_flow_style=False, sort_keys=False)


@subject_app.command(name="remove")
def subject_remove(
    path: Annotated[str, Parameter(help="subject 路径")],
    json_output: Annotated[
        bool, Parameter(name=["--json"], help="JSON 格式输出")
    ] = False,
):
    """删除 subject。同时删除子 subject。"""
    path_n = _norm(path)
    data = load_state()
    subjects = data.get("subjects", {})

    if path_n not in subjects:
        print(f"错误: subject {shlex.quote(path_n)} 不存在", file=sys.stderr)
        sys.exit(1)

    # 删除自身及子节点
    to_delete = [p for p in subjects if p == path_n or p.startswith(path_n + "/")]
    for p in to_delete:
        del subjects[p]
    save_state(data)

    result = {"status": "success", "data": {"path": path_n, "removed": len(to_delete)}}
    if json_output:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        yaml.dump(result, sys.stdout, allow_unicode=True, default_flow_style=False, sort_keys=False)


@subject_app.command(name="scan")
def subject_scan(
    root: Annotated[str, Parameter(help="扫描根目录")],
    json_output: Annotated[
        bool, Parameter(name=["--json"], help="JSON 格式输出")
    ] = False,
):
    """扫描文件系统，发现 git 仓库作为 subject。"""
    root_path = os.path.abspath(os.path.expanduser(root))
    if not os.path.isdir(root_path):
        print(f"错误: 目录不存在 {shlex.quote(root)}", file=sys.stderr)
        sys.exit(1)

    found: dict[str, dict[str, object]] = {}
    for dirpath, dirs, _ in os.walk(root_path):
        if os.path.isdir(os.path.join(dirpath, ".git")) or os.path.isfile(os.path.join(dirpath, ".git")):
            found[_norm(dirpath)] = {}
            dirs.clear()  # 不深入 git 仓库内部

    # 写入 state.yaml
    data = load_state()
    subjects = data.setdefault("subjects", {})
    subjects.update(found)
    save_state(data)

    result = {"status": "success", "data": {"found": len(found)}}
    if json_output:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        yaml.dump(result, sys.stdout, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _build_subject_tree(subjects: dict[str, dict]) -> dict[str, object]:
    """从扁平 subject 字典构建嵌套树。"""
    sorted_paths = sorted(subjects.keys(), key=lambda p: (p.count("/"), p))
    tree: dict[str, object] = {}
    for path in sorted_paths:
        _place_in_tree(tree, path, dict(subjects[path]))
    return tree


def _place_in_tree(tree: dict[str, object], path: str, entry: dict) -> None:
    """递归在树中找 path 的父级并插入。"""
    # 找 path 的父级路径
    parent = "/".join(path.lstrip("~/").split("/")[:-1])
    if not parent:
        # 根级节点，直接挂 tree
        tree[path] = entry
        return
    parent_key = "~/" + parent

    # 在 tree 中找 parent_key（递归搜索所有层级）
    def _find(node: dict, target: str) -> dict | None:
        for k, v in node.items():
            if k == target and isinstance(v, dict):
                return v
            if isinstance(v, dict):
                children = v.get("children")
                if children:
                    result = _find(children, target)
                    if result:
                        return result
        return None

    parent_node = _find(tree, parent_key)
    if parent_node is not None:
        children = parent_node.setdefault("children", {})
        children[path] = entry
    else:
        # 父级不存在，挂在根
        tree[path] = entry


app.command(subject_app)


# ════════════════════════════════════════════════════════════════
# dai task — 任务管理
# ════════════════════════════════════════════════════════════════

task_app = App(name="task", help="任务管理")


def _notify_app_reload() -> None:
    """通知 GUI app 刷新任务树（如果正在运行）。失败静默。"""
    import socket as _sock
    socket_path = os.path.join(
        os.environ.get("DIY_HOME", os.path.expanduser("~/.diy")),
        "app.sock",
    )
    try:
        s = _sock.socket(_sock.AF_UNIX, _sock.SOCK_STREAM)
        s.settimeout(2)
        s.connect(socket_path)
        s.sendall(b"ai reload\n")
        s.shutdown(_sock.SHUT_WR)
        s.close()
    except OSError:
        pass


@task_app.command(name="create")
def task_create(
    title: Annotated[str, Parameter(name="--title", help="任务标题")],
    subject: Annotated[str, Parameter(name="--subject", help="subject 路径")],
    parent: Annotated[str | None, Parameter(name="--parent", help="父任务 URI")] = None,
    detail: Annotated[str | None, Parameter(name="--detail", help="任务详情")] = None,
    body_file: Annotated[str | None, Parameter(name="--body-file", help="markdown body 文件路径")] = None,
    source_type: Annotated[str, Parameter(name="--source-type", help="任务来源类型")] = "local",
    source_uri: Annotated[str | None, Parameter(name="--source-uri", help="外部任务 URI（非 local 必填）")] = None,
    json_output: Annotated[
        bool, Parameter(name=["--json"], help="JSON 格式输出")
    ] = False,
):
    """创建任务。subject 必须已注册。"""
    subject_n = _norm(subject)
    data = load_state()
    subjects = data.get("subjects", {})

    if subject_n not in subjects:
        print(f"错误: subject {shlex.quote(subject_n)} 未注册", file=sys.stderr)
        sys.exit(1)

    if parent is not None and get_task(parent) is None:
        print(f"错误: parent {parent} 不存在", file=sys.stderr)
        sys.exit(1)

    body = ""
    if body_file:
        try:
            body = Path(body_file).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"错误: 无法读取 body 文件 {shlex.quote(body_file)}: {exc}", file=sys.stderr)
            sys.exit(1)

    try:
        uri = create_task(
            title=title, subject=subject_n, parent=parent, detail=detail,
            source_type=source_type, source_uri=source_uri, body=body,
        )
    except ValueError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        sys.exit(1)

    task = get_task(uri) or {}
    result = {"status": "success", "data": task}
    _notify_app_reload()
    if json_output:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        yaml.dump(result, sys.stdout, allow_unicode=True, default_flow_style=False, sort_keys=False)


@task_app.command(name="link")
def task_link(
    title: Annotated[str, Parameter(name="--title", help="任务标题")],
    subject: Annotated[str, Parameter(name="--subject", help="subject 路径")],
    source_uri: Annotated[str, Parameter(name="--source-uri", help="外部任务 URI（如 github.com/owner/repo/issues/58）")],
    parent: Annotated[str | None, Parameter(name="--parent", help="父任务 URI")] = None,
    detail: Annotated[str | None, Parameter(name="--detail", help="任务详情")] = None,
    json_output: Annotated[
        bool, Parameter(name=["--json"], help="JSON 格式输出")
    ] = False,
):
    """链接外部任务（GitHub issue / PR 等）。不修改远端，仅建立本地引用。"""
    if not source_uri:
        print("错误: --source-uri 必填", file=sys.stderr)
        sys.exit(1)

    # 从 source_uri 格式推测 type
    if "github.com" in source_uri:
        if "/pull/" in source_uri:
            source_type = "github_pr"
        else:
            source_type = "github_issue"
    else:
        source_type = "external"

    subject_n = _norm(subject)
    data = load_state()
    subjects = data.get("subjects", {})
    if subject_n not in subjects:
        print(f"错误: subject {shlex.quote(subject_n)} 未注册", file=sys.stderr)
        sys.exit(1)
    if parent is not None and get_task(parent) is None:
        print(f"错误: parent {parent} 不存在", file=sys.stderr)
        sys.exit(1)

    try:
        uri = create_task(
            title=title, subject=subject_n, parent=parent, detail=detail,
            source_type=source_type, source_uri=source_uri,
        )
    except ValueError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        sys.exit(1)

    task = get_task(uri) or {}
    result = {"status": "success", "data": task}
    _notify_app_reload()
    if json_output:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        yaml.dump(result, sys.stdout, allow_unicode=True, default_flow_style=False, sort_keys=False)


@task_app.command(name="list")
def task_list(
    json_output: Annotated[
        bool, Parameter(name=["--json"], help="JSON 格式输出")
    ] = False,
):
    """列出所有任务。"""
    tasks_out: dict[str, Any] = {}
    for k, v in list_tasks().items():
        tasks_out[k] = dict(v)
    output = {"tasks": tasks_out}
    if json_output:
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        yaml.dump(output, sys.stdout, allow_unicode=True, default_flow_style=False, sort_keys=False)


@task_app.command(name="show")
def task_show(
    uri: Annotated[str, Parameter(help="任务 URI")],
    json_output: Annotated[
        bool, Parameter(name=["--json"], help="JSON 格式输出")
    ] = False,
):
    """查看单个任务。"""
    task = get_task(uri)
    if task is None:
        print(f"错误: 任务 {uri} 不存在", file=sys.stderr)
        sys.exit(1)
    body = task.pop("body", "") if not json_output else task.get("body", "")
    if json_output:
        print(json.dumps(task, indent=2, ensure_ascii=False))
    else:
        yaml.dump(task, sys.stdout, allow_unicode=True, default_flow_style=False, sort_keys=False)
        if body:
            print()
            print(body)


@task_app.command(name="edit")
def task_edit(
    uri: Annotated[str, Parameter(help="任务 URI")],
    title: Annotated[str | None, Parameter(name="--title", help="新标题")] = None,
    state: Annotated[str | None, Parameter(name="--state", help="新状态")] = None,
    subject: Annotated[str | None, Parameter(name="--subject", help="新 subject")] = None,
    parent: Annotated[str | None, Parameter(name="--parent", help="新父任务 URI")] = None,
    detail: Annotated[str | None, Parameter(name="--detail", help="新详情")] = None,
    body_file: Annotated[str | None, Parameter(name="--body-file", help="markdown body 文件路径")] = None,
    json_output: Annotated[
        bool, Parameter(name=["--json"], help="JSON 格式输出")
    ] = False,
):
    """编辑任务。返回编辑后的完整字段。"""
    if get_task(uri) is None:
        print(f"错误: 任务 {uri} 不存在", file=sys.stderr)
        sys.exit(1)

    fields: dict[str, Any] = {}
    if title is not None:
        fields["title"] = title
    if state is not None:
        fields["state"] = state
    if subject is not None:
        fields["subject"] = _norm(subject)
    if parent is not None:
        if get_task(parent) is None:
            print(f"错误: parent {parent} 不存在", file=sys.stderr)
            sys.exit(1)
        fields["parent"] = parent
    if detail is not None:
        fields["detail"] = detail
    if body_file is not None:
        try:
            fields["body"] = Path(body_file).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"错误: 无法读取 body 文件 {shlex.quote(body_file)}: {exc}", file=sys.stderr)
            sys.exit(1)

    task = update_task_field(uri, **fields)
    result = {"status": "success", "data": task}
    _notify_app_reload()
    if json_output:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        yaml.dump(result, sys.stdout, allow_unicode=True, default_flow_style=False, sort_keys=False)


@task_app.command(name="delete")
def task_delete(
    uri: Annotated[str, Parameter(help="任务 URI")],
    json_output: Annotated[
        bool, Parameter(name=["--json"], help="JSON 格式输出")
    ] = False,
):
    """删除本地任务。外部任务请用 unlink。"""
    task = get_task(uri)
    if task is None:
        print(f"错误: 任务 {uri} 不存在", file=sys.stderr)
        sys.exit(1)

    src = task.get("source", {})
    if src.get("type") != "local":
        print(f"错误: {uri} 是外部任务，请用 dai task unlink {uri} 解绑", file=sys.stderr)
        sys.exit(1)

    delete_task(uri)
    result = {"status": "success"}
    _notify_app_reload()
    if json_output:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        yaml.dump(result, sys.stdout, allow_unicode=True, default_flow_style=False, sort_keys=False)


@task_app.command(name="unlink")
def task_unlink(
    uri: Annotated[str, Parameter(help="外部任务 URI（如 github.com/owner/repo/issues/58）")],
    json_output: Annotated[
        bool, Parameter(name=["--json"], help="JSON 格式输出")
    ] = False,
):
    """解绑外部任务引用。不删除远端 issue，仅移除本地记录。"""
    task = get_task(uri)
    if task is None:
        print(f"错误: 任务 {uri} 不存在", file=sys.stderr)
        sys.exit(1)

    src = task.get("source", {})
    if src.get("type") == "local":
        print(f"错误: {uri} 是本地任务，请用 dai task delete {uri}", file=sys.stderr)
        sys.exit(1)

    delete_task(uri)
    result = {"status": "success"}
    _notify_app_reload()
    if json_output:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        yaml.dump(result, sys.stdout, allow_unicode=True, default_flow_style=False, sort_keys=False)


app.command(task_app)


# ════════════════════════════════════════════════════════════════
# dai app — PySide6 管控台
# ════════════════════════════════════════════════════════════════


# ════════════════════════════════════════════════════════════════
# dai app → socket 透传
# ════════════════════════════════════════════════════════════════


def _app_probe(args: list[str]) -> None:
    """透传参数到 app socket，连不上自动启动 app。"""
    import socket as sock
    import subprocess
    import time as _time

    socket_path = os.path.expanduser("~/.diy/app.sock")
    # dai app 是 AI 原生接口，所有命令加 ai 前缀
    if not args:
        args = ["ai", "--help"]
    elif args[0] in ("--help", "-h"):
        args = ["ai"] + args  # ai --help
    elif args[0] == "ai":
        pass  # 已有前缀
    elif args[0] != "--version":
        args = ["ai"] + args

    def _send() -> int:
        """发送命令到 socket，返回 exit code（0=成功，1=失败）。"""
        try:
            s = sock.socket(sock.AF_UNIX, sock.SOCK_STREAM)
            s.settimeout(5)
            s.connect(socket_path)
            s.sendall((" ".join(args) + "\n").encode("utf-8"))
            s.shutdown(sock.SHUT_WR)
            buf: list[bytes] = []
            while True:
                data = s.recv(4096)
                if not data:
                    break
                buf.append(data)
            s.close()
            sys.stdout.write(b"".join(buf).decode("utf-8"))
            return 0
        except (FileNotFoundError, ConnectionRefusedError, OSError):
            return 1

    if _send() == 0:
        return

    # 连不上 → 启动 app
    # __file__ = src/diydev/_dai_cli.py, repo = _diy/
    srcdir = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(os.path.dirname(srcdir))
    sha_sh = os.path.join(repo, "sha.sh")
    if not os.path.exists(sha_sh):
        print("错误: 找不到 sha.sh，无法启动 app", file=sys.stderr)
        sys.exit(1)

    print("⏳ 正在启动 diy 管控台...", file=sys.stderr)
    subprocess.Popen(
        ["bash", sha_sh, "app"],
        cwd=repo,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # 等待 socket 就绪（最多 10 秒）
    deadline = _time.time() + 10
    while _time.time() < deadline:
        if os.path.exists(socket_path):
            _time.sleep(0.5)  # 让 app 初始化完
            if _send() == 0:
                return
        _time.sleep(0.3)

    print("错误: app 启动超时，请检查日志", file=sys.stderr)
    sys.exit(1)


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


def dai_doctor() -> None:
    """健康自检 — 分层检查 Socket 状态、多实例、state.yaml。
    
    有 app 运行时走 socket 获取完整上下文（含 inode 对比），
    无 app 运行时降级为客户端探针（检测 sock 残留/缺失）。
    """
    from diydev.app._doctor import format_report, run_check

    # 优先走 socket（运行中的 app 有完整上下文）
    import socket as _sock
    socket_path = os.path.expanduser("~/.diy/app.sock")
    try:
        s = _sock.socket(_sock.AF_UNIX, _sock.SOCK_STREAM)
        s.settimeout(3)
        s.connect(socket_path)
        s.sendall(b"ai doctor\n")
        s.shutdown(_sock.SHUT_WR)
        buf: list[bytes] = []
        while True:
            data = s.recv(4096)
            if not data:
                break
            buf.append(data)
        s.close()
        sys.stdout.write(b"".join(buf).decode("utf-8"))
        return
    except OSError:
        pass  # socket 不通 → 独立检查

    # socket 不通 → 独立检查
    issues = run_check()
    print(format_report(issues))
    if any(i.severity == "critical" for i in issues):
        sys.exit(1)


def main():
    # dai app → 透传到 socket，不经过 cyclopts
    if len(sys.argv) > 1 and sys.argv[1] == "app":
        _app_probe(sys.argv[2:] if len(sys.argv) > 2 else ["--help"])
        return

    # dai doctor → 自检
    if len(sys.argv) > 1 and sys.argv[1] == "doctor":
        dai_doctor()
        return

    try:
        app(sys.argv[1:] if len(sys.argv) > 1 else ["--help"])
    except SystemExit:
        raise
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
