"""dai CLI — diy agent 接口

命令:
  dai task ...         任务 CRUD（star/unstar/list/show/create/edit/delete/link/unlink/sync）
  dai subject ...      subject 树管理（add/list/tree/show/remove/scan）
  dai profile ...      profile 预设管理
  dai ui ...           UI 交互（tree/status/agents/node/reload/title/notify/metrics/shutdown/chat）
  dai doctor           健康自检
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import sys
from contextlib import suppress
from pathlib import Path
from typing import Annotated, Any

import yaml
from cyclopts import App, Parameter

from ._dai_scan import find_spaces, find_workspace_root
from ._state import (
    create_task,
    delete_task,
    diy_home,
    get_task,
    is_starred,
    list_starred,
    list_tasks,
    load_state,
    save_state,
    star_task,
    unstar_task,
    update_task_field,
)

app = App(
    name="dai",
    help="diy agent 接口 — state 查询与同步\n\n  子命令 dai app ... → 管控台探针（透传到 app socket）",
    version_flags=[],
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
        diy_home(),
        "app.sock",
    )
    try:
        s = _sock.socket(_sock.AF_UNIX, _sock.SOCK_STREAM)
        s.settimeout(2)
        s.connect(socket_path)
        s.sendall(b"diy ui reload\n")
        s.shutdown(_sock.SHUT_WR)
        s.close()
    except OSError:
        pass


# ════════════════════════════════════════════════════════════════
# dai task star / unstar
# ════════════════════════════════════════════════════════════════

@task_app.command(name="star")
def task_star(
    uri: Annotated[str, Parameter(help="任务 URI")],
    json_output: Annotated[
        bool, Parameter(name=["--json"], help="JSON 格式输出")
    ] = False,
):
    """star 任务（创建 symlink 到 ~/.diy/star/）。"""
    task = get_task(uri)
    if task is None:
        print(f"错误: 任务 {uri} 不存在", file=sys.stderr)
        sys.exit(1)

    try:
        star_task(uri)
    except FileNotFoundError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        sys.exit(1)

    _notify_app_reload()
    result = {"status": "success", "data": {"uri": uri, "starred": True}}
    if json_output:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        yaml.dump(result, sys.stdout, allow_unicode=True, default_flow_style=False, sort_keys=False)


@task_app.command(name="unstar")
def task_unstar(
    uri: Annotated[str, Parameter(help="任务 URI")],
    json_output: Annotated[
        bool, Parameter(name=["--json"], help="JSON 格式输出")
    ] = False,
):
    """unstar 任务（删除 symlink，数据不动）。"""
    task = get_task(uri)
    if task is None:
        print(f"错误: 任务 {uri} 不存在", file=sys.stderr)
        sys.exit(1)

    unstar_task(uri)

    _notify_app_reload()
    result = {"status": "success", "data": {"uri": uri, "starred": False}}
    if json_output:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        yaml.dump(result, sys.stdout, allow_unicode=True, default_flow_style=False, sort_keys=False)


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

    # 自动 star 新任务
    star_task(uri)

    task = get_task(uri) or {}
    task["starred"] = True
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


# ════════════════════════════════════════════════════════════════
# dai task sync — 同步外部任务
# ════════════════════════════════════════════════════════════════


_GH_STATE_MAP = {
    "OPEN": "active",
    "CLOSED": "done",
    "MERGED": "done",
}


def _gh_uri_parse(source_uri: str) -> tuple[str, str, str] | None:
    """解析 GitHub URI，返回 (owner, repo, issue_number)。

    github.com/owner/repo/issues/N
    """
    m = re.match(r"github\.com/([^/]+)/([^/]+)/issues/(\d+)", source_uri)
    if not m:
        return None
    return m.group(1), m.group(2), m.group(3)


def _sync_github_issue(uri: str, task: dict[str, Any]) -> dict[str, Any] | str:
    """同步单个 GitHub issue 到本地。成功返回更新后的 task dict，失败返回错误字符串。"""
    import subprocess

    src = task.get("source", {})
    source_uri = src.get("uri", uri)
    parsed = _gh_uri_parse(source_uri)
    if not parsed:
        return f"无法解析 GitHub URI: {source_uri}"

    owner, repo, number = parsed
    repo_full = f"{owner}/{repo}"

    try:
        result = subprocess.run(
            ["gh", "issue", "view", number, "--repo", repo_full,
             "--json", "title,body,state,updatedAt"],
            capture_output=True, text=True, timeout=15,
        )
    except FileNotFoundError:
        return "gh CLI 未安装，请先安装 GitHub CLI (brew install gh)"
    except subprocess.TimeoutExpired:
        return f"请求 {repo_full}#{number} 超时"

    if result.returncode != 0:
        err = result.stderr.strip()
        if "issue not found" in err.lower() or "not found" in err.lower():
            # GitHub issue 已删除 → 取消关注（数据不动）
            try:
                unstar_task(uri)
                return f"GitHub issue 已不存在，已取消关注（unstar）"
            except FileNotFoundError:
                return "GitHub issue 已不存在（本地数据同步前已移除）"
        return f"gh 调用失败: {err}"

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return f"gh 返回非 JSON: {result.stdout[:200]}"

    title = data.get("title", task.get("title", ""))
    body = data.get("body", "") or ""
    gh_state = _GH_STATE_MAP.get(data.get("state", ""), "active")

    return update_task_field(
        uri,
        title=title,
        state=gh_state,
        body=body,
    )


@task_app.command(name="sync")
def task_sync(
    uri: Annotated[str | None, Parameter(help="任务 URI（如 github.com/owner/repo/issues/58），--all 时省略")] = None,
    all: Annotated[
        bool, Parameter(name=["--all", "-a"], help="同步所有外部任务")
    ] = False,
    json_output: Annotated[
        bool, Parameter(name=["--json"], help="JSON 格式输出")
    ] = False,
):
    """同步外部任务内容到本地。

    从远端拉取最新 title / state / body 并更新本地 AGENTS.md。
    目前支持：GitHub issue（依赖 gh CLI）。

    用法:
      dai task sync <uri>          同步单个任务
      dai task sync --all          同步所有聚焦任务及其子树
    """
    if not uri and not all:
        print("错误: 请指定任务 URI 或使用 --all 同步全部", file=sys.stderr)
        sys.exit(1)

    if all:
        tasks = list_tasks()
        results: dict[str, str | dict[str, Any]] = {}
        total = 0
        for t_uri, t_data in sorted(tasks.items()):
            src = t_data.get("source", {})
            source_type = src.get("type", "")
            if source_type not in ("github_issue",):
                continue
            total += 1
            print(f"  ⟳ {_short_uri(t_uri)} {t_data.get('title', '')[:50]}...")
            r = _sync_github_issue(t_uri, t_data)
            if isinstance(r, str):
                print(f"    ✗ {r}")
                results[t_uri] = f"失败: {r}"
            else:
                results[t_uri] = r

        _notify_app_reload()

        ok = sum(1 for v in results.values() if isinstance(v, dict))
        fail = sum(1 for v in results.values() if isinstance(v, str))
        output = {
            "status": "success",
            "data": {
                "synced": ok,
                "failed": fail,
                "results": results,
            },
        }
        if json_output:
            print(json.dumps(output, indent=2, ensure_ascii=False))
        else:
            print(f"\n✅ 同步完成: {ok} 内容更新, {fail} 失败，共 {total} 个外部任务")
        if fail:
            sys.exit(1)
        return

    # 同步单个
    task = get_task(uri)
    if task is None:
        print(f"错误: 任务 {uri} 不存在", file=sys.stderr)
        sys.exit(1)

    src = task.get("source", {})
    source_type = src.get("type", "")

    if source_type == "github_issue":
        result = _sync_github_issue(uri, task)
    else:
        print(f"错误: {uri} 的类型 {source_type} 暂不支持同步", file=sys.stderr)
        sys.exit(1)

    if isinstance(result, str):
        print(f"错误: {result}", file=sys.stderr)
        sys.exit(1)

    _notify_app_reload()
    output = {"status": "success", "data": result}
    if json_output:
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        yaml.dump(output, sys.stdout, allow_unicode=True, default_flow_style=False, sort_keys=False)


@task_app.command(name="list")
def task_list(
    all: Annotated[
        bool, Parameter(name=["--all", "-a"], help="显示全部任务（含未 star 的）")
    ] = False,
    json_output: Annotated[
        bool, Parameter(name=["--json"], help="JSON 格式输出")
    ] = False,
):
    """列出任务。默认只显示 starred，--all 显示全部。"""
    if all:
        tasks = list_tasks()
    else:
        tasks = list_starred()

    tasks_out: dict[str, Any] = {}
    for k, v in tasks.items():
        task_data = dict(v)
        task_data["starred"] = is_starred(k)
        tasks_out[k] = task_data

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
# 辅助
# ════════════════════════════════════════════════════════════════


def _short_uri(uri: str) -> str:
    """URI 短显示：local/task/58 → local#58, github.com/.../58 → github#58"""
    if uri.startswith("local/"):
        num = uri.rstrip("/").rsplit("/", 1)[-1]
        return f"local#{num}"
    if "github.com" in uri:
        num = uri.rstrip("/").rsplit("/", 1)[-1]
        return f"github#{num}"
    return uri


