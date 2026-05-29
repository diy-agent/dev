"""dev commit - check + test + cleanup + message + git commit

Agent one-shot commit, never forget steps again.
"""

import os
from pathlib import Path
from typing import Optional, Annotated

from cyclopts import App, Parameter

from ._log import VerboseFlag, set_verbosity, info
from ._git_ops import run, get_current_branch, get_main_branch


COMMIT_TYPES = [
    "feat",
    "fix",
    "refactor",
    "test",
    "docs",
    "style",
    "perf",
    "build",
    "ci",
    "chore",
    "revert",
]

# 从 diff 文件名推断 scope 的规则
SCOPE_PATTERNS = [
    (r"^diydev/", "dev"),  # diydev/... -> dev
    (r"^skills/([^/]+)/", None),  # skills/git-cleanup/... -> git-cleanup
    (r"^packages/([^/]+)/", None),  # packages/diyui.py/... -> diyui.py
    (r"^docs/", "docs"),  # docs/... -> docs
    (r"^vendor/([^/]+)/", None),  # vendor/sha/... -> sha
    (r"^scripts/", "scripts"),  # scripts/... -> scripts
]

commit_app = App(name="commit", help="check + test + cleanup + message + git commit")


def _find_sha_sh(start_dir: str) -> Optional[Path]:
    """向上查找 sha.sh"""
    d = Path(start_dir).resolve()
    while True:
        candidate = d / "sha.sh"
        if candidate.exists():
            return candidate
        if d.parent == d:
            return None
        d = d.parent


def _sha_has_cmd(sha_path: Path, cmd: str) -> bool:
    """检查 sha.sh 是否定义了某个命令（通过 grep 函数定义）"""
    try:
        content = sha_path.read_text()
        # 匹配 `cmd() {` 形式的函数定义（不是子函数）
        import re

        return bool(re.search(rf"^{cmd}\(\)\s*\{{", content, re.MULTILINE))
    except Exception:
        return False


def _run_sha_check(sha_path: Path) -> bool:
    """运行 sha.sh check，返回是否通过"""
    if not _sha_has_cmd(sha_path, "check"):
        info("[SKIP] check not defined in sha.sh")
        return True
    info("Running: ./sha.sh check")
    try:
        run(f"bash {sha_path} check", cwd=str(sha_path.parent))
        info("[OK] check passed")
        return True
    except Exception as e:
        print(f"[FAIL] check: {e}")
        return False


def _run_sha_test(sha_path: Path) -> bool:
    """运行 sha.sh test，返回是否通过"""
    if not _sha_has_cmd(sha_path, "test"):
        info("[SKIP] test not defined in sha.sh")
        return True
    info("Running: ./sha.sh test")
    try:
        run(f"bash {sha_path} test", cwd=str(sha_path.parent))
        info("[OK] test passed")
        return True
    except Exception as e:
        print(f"[FAIL] test: {e}")
        return False


def _run_git_cleanup(project_root: str) -> bool:
    """运行 git-cleanup 残留检查"""
    # 先找 git-cleanup.sh 的位置（相对于 _diy 项目）
    script_dir = Path(__file__).resolve().parent.parent  # diydev/ -> _diy/
    cleanup_sh = script_dir / "skills" / "git-cleanup" / "scripts" / "git-cleanup.sh"
    if not cleanup_sh.exists():
        info("[SKIP] git-cleanup.sh not found")
        return True
    info("Running: git-cleanup.sh")
    try:
        output = run(f"bash {cleanup_sh} {project_root}")
        if output.strip():
            print(f"[WARN] Residual files found:\n{output}")
            # 有残留不阻塞提交，只警示
        else:
            info("[OK] no residual files")
        return True
    except Exception as e:
        print(f"[WARN] git-cleanup: {e}")
        return True  # cleanup 失败不阻塞


def _analyze_diff(project_root: str) -> dict:
    """分析 git diff --staged，返回推荐的 type / scope / files"""
    try:
        name_only = run("git diff --staged --name-only", cwd=project_root)
    except Exception:
        name_only = ""

    files = [f.strip() for f in name_only.split("\n") if f.strip()]

    # 推断 type
    commit_type = "chore"
    test_files = 0
    new_files = 0
    doc_files = 0

    for f in files:
        if "test" in f.lower() or f.endswith("_test.py") or f.endswith(".test."):
            test_files += 1
        if "docs/" in f or f.endswith(".md"):
            doc_files += 1
        if "SKILL.md" in f:
            doc_files += 1

    try:
        diff = run("git diff --staged", cwd=project_root)
        new_file_count = diff.count("\n+++ b/")
        if "BREAKING CHANGE" in diff:
            commit_type = "feat"  # breaking change
    except Exception:
        new_file_count = len(files)

    if test_files > 0 and test_files >= len(files) * 0.5:
        commit_type = "test"
    elif doc_files > 0 and doc_files >= len(files) * 0.5:
        commit_type = "docs"
    elif new_files > 0 or new_file_count > len(files) * 0.3:
        commit_type = "feat"
    else:
        # 检查是否有重命名/移动
        try:
            diff_raw = run(
                "git diff --staged --diff-filter=R --name-only", cwd=project_root
            )
            if diff_raw.strip():
                commit_type = "refactor"
        except Exception:
            pass

    # 推断 scope
    scope = ""
    import re

    for pattern, fallback in SCOPE_PATTERNS:
        for f in files:
            m = re.match(pattern, f)
            if m:
                if fallback:
                    scope = fallback
                else:
                    scope = m.group(1)
                break
        if scope:
            break

    return {"type": commit_type, "scope": scope, "files": files}


