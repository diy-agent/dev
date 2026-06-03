"""dev work new - 创建新 GitHub issue"""

from typing import Annotated

from cyclopts import App, Parameter

from ._gh_ops import gh_issue_create
from ._git_ops import get_github_repo
from ._json_output import output_json
from ._log import VerboseFlag, set_verbosity

new_app = App(name="new", help="创建新的 issue")


@new_app.default
def work_new(
    description: Annotated[
        list[str],
        Parameter(
            name=["description"],
            help="issue 描述（同时作为 title 和 body）",
        ),
    ],
    verbose: VerboseFlag = 0,
    json_output: Annotated[
        bool,
        Parameter(name=["--json"], help="JSON 格式输出 (agent 使用)"),
    ] = False,
):
    """创建新的 GitHub issue，描述同时作为 title 和 body。

    示例:
      dev new 修复登录页面样式问题
      dev new 需要支持多语言切换功能
    """
    set_verbosity(verbose)
    repo = get_github_repo()
    desc = " ".join(description)
    num = gh_issue_create(desc, desc, repo)
    if json_output:
        output_json(
            {"number": num, "url": f"https://github.com/{repo}/issues/{num}"},
            f"创建 issue #{num}",
        )
        return
    print(f"成功: 创建 issue #{num}")
    print(f"URL:   https://github.com/{repo}/issues/{num}")
