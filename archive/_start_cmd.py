"""dev start - 开始开发：pull main, 创建 worktree, 初始化环境, 推送"""

from pathlib import Path
from typing import Annotated

from cyclopts import App, Parameter

from ._gh_ops import gh_issue_view
from ._git_ops import (
    get_github_repo,
    get_main_branch,
    get_worktree_path,
    git_push_upstream,
    git_worktree_add,
    run,
)
from ._json_output import output_json
from ._log import VerboseFlag, info, set_verbosity

start_app = App(name="start", help="开始开发：pull main, 创建 worktree, 初始化并推送")


def _init_env(worktree_path: str) -> bool:
    """初始化 worktree 开发环境：submodule + 依赖安装"""
    wt = Path(worktree_path)

    # 1. submodule init
    if (wt / ".gitmodules").exists():
        info("initializing submodules...")
        try:
            run("git submodule update --init --recursive", cwd=str(wt))
            info("submodules ready")
        except Exception as e:
            print(f"  submodule init FAILED: {e}")
            return False

    # 2. Python 项目: uv sync
    if (wt / "pyproject.toml").exists():
        # 检查是否有 uv
        try:
            run("which uv", cwd=str(wt))
            info("running uv sync...")
            try:
                run("uv sync", cwd=str(wt))
                info("uv sync done")
            except Exception as e:
                print(f"  uv sync FAILED: {e}")
                return False
        except Exception:
            info("uv not found, skipping")

    # 3. Node.js 项目: npm install
    if (wt / "package.json").exists():
        info("running npm install...")
        try:
            run("npm install", cwd=str(wt))
            info("npm install done")
        except Exception as e:
            print(f"  npm install FAILED: {e}")
            return False

    return True


@start_app.default
def work_start(
    issue_num: Annotated[
        int,
        Parameter(
            name=["issue_num"],
            help="GitHub issue 编号",
        ),
    ],
    branch_name: Annotated[
        str,
        Parameter(
            name=["branch_name"],
            help="分支名后缀 (可选)",
        ),
    ] = "",
    verbose: VerboseFlag = 0,
    json_output: Annotated[
        bool,
        Parameter(name=["--json"], help="JSON 格式输出 (agent 使用)"),
    ] = False,
):
    """从 issue 编号开始开发。

    流程:
      1. git fetch + pull main (拿到最新基准)
      2. 创建 worktree + 分支
      3. submodule init + uv sync / npm install
      4. 推送远端

    示例:
      dev start 54           # 创建分支 54
      dev start 54 fix-xx    # 创建分支 54-fix-xx
    """
    set_verbosity(verbose)
    repo = get_github_repo()
    main_branch = get_main_branch()
    branch = f"{issue_num}-{branch_name}" if branch_name else str(issue_num)

    # 0. 先 pull main 拿到最新基准
    info(f"fetching + pulling {main_branch}...")
    try:
        run(f"git fetch origin {main_branch}")
        run(f"git pull origin {main_branch}")
        info(f"{main_branch} is up to date")
    except Exception as e:
        if json_output:
            output_json({"error": "pull failed"}, str(e))
        else:
            print(f"  无法更新 {main_branch}: {e}")
            print(f"  请手动: git pull origin {main_branch}")
        return

    # 1. 验证 issue 是否存在
    try:
        issue = gh_issue_view(issue_num, repo, "title")
        if not json_output:
            print(f"Issue:  #{issue_num}  {issue.get('title', '')}")
    except RuntimeError as e:
        if json_output:
            output_json({"error": "issue not found"}, str(e))
        else:
            print(f"错误: 无法获取 issue #{issue_num} - {e}")
        return

    # 2. 创建 worktree
    worktree_path = get_worktree_path(branch)
    try:
        git_worktree_add(branch, main_branch)
        if not json_output:
            print(f"成功: 创建 worktree {worktree_path}")
    except RuntimeError as e:
        if json_output:
            output_json({"error": "worktree create failed"}, str(e))
        else:
            print(f"错误: 创建 worktree 失败 - {e}")
        return

    # 3. 初始化环境
    if not json_output:
        print("初始化开发环境...")
    if not _init_env(worktree_path):
        if json_output:
            output_json(
                {
                    "worktree_path": worktree_path,
                    "branch": branch,
                    "issue": issue_num,
                    "env_init_failed": True,
                },
                "环境初始化失败",
            )
        else:
            print("\n  环境初始化失败，请检查后手动完成。")
            print(f"  cd {worktree_path}")
            print("  uv sync  # or npm install")
        return

    # 4. 推送分支
    try:
        git_push_upstream(branch)
        if not json_output:
            print(f"成功: 推送分支 {branch} 到远程")
    except RuntimeError as e:
        if not json_output:
            print(f"警告: 推送分支失败 - {e}")
            print(f"请手动推送: git push -u origin {branch}")

    if json_output:
        output_json(
            {
                "worktree_path": worktree_path,
                "branch": branch,
                "issue": issue_num,
                "issue_title": issue.get("title", ""),
            },
            f"开始开发 #{issue_num}",
        )
    else:
        print(f"\n开始开发: cd {worktree_path}")
