"""dev status - worktree tree overview

Shows all worktrees in a tree hierarchy with completion status.

Commands:
  dev status            简明树状概览（所有 worktree）
  dev status -v         展开详情（PR/issue/拓扑）
  dev status .          指定 worktree 的详细展示
  dev status -i <num>   查询指定 issue
"""

import json
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

    # --issue mode: query any issue
    if issue is not None:
        _show_issue_view(issue, repo)
        return

    # --path mode: detailed view for a specific worktree
    if worktree_path is not None:
        _show_detailed(worktree_path, repo, main_branch, verbose)
        return

    # Default: tree overview of all worktrees
    _show_tree(repo, main_branch, verbose)


# ===========================================================================
# 模式1: 树状概览（默认）
# ===========================================================================


def _show_tree(repo: str, main_branch: str, verbose: int):
    """渲染所有 worktree 的树状状态概览"""
    worktrees = git_worktree_list()
    rows = [_build_worktree_row(wt, repo, main_branch, verbose) for wt in worktrees]

    # 排序: warning → wip → completed → clean（main 在最后）
    _ORDER = {"warning": 0, "wip": 1, "completed": 2, "clean": 3}
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
        _console.print()  # 空行分隔

    # 汇总
    _print_summary(counts)


def _print_one_tree(row: dict, verbose: int):
    """打印一棵 worktree 的状态树"""
    wt: WorktreeInfo = row["wt"]
    status = row["status"]
    is_main = row["branch"] == get_main_branch()

    # --- 状态标记 → 颜色 ---
    SYM = {
        "completed": ("☑", "green"),
        "warning": ("⚠", "yellow"),
        "wip": ("☐", ""),
        "clean": ("·", "dim"),
    }
    icon, color = SYM.get(status, ("☐", ""))

    # ---- Level 1: [icon] path (branch) #issue title ----
    l1 = Text()
    l1.append(f"{icon} ", style=color or None)
    # main 分支始终显示 .，worktree 分支尽量短路径
    display_path = "." if is_main else wt.short_path
    l1.append(display_path)
    l1.append(f"  ({row['branch']})")
    if row["issue_num"]:
        l1.append(f"  #{row['issue_num']}")
        _append_colored_state(l1, row["issue_state"])
        l1.append(f"  {row['issue_title']}")
    _console.print(l1)

    if is_main:
        # Main 分支：仅在有变更时显示 Git
        if row["git_status_lines"]:
            l2_git = Text("  ⚠ ", style="yellow")
            l2_git.append(f"Git  {len(row['git_status_lines'])} 个文件未提交")
            _console.print(l2_git)
            for line in row["git_status_lines"][:10]:
                _console.print(Text(f"    {line}"))
        if row["next_step"]:
            _console.print(Text(f"  → {row['next_step']}"))
        return

    # ---- Level 2: PR ----
    l2_pr = Text("  ")
    if row["pr_state"] == "MERGED":
        l2_pr.append("☑ ", style="green")
        l2_pr.append(f"PR  #{row['pr_number']} 已合并")
    elif row["pr_number"]:
        l2_pr.append("☐ ")
        l2_pr.append(f"PR  #{row['pr_number']} {row['pr_state']}")
        if row["pr_is_draft"]:
            l2_pr.append(" (草稿)", style="yellow")
        mergeable = row["pr_mergeable"]
        if mergeable == "MERGEABLE":
            l2_pr.append("  ✅ 可合并", style="green")
        elif mergeable == "CONFLICTING":
            l2_pr.append("  ⚠ 冲突", style="yellow")
        elif mergeable == "UNKNOWN":
            l2_pr.append("  待审核")
        if verbose:
            l2_pr.append(f"  {row.get('pr_review_label', '')}")
    else:
        l2_pr.append("☐ ")
        l2_pr.append("PR  ⏳ 未提交")
    _console.print(l2_pr)

    # ---- Level 2: Git（仅异常时出现）----
    if row["git_status_lines"]:
        l2_git = Text("  ⚠ ", style="yellow")
        l2_git.append(f"Git  {len(row['git_status_lines'])} 个文件未提交")
        _console.print(l2_git)

        # Level 3: git 精简详情
        max_lines = 100 if verbose else 10
        for line in row["git_status_lines"][:max_lines]:
            _console.print(Text(f"    {line}"))
        if len(row["git_status_lines"]) > max_lines:
            _console.print(
                Text(
                    f"    ... 还有 {len(row['git_status_lines']) - max_lines} 个文件",
                    style="dim",
                )
            )

    # ---- 拓扑（仅 -v） ----
    if verbose and row["issue_num"]:
        diagram = _build_branch_diagram(row["branch"], get_main_branch())
        for line in diagram.split("\n"):
            _console.print(Text(f"    {line}", style="dim"))

    # ---- 动作提示 ----
    if row["next_step"]:
        _console.print(Text(f"  → {row['next_step']}"))


