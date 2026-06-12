"""dev prune 意图测试 — 面向人类与 agent 的完整外观

意图测试 = 用 terminal transcript 格式（$ 命令 → 完整输出）直接表达意图。
阅读本文件 = 理解 dev prune 全貌，无需查文档。

与 test_prune_integration.py 的关系：
  - 意图测试：全貌、慢、文档级（人类和 agent 阅读用）
  - 集成测试：缩减、快、CI 级（assert_cmd 片段匹配用）

语法（assert_intent）：
  $ <command>              — 执行命令（持久 bash，cd/export 跨 $ 共享）
  <text line>              — 预期输出行（substring 匹配）
  { ... }                  — JSON 预期（结构匹配，自动处理单行/多行）
  ...                      — 跳过任意输出（通配符）
  # <comment>              — 注释行（文档用，跳过匹配）
  （无预期行）              — 只运行不校验输出
"""

import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid


# ---------------------------------------------------------------------------
# 找到主仓库 _diy（兼容 worktree 环境）
# ---------------------------------------------------------------------------
_worktree_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_r = subprocess.run(
    ["git", "rev-parse", "--git-common-dir"],
    capture_output=True, text=True, cwd=_worktree_root,
)
_MAIN_GIT = _r.stdout.strip().removesuffix("/.git").removesuffix("/")
_DIY = os.path.realpath(os.path.join(_MAIN_GIT))


def _sh(cmd: str, *, cwd: str | None = None) -> str:
    """运行命令，非零退出 → AssertionError"""
    r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, f"$ {cmd}\n{r.stderr}"
    return r.stdout


# ============================================================================
# assert_intent — 意图测试引擎
# ============================================================================

def _try_parse_json(text: str) -> object | None:
    """尝试将 text 解析为 JSON，失败返回 None。"""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def _json_contains(expected: object, actual: object) -> bool:
    """递归检查 expected 的每个 key/value 是否存在于 actual 中。

    expected 是"必须满足的约束"集合，actual 可以有额外字段。
    """
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        return all(
            k in actual and _json_contains(expected[k], actual[k])
            for k in expected
        )
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return False
        if len(expected) == 0:
            return len(actual) == 0
        # 每个 expected 元素必须在 actual 中找到匹配
        actual_remaining = list(actual)
        for exp_item in expected:
            found = False
            for i, act_item in enumerate(actual_remaining):
                if _json_contains(exp_item, act_item):
                    actual_remaining.pop(i)
                    found = True
                    break
            if not found:
                return False
        return True
    # 标量：直接比较
    return expected == actual


def _match_lines(
    expected_lines: list[str],
    actual: str,
) -> None:
    """逐行匹配 expected_lines 与 actual 输出。

    规则：
      - 空行 / 纯空白 → 跳过
      - ... → 通配符（跳过任意一行实际输出）
      - 否则 → expected_line in actual（substring）
    """
    if not expected_lines:
        return

    actual_lines = actual.split("\n")
    ai = 0

    for exp_line in expected_lines:
        stripped = exp_line.strip()
        if not stripped:
            continue
        if stripped == "...":
            if ai < len(actual_lines):
                ai += 1
            continue
        # 在剩余 actual_lines 中查找匹配
        found = False
        while ai < len(actual_lines):
            if stripped in actual_lines[ai]:
                found = True
                ai += 1
                break
            ai += 1
        assert found, (
            f"期望含: {stripped!r}\n"
            f"实际输出:\n{actual[:600]}"
        )


