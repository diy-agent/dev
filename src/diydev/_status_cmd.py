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
        else:
            print("  no related PR")
            print("  create PR:      dev pr")
    except RuntimeError:
        print("  cannot fetch PR info")

    # === Branch diagram ===
    print("\n=== Branch Topology ===")
    diagram = _build_branch_diagram(branch, main_branch)
    print(diagram)
    print()


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