def _append_colored_state(text: Text, state: str):
    """追加带颜色的状态标记"""
    if state == "CLOSED":
        text.append(f" {state}", style="green")
    elif state == "OPEN":
        text.append(f" {state}")
    else:
        text.append(f" {state}")


def _print_summary(counts: dict[str, int]):
    """底部汇总行"""
    LABELS = {
        "completed": ("☑", "已完成"),
        "wip": ("☐", "开发中"),
        "warning": ("⚠", "需注意"),
        "clean": ("·", "最新"),
    }
    parts = []
    for key in ("completed", "wip", "warning", "clean"):
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
    """展示指定 worktree 的详细状态（原 dev status 行为）"""
    # 将 path 解析为绝对路径并找到对应的 worktree
    resolved = _resolve_worktree_path(path)
    if resolved is None:
        _console.print(f"[yellow]⚠ 找不到 worktree: {path}[/]")
        return

    row = _build_worktree_row(resolved, repo, main_branch, verbose)
    st = row["status"]
    SYM = {
        "completed": ("☑", "green"),
        "warning": ("⚠", "yellow"),
        "wip": ("☐", ""),
        "clean": ("·", "dim"),
    }
    icon, color = SYM.get(st, ("☐", ""))

    # Level 1
    l1 = Text()
    l1.append(f"{icon} ", style=color or None)
    l1.append(f"{row['wt'].short_path}")
    l1.append(f"  ({row['branch']})")
    if row["issue_num"]:
        l1.append(f"  #{row['issue_num']}")
        _append_colored_state(l1, row["issue_state"])
        l1.append(f"  {row['issue_title']}")
    _console.print(l1)

    # Git 详情
    _console.print(Text("\n  Git:", style="bold"))
    wt = row["wt"]
    _console.print(f"    Branch:    {row['branch']}")
    _console.print(f"    Base:      {main_branch}")
    if row["branch"] != main_branch:
        try:
            ahead = int(
                run(f'git rev-list --count "{main_branch}..{row["branch"]}"', wt.path)
            )
            behind = int(
                run(f'git rev-list --count "{row["branch"]}..{main_branch}"', wt.path)
            )
            if ahead > 0 or behind > 0:
                _console.print(f"    Ahead/Behind: +{ahead} / -{behind}")
        except (RuntimeError, ValueError):
            pass
    if row["git_status_lines"]:
        _console.print(f"    [yellow]⚠ {len(row['git_status_lines'])} 个文件未提交[/]")
        for line in row["git_status_lines"]:
            _console.print(f"      {line}")
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

    # Next step
    if row["next_step"]:
        _console.print(Text(f"\n  → {row['next_step']}"))


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
    wt: WorktreeInfo, repo: str, main_branch: str, verbose: int
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
                # review
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

    # --- 状态判定 ---
    status = _determine_status(
        branch, main_branch, issue_state, pr_state, wt.has_uncommitted
    )

    # --- 下一步 ---
    next_step = _get_next_step(
        status=status,
        branch=branch,
        main_branch=main_branch,
        has_uncommitted=wt.has_uncommitted,
        pr_number=pr_number,
        pr_state=pr_state,
        pr_is_draft=pr_is_draft,
        pr_mergeable=pr_mergeable,
        issue_state=issue_state,
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
        "status": status,
        "next_step": next_step,
    }


