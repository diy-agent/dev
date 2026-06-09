"""dai subject — Subject 树管理意图测试。

命令前缀 ! 代替 $，避免 shell 变量混淆。
匹配策略定义在 _assert_intent 模块。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from _assert_intent import assert_intent


# ════════════════════════════════════════════════════════════════
# 测试
# ════════════════════════════════════════════════════════════════

_DIY = os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))
_DAI = f"uv run --project {_DIY} python -m diydev._dai_cli"


def test_intent_subject_add_and_list():
    """添加 subject → 列表 → 树状。"""
    tmp = tempfile.mkdtemp(prefix="dai-")
    state = os.path.join(tmp, "state.yaml")

    assert_intent(f"""
# 路径自带父子关系：~/git/diy/_diy 的父级是 ~/git/diy
! export DIY_STATE_PATH={state}
! {_DAI} subject add ~/git --desc "根目录"
---
status: success

! {_DAI} subject add ~/git/diy --desc "diy 生态根"
---
status: success

! {_DAI} subject add ~/git/diy/_diy --desc "核心工具" --type workspace
---
status: success

# cat 看实际写入
! cat {state}
---
subjects:
  ~/git:
    description: 根目录
  ~/git/diy:
    description: diy 生态根
  ~/git/diy/_diy:
    description: 核心工具
    type: workspace

# 扁平列表
! {_DAI} subject list
---
~/git:
{{*}}
~/git/diy:
{{*}}
~/git/diy/_diy:
{{*}}

# 树状
! {_DAI} subject tree
---
~/git:
  {{*}}
  ~/git/diy:
    {{*}}
    ~/git/diy/_diy:
      {{*}}
""", cwd=_DIY, env={"DIY_STATE_PATH": state})


def test_intent_subject_remove():
    """删除 subject。"""
    tmp = tempfile.mkdtemp(prefix="dai-")
    state = os.path.join(tmp, "state.yaml")

    assert_intent(f"""
! export DIY_STATE_PATH={state}
! {_DAI} subject add ~/git
---
status: success

! {_DAI} subject add ~/git/diy
---
status: success

! {_DAI} subject remove ~/git/diy
---
status: success

! {_DAI} subject list
---
~/git:
  {{*}}
# 没有 ~/git/diy

! {_DAI} subject show ~/git/diy 2>&1; echo $?
{{regex:.*}}
1
""", cwd=_DIY, env={"DIY_STATE_PATH": state})


def test_intent_subject_duplicate():
    """重复添加 → 报错。"""
    tmp = tempfile.mkdtemp(prefix="dai-")
    state = os.path.join(tmp, "state.yaml")

    assert_intent(f"""
! export DIY_STATE_PATH={state}
! {_DAI} subject add ~/git
---
status: success

! {_DAI} subject add ~/git 2>&1; echo $?
{{regex:.*}}
1
""", cwd=_DIY, env={"DIY_STATE_PATH": state})


def test_intent_subject_scan():
    """scan 扫描文件系统发现 subject 树。"""
    tmp = tempfile.mkdtemp(prefix="dai-")
    state = os.path.join(tmp, "state.yaml")
    repo = Path(tmp) / "repos"
    (repo / "alpha").mkdir(parents=True)
    (repo / "beta").mkdir()
    (repo / "beta" / "gamma").mkdir()
    (repo / "alpha" / ".git").touch()
    (repo / "beta" / ".git").touch()
    (repo / "beta" / "gamma" / ".git").touch()

    assert_intent(f"""
! export DIY_STATE_PATH={state}
! {_DAI} subject scan --root {repo}
---
status: success

! {_DAI} subject tree
---
{repo}:
  {{*}}
  {repo / "alpha"}:
    {{*}}
  {repo / "beta"}:
    {{*}}
    {repo / "beta" / "gamma"}:
      {{*}}
""", cwd=_DIY, env={"DIY_STATE_PATH": state})
