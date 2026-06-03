"""dev close - close issue with interactive confirmation"""

from typing import Annotated

from cyclopts import App, Parameter

from ._gh_ops import gh_issue_close, gh_issue_comment, gh_issue_view
from ._git_ops import get_github_repo
from ._json_output import output_json
from ._log import VerboseFlag, set_verbosity

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
        str | None,
        Parameter(
            name=["--reason"],
            help="关闭原因: completed | not-planned（state_reason，默认 completed）",
        ),
    ] = None,
    comment: Annotated[
        str | None,
        Parameter(
            name=["--comment", "-c"],
            help="close comment",
        ),
    ] = None,
    yes: Annotated[
        bool,
        Parameter(
            name=["--yes", "-y"],
            help="跳过确认（Agent: 使用 --yes 跳过交互确认）",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        Parameter(name=["--json"], help="JSON 格式输出，自动跳过确认 (agent 使用)"),
    ] = False,
    verbose: VerboseFlag = 0,
):
    """Close a GitHub issue with reason and comment.

    Shows issue info, asks for confirmation before closing.
    Requires explicit confirmation unless --yes.

    Examples:
      dev close 19                           # interactive confirm
      dev close 19 --reason duplicate --comment "dup #14"
      dev close 19 --yes --reason completed
      dev close 19 --json --reason completed # agent mode
    """
    set_verbosity(verbose)
    repo = get_github_repo()

    # show issue info
    try:
        issue = gh_issue_view(issue_num, repo, "number,title,state,url")
        if not json_output:
            print(f"\n  #{issue['number']}  {issue['title']}")
            print(f"  State:  {issue['state']}")
            print(f"  URL:    {issue['url']}")
    except RuntimeError as e:
        if json_output:
            output_json({"error": "issue not found"}, str(e))
        else:
            print(f"error: cannot fetch issue #{issue_num}: {e}")
        return

    if issue["state"] != "OPEN":
        if json_output:
            msg = f"issue already {issue['state']}"
            output_json({"number": issue_num, "state": issue["state"]}, msg)
        else:
            print(f"  issue is already {issue['state']}, nothing to close")
        return

    # validate reason
    if reason and reason not in REASONS:
        if json_output:
            output_json({"error": "invalid reason"}, f"'{reason}' 不合法")
        else:
            print(f"error: invalid reason '{reason}'. use: {', '.join(REASONS.keys())}")
        return

    # --json 模式自动确认
    auto_confirm = json_output or yes

    if not auto_confirm:
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
            if not json_output:
                print("  comment added")
        except RuntimeError as e:
            if not json_output:
                print(f"  comment failed: {e}")

    # close
    try:
        if reason:
            gh_issue_close(issue_num, repo, reason)
        else:
            gh_issue_close(issue_num, repo)
        if json_output:
            msg = f"closed #{issue_num}"
            output_json({"number": issue_num, "reason": reason or "completed"}, msg)
        else:
            print(f"  closed #{issue_num}")
    except RuntimeError as e:
        if json_output:
            output_json({"error": "close failed"}, str(e))
        else:
            print(f"  close failed: {e}")
