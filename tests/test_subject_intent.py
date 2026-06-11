"""dai subject — Subject 树管理意图测试。

sh fixture 已激活 .venv（dai 直接可用）+ DIY_HOME 已隔离。
* 在预期行中作为 glob 通配符（匹配任意字符序列）。
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
        f"*{diy}*\n"
        f"*is_git*\n"
        f"*{root}*\n"
        f"*is_git*\n"
        f"*{sub}*\n"
        f"*is_git*\n"
        "\n"
        "$ dai subject tree\n"
        f"*{root}*\n"
        f"*is_git*\n"
        f"*{diy}*\n"
        f"*is_git*\n"
        f"*{sub}*\n"
        f"*is_git*\n"
    )


def test_intent_subject_remove(sh: ShellTest):
    """删除 subject。"""
    tmp = Path(tempfile.mkdtemp(prefix="dai-"))
    root = tmp / "git"
    root.mkdir()
    (root / ".git").touch()
    sub = root / "sub"
    sub.mkdir()

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
        f"*{root}*\n"
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

    sh.assert_session(
        f"$ dai subject scan --root {repo}\n"
        "status: success\n"
        "data:\n"
        "*found*\n"
        "\n"
        "$ dai subject tree\n"
        f"*{repo / 'alpha'}*\n"
        f"*is_git*\n"
        f"*{repo / 'beta'}*\n"
        f"*is_git*\n"
    )
