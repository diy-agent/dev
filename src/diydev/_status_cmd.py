"""dev status - current branch / issue query"""

from typing import Optional, Annotated
from cyclopts import App, Parameter

from ._log import VerboseFlag, set_verbosity
from ._git_ops import (
    run,
    get_github_repo,
    get_main_branch,
    get_current_branch,
    get_merge_base,
)
from ._gh_ops import gh_issue_view, gh_pr_list

status_app = App(name="status", help="current branch / issue query")


def _show_issue_info(issue_num: int, repo: str):
    """display issue info"""
    print("\n=== Issue ===")
    try:
        data = gh_issue_view(
            issue_num, repo, "number,title,state,url,createdAt,author,body"
        )
        author = data.get("author", {})
        author_login = author.get("login", "-") if isinstance(author, dict) else "-"
        print(f"  #{data['number']}  {data['title']}")
        print(f"  State:          {data['state']}")
        print(f"  Author:         {author_login}")
        print(f"  Created:        {data.get('createdAt', '-')}")
        print(f"  URL:            {data.get('url', '-')}")
        body = data.get("body", "") or ""
        if body:
            lines = [ln for ln in body.strip().split("\n") if ln.strip()]
            summary = lines[:3]
            if len(lines) > 3:
                summary.append("...")
            print("  Body:")
            for s in summary:
                print(f"    {s[:80]}")
    except RuntimeError as e:
        print(f"  cannot fetch issue #{issue_num}: {e}")


@status_app.default
def work_status(
    verbose: VerboseFlag = 0,
    issue: Annotated[
        Optional[int],
        Parameter(
            name=["--issue", "-i"],
            help="query a specific issue (no worktree required)",
        ),
    ] = None,
):
    """Show current branch status, or query a specific issue with -i.

    Examples:
      dev status          # current worktree status
      dev status -i 19    # query issue #19 status
    """
    set_verbosity(verbose)
    repo = get_github_repo()

    # --issue mode: query any issue
    if issue is not None:
        _show_issue_info(issue, repo)
        print("\n=== Related PRs ===")
        try:
            prs = gh_pr_list(repo, head=str(issue))
            if not prs:
                prs = gh_pr_list(repo, head=f"issue-{issue}")
            if prs:
                for pr in prs[:3]:
                    state = pr["state"]
                    if pr.get("isDraft"):
                        state += " (draft)"
                    print(f"  #{pr['number']} {state}  {pr['title'][:60]}")
            else:
                print("  no related PR found")
        except RuntimeError:
            print("  cannot fetch PR info")
        print()
        return

    # default mode: current worktree
    branch = get_current_branch()
    main_branch = get_main_branch()

    # === Git info ===
    print("=== Git ===")
    print(f"  Branch:          {branch}")
    print(f"  Base:            {main_branch}")
    print(f"  Repo:            {repo}")

    status_out = run("git status --porcelain")
    if status_out.strip():
        count = len([line for line in status_out.split("\n") if line.strip()])
        print(f"  Changes:         {count} files")
    else:
        print("  Changes:         clean")

    if branch != main_branch:
        try:
            ahead = int(run(f'git rev-list --count "{main_branch}..{branch}"'))
            behind = int(run(f'git rev-list --count "{branch}..{main_branch}"'))
            if ahead > 0 or behind > 0:
                print(f"  Ahead/Behind:    +{ahead} / -{behind}")
        except (RuntimeError, ValueError):
            pass

    # === Issue info ===
    issue_num = None
    for pattern, parser in [
        (r"^(\d+)-", 1),
        (r"^issue-(\d+)$", 1),
        (r"^(\d+)$", 1),
    ]:
        import re

        m = re.match(pattern, branch)
        if m:
            issue_num = int(m.group(parser))
            break

    if not issue_num:
        print(f'\n  branch "{branch}" cannot resolve issue number')
        return

    _show_issue_info(issue_num, repo)

    # === PR info ===
    print("\n=== PR ===")
    prs: list[dict] = []
    try:
        prs = gh_pr_list(repo, head=branch)
        if prs:
            pr = prs[0]
            print(f"  #{pr['number']}  {pr['title']}")
            state = pr["state"]
            if pr.get("isDraft"):
                state += " (draft)"
            print(f"  State:          {state}")

            mergeable = pr.get("mergeable", "UNKNOWN")
            if pr.get("isDraft") and mergeable != "CONFLICTING":
                mergeable = "BLOCKED(draft)"
            elif mergeable == "MERGEABLE":
                mergeable = "OK"
            elif mergeable == "CONFLICTING":
                mergeable = "CONFLICT"
            print(f"  Mergeable:      {mergeable}")

            try:
                reviews_raw = run(
                    f"gh pr view {pr['number']} --repo {repo} --json reviews -q '.reviews'"
                )
            except RuntimeError:
                reviews_raw = "[]"
            import json

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
                print(f"  Review:         {reviewer}: {state_label}")
            else:
                print("  Review:         (none)")

            print(f"  URL:            {pr['url']}")

            # MERGED 状态醒目警告
            if pr["state"] == "MERGED":
                print()
                print("  ⚠️  此 PR 已合并！无需再操作此分支")
                print(f"  清理 worktree:  dev prune")
        else:
            print("  no related PR")
            print("  create PR:      dev pr")
    except RuntimeError:
        print("  cannot fetch PR info")

    # === Branch diagram ===
    print("\n=== Branch Topology ===")
    diagram = _build_branch_diagram(branch, main_branch)
    print(diagram)

    # === 下一步 ===
    _print_next_step(branch, main_branch, prs)
    print()


def _print_next_step(branch: str, main_branch: str, prs: list[dict]):
    """根据当前状态输出下一步建议"""
    if branch == main_branch:
        return

    print("=== 下一步 ===")

    if prs:
        pr = prs[0]
        state = pr["state"]
        is_draft = pr.get("isDraft", False)

        if state == "MERGED":
            print("  PR 已合并 → dev prune  清理 worktree + 远程分支")
        elif is_draft:
            print("  PR 草稿中  → 推送新提交后 dev pr 更新")
            print("              → 或 dev merge-pr --ready  转正后合并")
        elif state == "OPEN":
            mergeable = pr.get("mergeable", "UNKNOWN")
            if mergeable == "MERGEABLE":
                print("  PR 可合并  → dev merge-pr  选择策略合并")
            elif mergeable == "CONFLICTING":
                print("  PR 有冲突  → git rebase origin/main 解决后 dev merge-pr")
            else:
                print("  PR 待审核  → 等待 review")
        elif state == "CLOSED":
            print("  PR 已关闭  → dev prune  清理，或重新 dev pr")
    else:
        # 检查是否有未提交变更
        try:
            status_out = run("git status --porcelain")
            if status_out.strip():
                print("  有未提交变更 → git add && git commit")
                print("               → dev pr  提交后创建 PR")
            else:
                print("  无 PR    → dev pr  创建 Pull Request")
        except RuntimeError:
            print("  无 PR    → dev pr  创建 Pull Request")


def _build_branch_diagram(branch: str, main_branch: str) -> str:
    """build ASCII topology for current branch"""
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
