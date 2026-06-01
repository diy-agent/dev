"""dev status - worktree tree overview

Shows all worktrees in a tree hierarchy with completion status.

Commands:
  dev status            简明树状概览（所有 worktree）
  dev status -v         展开详情（PR/issue/拓扑）
  dev status .          指定 worktree 的详细展示
  dev status -i <num>   查询指定 issue
"""

import json
import os
from typing import Optional, Annotated

from cyclopts import App, Parameter
from rich.console import Console
from rich.text import Text

from ._log import VerboseFlag, set_verbosity
from ._git_ops import (
    run,
    get_github_repo,
    get_main_branch,
    get_merge_base,
    parse_issue_number,
)
from ._gh_ops import gh_issue_view, gh_pr_list
from ._list_cmd import git_worktree_list, WorktreeInfo

status_app = App(name="status", help="worktree tree overview")
_console = Console()

# ===========================================================================
# 路径工具
# ===========================================================================

_HOME = os.path.expanduser("~")


def _short_path(path: str) -> str:
    """将绝对路径转为 ~/... 的短路径"""
    if path == _HOME:
        return "~"
    if path.startswith(_HOME + "/"):
        return "~" + path[len(_HOME) :]
    return path


# ===========================================================================
# 命令入口
# ===========================================================================


@status_app.default
def work_status(
    worktree_path: Annotated[
        Optional[str],
        Parameter(
            help="worktree path for detailed view (eg '.')",
        ),
    ] = None,
    verbose: VerboseFlag = 0,
    issue: Annotated[
        Optional[int],
        Parameter(
            name=["--issue", "-i"],
            help="query a specific issue (no worktree required)",
        ),
    ] = None,
):
    """Show worktree status overview or detailed view.

    Default: show all worktrees as a status tree.
    With worktree_path: show detailed status of a specific worktree.

    Examples:
      dev status            # tree overview of all worktrees
      dev status -v         # verbose tree with details
      dev status .          # detailed status of current worktree
      dev status -i 19      # query issue #19
    """
    set_verbosity(verbose)
    repo = get_github_repo()
    main_branch = get_main_branch()

    if issue is not None:
        _show_issue_view(issue, repo)
        return

    if worktree_path is not None:
        _show_detailed(worktree_path, repo, main_branch, verbose)
        return

    _show_tree(repo, main_branch, verbose)


# ===========================================================================
# 模式1: 树状概览（默认）
# ===========================================================================


def _show_tree(repo: str, main_branch: str, verbose: int):
    """渲染所有 worktree 的树状状态概览"""
    worktrees = git_worktree_list()
    rows = [_build_worktree_row(wt, repo, main_branch) for wt in worktrees]

    # 排序: error → wip → completed（main 在最后）
    _ORDER = {"error": 0, "wip": 1, "completed": 2}
    rows.sort(
        key=lambda r: (
            _ORDER.get(r["status"], 9),
            r["branch"] == main_branch,
            r["branch"],
        )
    )

    counts: dict[str, int] = {}
    for row in rows:
        st = row["status"]
        counts[st] = counts.get(st, 0) + 1
        _print_one_tree(row, verbose)
        _console.print()

    _print_summary(counts)


def _print_one_tree(row: dict, verbose: int):
    """打印一棵 worktree 的状态树"""
    wt: WorktreeInfo = row["wt"]
    status = row["status"]
    is_main = row["branch"] == get_main_branch()

    # ---- Level 1: [✅🟥🔳] 路径 (分支) #issue title ----
    ICON = {
        "completed": ("✅", "green"),
        "error": ("🟥", "red"),
        "wip": ("🔳", "dim"),
    }
    icon, color = ICON.get(status, ("🔳", "dim"))
    l1 = Text()
    l1.append(f"{icon} ", style=color)
    l1.append(_short_path(wt.path))
    l1.append(f"  ({row['branch']})")
    if row["issue_num"]:
        l1.append(f"  #{row['issue_num']}")
        _append_colored_state(l1, row["issue_state"])
        l1.append(f"  {row['issue_title']}")
    _console.print(l1)

    if is_main:
        # Main 分支：只显示错误和指导
        if row["errors"]:
            _print_errors(row["errors"])
        if row["guidance"]:
            _print_guidance(row["guidance"])
        return

    # ---- Level 2: PR ----
    pr_line = _format_pr(row)
    if pr_line:
        _console.print(Text(f"  {pr_line}"))

    # ---- ERRORS ----
    if row["errors"]:
        _print_errors(row["errors"])

    # ---- 指导 ----
    if row["guidance"]:
        _print_guidance(row["guidance"])


