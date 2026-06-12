"""dev work list 命令 - 统一列出 issue 与 worktree 对应关系

先找出 git worktree 对应的 issue（排最前面），再列出 GitHub 最近前 50 个 open issue。
已由 worktree 覆盖的 issue 不会重复出现在后续列表中。
无 worktree 对应关系的 issue，path/branch 等字段标注 '-'。
"""

import json
import re
from dataclasses import dataclass
from typing import Annotated

from cyclopts import Parameter
from rich.console import Console
from rich.table import Table

from ._gh_ops import gh_all_prs_map, gh_issue_list, gh_issue_view, gh_project_items
from ._git_ops import get_github_repo, get_main_branch, parse_issue_number, run
from ._log import VerboseFlag, set_verbosity

# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------


@dataclass
class IssueRow:
    """统一的行数据结构"""

    issue_number: int
    issue_title: str
    issue_state: str
    issue_url: str
    issue_created: str
    issue_author: str
    # worktree 关联字段（无关联时为 '-'）
    worktree_path: str = "-"
    branch: str = "-"
    ahead: int = 0
    is_prunable: bool = False
    # PR 信息
    pr_number: str = "-"
    pr_state: str = "-"
    pr_mergeable: str = "-"
    is_draft: bool = False
    # project 字段
    priority: str = "-"
    status: str = "-"


@dataclass
class WorktreeInfo:
    path: str
    short_path: str
    branch: str
    ahead: int
    is_prunable: bool
    has_uncommitted: bool


# ---------------------------------------------------------------------------
# Filter 解析
# ---------------------------------------------------------------------------


def parse_filter(filter_str: str | None) -> dict[str, dict]:
    """解析 --filter 字符串，返回条件 dict。

    语法：key:value 用空格分隔为 AND，-key:value 为排除，value 逗号分隔为 OR。

    返回:
        {"priority": {"values": ["P0"], "negate": False},
         "status": {"values": ["Ready"], "negate": False}}
    """
    if not filter_str:
        return {}

    conditions: dict[str, dict] = {}
    for token in filter_str.split():
        token = token.strip()
        if not token:
            continue
        negate = token.startswith("-")
        if negate:
            token = token[1:]
        if ":" not in token:
            continue
        key, value = token.split(":", 1)
        conditions[key.lower()] = {
            "values": [v.strip() for v in value.split(",") if v.strip()],
            "negate": negate,
        }
    return conditions


def needs_project_data(conditions: dict[str, dict]) -> bool:
    """检查是否需要 project 数据（priority, status）"""
    return bool({"priority", "status"} & set(conditions.keys()))


def match_row(row: IssueRow, conditions: dict[str, dict]) -> bool:
    """检查 IssueRow 是否匹配所有过滤条件"""
    for key, cond in conditions.items():
        if key == "number":
            actual = str(row.issue_number)
        elif key == "state":
            actual = row.issue_state
        elif key == "title":
            actual = row.issue_title
        elif key == "priority":
            actual = row.priority
        elif key == "status":
            actual = row.status
        else:
            continue  # 未知字段跳过（不阻断）

        values = cond["values"]
        negate = cond["negate"]

        matched = any(
            v.upper() == actual.upper() if v.upper() in ("OPEN", "CLOSED", "ALL") else v.lower() in actual.lower()
            for v in values
        )
        if negate == matched:  # 排除时 matched 应为 False，包含时 matched 应为 True
            return False
    return True


# ---------------------------------------------------------------------------
# Worktree 扫描
# ---------------------------------------------------------------------------


