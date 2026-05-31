"""dev doctor - 项目规范自动检查

代码即规范：规范不需要 markdown 描述，dev doctor 直接检查违规。
当 dev 工具的检查逻辑更新时，规范自动同步。

Usage:
    dev doctor           # 全部检查
    dev doctor sha       # sha.sh 规范检查
    dev doctor py        # pyproject.toml 规范检查
"""

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Annotated, Callable

from cyclopts import App, Parameter

from ._log import VerboseFlag, set_verbosity, info


# ============================================================================
# Check result types
# ============================================================================


class Status(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    SKIP = "SKIP"


@dataclass
class CheckResult:
    category: str
    name: str
    status: Status
    detail: str = ""
    fix: str = ""

    @property
    def icon(self) -> str:
        return {
            Status.PASS: "✅",
            Status.FAIL: "❌",
            Status.WARN: "⚠️",
            Status.SKIP: "⏭️",
        }[self.status]


@dataclass
class CheckSuite:
    checks: list[tuple[str, Callable[[str], CheckResult]]] = field(default_factory=list)


# ============================================================================
# Utility functions
# ============================================================================


def _read_file(path: str | Path) -> Optional[str]:
    """读取文件内容"""
    try:
        return Path(path).read_text()
    except Exception:
        return None


def _has_function(content: str, name: str) -> bool:
    """检查 shell 脚本中是否定义了某个顶层函数"""
    return bool(re.search(rf"^{name}\(\)\s*\{{", content, re.MULTILINE))


def _check_toml_section(path: str, section: str) -> bool:
    """检查 toml 文件中是否存在某个 section"""
    content = _read_file(Path(path))
    if not content:
        return False
    # 匹配 [section] 或 [section.sub]
    return bool(re.search(rf"^\[{re.escape(section)}(?:\]|\.)", content, re.MULTILINE))


# ============================================================================
# SHA checks
# ============================================================================


def _check_sha_exists(project_root: str) -> CheckResult:
    p = Path(project_root) / "sha.sh"
    if p.exists():
        return CheckResult("sha", "sha.sh exists", Status.PASS)
    return CheckResult(
        "sha",
        "sha.sh exists",
        Status.FAIL,
        "sha.sh not found",
        "run 'cp _diy/sha.sh .'",
    )


def _check_sha_executable(project_root: str) -> CheckResult:
    p = Path(project_root) / "sha.sh"
    if not p.exists():
        return CheckResult("sha", "sha.sh executable", Status.SKIP, "sha.sh not found")
    if os.access(p, os.X_OK):
        return CheckResult("sha", "sha.sh executable", Status.PASS)
    return CheckResult(
        "sha",
        "sha.sh executable",
        Status.FAIL,
        "sha.sh is not executable",
        "run 'chmod +x sha.sh'",
    )


def _check_sha_common_naming(project_root: str) -> CheckResult:
    """sha.common.sh must exist, sha_common.sh is deprecated"""
    good = Path(project_root) / "sha.common.sh"
    bad = Path(project_root) / "sha_common.sh"
    if good.exists() and not bad.exists():
        return CheckResult("sha", "sha.common.sh naming", Status.PASS)
    if bad.exists():
        return CheckResult(
            "sha",
            "sha.common.sh naming",
            Status.FAIL,
            "found deprecated sha_common.sh (underscore)",
            "run 'git mv sha_common.sh sha.common.sh'",
        )
    return CheckResult(
        "sha",
        "sha.common.sh naming",
        Status.FAIL,
        "sha.common.sh not found",
        "copy from _diy/sha.common.sh",
    )


def _check_sha_run_naming(project_root: str) -> CheckResult:
    """sha.common.sh must define 'run()', not '_run()'"""
    content = _read_file(Path(project_root) / "sha.common.sh")
    if not content:
        return CheckResult(
            "sha", "run() naming", Status.SKIP, "sha.common.sh not found"
        )
    if _has_function(content, "run"):
        if _has_function(content, "_run"):
            return CheckResult(
                "sha",
                "run() naming",
                Status.WARN,
                "both run() and _run() defined",
                "remove _run(), keep run()",
            )
        return CheckResult("sha", "run() naming", Status.PASS)
    if _has_function(content, "_run"):
        return CheckResult(
            "sha",
            "run() naming",
            Status.FAIL,
            "only _run() found (deprecated)",
            "rename _run() to run()",
        )
    return CheckResult(
        "sha", "run() naming", Status.WARN, "neither run() nor _run() found"
    )


_REQUIRED_COMMANDS = ["check", "test", "sync", "clean", "fix", "ci"]


def _check_sha_required_commands(project_root: str) -> CheckResult:
    """sha.sh must define check, test, sync, clean"""
    content = _read_file(Path(project_root) / "sha.sh")
    if not content:
        return CheckResult("sha", "required commands", Status.SKIP, "sha.sh not found")
    missing = [c for c in _REQUIRED_COMMANDS if not _has_function(content, c)]
    if not missing:
        return CheckResult(
            "sha",
            "required commands",
            Status.PASS,
            f"all {len(_REQUIRED_COMMANDS)} defined",
        )
    return CheckResult(
        "sha",
        "required commands",
        Status.FAIL,
        f"missing: {', '.join(missing)}",
        f"add {', '.join(missing)}() functions to sha.sh",
    )


def _check_sha_vendor_submodule(project_root: str) -> CheckResult:
    """vendor/sha submodule should be initialized"""
    vendor = Path(project_root) / "vendor" / "sha"
    if not vendor.exists():
        return CheckResult(
            "sha",
            "vendor/sha submodule",
            Status.WARN,
            "vendor/sha not found",
            "run 'git submodule add ...' and './sha.sh sync'",
        )
    if not any(vendor.iterdir()):
        return CheckResult(
            "sha",
            "vendor/sha submodule",
            Status.WARN,
            "vendor/sha is empty",
            "run './sha.sh sync'",
        )
    return CheckResult("sha", "vendor/sha submodule", Status.PASS)


SHA_CHECKS: list[tuple[str, Callable[[str], CheckResult]]] = [
    ("sha.sh exists", _check_sha_exists),
    ("sha.sh executable", _check_sha_executable),
    ("sha.common.sh naming", _check_sha_common_naming),
    ("run() naming", _check_sha_run_naming),
    ("required commands", _check_sha_required_commands),
    ("vendor/sha submodule", _check_sha_vendor_submodule),
]


# ============================================================================
# Python checks
# ============================================================================


def _check_pyproject_exists(project_root: str) -> CheckResult:
    p = Path(project_root) / "pyproject.toml"
    if p.exists():
        return CheckResult("py", "pyproject.toml exists", Status.PASS)
    return CheckResult(
        "py", "pyproject.toml exists", Status.FAIL, "pyproject.toml not found"
    )


def _check_py_dev_dep(project_root: str, dep: str, display_name: str) -> CheckResult:
    """检查某个 dev dependency 是否存在"""
    content = _read_file(Path(project_root) / "pyproject.toml")
    if not content:
        return CheckResult(
            "py", f"dev dep: {display_name}", Status.SKIP, "pyproject.toml not found"
        )
    # 检查是否在任何 dependencies 段中出现（支持 "ruff"、"ruff>=0.15" 等格式）
    if re.search(rf'"{re.escape(dep)}(?:[>"]|\s*$)', content):
        return CheckResult("py", f"dev dep: {display_name}", Status.PASS)
    return CheckResult(
        "py",
        f"dev dep: {display_name}",
        Status.FAIL,
        f"'{dep}' not found in dependencies",
        f"run 'uv add --dev {display_name}'",
    )


def _check_py_tool_section(
    project_root: str, section: str, display_name: str
) -> CheckResult:
    """检查 pyproject.toml 中是否有某个 [tool.*] section"""
    content = _read_file(Path(project_root) / "pyproject.toml")
    if not content:
        return CheckResult("py", f"tool section: {display_name}", Status.SKIP)
    if _check_toml_section(str(Path(project_root) / "pyproject.toml"), section):
        return CheckResult("py", f"tool section: {display_name}", Status.PASS)
    return CheckResult(
        "py",
        f"tool section: {display_name}",
        Status.WARN,
        f"[{section}] section missing",
        f"add [{section}] configuration",
    )


def _check_py_project_name(project_root: str) -> CheckResult:
    """项目名应遵循 diy-* 或 _* 前缀"""
    content = _read_file(Path(project_root) / "pyproject.toml")
    if not content:
        return CheckResult("py", "project naming", Status.SKIP)
    m = re.search(r'name\s*=\s*"([^"]+)"', content)
    if not m:
        return CheckResult(
            "py", "project naming", Status.WARN, "cannot parse project name"
        )
    name = m.group(1)
    if name.startswith("diy") or name.startswith("_"):
        return CheckResult("py", "project naming", Status.PASS, f"name='{name}'")
    return CheckResult(
        "py",
        "project naming",
        Status.WARN,
        f"name='{name}' doesn't follow diy-* or _* convention",
    )


def _check_py_packages_dir(project_root: str) -> CheckResult:
    """检查是否使用 pkgs/（已废弃），应使用 packages/"""
    pkgs = Path(project_root) / "pkgs"
    packages = Path(project_root) / "packages"
    if packages.exists() and not pkgs.exists():
        return CheckResult("py", "packages/ directory", Status.PASS)
    if pkgs.exists():
        return CheckResult(
            "py",
            "packages/ directory",
            Status.FAIL,
            "found deprecated 'pkgs/' directory",
            "rename to 'packages/' (check import paths first)",
        )
    return CheckResult(
        "py", "packages/ directory", Status.SKIP, "no packages/ or pkgs/ found"
    )


PY_CHECKS: list[tuple[str, Callable[[str], CheckResult]]] = [
    ("pyproject.toml exists", _check_pyproject_exists),
    ("dev dep: ruff", lambda r: _check_py_dev_dep(r, "ruff", "ruff")),
    ("dev dep: pyright", lambda r: _check_py_dev_dep(r, "pyright", "pyright")),
    ("dev dep: pytest", lambda r: _check_py_dev_dep(r, "pytest", "pytest")),
    (
        "tool section: ruff",
        lambda r: _check_py_tool_section(r, "tool.ruff", "[tool.ruff]"),
    ),
    (
        "tool section: pyright",
        lambda r: _check_py_tool_section(r, "tool.pyright", "[tool.pyright]"),
    ),
    (
        "tool section: pytest",
        lambda r: _check_py_tool_section(
            r, "tool.pytest.ini_options", "[tool.pytest.ini_options]"
        ),
    ),
    ("project naming", _check_py_project_name),
    ("packages/ directory", _check_py_packages_dir),
]


# ============================================================================
# General checks
# ============================================================================


def _check_agents_md(project_root: str) -> CheckResult:
    p = Path(project_root) / "AGENTS.md"
    if p.exists():
        return CheckResult("general", "AGENTS.md exists", Status.PASS)
    # also check for AGENT.md typo
    typo = Path(project_root) / "AGENT.md"
    if typo.exists():
        return CheckResult(
            "general",
            "AGENTS.md exists",
            Status.FAIL,
            "found 'AGENT.md' (missing S), rename to 'AGENTS.md'",
            "run 'git mv AGENT.md AGENTS.md'",
        )
    return CheckResult(
        "general",
        "AGENTS.md exists",
        Status.WARN,
        "AGENTS.md not found",
        "create AGENTS.md for project instructions",
    )


def _check_gitignore_entry(
    project_root: str, pattern: str, display: str
) -> CheckResult:
    """检查 .gitignore 是否包含某个 pattern"""
    gi = _read_file(Path(project_root) / ".gitignore")
    if not gi:
        return CheckResult(
            "general",
            f".gitignore: {display}",
            Status.WARN,
            ".gitignore not found",
            "create .gitignore",
        )
    if pattern in gi:
        return CheckResult("general", f".gitignore: {display}", Status.PASS)
    return CheckResult(
        "general",
        f".gitignore: {display}",
        Status.WARN,
        f"'{pattern}' not in .gitignore",
        f"add '{pattern}' to .gitignore",
    )


GENERAL_CHECKS: list[tuple[str, Callable[[str], CheckResult]]] = [
    ("AGENTS.md exists", _check_agents_md),
    (".gitignore: .venv/", lambda r: _check_gitignore_entry(r, ".venv/", ".venv/")),
    (
        ".gitignore: __pycache__/",
        lambda r: _check_gitignore_entry(r, "__pycache__/", "__pycache__/"),
    ),
]


# ============================================================================
# Runner
# ============================================================================


def _find_project_root(start_dir: str) -> str:
    """向上查找项目根目录（包含 sha.sh 或 pyproject.toml 或 .git）"""
    d = Path(start_dir).resolve()
    while True:
        if (
            (d / "sha.sh").exists()
            or (d / "pyproject.toml").exists()
            or (d / ".git").exists()
        ):
            return str(d)
        if d.parent == d:
            return start_dir
        d = d.parent


# ANSI styling
PASS_STYLE = "\033[32m"
FAIL_STYLE = "\033[31m"
WARN_STYLE = "\033[33m"
SKIP_STYLE = "\033[90m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _print_header(text: str) -> None:
    print(f"\n{BOLD}{text}{RESET}")
    print("─" * 60)


def _print_result(r: CheckResult) -> None:
    style = {
        Status.PASS: PASS_STYLE,
        Status.FAIL: FAIL_STYLE,
        Status.WARN: WARN_STYLE,
        Status.SKIP: SKIP_STYLE,
    }[r.status]
    icon = r.icon
    line = f"  {style}{icon} {r.name}{RESET}"
    if r.detail:
        line += f"  — {r.detail}"
    print(line)
    if r.fix and r.status in (Status.FAIL, Status.WARN):
        print(f"    {SKIP_STYLE}→ fix: {r.fix}{RESET}")


def run_checks(
    project_root: str,
    checks: list[tuple[str, Callable[[str], CheckResult]]],
    category: str,
) -> list[CheckResult]:
    """运行一组检查并打印结果"""
    results = []
    for name, check_fn in checks:
        r = check_fn(project_root)
        results.append(r)
        _print_result(r)
    return results


def run_all(project_root: str, categories: list[str] | None = None) -> bool:
    """运行所有检查。返回 True 表示全部通过（无 FAIL）"""
    all_checks: dict[str, list[tuple[str, Callable[[str], CheckResult]]]] = {
        "sha": SHA_CHECKS,
        "py": PY_CHECKS,
        "general": GENERAL_CHECKS,
    }

    target = categories or list(all_checks.keys())
    all_results: list[CheckResult] = []

    for cat in target:
        if cat in all_checks:
            _print_header(f"📋 {cat.upper()} checks")
            results = run_checks(project_root, all_checks[cat], cat)
            all_results.extend(results)

    # Summary
    fail_count = sum(1 for r in all_results if r.status == Status.FAIL)
    warn_count = sum(1 for r in all_results if r.status == Status.WARN)
    pass_count = sum(1 for r in all_results if r.status == Status.PASS)
    skip_count = sum(1 for r in all_results if r.status == Status.SKIP)

    print(
        f"\n{BOLD}Summary:{RESET} {PASS_STYLE}{pass_count} passed{RESET}, "
        f"{WARN_STYLE}{warn_count} warnings{RESET}, "
        f"{FAIL_STYLE}{fail_count} failed{RESET}, "
        f"{SKIP_STYLE}{skip_count} skipped{RESET}"
    )

    if fail_count > 0:
        print(
            f"\n{FAIL_STYLE}❌ {fail_count} check(s) failed. Fix them before committing.{RESET}"
        )
    elif warn_count > 0:
        print(f"\n{WARN_STYLE}⚠️  {warn_count} warning(s). Recommended to fix.{RESET}")
    else:
        print(f"\n{PASS_STYLE}✅ All checks passed!{RESET}")

    return fail_count == 0


# ============================================================================
# CLI registration
# ============================================================================

doctor_app = App(name="doctor", help="项目规范自动检查")


@doctor_app.default
def work_doctor(
    verbose: VerboseFlag = 0,
    sha: Annotated[
        bool,
        Parameter(name=["--sha"], help="sha.sh checks only", group="Category"),
    ] = False,
    py: Annotated[
        bool,
        Parameter(name=["--py"], help="pyproject.toml checks only", group="Category"),
    ] = False,
):
    """
    Check project conventions automatically.

    Examples:
      dev doctor           # run all checks
      dev doctor --sha     # sha.sh checks only
      dev doctor --py      # python project checks only
    """
    set_verbosity(verbose)
    project_root = _find_project_root(os.getcwd())
    info(f"Project root: {project_root}")

    if not sha and not py:
        run_all(project_root)
    else:
        categories = []
        if sha:
            categories.append("sha")
        if py:
            categories.append("py")
        categories.append("general")
        run_all(project_root, categories)
