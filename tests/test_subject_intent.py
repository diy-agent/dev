"""dai subject — Subject 树管理意图测试。

sh fixture 已激活 .venv（dai 直接可用）+ DIY_STATE_PATH 已隔离。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from _shelltest import ShellTest


def test_intent_subject_add_and_list(sh: ShellTest):
    """添加 subject → 列表 → 树状。"""
    tmp = Path(tempfile.mkdtemp(prefix="dai-"))
    root = tmp / "git"
    root.mkdir()
    (root / ".git").touch()
    diy = root / "diy"
    diy.mkdir()
    (diy / ".git").touch()
    sub = diy / "_diy"
    sub.mkdir()

    S = "{{*}}"
    sh.assert_session(
        f"$ dai subject add {root} --desc \"根目录\"\n"
        "status: success\n"
        "\n"
        f"$ dai subject add {diy} --desc \"diy 生态根\"\n"
        "status: success\n"
        "\n"
        f"$ dai subject add {sub} --desc \"核心工具\"\n"
        "status: success\n"
        "\n"
        "$ dai subject list\n"
        f"{S}{diy}{S}\n"
        f"{S}is_git{S}\n"
        f"{S}{root}{S}\n"
        f"{S}is_git{S}\n"
        f"{S}{sub}{S}\n"
        f"{S}is_git{S}\n"
        "\n"
        "$ dai subject tree\n"
        f"{S}{root}{S}\n"
        f"{S}is_git{S}\n"
        f"{S}{diy}{S}\n"
        f"{S}is_git{S}\n"
        f"{S}{sub}{S}\n"
        f"{S}is_git{S}\n"
    )


def test_intent_subject_remove(sh: ShellTest):
    """删除 subject。"""
    tmp = Path(tempfile.mkdtemp(prefix="dai-"))
    root = tmp / "git"
    root.mkdir()
    (root / ".git").touch()
    sub = root / "sub"
    sub.mkdir()
    S = "{{*}}"

    sh.assert_session(
        f"$ dai subject add {root}\n"
        "status: success\n"
        "\n"
        f"$ dai subject add {sub}\n"
        "status: success\n"
        "\n"
        f"$ dai subject remove {sub}\n"
        "status: success\n"
        "\n"
        "$ dai subject list\n"
        f"{S}{root}{S}\n"
        "\n"
        f"$ dai subject show {sub} 2>&1; echo $?\n"
        "{{regex:.*}}\n"
        "1\n"
    )


def test_intent_subject_duplicate(sh: ShellTest):
    """重复添加 → 报错。"""
    tmp = Path(tempfile.mkdtemp(prefix="dai-"))
    root = tmp / "x"
    root.mkdir()

    sh.assert_session(
        f"$ dai subject add {root}\n"
        "status: success\n"
        "\n"
        f"$ dai subject add {root} 2>&1; echo $?\n"
        "{{regex:.*}}\n"
        "1\n"
    )


def test_intent_subject_scan(sh: ShellTest):
    """scan 扫描文件系统发现 subject。"""
    tmp = Path(tempfile.mkdtemp(prefix="dai-"))
    repo = tmp / "repos"
    (repo / "alpha").mkdir(parents=True)
    (repo / "beta").mkdir()
    (repo / "alpha" / ".git").touch()
    (repo / "beta" / ".git").touch()
    S = "{{*}}"

    sh.assert_session(
        f"$ dai subject scan --root {repo}\n"
        "status: success\n"
        "data:\n"
        f"{S}found{S}\n"
        "\n"
        "$ dai subject tree\n"
        f"{S}{repo / 'alpha'}{S}\n"
        f"{S}is_git{S}\n"
        f"{S}{repo / 'beta'}{S}\n"
        f"{S}is_git{S}\n"
    )
