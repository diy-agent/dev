"""dev commit - 检查并提交代码（任意分支直接放行，不做 worktree 逻辑）"""

import sys
from typing import Annotated

from cyclopts import App, Parameter

from ._git_ops import get_current_branch, run
from ._json_output import error_json, output_json
from ._log import VerboseFlag, set_verbosity

commit_app = App(name="commit", help="执行 check 后提交代码")


def _run_check() -> bool:
    """运行 sha.sh check（ruff + pyright），返回是否通过"""
    try:
        run("uv run ruff check src/ tests/")
        run("uv run ruff format --check src/ tests/")
        run("uv run pyright src/ tests/")
        return True
    except RuntimeError as e:
        print(f"check 失败: {e}", file=sys.stderr)
        return False


@commit_app.default
def work_commit(
    verbose: VerboseFlag = 0,
    message: Annotated[
        str,
        Parameter(name=["--message", "-m"], help="commit message"),
    ] = "",
    json_output: Annotated[
        bool,
        Parameter(name=["--json"], help="JSON 格式输出 (agent 使用)"),
    ] = False,
):
    """执行 lint + type check 后提交代码。

    不限制分支：main / worktree / 普通分支均可直接提交。
    """
    set_verbosity(verbose)

    # 检查未提交变更
    status_out = run("git status --porcelain")
    if not status_out.strip():
        if json_output:
            output_json({"warning": "nothing to commit"}, "没有待提交的变更")
        else:
            print("没有待提交的变更")
        return

    # 执行 check（lint + type check）
    if not _run_check():
        if json_output:
            error_json("check 未通过，拒绝提交")
        sys.exit(1)

    # 提交
    branch = get_current_branch()
    msg = message or "WIP"
    run("git add -A")
    run(f'git commit -m "{msg}"')

    if json_output:
        output_json(
            {"branch": branch, "message": msg},
            f"已在 {branch} 分支提交",
        )
    else:
        print(f"成功: 已在 {branch} 分支提交")
