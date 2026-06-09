"""dai subject — Subject 树管理意图测试。

命令前缀 ! 代替 $。
subject 自动检测 is_git（路径下 .git 是否存在）。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from _assert_intent import assert_intent


def test_intent_subject_add_and_list():
    """添加 subject → 列表 → 树状。"""
    tmp = Path(tempfile.mkdtemp(prefix="dai-"))
    state = tmp / "state.yaml"

    # 创建实际目录区分 git/non-git
    root = tmp / "git"
    root.mkdir()
    (root / ".git").touch()  # git 仓库
    diy = root / "diy"
    diy.mkdir()
    (diy / ".git").touch()  # git 仓库
    sub = diy / "_diy"
    sub.mkdir()
    # 无 .git → 非 git

    assert_intent(f"""
! export DIY_STATE_PATH={state}
! dai subject add {root} --desc "根目录"
status: success

! dai subject add {diy} --desc "diy 生态根"
status: success

! dai subject add {sub} --desc "核心工具"
status: success

# cat 看实际写入（is_git 不在文件中，实时检测）
! cat {state}
subjects:
  {root}:
    description: 根目录
  {diy}:
    description: diy 生态根
  {sub}:
    description: 核心工具

# 扁平列表（实时 is_git 显示）
! dai subject list
{root}:
  {{*}}
{diy}:
  {{*}}
{sub}:
  {{*}}

# 树状
! dai subject tree
{root}:
  {{*}}
  {diy}:
    {{*}}
    {sub}:
      {{*}}
""", env={"DIY_STATE_PATH": str(state)})


def test_intent_subject_remove():
    """删除 subject。"""
    tmp = Path(tempfile.mkdtemp(prefix="dai-"))
    state = tmp / "state.yaml"
    root = tmp / "git"
    root.mkdir()
    sub = root / "sub"
    sub.mkdir()

    assert_intent(f"""
! export DIY_STATE_PATH={state}
! dai subject add {root}
status: success

! dai subject add {sub}
status: success

! dai subject remove {sub}
status: success

! dai subject list
{root}:
  {{*}}

! dai subject show {sub} 2>&1; echo $?
{{regex:.*}}
1
""", env={"DIY_STATE_PATH": str(state)})


def test_intent_subject_duplicate():
    """重复添加 → 报错。"""
    tmp = Path(tempfile.mkdtemp(prefix="dai-"))
    state = tmp / "state.yaml"
    root = tmp / "x"
    root.mkdir()

    assert_intent(f"""
! export DIY_STATE_PATH={state}
! dai subject add {root}
status: success

! dai subject add {root} 2>&1; echo $?
{{regex:.*}}
1
""", env={"DIY_STATE_PATH": str(state)})


def test_intent_subject_scan():
    """scan 扫描文件系统发现 subject 树。"""
    tmp = Path(tempfile.mkdtemp(prefix="dai-"))
    state = tmp / "state.yaml"
    repo = tmp / "repos"
    (repo / "alpha").mkdir(parents=True)
    (repo / "beta").mkdir()
    (repo / "beta" / "gamma").mkdir()
    (repo / "alpha" / ".git").touch()
    (repo / "beta" / ".git").touch()
    (repo / "beta" / "gamma" / ".git").touch()

    assert_intent(f"""
! export DIY_STATE_PATH={state}
! dai subject scan --root {repo}
status: success

! dai subject tree
{repo}:
  {{*}}
  {repo / "alpha"}:
    {{*}}
  {repo / "beta"}:
    {{*}}
    {repo / "beta" / "gamma"}:
      {{*}}
""", env={"DIY_STATE_PATH": str(state)})