def git_worktree_list(cwd: str | None = None) -> list[WorktreeInfo]:
    """解析 git worktree list 输出"""
    main_branch = get_main_branch()
    raw = run("git worktree list", cwd)
    results: list[WorktreeInfo] = []

    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue

        parts = line.split()
        if len(parts) < 3:
            continue

        full_path = parts[0]
        bracket_match = re.search(r"\[(.+?)\]", line)
        branch = bracket_match.group(1).strip() if bracket_match else ""

        # 缩短路径
        cwd_root = cwd or run("pwd")
        if full_path == cwd_root:
            short_path = "."
        elif full_path.startswith(cwd_root + "/"):
            short_path = full_path[len(cwd_root) + 1 :]
        else:
            short_path = full_path

        # ahead 计数
        ahead = 0
        if branch and branch != main_branch:
            try:
                ahead_str = run(f'git rev-list --count "{main_branch}..{branch}"')
                ahead = int(ahead_str)
            except (RuntimeError, ValueError):
                pass

        # 未提交变更
        has_uncommitted = False
        try:
            status_out = run("git status --porcelain", full_path)
            if status_out.strip():
                has_uncommitted = True
        except RuntimeError:
            pass

        results.append(
            WorktreeInfo(
                path=full_path,
                short_path=short_path,
                branch=branch,
                ahead=ahead,
                is_prunable=(branch == ""),
                has_uncommitted=has_uncommitted,
            )
        )

    return results


# ---------------------------------------------------------------------------
# 核心：合并 issue 与 worktree
# ---------------------------------------------------------------------------


def build_unified_rows(
    repo: str,
    labels: str | None = None,
    conditions: dict[str, dict] | None = None,
    project_map: dict[int, dict[str, str]] | None = None,
) -> list[IssueRow]:
    """构建统一的 issue-worktree 行列表

    流程:
    1. 扫描所有 git worktree，匹配对应的 issue
    2. 从 GitHub 获取最近 50 个 open issue
    3. 将 worktree 已覆盖的 issue 排在前面，其余跟在后面
    4. 应用过滤条件
    """
    if conditions is None:
        conditions = {}

    # 从 filter 中获取 limit
    limit_cond = conditions.pop("limit", None)
    sort_cond = conditions.pop("sort", None)
    gh_limit = 50
    if limit_cond:
        try:
            gh_limit = max(int(limit_cond["values"][0]), 1)
        except (ValueError, IndexError):
            pass

    # 1. 扫描 worktree
    worktrees = git_worktree_list()

    # 2. 获取所有 PR 映射
    pr_map = gh_all_prs_map(repo)

    # 3. 为每个 worktree 构建 IssueRow
    covered_issue_numbers: set[int] = set()
    wt_rows: list[IssueRow] = []

    main_branch = get_main_branch()
    for wt in worktrees:
        # 跳过主分支 worktree（main/master），它不属于任何 issue
        if wt.branch == main_branch:
            continue
        issue_num = parse_issue_number(wt.branch)
        branch_display = wt.branch + ("*" if wt.has_uncommitted else "")

        # 默认值（无 issue 对应的 worktree）
        row = IssueRow(
            issue_number=0,
            issue_title="-",
            issue_state="-",
            issue_url="-",
            issue_created="-",
            issue_author="-",
            worktree_path=wt.short_path + (" *prunable*" if wt.is_prunable else ""),
            branch=branch_display,
            ahead=wt.ahead,
            is_prunable=wt.is_prunable,
            pr_number="-",
            pr_state="-",
        )

        # 尝试获取关联的 issue
        if issue_num:
            covered_issue_numbers.add(issue_num)
            try:
                issue = gh_issue_view(issue_num, repo)
                author = issue.get("author", {})
                author_login = (
                    author.get("login", "-") if isinstance(author, dict) else "-"
                )
                row.issue_number = issue["number"]
                row.issue_title = issue.get("title", "-")
                row.issue_state = issue.get("state", "-")
                row.issue_url = issue.get("url", "-")
                row.issue_created = issue.get("createdAt", "-")
                row.issue_author = author_login

                # project 字段
                if project_map and issue_num in project_map:
                    row.priority = project_map[issue_num].get("priority", "-")
                    row.status = project_map[issue_num].get("status", "-")
            except RuntimeError:
                pass

            # PR 信息
            pr = pr_map.get(wt.branch)
            if pr:
                row.pr_number = str(pr["number"])
                row.pr_state = pr.get("state", "-")
                row.pr_mergeable = pr.get("mergeable", "-")
                row.is_draft = pr.get("isDraft", False)
                # PR 已合并时标记可 prune
                if pr.get("state") == "MERGED":
                    row.is_prunable = True

        wt_rows.append(row)

    # 4. 获取 GitHub open issues（排除已覆盖的）
    # 如果 filter 要求 state:ALL 或 state:CLOSED，需要特殊处理
    state_filter = conditions.get("state", {})
    gh_state = "open"
    if state_filter and not state_filter.get("negate"):
        vals = [v.upper() for v in state_filter["values"]]
        if "ALL" in vals:
            gh_state = "all"
        elif "CLOSED" in vals:
            gh_state = "closed"

    try:
        all_issues = gh_issue_list(repo, state=gh_state, limit=gh_limit, labels=labels)
    except RuntimeError:
        all_issues = []

    issue_rows: list[IssueRow] = []
    for iss in all_issues:
        num = iss["number"]
        if num in covered_issue_numbers:
            continue
        author = iss.get("author", {})
        author_login = author.get("login", "-") if isinstance(author, dict) else "-"
        row = IssueRow(
            issue_number=num,
            issue_title=iss.get("title", "-"),
            issue_state=iss.get("state", "-"),
            issue_url=iss.get("url", "-"),
            issue_created=iss.get("createdAt", "-"),
            issue_author=author_login,
            worktree_path="-",
            branch="-",
            ahead=0,
            is_prunable=False,
            pr_number="-",
            pr_state="-",
        )

        # project 字段
        if project_map and num in project_map:
            row.priority = project_map[num].get("priority", "-")
            row.status = project_map[num].get("status", "-")

        issue_rows.append(row)

    # 5. 应用过滤条件
    all_rows = wt_rows + issue_rows
    if conditions:
        all_rows = [r for r in all_rows if match_row(r, conditions)]

    # 6. 排序
    if sort_cond:
        sort_val = sort_cond["values"][0].lower()
        if sort_val == "created":
            all_rows.sort(key=lambda r: r.issue_created, reverse=True)
        elif sort_val == "updated":
            all_rows.sort(key=lambda r: r.issue_created, reverse=True)  # 暂无 updated 字段

    # 7. 应用结果 limit
    if limit_cond:
        try:
            result_limit = int(limit_cond["values"][0])
            all_rows = all_rows[:result_limit]
        except (ValueError, IndexError):
            pass

    return all_rows


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------