def _format_pr(row: dict) -> str:
    """格式化 PR 行（无 emoji，纯文本）"""
    if row["pr_state"] == "MERGED":
        return f"PR  #{row['pr_number']} 已合并"
    if row["pr_number"]:
        parts = [f"PR  #{row['pr_number']} {row['pr_state']}"]
        if row["pr_is_draft"]:
            parts.append("(草稿)")
        m = row["pr_mergeable"]
        if m == "MERGEABLE":
            parts.append("可合并")
        elif m == "CONFLICTING":
            parts.append("冲突")
        elif m == "UNKNOWN":
            parts.append("待审核")
        return "  ".join(parts)
    return "PR  ⏳ 未提交"


def _print_errors(errors: list[tuple[str, list[str]]]):
    """打印红色 ERRORS 区块"""
    _console.print(Text("  🟥 ERRORS:", style="red"))
    for title, lines in errors:
        if title:
            _console.print(Text(f"    {title}", style="red"))
        for line in lines:
            _console.print(f"      {line}")


def _print_guidance(guidance: list[str]):
    """打印 😝指导: 区块"""
    _console.print(Text("  😝指导:", style="bold"))
    for g in guidance:
        _console.print(f"    {g}")


def _append_colored_state(text: Text, state: str):
    """追加带颜色的状态标记"""
    if state == "CLOSED":
        text.append(f" {state}", style="green")
    else:
        text.append(f" {state}")


def _print_summary(counts: dict[str, int]):
    """底部汇总行"""
    LABELS = {
        "completed": ("✅", "已完成"),
        "wip": ("🔳", "开发中"),
        "error": ("🟥", "需注意"),
    }
    parts = []
    for key in ("completed", "wip", "error"):
        n = counts.get(key, 0)
        if n:
            sym, label = LABELS[key]
            parts.append(f"{sym} {label} {n}")
    if parts:
        _console.print(Text("  " + "  |  ".join(parts), style="dim"))


# ===========================================================================
# 模式2: 指定 worktree 详细展示
# ===========================================================================


def _show_detailed(path: str, repo: str, main_branch: str, verbose: int):
    """展示指定 worktree 的详细状态"""
    resolved = _resolve_worktree_path(path)
    if resolved is None:
        _console.print(f"[red]🟥 找不到 worktree: {path}[/]")
        return

    row = _build_worktree_row(resolved, repo, main_branch)
    st = row["status"]
    ICON = {"completed": ("✅", "green"), "error": ("🟥", "red"), "wip": ("🔳", "dim")}
    icon, color = ICON.get(st, ("🔳", "dim"))

    # Level 1
    l1 = Text()
    l1.append(f"{icon} ", style=color)
    l1.append(_short_path(row["wt"].path))
    l1.append(f"  ({row['branch']})")
    if row["issue_num"]:
        l1.append(f"  #{row['issue_num']}")
        _append_colored_state(l1, row["issue_state"])
        l1.append(f"  {row['issue_title']}")
    _console.print(l1)

    # Git 详情
    _console.print(Text("\n  Git:", style="bold"))
    _console.print(f"    Branch:    {row['branch']}")
    _console.print(f"    Base:      {main_branch}")
    if row["branch"] != main_branch:
        try:
            ahead = int(
                run(
                    f'git rev-list --count "{main_branch}..{row["branch"]}"',
                    row["wt"].path,
                )
            )
            behind = int(
                run(
                    f'git rev-list --count "{row["branch"]}..{main_branch}"',
                    row["wt"].path,
                )
            )
            if ahead > 0 or behind > 0:
                _console.print(f"    Ahead/Behind: +{ahead} / -{behind}")
        except (RuntimeError, ValueError):
            pass
    if row["errors"]:
        _print_errors(row["errors"])
    else:
        _console.print("    Changes:   clean")

    # Issue 详情
    if row["issue_num"]:
        _show_issue_detail(row["issue_num"], repo)

    # PR 详情
    if row["pr_number"]:
        _console.print(Text("\n  PR:", style="bold"))
        _console.print(f"    #{row['pr_number']}  {row['pr_title']}")
        _console.print(f"    State:     {row['pr_state']}")
        if row["pr_is_draft"]:
            _console.print("    State:     [yellow]DRAFT[/]")
        mergeable = row["pr_mergeable"]
        if row["pr_is_draft"] and mergeable != "CONFLICTING":
            mergeable_display = "BLOCKED(draft)"
        elif mergeable == "MERGEABLE":
            mergeable_display = "OK"
        elif mergeable == "CONFLICTING":
            mergeable_display = "CONFLICT"
        else:
            mergeable_display = mergeable
        _console.print(f"    Mergeable: {mergeable_display}")
        if row.get("pr_review_label"):
            _console.print(f"    Review:    {row['pr_review_label']}")
        _console.print(f"    URL:       {row['pr_url']}")

    # 拓扑
    if row["branch"] != main_branch:
        _console.print(Text("\n  Branch Topology:", style="bold"))
        diagram = _build_branch_diagram(row["branch"], main_branch)
        for line in diagram.split("\n"):
            _console.print(f"    {line}")

    # 指导
    if row["guidance"]:
        _print_guidance(row["guidance"])


