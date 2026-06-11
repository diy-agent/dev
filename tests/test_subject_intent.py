"""dai subject — Subject 树管理意图测试。

用 ShellTest 编写，命令前缀 $ 符合 bash 习惯。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from _shelltest import ShellTest

_PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DAI = f"uv run --project {_PROJECT} dai"


def test_intent_subject_add_and_list():
    """添加 subject → 列表 → 树状。"""
    tmp = Path(tempfile.mkdtemp(prefix="dai-"))
    state = tmp / "state.yaml"
    root = tmp / "git"
    root.mkdir()
    (root / ".git").touch()
    diy = root / "diy"
    diy.mkdir()
    (diy / ".git").touch()
    sub = diy / "_diy"
    sub.mkdir()

    S = "{{*}}"  # sentinel shorthand

    sh = ShellTest(cwd=str(tmp), init_commands=[f"export DIY_STATE_PATH={state}"])
    sh.assert_session(
        f"$ {_DAI} subject add {root} --desc \"根目录\"\n"
        "status: success\n"
        "\n"
        f"$ {_DAI} subject add {diy} --desc \"diy 生态根\"\n"
        "status: success\n"
        "\n"
        f"$ {_DAI} subject add {sub} --desc \"核心工具\"\n"
        "status: success\n"
        "\n"
        f"$ {_DAI} subject list\n"
        f"{S}{diy}{S}\n"
        f"{S}is_git{S}\n"
        f"{S}{root}{S}\n"
        f"{S}is_git{S}\n"
        f"{S}{sub}{S}\n"
        f"{S}is_git{S}\n"
        "\n"
        f"$ {_DAI} subject tree\n"
        f"{S}{root}{S}\n"
        f"{S}is_git{S}\n"
        f"{S}{diy}{S}\n"
        f"{S}is_git{S}\n"
        f"{S}{sub}{S}\n"
        f"{S}is_git{S}\n"
    )


def test_intent_subject_remove():
    """删除 subject。"""
    tmp = Path(tempfile.mkdtemp(prefix="dai-"))
    state = tmp / "state.yaml"
    root = tmp / "git"
    root.mkdir()
    (root / ".git").touch()
    sub = root / "sub"
    sub.mkdir()
    S = "{{*}}"

    sh = ShellTest(cwd=str(tmp), init_commands=[f"export DIY_STATE_PATH={state}"])
    sh.assert_session(
        f"$ {_DAI} subject add {root}\n"
        "status: success\n"
        "\n"
        f"$ {_DAI} subject add {sub}\n"
        "status: success\n"
        "\n"
        f"$ {_DAI} subject remove {sub}\n"
        "status: success\n"
        "\n"
        f"$ {_DAI} subject list\n"
        f"{S}{root}{S}\n"
        "\n"
        f"$ {_DAI} subject show {sub} 2>&1; echo $?\n"
        "{{regex:.*}}\n"
        "1\n"
    )


def test_intent_subject_duplicate():
    """重复添加 → 报错。"""
    tmp = Path(tempfile.mkdtemp(prefix="dai-"))
    state = tmp / "state.yaml"
    root = tmp / "x"
    root.mkdir()

    sh = ShellTest(cwd=str(tmp), init_commands=[f"export DIY_STATE_PATH={state}"])
    sh.assert_session(
        f"$ {_DAI} subject add {root}\n"
        "status: success\n"
        "\n"
        f"$ {_DAI} subject add {root} 2>&1; echo $?\n"
        "{{regex:.*}}\n"
        "1\n"
    )


def test_intent_subject_scan():
    """scan 扫描文件系统发现 subject。"""
    tmp = Path(tempfile.mkdtemp(prefix="dai-"))
    state = tmp / "state.yaml"
    repo = tmp / "repos"
    (repo / "alpha").mkdir(parents=True)
    (repo / "beta").mkdir()
    (repo / "alpha" / ".git").touch()
    (repo / "beta" / ".git").touch()
    S = "{{*}}"

    sh = ShellTest(cwd=str(tmp), init_commands=[f"export DIY_STATE_PATH={state}"])
    sh.assert_session(
        f"$ {_DAI} subject scan --root {repo}\n"
        "status: success\n"
        "data:\n"
        "{{*}}found{{*}}\n"
        "\n"
        f"$ {_DAI} subject tree\n"
        f"{S}{repo / 'alpha'}{S}\n"
        f"{S}is_git{S}\n"
        f"{S}{repo / 'beta'}{S}\n"
        f"{S}is_git{S}\n"
    )