def work_list(
    verbose: VerboseFlag = 0,
    labels: Annotated[
        str | None,
        Parameter(
            name=["--label"],
            help="按标签过滤 issue",
        ),
    ] = None,
    filter_str: Annotated[
        str | None,
        Parameter(
            name=["--filter"],
            help="过滤条件，语法: key:value（空格=AND, 逗号=OR, -前缀=排除）。"
            "支持 number/state/title/priority/status/limit/sort",
        ),
    ] = None,
    json_output: Annotated[
        bool,
        Parameter(
            name="--json",
            help="输出 JSON 格式",
        ),
    ] = False,
):
    """列出 issue，并标出与 worktree 的对应关系。

    先列出有 worktree 对应的 issue（正在开发中），再列出其余最近 open issue。
    无 worktree 对应关系的 issue，path/branch 等字段标注 '-'。

    示例:
      dev list --filter "priority:P0 status:Ready"
      dev list --filter "number:42"
      dev list --filter "title:prune"
      dev list --filter "state:ALL limit:10"
    """
    set_verbosity(verbose)
    repo = get_github_repo()

    # 解析 filter
    conditions = parse_filter(filter_str)

    # 如果需要 project 字段，获取 project 数据
    project_map = None
    if needs_project_data(conditions):
        repo_short = repo.split("/", 1)[-1] if "/" in repo else repo
        project_map = gh_project_items(repo_filter=repo_short)

    rows = build_unified_rows(repo, labels, conditions, project_map)

    if json_output:
        result = []
        for r in rows:
            result.append(
                {
                    "issue": {
                        "number": r.issue_number if r.issue_number > 0 else None,
                        "title": r.issue_title,
                        "state": r.issue_state,
                        "url": r.issue_url,
                        "created": r.issue_created,
                        "author": r.issue_author,
                    },
                    "worktree": {
                        "path": r.worktree_path,
                        "branch": r.branch,
                        "ahead": r.ahead,
                        "is_prunable": r.is_prunable,
                    },
                    "pr": {
                        "number": r.pr_number if r.pr_number != "-" else None,
                        "state": r.pr_state if r.pr_state != "-" else None,
                        "mergeable": r.pr_mergeable if r.pr_mergeable != "-" else None,
                        "isDraft": r.is_draft,
                    },
                    "prune": r.is_prunable,
                    "project": {
                        "priority": r.priority if r.priority != "-" else None,
                        "status": r.status if r.status != "-" else None,
                    },
                }
            )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    if not rows:
        print("没有匹配的 issue")
        return

    # Rich 表格输出
    console = Console()
    table = Table(
        show_header=True,
        header_style="bold dim",
        border_style="dim",
        expand=True,
    )
    table.add_column("Issue", no_wrap=True, width=7)
    table.add_column("State", no_wrap=True, width=6)
    table.add_column("Created", no_wrap=True, width=10)
    table.add_column("Title", no_wrap=True, max_width=40)
    table.add_column("Priority", no_wrap=True, width=4)
    table.add_column("Status", no_wrap=True, width=8)
    table.add_column("Worktree", no_wrap=True, max_width=35)
    table.add_column("Ahead", justify="right", width=5)
    table.add_column("PR", no_wrap=True, max_width=12)
    table.add_column("PR State", no_wrap=True, width=7)
    table.add_column("Mergeable", no_wrap=True, width=10)

    for r in rows:
        issue_str = f"#{r.issue_number}" if r.issue_number > 0 else "-"
        created_short = r.issue_created[:10] if r.issue_created != "-" else "-"
        title = r.issue_title

        # 构建 worktree 展示列：path [branch]（可 prune 时加标记）
        if r.worktree_path != "-":
            wt_display = r.worktree_path
            if r.branch:
                wt_display += f" [{r.branch}]"
            if r.is_prunable:
                wt_display += " [bold red]🗑[/]"
        else:
            wt_display = "-"

        # PR 信息
        pr_display = "-"
        pr_state = "-"
        pr_mergeable = "-"
        if r.pr_number != "-":
            pr_display = f"#{r.pr_number}"
            if r.is_draft:
                pr_state = f"[yellow]{r.pr_state} 草稿[/]"
                pr_mergeable = (
                    "[yellow]BLOCKED(草稿)[/]"
                    if r.pr_mergeable != "CONFLICTING"
                    else f"[yellow]{r.pr_mergeable}[/]"
                )
            else:
                pr_state = r.pr_state
                pr_mergeable = r.pr_mergeable

        # 异常状态标红：issue 已关闭、PR 已合并/关闭、mergeable 未知
        issue_state_display = r.issue_state
        if r.issue_state in ("CLOSED",):
            issue_state_display = f"[bold red]{r.issue_state}[/]"
        # PR 状态：只在非草稿时检查原始值
        raw_pr_state = r.pr_state  # 原始值，如 OPEN/CLOSED/MERGED
        if not r.is_draft and raw_pr_state in ("MERGED", "CLOSED"):
            pr_state = f"[bold red]{raw_pr_state}[/]"
        # PR mergeable
        raw_mergeable = r.pr_mergeable
        if not r.is_draft and raw_mergeable == "UNKNOWN":
            pr_mergeable = f"[bold red]{raw_mergeable}[/]"

        ahead_str = str(r.ahead) if r.ahead > 0 else "-"

        # 有 worktree 的行高亮
        style = "bold" if r.worktree_path != "-" else None

        table.add_row(
            issue_str,
            issue_state_display,
            created_short,
            title,
            r.priority,
            r.status,
            wt_display,
            ahead_str,
            pr_display,
            pr_state,
            pr_mergeable,
            style=style,
        )

    # 统计
    wt_count = sum(1 for r in rows if r.worktree_path != "-")
    issue_count = sum(1 for r in rows if r.worktree_path == "-")

    console.print(table)
    console.print(
        f"\n[dim]共 {wt_count} 个 worktree 关联 + {issue_count} 个待处理 issue[/dim]"
    )