# ════════════════════════════════════════════════════════════════
# 入口
# ════════════════════════════════════════════════════════════════


def dai_doctor() -> None:
    """健康自检 — 分层检查 Socket 状态、多实例、state.yaml。
    
    有 app 运行时走 socket 获取完整上下文（含 inode 对比），
    无 app 运行时降级为客户端探针（检测 sock 残留/缺失）。
    """
    # 优先走 socket（运行中的 app 有完整上下文）
    import socket as _sock

    from diydev.app._doctor import format_report, run_check
    socket_path = str(diy_home() / "app.sock")
    try:
        s = _sock.socket(_sock.AF_UNIX, _sock.SOCK_STREAM)
        s.settimeout(3)
        s.connect(socket_path)
        s.sendall(b"diy doctor\n")
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


def dai_doctor_metrics() -> None:
    """查看运行中 app 的指标快照。
    
    需要 app 正在运行。
    """
    resp = _send_to_socket("diy ui metrics", timeout=5.0)
    if resp is None:
        print("管控台未运行，无法获取指标", file=sys.stderr)
        sys.exit(1)
    import re  # noqa: PLC0415
    clean = re.sub(r"\x1b\[\d+(;\d+)*m", "", resp).strip()
    sys.stdout.write(clean)
    if not clean.endswith("\n"):
        sys.stdout.write("\n")


