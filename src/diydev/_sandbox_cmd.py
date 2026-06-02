"""dev sandbox - 打开隔离的 sandbox bash 环境

使用 macOS sandbox-exec 创建一个白名单模式的隔离 shell。
支持 --dir 附加工作目录，所有目录动态注入策略。
无模板时使用内置默认模板 _sandbox_default.sb。
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Annotated, Optional

from cyclopts import App, Parameter
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from ._log import VerboseFlag, set_verbosity, info, debug

_console = Console(highlight=False)
_console_err = Console(stderr=True, highlight=False)

_SANDBOX_EXEC = "/usr/bin/sandbox-exec"
_DEFAULT_SHELL = os.environ.get("SHELL", "/bin/bash")
_TEMPLATE_FILE = ".sandbox.sb"
_BUILTIN_TEMPLATE = Path(__file__).parent / "_sandbox_default.sb"

sandbox_app = App(
    name="sandbox",
    help="打开隔离的 sandbox bash 环境",
    version_flags=[],
)

# ---------------------------------------------------------------------------
# 模板查找
# ---------------------------------------------------------------------------


def _find_template_path(start_dir: str) -> Optional[Path]:
    """向上查找项目级 .sandbox.sb 模板文件，返回路径或 None"""
    d = Path(start_dir).resolve()
    while True:
        tmpl = d / _TEMPLATE_FILE
        if tmpl.is_file():
            return tmpl
        parent = d.parent
        if parent == d:
            return None
        d = parent


def _get_template(start_dir: str) -> tuple[str, str]:
    """获取模板内容和来源描述"""
    tmpl_path = _find_template_path(start_dir)
    if tmpl_path:
        debug(f"使用项目模板: {tmpl_path}")
        return tmpl_path.read_text(), f"项目模板 ({tmpl_path})"
    debug(f"使用内置模板: {_BUILTIN_TEMPLATE}")
    return _BUILTIN_TEMPLATE.read_text(), f"内置默认 ({_BUILTIN_TEMPLATE})"


# ---------------------------------------------------------------------------
# 策略生成
# ---------------------------------------------------------------------------


def _resolve_dirs(cwd: str, extra_dirs: list[str]) -> list[str]:
    """解析并规范化所有工作目录（去重、保留顺序）"""
    seen: set[str] = set()
    result: list[str] = []
    raw = [cwd] + [os.path.expanduser(d) for d in extra_dirs]
    for d in raw:
        real = os.path.realpath(d)
        if real not in seen:
            seen.add(real)
            result.append(real)
    return result


def _build_workdirs_rules(dirs: list[str]) -> tuple[str, str, str]:
    """根据目录列表生成策略规则段

    Returns:
        (读白名单段, 写白名单段, deny-unlink 段)
    """
    # 读白名单（cwd + --dir，不含重复）
    read_lines = ""
    for d in dirs[1:]:  # dirs[0] 是 WORKDIR，已单独写入模板
        read_lines += f'  (subpath "{d}")\n'

    # 写白名单（所有目录）
    write_lines = ""
    for d in dirs:
        write_lines += f'  (subpath "{d}")\n'

    # deny file-write-unlink
    deny_lines = ""
    for d in dirs:
        deny_lines += f'(deny file-write-unlink (literal "{d}"))\n'
        deny_lines += f'(deny file-write-unlink (literal "{d}/.git"))\n'

    return read_lines, write_lines, deny_lines


def _build_policy(home: str, workdir: str, extra_dirs: list[str]) -> str:
    """生成 sandbox 策略：模板 → 替换变量 → 注入动态目录"""
    template, _ = _get_template(workdir)

    dirs = _resolve_dirs(workdir, extra_dirs)
    read_seg, write_seg, deny_seg = _build_workdirs_rules(dirs)

    # 变量替换
    policy = template.replace("${HOME}", home)
    policy = policy.replace("${WORKDIR}", dirs[0])
    policy = policy.replace("${WORKDIRS_READ}", read_seg.rstrip("\n"))
    policy = policy.replace("${WORKDIRS_WRITE}", write_seg.rstrip("\n"))
    policy = policy.replace("${DENY_UNLINKS}", deny_seg.rstrip("\n"))

    return policy


# ---------------------------------------------------------------------------
# 嵌套检测
# ---------------------------------------------------------------------------


def _check_sandbox() -> None:
    """检查 sandbox-exec 是否可用 / 是否已在 sandbox 内"""
    if not os.path.isfile(_SANDBOX_EXEC):
        _console_err.print("[bold red]错误:[/] sandbox-exec 不可用，仅支持 macOS")
        raise SystemExit(1)
    inside = (
        os.environ.get("PI_INSIDE_SANDBOX") == "1"
        or os.environ.get("DIY_DEV_INSIDE_SANDBOX") == "1"
    )
    if inside:
        _console_err.print("[bold red]错误:[/] 当前已在 sandbox 内，无法启动新 sandbox")
        _console_err.print("[dim]sandbox 内可用命令: dev sb status (诊断)[/]")
        _console_err.print("[dim]退出 sandbox: exit 或 Ctrl+D[/]")
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# dev sb init — 创建策略模板
# ---------------------------------------------------------------------------


@sandbox_app.command(name="init")
def sandbox_init(
    verbose: VerboseFlag = 0,
    force: Annotated[
        bool,
        Parameter(
            name=["--force", "-f"],
            help="覆盖已有模板文件",
        ),
    ] = False,
):
    """在当前目录创建 .sandbox.sb 策略模板。

    从内置模板复制，支持 ${HOME}、${WORKDIR} 等变量。
    可自由修改来定制 sandbox 策略。

    示例:
      dev sb init        # 创建模板
      dev sb init -f     # 强制覆盖已有模板
    """
    set_verbosity(verbose)

    target = Path.cwd() / _TEMPLATE_FILE
    if target.exists() and not force:
        print(f"模板已存在: {target}", file=sys.stderr)
        print("使用 -f 强制覆盖", file=sys.stderr)
        raise SystemExit(1)

    shutil.copy(_BUILTIN_TEMPLATE, target)
    print(f"已创建模板: {target}")
    print()
    print("模板变量:")
    print("  ${{HOME}}           → 用户主目录")
    print("  ${{WORKDIR}}        → 当前工作目录")
    print("  ${{WORKDIRS_READ}}  → 附加目录读白名单（--dir 动态注入）")
    print("  ${{WORKDIRS_WRITE}} → 所有工作目录写白名单（动态注入）")
    print("  ${{DENY_UNLINKS}}   → 目录删除保护（动态注入）")
    print()
    print("修改后 dev sb 会自动检测并使用该模板。")


# ---------------------------------------------------------------------------
# dev sb status — 诊断当前 sandbox 状态
# ---------------------------------------------------------------------------


def _detect_sandbox_marker() -> Optional[str]:
    """检测 sandbox 标记"""
    if os.environ.get("DIY_DEV_INSIDE_SANDBOX") == "1":
        return "DIY_DEV_INSIDE_SANDBOX=1 (dev sb)"
    if os.environ.get("PI_INSIDE_SANDBOX") == "1":
        return "PI_INSIDE_SANDBOX=1 (pi sandbox)"
    return None


def _print_link_item(
    label: str,
    links: list[str],
    fallback: str = "",
    suffix: str = "",
) -> None:
    """打印带 OSC 8 超链接的键值行

    label: 项目名（加粗）
    links: file:// 或 https:// URL 列表
    fallback: 无链接时的占位文本
    suffix: 链接后的附加文本
    """
    from rich.text import Text

    line = Text()
    line.append("- ", style="dim")
    line.append(f"{label}：", style="bold")
    if links:
        for i, url in enumerate(links):
            if i > 0:
                line.append("\n     ")
            # 去掉 file:// 前缀做显示文本
            display = url.removeprefix("file://") if url.startswith("file://") else url
            line.append(f"{display}{suffix}", style=f"link {url}")
    elif fallback:
        line.append(f" {fallback}", style="dim")
    _console.print(line)


@sandbox_app.command(name="status")
def sandbox_status(
    verbose: VerboseFlag = 0,
    rich: Annotated[
        bool,
        Parameter(name=["--rich"], help="以 Rich 表格格式输出"),
    ] = False,
    show_policy: Annotated[
        bool,
        Parameter(name=["--policy"], help="同时显示实际生效的策略内容"),
    ] = False,
):
    """显示 sandbox 诊断信息。

    示例:
      dev sb status          # Markdown 格式
      dev sb status --rich   # Rich 表格格式
      dev sb status --policy # 同时显示策略内容
    """
    set_verbosity(verbose)
    home = os.environ["HOME"]
    cwd = os.getcwd()
    marker = _detect_sandbox_marker()

    dirs_env = os.environ.get("DIYDEV_SANDBOX_DIRS", "")
    sandbox_dirs = [d for d in dirs_env.split(":") if d] if dirs_env else []
    workdirs = sandbox_dirs if sandbox_dirs else [cwd]

    proj_tmpl = _find_template_path(cwd)
    if proj_tmpl:
        lines = proj_tmpl.read_text().count("\n") + 1
        tmpl_path = str(proj_tmpl)
    else:
        lines = _BUILTIN_TEMPLATE.read_text().count("\n") + 1
        tmpl_path = str(_BUILTIN_TEMPLATE)

    policy_file = os.environ.get("DIYDEV_SANDBOX_POLICY", "")

    _console.print()

    if marker:
        status_line = f"> ⚠️ **已隔离**（{marker}）\n>"
    else:
        status_line = "**未隔离**（宿主终端）"

    if not rich:
        from rich.markdown import Markdown

        # 状态头部用 Markdown
        _console.print(Markdown(f"# Sandbox 状态\n\n{status_line}\n"))
        # 每一项手动排版，路径用 OSC 8 超链接
        _print_link_item("工作目录", [f"file://{w}" for w in workdirs])
        _print_link_item(
            "策略文件",
            [f"file://{policy_file}"] if policy_file else [],
            fallback="*(未启动，使用 `dev sb --dry-run` 预览)*",
        )
        _print_link_item(
            "策略模板",
            [f"file://{tmpl_path}"] if tmpl_path.startswith("/") else [],
            suffix=f"（{lines} 行）",
        )
        _print_link_item("用户主目录", [f"file://{home}"])
    else:
        table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1), expand=False)
        table.add_column(style="dim", width=11)
        table.add_column()

        if marker:
            table.add_row("当前进程", f"[bold yellow]已隔离[/] ({marker})")
        else:
            table.add_row("当前进程", "[green]未隔离[/] (宿主终端)")

        table.add_row("工作目录", "\n".join(workdirs))

        if policy_file:
            table.add_row("策略文件", policy_file)
        else:
            table.add_row("策略文件", "[dim](未启动，使用 dev sb --dry-run 预览)[/]")

        table.add_row("策略模板", f"[dim]{tmpl_path}（{lines} 行）[/]")
        table.add_row("用户主目录", home)

        _console.print(Panel(table, title="Sandbox 状态", border_style="dim"))

    _console.print()

    if show_policy:
        if marker:
            _console.print("[dim](sandbox 内仅显示当前目录策略预览)[/]")
        policy = _build_policy(home, cwd, [])
        _console.print(Panel(policy, title="策略预览", border_style="dim"))


# ---------------------------------------------------------------------------
# dev sb — 启动 sandbox
# ---------------------------------------------------------------------------


def _validate_sandbox_subcommand() -> None:
    """检测是否有拼写错误的子命令（cyclopts fallback 到 default 前拦截）"""
    import difflib

    known = ["init", "status"]
    for i in range(1, len(sys.argv)):
        if sys.argv[i] in ("sb", "sandbox") and i + 1 < len(sys.argv):
            token = sys.argv[i + 1]
            if not token.startswith("-") and token not in known:
                suggestions = difflib.get_close_matches(token, known, n=1, cutoff=0.5)
                hint = (
                    f" Did you mean '[bold]{suggestions[0]}[/]'?" if suggestions else ""
                )
                _console_err.print(
                    f"[bold red]错误:[/] 未知命令 '[bold]{token}[/]'。{hint}"
                )
                _console_err.print(f"[dim]可用命令: {', '.join(known)}[/]")
                raise SystemExit(1)
            return


@sandbox_app.default
def sandbox(
    verbose: VerboseFlag = 0,
    workdir: Annotated[
        Optional[str],
        Parameter(
            name=["--cd"],
            help="进入 sandbox 后的工作目录（默认当前目录）",
        ),
    ] = None,
    dir_: Annotated[
        list[str],
        Parameter(
            name=["--dir"],
            help="附加工作目录，可多次指定（读写白名单 + 防删保护）",
        ),
    ] = [],
    shell: Annotated[
        str,
        Parameter(
            name=["--shell"],
            help=f"使用的 shell（默认 $SHELL，当前 {_DEFAULT_SHELL}）",
        ),
    ] = _DEFAULT_SHELL,
    dry_run: Annotated[
        bool,
        Parameter(
            name=["--dry-run"],
            help="仅打印 sandbox 策略，不实际执行",
        ),
    ] = False,
):
    """打开隔离的 sandbox bash 环境。

    使用 macOS sandbox-exec 创建白名单模式的隔离 shell。
    若当前目录或父目录存在 .sandbox.sb 模板则优先使用，
    否则使用内置默认模板。

    示例:
      dev sb                              # 当前目录
      dev sb --dir ~/git/lib --dir ~/git/app  # 附加多个工作目录
      dev sb --cd ~/git/proj --dir ~/data     # 指定主目录 + 附加目录
      dev sb --shell /bin/zsh             # 使用 zsh
      dev sb --dry-run                    # 预览策略
      dev sb init                         # 创建策略模板
      dev sb status                       # 查看诊断信息
    """
    set_verbosity(verbose)
    _validate_sandbox_subcommand()
    _check_sandbox()

    home = os.environ["HOME"]

    if workdir:
        cwd = os.path.expanduser(workdir)
    else:
        cwd = os.getcwd()

    if not os.path.isdir(cwd):
        print(f"错误: 目录不存在: {cwd}", file=sys.stderr)
        raise SystemExit(1)

    # 校验附加目录
    for d in dir_:
        expanded = os.path.expanduser(d)
        if not os.path.isdir(expanded):
            print(f"错误: --dir 目录不存在: {d}", file=sys.stderr)
            raise SystemExit(1)

    shell_path = shutil.which(shell)
    if not shell_path:
        if os.path.isfile(shell) and os.access(shell, os.X_OK):
            shell_path = shell
        else:
            print(f"错误: shell 不可用: {shell}", file=sys.stderr)
            raise SystemExit(1)

    policy = _build_policy(home, cwd, dir_)
    info(f"工作目录: {cwd}")
    if dir_:
        info(f"附加目录: {', '.join(dir_)}")
    info(f"Shell: {shell_path}")
    debug(f"\n--- sandbox 策略 ---\n{policy}--- 策略结束 ---")

    if dry_run:
        print(policy)
        return

    fd, policy_path = tempfile.mkstemp(prefix="diydev-sandbox-", suffix=".sb")
    try:
        os.write(fd, policy.encode())
        os.close(fd)

        info(f"策略文件: {policy_path}")

        # 进入前打印清晰横幅，帮助理解后续的 "Operation not permitted"
        _console.print()
        _console.print(
            Panel(
                f"工作目录: [bold]{cwd}[/]\n"
                f"附加目录: [dim]{', '.join(dir_) or '(无)'}[/]\n\n"
                "[dim]如遇 [bold]Operation not permitted[/] 说明文件不在沙箱白名单中[/]\n"
                "[dim]可用 [bold]dev sb status[/] 查看诊断（需要新终端窗口）[/]\n"
                "[dim]退出: exit 或 Ctrl+D[/]",
                title="[bold]🔒 Sandbox 隔离环境[/]",
                border_style="yellow",
            )
        )
        _console.print()

        os.environ["DIY_DEV_INSIDE_SANDBOX"] = "1"
        # 记录所有工作目录供 status 查询
        all_dirs = _resolve_dirs(cwd, dir_)
        os.environ["DIYDEV_SANDBOX_DIRS"] = ":".join(all_dirs)
        os.environ["DIYDEV_SANDBOX_POLICY"] = policy_path
        os.environ["PS1"] = f"[sandbox] {os.environ.get('PS1', '\\h:\\W \\u\\$ ')}"
        os.chdir(cwd)
        os.execv(
            _SANDBOX_EXEC,
            [
                "sandbox-exec",
                "-f",
                policy_path,
                shell_path,
                "-i",
            ],
        )
    finally:
        try:
            os.unlink(policy_path)
        except OSError:
            pass