def _show_issue_detail(issue_num: int, repo: str):
    """展示 issue 详情"""
    _console.print(Text("\n  Issue:", style="bold"))
    try:
        data = gh_issue_view(
            issue_num, repo, "number,title,state,url,createdAt,author,body"
        )
        author = data.get("author", {})
        author_login = author.get("login", "-") if isinstance(author, dict) else "-"
        _console.print(f"    #{data['number']}  {data['title']}")
        _console.print(f"    State:     {data['state']}")
        _console.print(f"    Author:    {author_login}")
        _console.print(f"    Created:   {data.get('createdAt', '-')}")
        _console.print(f"    URL:       {data.get('url', '-')}")
        body = data.get("body", "") or ""
        if body:
            lines = [ln for ln in body.strip().split("\n") if ln.strip()]
            summary = lines[:3]
            if len(lines) > 3:
                summary.append("...")
            _console.print("    Body:")
            for s in summary:
                _console.print(f"      {s[:80]}")
    except RuntimeError as e:
        _console.print(f"    [yellow]cannot fetch issue #{issue_num}: {e}[/]")


# ===========================================================================
# 模式3: 查询 issue（原 -i 行为增强）
# ===========================================================================


def _show_issue_view(issue_num: int, repo: str):
    """查询 issue 详情"""
    _show_issue_detail(issue_num, repo)
    _console.print()
    _console.print(Text("  Related PRs:", style="bold"))
    try:
        prs = gh_pr_list(repo, head=str(issue_num))
        if not prs:
            prs = gh_pr_list(repo, head=f"issue-{issue_num}")
        if prs:
            for pr in prs[:3]:
                state = pr["state"]
                if pr.get("isDraft"):
                    state += " (draft)"
                _console.print(f"    #{pr['number']} {state}  {pr['title'][:60]}")
        else:
            _console.print("    no related PR found")
    except RuntimeError:
        _console.print("    [yellow]cannot fetch PR info[/]")
    _console.print()


# ===========================================================================
# 数据构建
# ===========================================================================