# ════════════════════════════════════════════════════════════════


# ════════════════════════════════════════════════════════════════
# dai agent — ACP agent 管理（全 async）
# ════════════════════════════════════════════════════════════════


def _dai_agent_dispatch(args: list[str]) -> None:
    if not args:
        _agent_print_help()
        return

    # 解析 --pi / --backend 标志
    backend: str = "hermes"
    provider: str | None = None
    model: str | None = None
    while args and args[0].startswith("--"):
        flag = args.pop(0)
        if flag == "--pi":
            backend = "pi"
        elif flag == "--hermes":
            backend = "hermes"
        elif flag == "--provider" and args:
            provider = args.pop(0)
        elif flag == "--model" and args:
            model = args.pop(0)
        else:
            print(f"未知标志: {flag}", file=sys.stderr)
            return

    if not args:
        _agent_print_help(backend)
        return

    sub = args[0]
    rest = args[1:]

    if sub == "list":
        _agent_cmd_list()
    elif sub == "status":
        _agent_cmd_status(rest)
    elif sub == "chat":
        _agent_cmd_chat(rest, backend=backend, provider=provider, model=model)
    elif sub == "send":
        _agent_cmd_send(rest, backend=backend, provider=provider, model=model)
    elif sub == "stop":
        _agent_cmd_stop(rest)
    elif sub in ("-h", "--help", "help"):
        _agent_print_help(backend)
    else:
        print(f"未知子命令: {sub}", file=sys.stderr)
        _agent_print_help(backend)


def _agent_print_help(backend: str = "hermes") -> None:
    pi_hint = " [--pi]" if backend == "hermes" else ""
    print(f"""dai agent — ACP agent 管理（全 async）

后端: {backend}

用法:
  dai agent{pi_hint} list               列出存活 agent
  dai agent{pi_hint} status <task>      查看 agent 状态
  dai agent{pi_hint} [--provider X] [--model Y] send <task> <文本>  发消息
  dai agent{pi_hint} [--provider X] [--model Y] chat <task>        交互终端
  dai agent{pi_hint} stop <task>        停止 agent
""")


def _get_session_counts(task_uri: str) -> tuple[int, int]:
    """返回 (活跃 session 数, 总历史 session 数)。"""
    alive = 0
    total = 0
    from diydev.core.agent_manager import get_manager
    if get_manager().get(task_uri):
        alive = 1
    # 从 Hermes DB 统计历史 session
    db = Path.home() / ".hermes" / "state.db"
    if db.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(str(db), timeout=1)
            sid = f"agent-{task_uri}"
            rows = conn.execute(
                "SELECT COUNT(DISTINCT session_id) FROM messages WHERE session_id=?", (sid,)
            ).fetchone()
            if rows and rows[0]:
                total = rows[0]
            conn.close()
        except Exception:
            pass
    return alive, total


