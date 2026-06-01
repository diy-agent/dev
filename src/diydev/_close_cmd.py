"""dev close - close issue with interactive confirmation"""

from typing import Optional, Annotated
from cyclopts import App, Parameter

from ._log import VerboseFlag, set_verbosity
from ._git_ops import get_github_repo
from ._gh_ops import gh_issue_view, gh_issue_comment, gh_issue_close

close_app = App(name="close", help="close issue with confirmation")

REASONS = {
    "completed": "completed",
    "not-planned": "not planned",
    "duplicate": "duplicate",
}


@close_app.default
def work_close(
    issue_num: Annotated[
        int,
        Parameter(
            name=["issue_num"],
            help="issue number to close",
        ),
    ],
    reason: Annotated[
        Optional[str],
        Parameter(
            name=["--reason", "-r"],
            help="关闭原因: completed | not-planned（GitHub state_reason；Agent: 默认 completed）",
        ),
    ] = None,
    comment: Annotated[
        Optional[str],
        Parameter(
            name=["--comment", "-c"],
            help="close comment",
        ),
    ] = None,
    yes: Annotated[
        bool,
        Parameter(
            name=["--yes", "-y"],
            help="跳过确认（Agent: 使用 -y 跳过交互确认）",
        ),
    ] = False,
    verbose: VerboseFlag = 0,
):
    """Close a GitHub issue with reason and comment.

    Shows issue info, asks for confirmation before closing.
    Requires explicit confirmation unless --yes.

    Examples:
      dev close 19                           # interactive confirm
      dev close 19 -r duplicate -c "dup #14"  # specify reason+comment
      dev close 19 -y -r completed            # skip confirm
    """
    set_verbosity(verbose)
    repo = get_github_repo()

    # show issue info
    try:
        issue = gh_issue_view(issue_num, repo, "number,title,state,url")
        print(f"\n  #{issue['number']}  {issue['title']}")
        print(f"  State:  {issue['state']}")
        print(f"  URL:    {issue['url']}")
    except RuntimeError as e:
        print(f"error: cannot fetch issue #{issue_num}: {e}")
        return

    if issue["state"] != "OPEN":
        print(f"  issue is already {issue['state']}, nothing to close")
        return

    # validate reason
    if reason and reason not in REASONS:
        print(f"error: invalid reason '{reason}'. use: {', '.join(REASONS.keys())}")
        return

    # confirm
    if not yes:
        print()
        if reason:
            print(f"  Close as:  {REASONS.get(reason, reason)}")
        if comment:
            print(f"  Comment:   {comment}")
        print()
        try:
            answer = input("  Confirm close? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n  cancelled")
            return
        if answer != "y":
            print("  cancelled")
            return

    # comment
    if comment:
        try:
            gh_issue_comment(issue_num, comment, repo)
            print("  comment added")
        except RuntimeError as e:
            print(f"  comment failed: {e}")

    # close
    try:
        if reason:
            gh_issue_close(issue_num, repo, reason)
        else:
            gh_issue_close(issue_num, repo)
        print(f"  closed #{issue_num}")
    except RuntimeError as e:
        print(f"  close failed: {e}")
