"""_check_branch_unmerged_changes 单元测试

覆盖三种 GitHub merge 方式:
  - Squash merge:  diff(S^..S) vs diff(S^..branch)
  - Merge commit:  检查 merge 后分支有无新 commit
  - Rebase merge:  git cherry 检测
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


# ============================================================================
# Fixtures
# ============================================================================


class GitRepo:
    """临时 git 仓库，模拟 origin + local clone 结构。

    用法:
        with GitRepo() as repo:
            repo.commit("message")
            repo.branch("feature")
            repo.squash_merge("feature", "#42", "feat: something")

    结构:
        repo.origin/   — bare repo (充当远程)
        repo.local/    — clone from origin
    """

    def __init__(self):
        self._tmp = tempfile.mkdtemp(prefix="diy-test-check-branch-")
        self.origin = os.path.join(self._tmp, "origin.git")
        self.local = os.path.join(self._tmp, "local")
        self.main_branch = "main"

    def setup(self):
        """初始化 bare origin + clone"""
        # bare origin
        self._run(f"git init --bare {shlex_quote(self.origin)}", self._tmp)

        # clone
        self._run(
            f"git clone {shlex_quote(self.origin)} {shlex_quote(self.local)}",
            self._tmp,
        )

        # 初始 commit（在 local 中做，然后 push）
        (Path(self.local) / "README.md").write_text("# test\n")
        self._run("git add -A && git commit -m 'initial commit'", self.local)
        self._run(f"git push origin {self.main_branch}", self.local)
        self._run(f"git branch --set-upstream-to=origin/{self.main_branch}", self.local)
        return self

    def commit(self, message: str, branch: str | None = None):
        """在指定分支上创建 commit 并 push 到 origin"""
        cwd = self.local
        if branch:
            self._run(f"git checkout {shlex_quote(branch)}", cwd)
        fname = f"file-{message.replace(' ', '-')[:20]}.txt"
        (Path(cwd) / fname).write_text(message + "\n")
        self._run(f"git add -A && git commit -m '{message}'", cwd)
        # push 到 origin，确保 origin/branch 与本地同步
        current = self._run("git rev-parse --abbrev-ref HEAD", cwd)
        self._push_branch(current)

    def branch(self, name: str) -> str:
        """创建并切换到新分支，push 到 origin，返回分支名"""
        cwd = self.local
        self._run(f"git checkout -b {shlex_quote(name)}", cwd)
        self._push_branch(name)
        return name

    def squash_merge(self, branch: str, pr_number: int, title: str):
        """模拟 squash merge：在 main 上创建一个 squash commit。

        squashed content = 从分支 fork point 到分支 tip 的所有 diff，
        用 git merge --squash 产生真实 squash diff，然后 commit。
        """
        cwd = self.local
        # 保存分支 tip
        branch_tip = self._run(f"git rev-parse {shlex_quote(branch)}", cwd)

        # 回到 main
        self._run(f"git checkout {self.main_branch}", cwd)
        self._run(f"git pull origin {self.main_branch}", cwd)

        # git merge --squash 产生 index 变更
        self._run(f"git merge --squash {shlex_quote(branch)}", cwd)
        # commit with PR number
        self._run(
            f"git commit -m '{title} (#{pr_number})'",
            cwd,
        )
        self._run(f"git push origin {self.main_branch}", cwd)

    def true_merge(self, branch: str, pr_number: int, title: str):
        """模拟 true merge commit：在 main 上创建 --no-ff merge。

        返回 merge commit SHA。
        """
        cwd = self.local
        self._run(f"git checkout {self.main_branch}", cwd)
        self._run(f"git pull origin {self.main_branch}", cwd)

        self._run(
            f"git merge --no-ff {shlex_quote(branch)} "
            f"-m 'Merge pull request #{pr_number} from {branch}'",
            cwd,
        )
        self._run(f"git push origin {self.main_branch}", cwd)
        return self._run(f"git rev-parse HEAD", cwd)

    def rebase_merge(self, branch: str, pr_number: int, title: str):
        """模拟 rebase merge：将分支 commit cherry-pick 到 main。

        分支的 commit 内容一致但 hash 不同（模拟 GitHub rebase merge）。
        """
        cwd = self.local
        # 获取分支上的 commits
        merge_base = self._run(
            f"git merge-base {self.main_branch} {shlex_quote(branch)}", cwd
        )
        commits = self._run(
            f"git log --reverse --format=%H {merge_base}..{shlex_quote(branch)}",
            cwd,
        ).split()

        # 在 main 上 cherry-pick 每个 commit
        self._run(f"git checkout {self.main_branch}", cwd)
        self._run(f"git pull origin {self.main_branch}", cwd)
        for c in commits:
            self._run(f"git cherry-pick {c}", cwd)

        self._run(f"git push origin {self.main_branch}", cwd)

    def switch(self, branch: str):
        """切换 local 到指定分支并 pull"""
        self._run(f"git checkout {shlex_quote(branch)}", self.local)
        self._run(f"git pull origin {shlex_quote(branch)}", self.local)

    def add_commit_to_branch(self, branch: str, message: str):
        """在分支上追加一个新 commit 并 push"""
        self.commit(message, branch=branch)

    def destroy(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    # -- internal helpers --

    def _push_branch(self, branch: str):
        self._run(
            f"git push -u origin {shlex_quote(branch)}", self.local,
        )

    @staticmethod
    def _run(cmd: str, cwd: str) -> str:
        r = subprocess.run(
            cmd, shell=True, cwd=cwd, capture_output=True, text=True,
        )
        if r.returncode != 0:
            raise RuntimeError(f"cmd failed [{cwd}]: {cmd}\n{r.stderr}")
        return r.stdout.strip()


def shlex_quote(s: str) -> str:
    import shlex
    return shlex.quote(s)


# ============================================================================
# Tests
# ============================================================================


class TestSquashMerge:
    """Squash merge 场景：比较 diff(S^..S) vs diff(S^..branch)。"""

    def test_fully_merged_safe(self):
        """分支完全 squash 进 main → 返回 None（安全）"""
        repo = GitRepo().setup()
        try:
            repo.branch("fix/42-test")
            repo.commit("feat: add feature A", branch="fix/42-test")
            repo.commit("feat: add feature B", branch="fix/42-test")
            repo.squash_merge("fix/42-test", 42, "feat: my feature")

            # 先 fetch 让 origin/branch 可见
            repo._run("git fetch origin", repo.local)
            repo.switch(repo.main_branch)

            result = _call_check(repo, "fix/42-test", pr_number=42)
            assert result is None, f"完全合并应返回 None，实际: {result}"
        finally:
            repo.destroy()

    def test_branch_has_new_commits_after_squash(self):
        """分支在 squash 后有新 commit → 返回错误 dict"""
        repo = GitRepo().setup()
        try:
            repo.branch("fix/43-test")
            repo.commit("feat: original work", branch="fix/43-test")
            repo.squash_merge("fix/43-test", 43, "feat: original")

            # 合并后分支又加了新 commit
            repo.add_commit_to_branch("fix/43-test", "fix: post-merge fix")

            repo._run("git fetch origin", repo.local)
            repo.switch(repo.main_branch)

            result = _call_check(repo, "fix/43-test", pr_number=43)
            assert result is not None, "分支有新 commit 应返回错误"
            assert "变更未进 main" in result["category"]
        finally:
            repo.destroy()

    def test_no_pr_number_match_falls_back_to_cherry(self):
        """找不到对应的 squash commit → fallback 到 git cherry"""
        repo = GitRepo().setup()
        try:
            repo.branch("fix/99-test")
            repo.commit("feat: standalone work", branch="fix/99-test")
            # 不创建对应的 squash commit，所以 grep #99 找不到

            repo._run("git fetch origin", repo.local)
            repo.switch(repo.main_branch)

            result = _call_check(repo, "fix/99-test", pr_number=99)
            # 分支有 commits 未 merge → cherry 应检测到
            assert result is not None, "找不到 PR commit + 有未合入 commit → 应报错"
            assert "未合入 main 的 commit" in result["category"]
        finally:
            repo.destroy()


class TestMergeCommit:
    """Merge commit (--no-ff) 场景。"""

    def test_fully_merged_safe(self):
        """分支通过 merge commit 合入 → 返回 None"""
        repo = GitRepo().setup()
        try:
            repo.branch("fix/50-test")
            repo.commit("feat: merge feature", branch="fix/50-test")
            repo.true_merge("fix/50-test", 50, "feat: merge feature")

            repo._run("git fetch origin", repo.local)
            repo.switch(repo.main_branch)

            result = _call_check(repo, "fix/50-test", pr_number=50)
            assert result is None, f"完全合并应返回 None，实际: {result}"
        finally:
            repo.destroy()

    def test_branch_has_new_commits_after_merge(self):
        """merge 后分支有新 commit → 返回错误 dict"""
        repo = GitRepo().setup()
        try:
            repo.branch("fix/51-test")
            repo.commit("feat: merge work", branch="fix/51-test")
            repo.true_merge("fix/51-test", 51, "feat: merge work")

            # merge 后分支又加了新 commit
            repo.add_commit_to_branch("fix/51-test", "fix: post-merge")

            repo._run("git fetch origin", repo.local)
            repo.switch(repo.main_branch)

            result = _call_check(repo, "fix/51-test", pr_number=51)
            assert result is not None, "分支有新 commit 应返回错误"
            assert "变更未进 main" in result["category"]
        finally:
            repo.destroy()


class TestRebaseMerge:
    """Rebase merge 场景：git cherry fallback。"""

    def test_fully_rebased_safe(self):
        """分支已 rebase 进 main（cherry 全 -）→ 返回 None"""
        repo = GitRepo().setup()
        try:
            repo.branch("fix/60-test")
            repo.commit("feat: rebase work A", branch="fix/60-test")
            repo.commit("feat: rebase work B", branch="fix/60-test")

            # rebase merge: cherry-pick 到 main
            repo.rebase_merge("fix/60-test", 60, "feat: rebase work")

            repo._run("git fetch origin", repo.local)
            repo.switch(repo.main_branch)

            result = _call_check(repo, "fix/60-test", pr_number=60)
            # cherry 应该判定全部已合入
            assert result is None, f"rebase 后 cherry 应返回 None，实际: {result}"
        finally:
            repo.destroy()

    def test_branch_has_unmerged_commits_after_rebase(self):
        """rebase 后分支有新增未合入 commit → 返回错误 dict"""
        repo = GitRepo().setup()
        try:
            repo.branch("fix/61-test")
            repo.commit("feat: rebase work A", branch="fix/61-test")
            repo.rebase_merge("fix/61-test", 61, "feat: rebase work")

            # rebase 后分支又加了新 commit
            repo.add_commit_to_branch("fix/61-test", "feat: unrebaseable extra")

            repo._run("git fetch origin", repo.local)
            repo.switch(repo.main_branch)

            result = _call_check(repo, "fix/61-test", pr_number=61)
            assert result is not None, "rebase 后有未合入 commit 应报错"
            assert "未合入 main 的 commit" in result["category"]
        finally:
            repo.destroy()


class TestEdgeCases:
    """边界场景。"""

    def test_main_branch_itself(self):
        """对 main 分支自己检查 → 不应报错（无 PR commit 匹配时正常）"""
        repo = GitRepo().setup()
        try:
            repo._run("git fetch origin", repo.local)
            result = _call_check(repo, repo.main_branch, pr_number=9999)
            # main 没有 PR#9999，cherry 也不该有未合入 commit
            assert result is None, f"main 分支自身检查应返回 None"
        finally:
            repo.destroy()

    def test_pr_number_not_on_main(self):
        """PR number 在 main 历史里完全不存在 → 返回 None（无匹配 commit）"""
        repo = GitRepo().setup()
        try:
            repo.branch("fix/200-test")
            repo.commit("feat: standalone", branch="fix/200-test")
            # 不创建任何 merge commit — PR #200 不存在于 main

            repo._run("git fetch origin", repo.local)
            repo.switch(repo.main_branch)

            result = _call_check(repo, "fix/200-test", pr_number=200)
            # cherry 显示有未合入 commit（分支上有 commit 没进 main）
            assert result is not None, "未合入 commit 应被检测到"
        finally:
            repo.destroy()


# ============================================================================
# Helper
# ============================================================================


def _call_check(repo: GitRepo, branch: str, pr_number: int) -> dict | None:
    """调用 _check_branch_unmerged_changes 并返回结果。"""
    from diydev._status_cmd import _check_branch_unmerged_changes

    return _check_branch_unmerged_changes(
        branch=branch,
        main_branch=repo.main_branch,
        pr_number=pr_number,
        cwd=repo.local,
    )