def _agent_cmd_list() -> None:
    """列出存活 agent（当前进程）。"""
    from diydev.core.agent_manager import get_manager
    mgr = get_manager()
    agents = mgr.list()
    if not agents:
        print("(无活跃 ACP agent)")
        return
    print(f"{'TASK':<35s}  {'SESSION':<10s}  {'MSG'}")
    print("-" * 60)
    for a in agents:
        live, total = _get_session_counts(a.task_uri)
        cnt = f"{live}/{total}" if total else "—"
        print(f"{a.task_uri:<35s}  {cnt:<10s}  {a.message_count}条")


def _agent_cmd_status(args: list[str]) -> None:
    if not args:
        print("用法: dai agent status <task>", file=sys.stderr)
        return
    task_uri = args[0]
    from diydev.core.agent_manager import get_manager
    mgr = get_manager()
    a = mgr.get(task_uri)
    if a is None:
        print(f"agent {task_uri} 不活跃")
        return
    s = a.state_snapshot()
    live, total = _get_session_counts(task_uri)
    print(f"Task:     {s.task_uri}")
    print(f"会话:     {live}/{total}  (活跃/总计)")
    print(f"状态:     {s.state}")
    print(f"消息:     {s.message_count} 条")
    print(f"历史:")
    for m in a.history[-6:]:
        tag = "◈" if m.role == "assistant" else "✦"
        txt = m.content[:80] + ("..." if len(m.content) > 80 else "")
        print(f"  {tag} {txt}")


def _agent_cmd_chat(args: list[str], *, backend: str = "hermes", provider: str | None = None, model: str | None = None) -> None:
    if not args:
        print("用法: dai agent chat <task> [cwd]", file=sys.stderr)
        return
    task_uri = args[0]
    cwd = args[1] if len(args) > 1 else os.getcwd()
    from diydev.core.backend import AgentCallbacks
    cb = AgentCallbacks(
        on_delta=lambda t: (print(t, end="", flush=True)),
        on_reasoning=lambda t: print(f"\n[思考] {t}"),
        on_tool_start=lambda n, i, a: print(f"\n[工具] {n}"),
        on_error=lambda e: print(f"\n[错误] {e}", file=sys.stderr),
    )
    asyncio.run(_async_chat(task_uri, cwd, callbacks=cb, backend=backend, provider=provider, model=model))


async def _async_chat(task_uri: str, cwd: str, callbacks, *, backend: str = "hermes", provider: str | None = None, model: str | None = None) -> None:
    from diydev.core.agent_manager import get_manager
    mgr = get_manager()
    agent = await mgr.get_or_create(task_uri, cwd, backend=backend, provider=provider, model=model, callbacks=callbacks)
    print(f"Session: {agent.session_id}")
    print("输入消息 / Ctrl+D 退出")
    print("-" * 50)
    try:
        while True:
            line = await asyncio.to_thread(input, "\n> ")
            line = line.strip()
            if not line:
                continue
            if line in ("/quit", "/exit", "/q"):
                break
            print()
            reason = await agent.send(line)
            print(f"\n[完成: {reason}]")
    except (EOFError, KeyboardInterrupt):
        print()
    print("agent 仍在后台运行（重新输入 dai agent chat 可继续）")


def _agent_cmd_send(args: list[str], *, backend: str = "hermes", provider: str | None = None, model: str | None = None) -> None:
    if len(args) < 2:
        print("用法: dai agent send <task> <文本>", file=sys.stderr)
        return
    task_uri = args[0]
    text = " ".join(args[1:])
    from diydev.core.backend import AgentCallbacks
    cb = AgentCallbacks(
        on_delta=lambda t: (print(t, end="", flush=True)),
        on_error=lambda e: print(f"\n[错误] {e}", file=sys.stderr),
    )
    asyncio.run(_async_send(task_uri, text, callbacks=cb, backend=backend, provider=provider, model=model))


async def _async_send(task_uri: str, text: str, callbacks, *, backend: str = "hermes", provider: str | None = None, model: str | None = None) -> None:
    from diydev.core.agent_manager import get_manager
    mgr = get_manager()
    agent = await mgr.get_or_create(task_uri, os.getcwd(), backend=backend, provider=provider, model=model, callbacks=callbacks)
    reason = await agent.send(text)
    print(f"\n--- {reason} ---")
    print(f"历史: {len(agent.history)} 条（agent 继续存活）")


def _agent_cmd_stop(args: list[str]) -> None:
    if not args:
        print("用法: dai agent stop <task>", file=sys.stderr)
        return
    task_uri = args[0]
    asyncio.run(_async_stop(task_uri))


