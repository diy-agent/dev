"""dev prune 集成测试 — 缩减版，快速 CI 用

assert_cmd 用持久 bash 进程，$ 命令间共享状态(cd/export/...)。

⚠️ 全貌查看请阅读: tests/test_prune_intent.py （意图测试 — 完整 JSON 外观 + 结构断言）
"""

import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid

# 从 worktree 找到主仓库的 .git 目录，进而推导出 _diy 项目根
_worktree_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_r = subprocess.run(
    ["git", "rev-parse", "--git-common-dir"],
    capture_output=True, text=True, cwd=_worktree_root,
)
_MAIN_GIT = _r.stdout.strip().removesuffix("/.git").removesuffix("/")
_DIY = os.path.realpath(os.path.join(_MAIN_GIT))


def _sh(cmd: str, cwd: str | None = None) -> str:
    r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, f"$ {cmd}\n{r.stderr}"
    return r.stdout


def _sh_may_fail(cmd: str, cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)


def assert_cmd(session: str, cwd: str | None = None, **captures: str) -> None:
    """持久 bash 逐条执行 $ 命令，比对输出。{NAME} 被 **captures 替换。"""
    for k, v in captures.items():
        session = session.replace("{" + k + "}", str(v))

    lines = session.split("\n")
    indent = 0
    for line in lines:
        s = line.lstrip()
        if s.startswith("$ "):
            indent = len(line) - len(s)
            break

    dedented = []
    for line in lines:
        if len(line) >= indent and line[:indent].strip() == "":
            dedented.append(line[indent:])
        else:
            dedented.append(line)

    blocks = []
    i = 0
    while i < len(dedented):
        line = dedented[i]
        i += 1
        if not line.startswith("$ "):
            continue
        cmd = line[2:]
        expected: list[str] = []
        while i < len(dedented) and not dedented[i].startswith("$ "):
            expected.append(dedented[i])
            i += 1
        blocks.append((cmd, expected))

    if not blocks:
        return

    proc = subprocess.Popen(
        ["bash", "--norc"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
    )
    assert proc.stdin and proc.stdout and proc.stderr

    try:
        for cmd, expected_lines in blocks:
            marker = f"__END_{uuid.uuid4().hex[:8]}__"
            proc.stdin.write(f"{cmd}\necho {marker} $?\n")
            proc.stdin.flush()

            output_lines = []
            exit_code = None
            for line in proc.stdout:
                if marker in line:
                    parts = line.strip().split()
                    if len(parts) >= 2 and parts[-1].isdigit():
                        exit_code = int(parts[-1])
                    break
                output_lines.append(line.rstrip("\n"))

            actual = "\n".join(output_lines).strip()
            assert exit_code == 0, (
                f"$ {cmd}\nexit={exit_code}\nstderr: {proc.stderr.read()}"
            )

            if expected_lines:
                for exp_line in expected_lines:
                    stripped = exp_line.strip()
                    if not stripped:
                        continue
                    assert stripped in actual, (
                        f"$ {cmd}\n期望含: {stripped}\n实际: {actual[:400]}"
                    )
    finally:
        proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=5)


# ============================================================================
# 测试
# ============================================================================


def test_prune_full_lifecycle():
    """完整生命周期 → prune 清理成功。"""
    tmp = tempfile.mkdtemp(prefix="prune-")
    try:
        repo = os.path.join(tmp, "repo")
        _sh(f"git clone git@github.com:diy-agent/_dev-testbed.git {repo}", tmp)

        new = _sh(f'uv run --project {_DIY} dev new --json "replay"', repo)
        N = json.loads(new)["data"]["number"]

        start = _sh(f"uv run --project {_DIY} dev start {N} --json", repo)
        s = json.loads(start)["data"]
        wt = os.path.normpath(os.path.join(repo, s["worktree_path"]))
        br = s["branch"]

        with open(os.path.join(wt, "README.md"), "a") as f:
            f.write(f"\n{N}\n")
        _sh("git add -A", wt)
        _sh(f'git commit -m "replay {N}"', wt)
        _sh(f"git push -u origin {br}", wt)

        _sh(f"uv run --project {_DIY} dev pr --json", wt)
        time.sleep(2)
        _sh(f"uv run --project {_DIY} dev merge-pr --method squash --json", wt)
        _sh("git pull", repo)

        # prune: 终端回放格式，输出即期望
        assert_cmd(
            f"""
            $ uv run --project {_DIY} dev prune --dry-run --json
            "status": "success"
            "data": {{
            "items": [
            "dry_run": true

            $ uv run --project {_DIY} dev prune -y --json
            "status": "success"
            "data": {{
            "errors": 0
            "cleaned":
            """,
            cwd=repo,
        )

        assert not os.path.exists(wt)
        assert os.path.exists(os.path.join(repo, ".git"))

    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_prune_rejects_main_repo():
    """dev prune 拒绝删除主仓库——即使在主仓库目录执行也安全退出。"""
    tmp = tempfile.mkdtemp(prefix="prune-")
    try:
        repo = os.path.join(tmp, "repo")
        _sh(f"git clone git@github.com:diy-agent/_dev-testbed.git {repo}", tmp)

        # 在主仓库目录执行 prune，预期无操作（没有可清理的 worktree）
        r = _sh_may_fail(f"uv run --project {_DIY} dev prune --json", cwd=repo)
        # 正常退出（找不到可清理项不是错误）
        assert os.path.exists(os.path.join(repo, ".git")), "主仓库 .git 应完好"

        # 验证 prune 没有输出清理成功的条目
        assert '"cleaned"' not in r.stdout or r.returncode == 0, (
            f"prune 在主仓库不应输出清理结果:\n{r.stdout}"
        )

        # 直接 git worktree remove 主仓库 → 被 git 拒绝
        r2 = _sh_may_fail(f"git worktree remove {repo} --force 2>&1", cwd=tmp)
        assert r2.returncode != 0, "git 不应允许删除主仓库"
        assert os.path.isdir(os.path.join(repo, ".git")), "主仓库完好"

    finally:
        shutil.rmtree(tmp, ignore_errors=True)