def _build_worktree_row(
    wt: WorktreeInfo,
    repo: str,
    main_branch: str,
) -> dict:
    """为单个 worktree 构建所有状态字段"""
    branch = wt.branch

    # --- Issue ---
    issue_num = parse_issue_number(branch) if branch else None
    issue_title = ""
    issue_state = ""
    if issue_num:
        try:
            issue = gh_issue_view(issue_num, repo, "number,title,state")
            issue_title = issue.get("title", "")
            issue_state = issue.get("state", "")
        except RuntimeError:
            pass

    # --- PR ---
    pr_number = None
    pr_state = ""
    pr_is_draft = False
    pr_mergeable = ""
    pr_title = ""
    pr_url = ""
    pr_review_label = ""
    if branch and branch != main_branch:
        try:
            prs = gh_pr_list(repo, head=branch)
            if prs:
                pr = prs[0]
                pr_number = pr["number"]
                pr_state = pr["state"]
                pr_is_draft = pr.get("isDraft", False)
                pr_mergeable = pr.get("mergeable", "")
                pr_title = pr.get("title", "")
                pr_url = pr.get("url", "")
                try:
                    reviews_raw = run(
                        f"gh pr view {pr_number} --repo {repo} --json reviews -q '.reviews'"
                    )
                    reviews = json.loads(reviews_raw)
                    if reviews:
                        latest = reviews[-1]
                        reviewer = latest.get("author", {}).get("login", "?")
                        review_state = latest.get("state", "?")
                        state_label = {
                            "APPROVED": "approved",
                            "CHANGES_REQUESTED": "changes requested",
                            "COMMENTED": "commented",
                        }.get(review_state, review_state)
                        pr_review_label = f"{reviewer}: {state_label}"
                except (RuntimeError, json.JSONDecodeError):
                    pass
        except RuntimeError:
            pass

    # --- Git ---
    git_status_lines: list[str] = []
    if wt.has_uncommitted:
        try:
            short = run("git status --short", cwd=wt.path)
            git_status_lines = [ln for ln in short.split("\n") if ln.strip()]
        except RuntimeError:
            pass

    # --- 错误分类 ---
    errors = _categorize_git_errors(git_status_lines)

    # --- 状态判定 ---
    status = _determine_status(
        branch=branch,
        main_branch=main_branch,
        issue_state=issue_state,
        pr_state=pr_state,
        has_uncommitted=wt.has_uncommitted,
        errors=errors,
    )

    # --- 指导 ---
    guidance = _get_guidance(
        status=status,
        branch=branch,
        main_branch=main_branch,
        has_uncommitted=wt.has_uncommitted,
        pr_number=pr_number,
        pr_state=pr_state,
        pr_is_draft=pr_is_draft,
        pr_mergeable=pr_mergeable,
        issue_state=issue_state,
        errors=errors,
    )

    return {
        "wt": wt,
        "branch": branch,
        "issue_num": issue_num,
        "issue_title": issue_title,
        "issue_state": issue_state,
        "pr_number": pr_number,
        "pr_state": pr_state,
        "pr_is_draft": pr_is_draft,
        "pr_mergeable": pr_mergeable,
        "pr_title": pr_title,
        "pr_url": pr_url,
        "pr_review_label": pr_review_label,
        "git_status_lines": git_status_lines,
        "errors": errors,
        "status": status,
        "guidance": guidance,
    }


def _categorize_git_errors(
    lines: list[str],
) -> list[tuple[str, list[str]]]:
    """将 git status --short 输出分类为多个错误段落

    返回: [(section_title, lines), ...]
    """
    if not lines:
        return []

    sections: list[tuple[str, list[str]]] = []

    # 未暂存的变更
    unstaged = [ln for ln in lines if ln.startswith(" M") or ln.startswith(" D")]
    if unstaged:
        sections.append(("Changes not staged for commit:", unstaged))

    # 已暂存的变更
    staged = [
        ln
        for ln in lines
        if ln.startswith("M ") or ln.startswith("A ") or ln.startswith("D ")
    ]
    if staged:
        sections.append(("Changes to be committed:", staged))

    # 未追踪的文件
    untracked = [ln for ln in lines if ln.startswith("??")]
    if untracked:
        sections.append(("Untracked files:", untracked))

    return sections


def _determine_status(
    branch: str,
    main_branch: str,
    issue_state: str,
    pr_state: str,
    has_uncommitted: bool,
    errors: list,
) -> str:
    """判定 worktree 完成状态

    返回: 'completed' | 'wip' | 'error'
    """
    is_main = branch == main_branch

    if is_main:
        return "error" if (has_uncommitted or errors) else "completed"

    is_pr_merged = pr_state == "MERGED"
    is_issue_closed = issue_state == "CLOSED"

    # 异常
    if errors:
        return "error"
    if is_pr_merged and not is_issue_closed:
        return "error"
    if is_pr_merged and has_uncommitted:
        return "error"

    # 全部完成
    if is_pr_merged and not has_uncommitted and is_issue_closed:
        return "completed"

    # 正常开发中
    return "wip"


