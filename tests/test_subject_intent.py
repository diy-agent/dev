"""dai subject — Subject 树管理意图测试。

sh fixture 已激活 .venv（dai 直接可用）。
fake_home fixture 将 $HOME 隔离到临时目录，~/ 路径在子进程内有效。
"""

from __future__ import annotations

from pathlib import Path

from _shelltest import ShellTest


def test_intent_subject_add_and_list(sh: ShellTest, fake_home: Path):
    """添加 subject → 列表 → 树状。"""
    (fake_home / "git").mkdir()
    (fake_home / "git" / ".git").touch()
    (fake_home / "git" / "diy").mkdir()
    (fake_home / "git" / "diy" / ".git").touch()
    (fake_home / "git" / "diy" / "_diy").mkdir()

    sh.assert_session("""
        $ dai subject add ~/git --desc "根目录"
        status: success

        $ dai subject add ~/git/diy --desc "diy 生态根"
        status: success

        $ dai subject add ~/git/diy/_diy --desc "核心工具"
        status: success

        $ dai subject list
        *~/git/diy*
        *is_git*
        *~/git*
        *is_git*
        *~/git/diy/_diy*
        *is_git*

        $ dai subject tree
        *~/git*
        *is_git*
        *~/git/diy*
        *is_git*
        *~/git/diy/_diy*
        *is_git*
    """)


def test_intent_subject_remove(sh: ShellTest, fake_home: Path):
    """删除 subject。"""
    (fake_home / "git").mkdir()
    (fake_home / "git" / ".git").touch()
    (fake_home / "git" / "sub").mkdir()

    sh.assert_session("""
        $ dai subject add ~/git
        status: success

        $ dai subject add ~/git/sub
        status: success

        $ dai subject remove ~/git/sub
        status: success

        $ dai subject list
        *~/git*

        $ dai subject show ~/git/sub 2>&1; echo $?
        *
        1
    """)


def test_intent_subject_duplicate(sh: ShellTest, fake_home: Path):
    """重复添加 → 报错。"""
    (fake_home / "x").mkdir()

    sh.assert_session("""
        $ dai subject add ~/x
        status: success

        $ dai subject add ~/x 2>&1; echo $?
        *
        1
    """)


def test_intent_subject_scan(sh: ShellTest, fake_home: Path):
    """scan 扫描文件系统发现 subject。"""
    (fake_home / "repos" / "alpha").mkdir(parents=True)
    (fake_home / "repos" / "beta").mkdir()
    (fake_home / "repos" / "alpha" / ".git").touch()
    (fake_home / "repos" / "beta" / ".git").touch()

    sh.assert_session("""
        $ dai subject scan --root ~/repos
        status: success
        data:
        *found*

        $ dai subject tree
        *alpha*
        *is_git*
        *beta*
        *is_git*
    """)
