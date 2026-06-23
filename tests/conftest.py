"""意图测试共享引擎 — ShellTest 会话 + fake_home 隔离。

ShellTest fixture `sh`：
  - 持久 bash 子进程（PTY）
  - dai 命令通过 _dai_runner 在进程内执行（快，不 spawn uv run）
  - 已激活项目 .venv

fake_home fixture：
  - 独立 $HOME + $DIY_HOME，隔离 ~/.diy/ 数据
  - 自动 symlink 系统目录（.config/.local/.ssh/.cache）
"""

import io
import os
import shlex
import sys
import tempfile
from pathlib import Path

import pytest

from _shelltest import ShellTest

_PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def fake_home(monkeypatch):
    """独立 $HOME 目录——需要隔离的测试显式声明。

    ∼ 展开到此目录，dai 数据也存于此。
    自动 symlink .config/.local/.ssh/.cache/.gitconfig 并设 GH_TOKEN。
    """
    tmp = Path(tempfile.mkdtemp(prefix="diy-test-state-"))
    real = Path.home()

    # symlink 系统目录
    for d in [".config", ".local", ".ssh", ".cache"]:
        src = real / d
        if src.exists():
            (tmp / d).symlink_to(src)
    for f in [".gitconfig"]:
        src = real / f
        if src.exists():
            (tmp / f).symlink_to(src)

    # gh token: 必须设 HOME 之前拿（Keychain 依赖真实 HOME）
    try:
        import subprocess as _sp
        r = _sp.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            monkeypatch.setenv("GH_TOKEN", r.stdout.strip())
    except Exception:
        pass

    monkeypatch.setenv("HOME", str(tmp))
    monkeypatch.setenv("DIY_HOME", str(tmp))

    return tmp


def _dai_runner(args_str: str) -> tuple[int, str, str]:
    """Execute dai CLI in-process, avoiding subprocess overhead.

    Captures stdout/stderr via sys redirection.
    """
    from diydev._dai_cli import app as _dai_app
    import diydev._dai_cli as _dai_mod

    # Refresh module-level _HOME so _norm() converts paths to ~ form correctly
    # even when monkeypatch changes $HOME between tests.
    _dai_mod._HOME = os.path.expanduser("~")

    args = shlex.split(args_str)
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out_buf, err_buf
    exit_code = 0
    try:
        _dai_app(args)
    except SystemExit as e:
        code = e.code
        exit_code = code if isinstance(code, int) else (0 if code is None else 1)
    finally:
        sys.stdout, sys.stderr = old_out, old_err

    return exit_code, out_buf.getvalue(), err_buf.getvalue()


@pytest.fixture
def sh():
    """ShellTest 实例，已激活项目 .venv，dai 直接可用。"""
    return ShellTest(
        cwd=_PROJECT,
        init_commands=["source .venv/bin/activate"],
        fast_commands={"dai": _dai_runner},
    )