async def _async_stop(task_uri: str) -> None:
    from diydev.core.agent_manager import get_manager
    mgr = get_manager()
    agent = mgr.get(task_uri)
    if agent is None:
        print(f"agent {task_uri} 不活跃")
        return
    await mgr.stop(task_uri)
    print(f"agent {task_uri} 已停止")


def _send_to_socket(cmd_line: str, timeout: float = 5) -> str | None:
    """直接向 app.sock 发送一行文本，不经过 forward_to_app。

    用于 restart/shutdown 等需要控制 app 生命周期的命令。
    """
    import socket as sock
    socket_path = str(diy_home() / "app.sock")
    try:
        s = sock.socket(sock.AF_UNIX, sock.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(socket_path)
        s.sendall((cmd_line + "\n").encode("utf-8"))
        s.shutdown(sock.SHUT_WR)
        buf = b""
        while True:
            data = s.recv(4096)
            if not data:
                break
            buf += data
        s.close()
        return buf.decode("utf-8")
    except OSError:
        return None


def _local_shutdown():
    """关闭管控台（本地执行，不自动启动 app）。

    先试 socket 优雅关闭，socket 不存在或连不上时
    用 pkill 兜底杀 diydev.app.main 进程。
    """
    from ._forward import _send_to_socket

    socket_path = str(diy_home() / "app.sock")
    if os.path.exists(socket_path):
        resp = _send_to_socket(socket_path, "diy ui shutdown")
        if resp is not None:
            print(resp, file=sys.stderr)
            return

    # socket 不存在或不通 → 进程级兜底
    import subprocess
    kill = subprocess.run(
        ["pkill", "-f", "diydev.app.main"],
        capture_output=True, text=True, timeout=5,
    )
    if kill.returncode == 0:
        print("管控台已强制关闭", file=sys.stderr)
    else:
        print("管控台未运行", file=sys.stderr)


def _app_restart():
    """重启管控台：shutdown → 清理 socket → 启动 app。"""
    import subprocess
    import time as _time

    socket_path = str(diy_home() / "app.sock")

    # 1) shutdown — 不管成功与否，只发一次
    if os.path.exists(socket_path):
        print("⏳ 正在关闭管控台...", file=sys.stderr)
        _send_to_socket("diy ui shutdown", timeout=1.0)

    # 2) 短等 socket 消失（旧 app 响应 shutdown 后清理）
    _time.sleep(0.5)

    # 3) 强制清理残留 socket（旧 app 可能未及时清理或已死）
    try:
        os.unlink(socket_path)
    except FileNotFoundError:
        pass

    # 4) 启动 app — 直接用当前 Python 解释器，不依赖 sha.sh
    print("⏳ 正在启动管控台...", file=sys.stderr)
    proc = subprocess.Popen(
        [sys.executable, "-m", "diydev.app.main"],
        stdout=subprocess.DEVNULL,
        env={**os.environ},
    )

    # 5) 等 socket 就绪（文件存在 + 可连接）
    deadline = _time.time() + 15
    while _time.time() < deadline:
        if os.path.exists(socket_path):
            _time.sleep(0.3)
            if _send_to_socket("diy", timeout=1.0) is not None:
                print("管控台已重启", file=sys.stderr)
                return
        _time.sleep(0.3)

    # 6) 超时
    print("错误: 管控台启动超时，请检查日志", file=sys.stderr)
    sys.exit(1)


def _dai_ui() -> None:
    """启动 PySide6 管控台。"""
    import subprocess, sys
    from pathlib import Path

    app_main = Path(__file__).resolve().parent / "app" / "main.py"
    subprocess.run([sys.executable, str(app_main)] + sys.argv[2:])


def main():
    from ._forward import forward_to_app

    tokens = sys.argv[1:] if len(sys.argv) > 1 else []
    if not tokens:
        forward_to_app(["diy", "--help"])
        return

    cmd = tokens[0]

    # 本地执行（不走 app.sock，生命周期类命令不应自动启动 app）
    if cmd == "restart":
        _app_restart()
        return
    if cmd == "shutdown":
        _local_shutdown()
        return
    if cmd == "doctor" and len(tokens) > 1 and tokens[1] == "metrics":
        dai_doctor_metrics()
        return

    # ACP agent 命令（本地运行，不依赖 app socket）
    if cmd == "agent":
        _dai_agent_dispatch(tokens[1:])
        return

    # UI 桌面 app 启动
    if cmd == "ui":
        _dai_ui()
        return

    # 所有命令走 app.sock，协议前缀 diy = v1
    args = ["diy"] + tokens
    forward_to_app(args)


if __name__ == "__main__":
    main()
