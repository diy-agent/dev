"""意图测试共享引擎 — assert_intent

意图测试 = 用 terminal transcript 格式（$ 命令 → 完整输出）直接表达意图。
阅读本文件 = 理解测试意图，无需查文档。

语法（assert_intent）：
  $ <command>              — 执行命令（持久 bash，cd/export 跨 $ 共享），期望 exit 0
  $! <command>             — 执行命令，期望 exit ≠ 0
  <text line>              — 预期输出行（substring 匹配）
  { ... }                  — JSON 预期（结构匹配，自动处理单行/多行）
  ...                      — 跳过任意输出（通配符）
  # <comment>              — 注释行（文档用，跳过匹配）
  （无预期行）              — 只运行不校验输出
"""

import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path

import pytest
import yaml

from _shelltest import ShellTest


_PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def fake_home(monkeypatch):
    """独立 $HOME 目录——需要隔离的测试显式声明。

    子进程 bash 中 ∼ 展开到此目录，dai 数据也存在这里。
    注意：此 fixture 会导致 gh 等依赖 ~/.config 的工具失效。
    """
    tmp = Path(tempfile.mkdtemp(prefix="diy-test-state-"))
    monkeypatch.setenv("HOME", str(tmp))
    monkeypatch.setenv("DIY_HOME", str(tmp))
    return tmp


@pytest.fixture
def sh():
    """ShellTest 实例，已激活项目 .venv，dai 直接可用。"""
    return ShellTest(
        cwd=_PROJECT,
        init_commands=["source .venv/bin/activate"],
    )


def _try_parse_json(text: str) -> object | None:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def _try_parse_yaml(text: str) -> object | None:
    """检测 --- 前缀 → YAML，否则返回 None。"""
    if text.startswith("---"):
        try:
            return yaml.safe_load(text)
        except yaml.YAMLError:
            return None
    return None


def _json_contains(expected: object, actual: object) -> bool:
    """递归检查 expected 的每个 key/value 是否存在于 actual 中。"""
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
    return expected == actual


def _match_lines(expected_lines: list[str], actual: str) -> None:
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
        found = False
        while ai < len(actual_lines):
            if stripped in actual_lines[ai]:
                found = True
                ai += 1
                break
            ai += 1
        assert found, (
            f"期望含: {stripped!r}\n实际输出:\n{actual[:600]}"
        )


def assert_intent(session: str, *, cwd: str | None = None) -> None:
    """意图测试：$ 命令 → 完整输出，支持 JSON 结构匹配。"""
    lines = session.split("\n")

    # 找第一个 $ 的缩进量，用于 dedent
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
    blocks: list[tuple[str, list[str], bool]] = []
    i = 0
    while i < len(dedented):
        line = dedented[i]
        i += 1
        if line.startswith("$! "):
            cmd = line[3:]
            expect_fail = True
        elif line.startswith("$ "):
            cmd = line[2:]
            expect_fail = False
        else:
            continue
        expected: list[str] = []
        while i < len(dedented) and not (dedented[i].startswith("$ ") or dedented[i].startswith("$! ")):
            expected.append(dedented[i])
            i += 1
        blocks.append((cmd, expected, expect_fail))

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
        for cmd, expected_lines, expect_fail in blocks:
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
            if expect_fail:
                assert exit_code != 0, (
                    f"$! {cmd}\nexit={exit_code}（期望非零）\nstdout: {actual}"
                )
                # For $! blocks: skip output matching (stderr not captured).
                # Intent tests for error paths validate exit code only;
                # error message format is verified by integration tests.
                continue

            assert exit_code == 0, (
                f"$ {cmd}\nexit={exit_code}\nstderr: {proc.stderr.read()}"
            )

            check_lines = [
                ln for ln in expected_lines
                if ln.strip() and not ln.strip().startswith("#")
            ]

            if not check_lines:
                continue

            joined = "\n".join(check_lines).strip()
            expected_json = _try_parse_json(joined)
            if expected_json is None:
                expected_json = _try_parse_yaml(joined)
            actual_json = _try_parse_json(actual)
            if actual_json is None:
                actual_json = _try_parse_yaml(actual)

            if expected_json is not None and actual_json is not None:
                ok = _json_contains(expected_json, actual_json)
                if not ok:
                    pretty_exp = json.dumps(expected_json, indent=2, ensure_ascii=False)
                    pretty_act = json.dumps(actual_json, indent=2, ensure_ascii=False)
                    assert False, (
                        f"$ {cmd}\nJSON 结构不匹配\n期望:\n{pretty_exp}\n实际:\n{pretty_act}"
                    )
            else:
                _match_lines(check_lines, actual)
    finally:
        proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=5)