def assert_intent(
    session: str,
    cwd: str | None = None,
) -> None:
    """意图测试：$ 命令 → 完整输出，支持 JSON 结构匹配。

    增强点（vs assert_cmd）：
      - JSON 输出用递归结构匹配而非 substring
      - ... 行 = 通配符（跳过输出行）
      - # 开头行 = 注释（纯文档，不参与匹配）
      - 无预期行 = 只运行命令，不校验输出

    变量替换用 Python f-string 在调用侧完成，本函数不做模板处理。
    """
    lines = session.split("\n")

    # 找到第一个 $ 的缩进量，用于 dedent
    indent = 0
    for line in lines:
        s = line.lstrip()
        if s.startswith("$ "):
            indent = len(line) - len(s)
            break

    dedented: list[str] = []
    for line in lines:
        if len(line) >= indent and line[:indent].strip() == "":
            dedented.append(line[indent:])
        else:
            dedented.append(line)

    # 解析为命令块
    blocks: list[tuple[str, list[str]]] = []  # [(cmd, expected_lines), ...]
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

    # 启动持久 bash
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

            output_lines: list[str] = []
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

            # 过滤注释行
            check_lines = [
                ln for ln in expected_lines
                if ln.strip() and not ln.strip().startswith("#")
            ]

            if not check_lines:
                # 无预期行 → 只运行不校验
                continue

            # 尝试 JSON 结构匹配
            joined = "\n".join(check_lines).strip()
            expected_json = _try_parse_json(joined)
            actual_json = _try_parse_json(actual)

            if expected_json is not None and actual_json is not None:
                # JSON 结构匹配
                ok = _json_contains(expected_json, actual_json)
                if not ok:
                    pretty_exp = json.dumps(expected_json, indent=2, ensure_ascii=False)
                    pretty_act = json.dumps(actual_json, indent=2, ensure_ascii=False)
                    assert False, (
                        f"$ {cmd}\n"
                        f"JSON 结构不匹配\n"
                        f"期望:\n{pretty_exp}\n"
                        f"实际:\n{pretty_act}"
                    )
            else:
                # 文本行匹配
                _match_lines(check_lines, actual)
    finally:
        proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=5)


# ============================================================================
# 意图测试：prune 完整生命周期 — 全貌展示
# ============================================================================

def test_intent_prune_full_lifecycle():
    """意图：完整 dev 工作流 → prune 清理

    dev new → start → 提交/push/PR/merge → prune 全链路完整 JSON 外观。
    阅读顺序 = 时间线 = 人类理解顺序。
    """
    tmp = tempfile.mkdtemp(prefix="prune-intent-")
    try:
        repo = os.path.join(tmp, "repo")

        # ── 0. 准备仓库 ───────────────────────────────────────────
        _sh(f"git clone git@github.com:diy-agent/_dev-testbed.git {repo}", cwd=tmp)

        # 获取初始数据（后续 {N} {BR} {PR} 替换用）
        new_raw = _sh(f'uv run --project {_DIY} dev new --json "replay"', cwd=repo)
        N = json.loads(new_raw)["data"]["number"]

        start_raw = _sh(f"uv run --project {_DIY} dev start {N} --json", cwd=repo)
        s = json.loads(start_raw)["data"]
        wt = os.path.normpath(os.path.join(repo, s["worktree_path"]))
        br = s["branch"]

        # 提交 → push → PR → merge
        with open(os.path.join(wt, "README.md"), "a") as f:
            f.write(f"\n{N}\n")
        _sh("git add -A", cwd=wt)
        _sh(f'git commit -m "replay {N}"', cwd=wt)
        _sh(f"git push -u origin {br}", cwd=wt)
        _sh(f"uv run --project {_DIY} dev pr --json", cwd=wt)
        time.sleep(2)
        merge_raw = _sh(f"uv run --project {_DIY} dev merge-pr --method squash --json", cwd=wt)
        PR = json.loads(merge_raw)["data"]["pr_number"]
        _sh("git pull", cwd=repo)

        # ── 意图 transcript ───────────────────────────────────────
        # 预期输出：用 Python dict 构建，json.dumps 格式化。
        # f-string 里只有简单变量，零花括号冲突。
        REPO_NAME = os.path.basename(repo)
        expected_dry = json.dumps({
            "status": "success",
            "data": {
                "items": [
                    {"branch": br, "pr_number": PR, "worktree_path": f"../{REPO_NAME}-{br}"}
                ],
                "dry_run": True,
            },
        }, indent=2, ensure_ascii=False)

        expected_clean = json.dumps({
            "status": "success",
            "data": {
                "items": [
                    {"branch": br, "pr_number": PR}
                ],
                "cleaned": 1,
                "errors": 0,
            },
        }, indent=2, ensure_ascii=False)

        assert_intent(
            f"""$ uv run --project {_DIY} dev prune --dry-run --json
{expected_dry}

$ uv run --project {_DIY} dev prune -y --json
{expected_clean}""",
            cwd=repo,
        )

        # ── 验证 ──────────────────────────────────────────────────
        assert not os.path.exists(wt), f"worktree 未被删除: {wt}"
        assert os.path.exists(os.path.join(repo, ".git")), "主仓库 .git 异常消失!"

    finally:
        shutil.rmtree(tmp, ignore_errors=True)
