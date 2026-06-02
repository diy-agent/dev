"""diydev CLI 入口 - dev 根命令"""

import os
import sys
from cyclopts import App

from ._log import set_verbosity
from ._list_cmd import work_list
from ._start_cmd import start_app
from ._new_cmd import new_app
from ._status_cmd import status_app
from ._pr_cmd import pr_app
from ._merge_pr_cmd import merge_pr_app
from ._prune_cmd import prune_app
from ._commit_cmd import commit_app
from ._close_cmd import close_app
from ._doctor_cmd import doctor_app
from ._sandbox_cmd import sandbox_app

app = App(
    name="dev",
    help="diy 开发流程 | --cd <path> | --json 输出 | 交互命令用 -h 查看参数",
    version_flags=[],
)

# dev list
app.command(work_list, name="list")

# dev start
app.command(start_app, name="start")

# dev new
app.command(new_app, name="new")

# dev status
app.command(status_app, name="status")

# dev pr
app.command(pr_app, name="pr")

# dev merge-pr
app.command(merge_pr_app, name="merge-pr")

# dev prune
app.command(prune_app, name="prune")

# dev commit
app.command(commit_app, name="commit")

# dev close
app.command(close_app, name="close")

# dev doctor
app.command(doctor_app, name="doctor")

# dev sandbox / sb
app.command(sandbox_app, name="sandbox")
app.command(sandbox_app, name="sb")


# 解析 -v/-vv/-vvv 并从 argv 中移除，再交给 cyclopts 处理
# 这样 "dev -v list" (选项在子命令前) 也能生效
def _strip_global_flags(argv: list[str]) -> tuple[int, str | None, list[str]]:
    """从 argv 中提取 -v 和 --cd，返回 (verbosity, cd_path, remaining_argv)"""
    verbose = 0
    cd_path: str | None = None
    remaining: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--cd":
            if i + 1 < len(argv):
                cd_path = argv[i + 1]
                i += 2
                continue
            i += 1
        elif arg.startswith("--cd="):
            cd_path = arg.split("=", 1)[1]
            i += 1
        elif arg == "--verbose":
            verbose += 1
            i += 1
        elif arg.startswith("--verbose="):
            try:
                verbose += int(arg.split("=", 1)[1])
            except ValueError:
                verbose += 1
            i += 1
        elif (
            arg.startswith("-") and not arg.startswith("--") and "v" in arg.lstrip("-")
        ):
            trimmed = arg.lstrip("-")
            verbose += trimmed.count("v")
            rest = trimmed.replace("v", "")
            if rest:
                remaining.append(f"-{rest}")
            i += 1
        else:
            remaining.append(arg)
            i += 1
    return verbose, cd_path, remaining


def _check_cd_allowed(target: str) -> None:
    """沙箱内限制 --cd 只能跳转到允许的目录"""
    if os.environ.get("DIY_DEV_INSIDE_SANDBOX") != "1":
        return
    dirs_env = os.environ.get("DIYDEV_SANDBOX_DIRS", "")
    allowed = [d for d in dirs_env.split(":") if d]
    if not allowed:
        return
    for d in allowed:
        if target == d or target.startswith(d + "/"):
            return
    _die("沙箱内 --cd 仅限工作目录:\n" + "\n".join(f"  {d}" for d in allowed))


def _die(msg: str) -> None:
    print(f"错误: {msg}", file=sys.stderr)
    sys.exit(1)


def main():
    """CLI 入口函数"""
    raw = sys.argv[1:]
    verbose, cd_path, args = _strip_global_flags(raw)
    set_verbosity(verbose)
    if cd_path:
        target = os.path.realpath(os.path.expanduser(cd_path))
        _check_cd_allowed(target)
        os.chdir(target)
    try:
        app(args if args else ["--help"])
    except SystemExit:
        raise
    except Exception:
        # cyclopts 通常已用 Rich 打印错误，此处兜底
        print("错误: 无效命令或参数，使用 dev --help 查看可用命令", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