def _generate_message(diff_info: dict) -> str:
    """根据 diff 分析结果生成 Conventional Commit message"""
    t = diff_info["type"]
    s = diff_info["scope"]
    prefix = f"{t}({s}): " if s else f"{t}: "

    files = diff_info.get("files", [])
    if not files:
        return f"{prefix}update"

    # 从文件列表推断变更主题
    # 优先用目录名，其次用文件名
    dirs = set()
    names = set()
    for f in files:
        parts = f.split("/")
        if len(parts) > 1:
            dirs.add(parts[0])
        name = parts[-1].rsplit(".", 1)[0]
        if name not in ("__init__", "index", "main"):
            names.add(name)

    subject = " ".join(sorted(dirs)) if dirs else " ".join(sorted(names))
    if not subject:
        subject = "update"

    return f"{prefix}{subject}"


@commit_app.default
def work_commit(
    verbose: VerboseFlag = 0,
    commit_type: Annotated[
        Optional[str],
        Parameter(
            name=["--type", "-t"], help="commit type: feat/fix/refactor/test/..."
        ),
    ] = None,
    scope: Annotated[
        Optional[str],
        Parameter(name=["--scope", "-s"], help="commit scope"),
    ] = None,
    message: Annotated[
        Optional[str],
        Parameter(
            name=["--message", "-m"], help="manual commit message (skip auto-generate)"
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        Parameter(name=["--dry-run", "-n"], help="only run checks, do not commit"),
    ] = False,
):
    """check + test + cleanup + message + git commit.

    Agent one-shot commit, never forget steps again.

    Execution chain:
      1. ./sha.sh check   (skip if not defined)
      2. ./sha.sh test    (skip if not defined)
      3. git-cleanup.sh   (warn if residuals)
      4. Analyze diff -> generate Conventional Commit message
      5. Show message, confirm (or override with -m/-t/-s)
      6. git add -A && git commit

    Examples:
      dev commit                    # check -> test -> message -> commit
      dev commit -n                 # dry-run: only checks, no commit
      dev commit -m "fix: typo"     # manual message
      dev commit -t fix -s cli      # force type and scope
    """
    set_verbosity(verbose)

    cwd = os.getcwd()
    project_root = cwd

    # 1. 查找 sha.sh
    sha_path = _find_sha_sh(cwd)
    if sha_path:
        project_root = str(sha_path.parent)
        info(f"Found sha.sh at: {sha_path}")
    else:
        info("No sha.sh found, skipping project checks")

    branch = get_current_branch(cwd=project_root)
    main_branch = get_main_branch()

    # 安全检查：不在 main 分支提交
    if branch == main_branch:
        print(f"Error: cannot commit on {main_branch} branch directly")
        print("Use worktree branches for development")
        return

    # 2. check (mandatory, no skip)
    if sha_path:
        if not _run_sha_check(sha_path):
            return

    # 3. test (mandatory, no skip)
    if sha_path:
        if not _run_sha_test(sha_path):
            return

    # 4. git-cleanup
    _run_git_cleanup(project_root)

    # 5. stage all
    info("Staging: git add -A")
    try:
        run("git add -A", cwd=project_root)
    except Exception as e:
        print(f"git add failed: {e}")
        return

    # 检查是否有东西可以提交
    try:
        staged = run("git diff --staged --name-only", cwd=project_root)
    except Exception:
        staged = ""
    if not staged.strip():
        print("Nothing to commit (working tree clean)")
        return

    # 6. 生成或使用指定的 message
    if message:
        final_message = message
    else:
        diff_info = _analyze_diff(project_root)
        if commit_type:
            diff_info["type"] = commit_type
        if scope:
            diff_info["scope"] = scope
        final_message = _generate_message(diff_info)
        info(f"Auto message: {final_message}")

    # 7. 展示确认
    print(f"\nBranch:   {branch}")
    print(f"Message:  {final_message}")
    print("Files:")
    for f in staged.strip().split("\n"):
        print(f"  {f}")

    if dry_run:
        print("\n[dry-run] Would commit with above message")
        return

    # auto-confirm if all flags were explicit (-m or -t/-s)
    auto_confirm = bool(message or commit_type or scope)

    if not auto_confirm:
        try:
            answer = input("\nCommit? [Y/n/edit]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled")
            return
        if answer == "" or answer == "y":
            pass
        elif answer == "e" or answer == "edit":
            import tempfile
            import subprocess as sp

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False
            ) as f:
                f.write(final_message)
                f.write(
                    "\n\n# Edit the message above. Lines starting with # are ignored.\n"
                )
                f.write("# Save and exit to commit, delete all to cancel.\n")
                tmp_path = f.name
            editor = os.environ.get("EDITOR", "vi")
            sp.call([editor, tmp_path])
            with open(tmp_path) as f:
                edited = f.read()
            os.unlink(tmp_path)
            # 过滤注释行
            lines = [x for x in edited.split("\n") if not x.strip().startswith("#")]
            edited_message = "\n".join(lines).strip()
            if not edited_message:
                print("Empty message, cancelled")
                return
            final_message = edited_message
        else:
            print("Cancelled")
            return

    # 8. commit
    try:
        run(f'git commit -m "{final_message}"', cwd=project_root)
        print(f"\n[OK] Committed: {final_message}")
    except Exception as e:
        print(f"Commit failed: {e}")
        return
