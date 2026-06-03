"""dev work pr - 推送并创建 PR"""

from typing import Annotated

from cyclopts import App, Parameter

from ._gh_ops import gh_issue_view, gh_pr_create, gh_pr_list
from ._git_ops import (
    get_current_branch,
    get_github_repo,
    get_main_branch,
    git_push,
    parse_issue_number,
    run,
)
from ._json_output import output_json
from ._log import VerboseFlag, set_verbosity

pr_app = App(name="pr", help="推送并创建 PR")


@pr_app.default
def work_pr(
    verbose: VerboseFlag = 0,
    json_output: Annotated[
        bool,
        Parameter(name=["--json"], help="JSON 格式输出 (agent 使用)"),
    ] = False,
):
    """推送当前分支并创建 Pull Request。

    自动从分支名提取 issue 编号，用 issue 标题作为 PR 标题。
    如果已有 open PR，则只推送新 commit。
    """
    set_verbosity(verbose)
    branch = get_current_branch()
    main_branch = get_main_branch()
    repo = get_github_repo()

    if branch == main_branch:
        if json_output:
            output_json(
                {"error": "cannot create PR on main branch"}, "不能在主分支创建 PR"
            )
        else:
            print("错误: 不能在主分支创建 PR")
        return

    # 检查未提交变更
    status_out = run("git status --porcelain")
    if status_out.strip():
        if json_output:
            output_json({"error": "uncommitted changes"}, "有未提交的变更")
        else:
            print("错误: 有未提交的变更，请先提交再创建 PR")
        return

    issue_num = parse_issue_number(branch)
    if not issue_num:
        if json_output:
            output_json(
                {"error": "cannot parse issue number"},
                f'无法从分支 "{branch}" 解析 issue 编号',
            )
        else:
            print(f'错误: 无法从分支 "{branch}" 解析 issue 编号')
        return

    # 获取 issue 标题
    try:
        issue = gh_issue_view(issue_num, repo, "title")
    except RuntimeError:
        if json_output:
            output_json({"error": "issue not found"}, f"找不到 issue #{issue_num}")
        else:
            print(f"错误: 找不到 issue #{issue_num}")
        return

    if not issue.get("title"):
        if json_output:
            output_json({"error": "empty title"}, f"issue #{issue_num} 没有标题")
        else:
            print(f"错误: issue #{issue_num} 没有标题")
        return

    title = issue["title"]

    # 检查是否已有 open PR
    existing = gh_pr_list(repo, head=branch, state="open")
    if existing:
        git_push()
        if json_output:
            output_json(
                {
                    "number": existing[0]["number"],
                    "url": existing[0]["url"],
                    "pushed": True,
                },
                f"分支 {branch} 已有 open PR，新 commit 已推送",
            )
        else:
            draft_hint = " (草稿)" if existing[0].get("isDraft") else ""
            print(
                f'警告: 分支 "{branch}" 已存在 open PR #{existing[0]["number"]}{draft_hint}，新 commit 已推送'
            )
            print(f"合并: dev work merge-pr 或到 {existing[0]['url']} 页面手动合并")
        return

    # 检查是否已有 merged PR
    merged = gh_pr_list(repo, head=branch, state="merged")
    if merged and not json_output:
        print(f'注意: 分支 "{branch}" 已有已合并的 PR，建议开新 issue + 新分支')

    # 推送
    git_push()

    # 创建 PR
    pr_num = gh_pr_create(repo, main_branch, branch, title, f"Complete #{issue_num}")
    if json_output:
        output_json(
            {
                "number": pr_num,
                "url": f"https://github.com/{repo}/pull/{pr_num}",
                "issue": issue_num,
            },
            f"创建 PR #{pr_num}",
        )
        return
    print(f"成功: 创建 PR #{pr_num}")
    print(f"URL:   https://github.com/{repo}/pull/{pr_num}")
