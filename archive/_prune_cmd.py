"""dev prune - 清理已完成合并的工作项

删除远程分支 + worktree，保留本地分支供人类 review。
"""

import os
import re
from dataclasses import dataclass, field
from importlib.metadata import version as pkg_version
from typing import Annotated

from cyclopts import App, Parameter

from ._gh_ops import (
    gh_issue_close,
    gh_issue_comment,
    gh_issue_view,
    gh_pr_list_by_branch,
)
from ._git_ops import (
    get_github_repo,
    get_main_branch,
    git_branch_delete_remote,
    git_worktree_remove,
    parse_issue_number,
    run,
)
from ._json_output import output_json
from ._log import VerboseFlag, set_verbosity

DIYDEV_VERSION = pkg_version("diydev")


def _build_close_comment(pr_number: int) -> str:
    """生成关闭 issue 时的评论"""
    return (
        f"Closed because #{pr_number} was merged.\n\n"
        f"---\n"
        f"*Automated by [diydev](https://github.com/diy-agent/diy/tree/main/packages/diydev) v{DIYDEV_VERSION}*"
    )


def validate_worktree_path(path: str, cwd: str | None = None) -> str:
    """校验路径是否为合法的 git worktree。

    校验:
      1. 路径在 git worktree list 中
      2. 不是主仓库（.git 是目录，worktree 的 .git 是文件）

    返回绝对路径。非法时抛出 RuntimeError。
    """
    abs_path = os.path.realpath(path)

    # 拒绝主仓库路径：.git 是目录（worktree 的 .git 是文件）
    git_path = os.path.join(abs_path, ".git")
    if os.path.isdir(git_path):
        raise RuntimeError(
            f"拒绝删除主仓库路径: {abs_path}（包含 .git 目录，这是主仓库！）"
        )

    # 校验在 git worktree list 中
    raw = run("git worktree list", cwd=cwd)
    matched = False
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 1:
            continue
        wt_path = os.path.realpath(parts[0])
        if wt_path == abs_path:
            matched = True
            break

    if not matched:
        raise RuntimeError(
            f"不是 git worktree: {abs_path}（不在 git worktree list 中）"
        )

    return abs_path


@dataclass
class _RawWorktree:
    """原始 worktree 信息（未查 PR 状态）"""

    full_path: str
    branch: str
    worktree_path: str  # 相对/简短路径


def scan_prunable_raw(cwd: str | None = None) -> list[_RawWorktree]:
    """扫描所有 worktree，返回原始列表（不查 PR，用于单元测试）"""
    main_branch = get_main_branch()
    raw = run("git worktree list", cwd=cwd)
    cwd_root = cwd if cwd else run("pwd", cwd=cwd)
    results: list[_RawWorktree] = []

    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 3:
            continue

        full_path = parts[0]
        bracket_match = re.search(r"\[(.+?)\]", line)
        branch = bracket_match.group(1).strip() if bracket_match else ""

        if not branch or branch == main_branch:
            continue

        if full_path == cwd_root:
            wt_path = "."
        elif full_path.startswith(cwd_root + "/"):
            wt_path = full_path[len(cwd_root) + 1 :]
        else:
            wt_path = full_path

        results.append(
            _RawWorktree(
                full_path=full_path,
                branch=branch,
                worktree_path=wt_path,
            )
        )

    return results


def safe_remove_worktree(wt_path: str, project_root: str) -> str:
    """安全删除 worktree：先校验路径合法性，再执行 remove。

    返回绝对路径。
    """
    abs_path = validate_worktree_path(wt_path, project_root)
    git_worktree_remove(abs_path)
    return abs_path


prune_app = App(name="prune", help="清理已完成合并的 worktree 和分支")


@dataclass
class _PruneTarget:
    """待清理的工作项"""

    branch: str
    worktree_path: str
    pr_number: int
    pr_state: str
    orphan_issue: int | None = field(default=None)


def _scan_prunable(repo: str) -> list[_PruneTarget]:
    """扫描所有 worktree，返回 PR 已 MERGED 的待清理列表"""
    main_branch = get_main_branch()
    raw = run("git worktree list")
    targets: list[_PruneTarget] = []
    cwd_root = run("pwd")

    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 3:
            continue

        full_path = parts[0]
        bracket_match = re.search(r"\[(.+?)\]", line)
        branch = bracket_match.group(1).strip() if bracket_match else ""

        # 跳过主分支和空分支（prunable worktree）
        if not branch or branch == main_branch:
            continue

        # 查询 PR 状态（合并后的 PR 需要 --state merged）
        pr = gh_pr_list_by_branch(repo, branch, state="merged")
        if not pr:
            continue

        if pr.get("state") != "MERGED":
            continue

        # 构建 worktree 路径
        if full_path == cwd_root:
            wt_path = "."
        elif full_path.startswith(cwd_root + "/"):
            wt_path = full_path[len(cwd_root) + 1 :]
        else:
            wt_path = full_path

        # 从分支名提取关联的 issue 编号，检查是否仍为 open
        orphan_issue: int | None = None
        issue_num = parse_issue_number(branch)
        if issue_num:
            try:
                issue = gh_issue_view(issue_num, repo, fields="number,state")
                if issue.get("state") == "OPEN":
                    orphan_issue = issue_num
            except RuntimeError:
                pass  # issue 不存在或无权限，跳过

        targets.append(
            _PruneTarget(
                branch=branch,
                worktree_path=wt_path,
                pr_number=pr["number"],
                pr_state=pr["state"],
                orphan_issue=orphan_issue,
            )
        )

    return targets