def _determine_status(
    branch: str,
    main_branch: str,
    issue_state: str,
    pr_state: str,
    has_uncommitted: bool,
) -> str:
    """判定 worktree 完成状态

    返回: 'warning' | 'completed' | 'wip' | 'clean'
    """
    if branch == main_branch:
        return "clean"

    is_pr_merged = pr_state == "MERGED"
    is_issue_closed = issue_state == "CLOSED"

    # 异常：已合并但 git 脏 / issue 未关
    if is_pr_merged and has_uncommitted:
        return "warning"
    if is_pr_merged and not is_issue_closed:
        return "warning"

    # 全部完成
    if is_pr_merged and not has_uncommitted and is_issue_closed:
        return "completed"

    # 正常开发中
    return "wip"


def _get_next_step(
    status: str,
    branch: str,
    main_branch: str,
    has_uncommitted: bool,
    pr_number: Optional[int],
    pr_state: str,
    pr_is_draft: bool,
    pr_mergeable: str,
    issue_state: str,
) -> str:
    """根据状态输出最优先的一个动作"""
    if branch == main_branch:
        if has_uncommitted:
            return "⚠ main 有未提交变更，在 worktree 分支处理此变更"
        try:
            ahead = int(
                run(f'git rev-list --count "origin/{main_branch}..{main_branch}"')
            )
            if ahead > 0:
                return "git push  推送本地提交"
        except (RuntimeError, ValueError):
            pass
        try:
            behind = int(
                run(f'git rev-list --count "{main_branch}..origin/{main_branch}"')
            )
            if behind > 0:
                return "git pull  拉取最新"
        except (RuntimeError, ValueError):
            pass
        return "最新，无需操作"

    # 异常处理
    if status == "warning":
        if pr_state == "MERGED" and has_uncommitted:
            return "⚠ 已合并但存在未提交变更，处理后 dev prune"
        if pr_state == "MERGED" and issue_state != "CLOSED":
            return "dev prune  关闭 issue 并清理"
        return "手动检查状态"

    # 正常流程
    if has_uncommitted:
        return "git add → dev commit"
    if pr_state == "MERGED":
        return "dev prune  清理 worktree"
    if not pr_number:
        return "dev pr  提交 PR"
    if pr_is_draft:
        return "dev merge-pr --ready  转正后合并"
    if pr_mergeable == "CONFLICTING":
        return "git rebase origin/main 解决冲突后 dev merge-pr"
    if pr_mergeable == "MERGEABLE":
        return "dev merge-pr  合并 PR"
    return "等待 review"


def _resolve_worktree_path(path: str) -> Optional[WorktreeInfo]:
    """将用户输入的路径解析为对应的 WorktreeInfo"""
    import os

    worktrees = git_worktree_list()
    cwd = os.getcwd()

    # 如果输入是 '.' 或空，用当前 worktree
    if path in (".", ""):
        for wt in worktrees:
            if wt.path == cwd:
                return wt
        # fallback: 取第一个匹配 cwd 前缀的
        for wt in worktrees:
            if cwd.startswith(wt.path):
                return wt
        return None

    # 精确匹配 path 或 short_path
    abs_input = os.path.abspath(path) if not path.startswith("/") else path
    for wt in worktrees:
        if wt.path == abs_input or wt.short_path == path:
            return wt
    return None


# ===========================================================================
# 分支拓扑（保留自原实现）
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