def _get_guidance(
    status: str,
    branch: str,
    main_branch: str,
    has_uncommitted: bool,
    pr_number: Optional[int],
    pr_state: str,
    pr_is_draft: bool,
    pr_mergeable: str,
    issue_state: str,
    errors: list,
) -> list[str]:
    """根据状态返回多行动作指导"""
    result: list[str] = []

    if branch == main_branch:
        if has_uncommitted or errors:
            result.append("在 worktree 分支处理未提交变更")
        else:
            # 检查是否需要推送/拉取
            try:
                ahead = int(
                    run(f'git rev-list --count "origin/{main_branch}..{main_branch}"')
                )
                if ahead > 0:
                    result.append("git push  推送本地提交")
            except (RuntimeError, ValueError):
                pass
            try:
                behind = int(
                    run(f'git rev-list --count "{main_branch}..origin/{main_branch}"')
                )
                if behind > 0:
                    result.append("git pull  拉取最新")
            except (RuntimeError, ValueError):
                pass
            if not result:
                result.append("最新，无需操作")
        return result

    # 异常场景
    if status == "error":
        if pr_state == "MERGED" and has_uncommitted:
            result.append("手动处理后 dev prune  清理")
        elif pr_state == "MERGED" and issue_state != "CLOSED":
            result.append("dev prune  关闭 issue 并清理 worktree")
        elif has_uncommitted:
            result.append("git add → dev commit")
            if not pr_number:
                result.append("dev pr  提交 PR")
            elif pr_state == "OPEN":
                result.append("git push  推送新 commit")
        else:
            result.append("手动检查状态")
        return result

    # 正常流程
    if has_uncommitted:
        result.append("git add → dev commit")
    if pr_state == "MERGED":
        result.append("dev prune  清理 worktree")
        return result
    if not pr_number:
        if not has_uncommitted:
            result.append("dev pr  提交 PR")
        return result
    if has_uncommitted:
        result.append("git push  推送新 commit")
        return result
    if pr_is_draft:
        result.append("dev merge-pr --ready  转正后合并")
        return result
    if pr_mergeable == "CONFLICTING":
        result.append("git rebase origin/main 解决冲突")
        result.append("dev merge-pr  合并")
        return result
    if pr_mergeable == "MERGEABLE":
        result.append("dev merge-pr  合并 PR")
        return result
    if pr_mergeable == "UNKNOWN":
        result.append("等待 review")
        return result
    return result


def _resolve_worktree_path(path: str) -> Optional[WorktreeInfo]:
    """将用户输入的路径解析为对应的 WorktreeInfo"""
    worktrees = git_worktree_list()
    cwd = os.getcwd()

    if path in (".", ""):
        for wt in worktrees:
            if wt.path == cwd:
                return wt
        for wt in worktrees:
            if cwd.startswith(wt.path):
                return wt
        return None

    abs_input = os.path.abspath(path) if not path.startswith("/") else path
    for wt in worktrees:
        if wt.path == abs_input or wt.short_path == path:
            return wt
    return None


# ===========================================================================
# 分支拓扑
# ===========================================================================


def _build_branch_diagram(branch: str, main_branch: str) -> str:
    """ASCII topology for a branch pair"""
    try:
        merge_base = get_merge_base(branch, main_branch)[:7]
    except RuntimeError:
        merge_base = "?"

    branch_commits: list[str] = []
    try:
        raw = run(f'git log --oneline "{merge_base}..{branch}"')
        branch_commits = [line[:7] for line in raw.split("\n") if line]
    except RuntimeError:
        pass

    main_commits: list[str] = []
    try:
        raw = run(f'git log --oneline "{merge_base}..{main_branch}"')
        main_commits = [line[:7] for line in raw.split("\n") if line]
    except RuntimeError:
        pass

    lines: list[str] = []
    indent = "  "

    if not main_commits:
        lines.append(f"{indent}main: ...---{merge_base}")
    else:
        lines.append(f"{indent}main: ...---{merge_base}---" + "---".join(main_commits))

    if branch_commits:
        lines.append(f"{indent}      \\")
        lines.append(f"{indent}{branch}:  " + "---".join(branch_commits))

    lines.append("")
    lines.append(
        f"  merge-base: {merge_base}  "
        f". {branch} +{len(branch_commits)}  "
        f". {main_branch} +{len(main_commits)}"
    )
    return "\n".join(lines)