@prune_app.default
def work_prune(
    verbose: VerboseFlag = 0,
    dry_run: Annotated[
        bool,
        Parameter(
            name=["--dry-run"],
            help="仅列出待清理项，不实际执行",
        ),
    ] = False,
    yes: Annotated[
        bool,
        Parameter(
            name=["--yes", "-y"],
            help="跳过确认，直接清理（Agent: 建议使用 --yes 跳过交互）",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        Parameter(name=["--json"], help="JSON 格式输出，自动跳过确认 (agent 使用)"),
    ] = False,
):
    """清理 PR 已合并的 worktree（删远程分支 + worktree，保留本地分支）。

    本地分支留给人类 review 后手动清理。

    示例:
      dev prune            # 列出并确认后清理
      dev prune --dry-run  # 仅预览，不执行
      dev prune --yes      # 直接清理，跳过确认
      dev prune --json     # JSON 输出，自动确认
    """
    set_verbosity(verbose)
    repo = get_github_repo()
    cwd = os.getcwd()
    targets = _scan_prunable(repo)

    if not targets:
        if json_output:
            output_json({"items": []}, "没有需要清理的工作项")
        else:
            print("没有需要清理的工作项")
        return

    orphan_count = sum(1 for t in targets if t.orphan_issue)

    if json_output:
        # JSON 模式：列出后直接执行
        items_preview = []
        for t in targets:
            item = {
                "branch": t.branch,
                "pr_number": t.pr_number,
                "worktree_path": t.worktree_path,
            }
            if t.orphan_issue:
                item["orphan_issue"] = t.orphan_issue
            items_preview.append(item)

        if dry_run:
            output_json(
                {"items": items_preview, "dry_run": True},
                f"共 {len(targets)} 项 (dry-run)",
            )
            return

        # 执行
        cleaned = 0
        errors = 0
        for t in targets:
            if t.orphan_issue:
                try:
                    comment = _build_close_comment(t.pr_number)
                    gh_issue_comment(t.orphan_issue, comment, repo)
                    gh_issue_close(t.orphan_issue, repo)
                except RuntimeError:
                    errors += 1

            try:
                git_branch_delete_remote(t.branch)
            except RuntimeError:
                errors += 1

            try:
                abs_path = safe_remove_worktree(t.worktree_path, cwd)
            except RuntimeError:
                errors += 1

            cleaned += 1

        output_json(
            {"items": items_preview, "cleaned": cleaned, "errors": errors},
            f"清理 {cleaned} 项" + (f" ({errors} 个错误)" if errors else ""),
        )
        return

    # --- 文本模式 ---
    print("待清理的工作项 (PR 已合并):\n")
    for t in targets:
        print(f"  分支: {t.branch}")
        print(f"   PR:  #{t.pr_number} ({t.pr_state})")
        print(f"   WT:  {t.worktree_path}")
        if t.orphan_issue:
            print(f"  Issue: #{t.orphan_issue} (仍 open)")
        print()
    if orphan_count:
        print(f"  其中 {orphan_count} 项有关联 issue 仍处于 open 状态，将一并关闭\n")

    if dry_run:
        print(f"[dry-run] 共 {len(targets)} 项，未执行清理")
        return

    if not yes:
        try:
            answer = input(f"确认清理以上 {len(targets)} 项? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n已取消")
            return
        if answer != "y":
            print("已取消")
            return

    cleaned = 0
    errors = 0
    for t in targets:
        print(f"\n清理: {t.branch} (PR #{t.pr_number})")

        if t.orphan_issue:
            try:
                comment = _build_close_comment(t.pr_number)
                gh_issue_comment(t.orphan_issue, comment, repo)
                gh_issue_close(t.orphan_issue, repo)
                print(f"  ✓ 关闭 issue #{t.orphan_issue}")
            except RuntimeError as e:
                print(f"  ✗ 关闭 issue #{t.orphan_issue} 失败: {e}")
                errors += 1

        try:
            git_branch_delete_remote(t.branch)
            print(f"  ✓ 删除远程分支 origin/{t.branch}")
        except RuntimeError as e:
            print(f"  ✗ 删除远程分支失败: {e}")
            errors += 1

            try:
                abs_path = safe_remove_worktree(t.worktree_path, cwd)
                print(f"  ✓ 删除 worktree {abs_path}")
            except RuntimeError as e:
                print(f"  ✗ 删除 worktree 失败: {e}")
            errors += 1

        print(f"  → 本地分支 {t.branch} 已保留，请 review 后手动清理")
        cleaned += 1

    print(f"\n完成: 清理 {cleaned} 项", end="")
    if orphan_count:
        print(f"  (关闭 {orphan_count} 个 issue)", end="")
    if errors:
        print(f"  ({errors} 个错误)")
    else:
        print()
