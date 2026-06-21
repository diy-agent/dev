"""dai state 意图测试 — CLI 级行为契约

意图测试 = CLI transcript（$ 命令 → 完整输出）。水手读即知 CLI 外观。
sh fixture 已激活 .venv（dai 直接可用），fake_home 隔离环境。

运行：uv run python -m pytest tests/test_dai_state_intent.py -v
"""

from __future__ import annotations

from pathlib import Path

from _shelltest import ShellTest


def test_intent_dai_state_default_output(sh: ShellTest, fake_home: Path):
    """意图：dai state 默认输出 state，含 profiles/tasks/spaces。"""
    sh.assert_session("""
        $ dai state
        profiles:
          quick:
            area: main
            merge: direct
            approval: null
          standard:
            area: branch
            merge: pr
            approval: self
          reviewed:
            area: worktree
            merge: pr
            approval: human
        tasks: {}
        spaces: {}
    """)


def test_intent_dai_state_set(sh: ShellTest, fake_home: Path):
    """意图: dai state --set 写入字段后 dai state 可见。"""
    sh.assert_session("""
        $ dai state --set tasks.73.title 测试任务
        $ dai state
        profiles:
          *
        tasks:
          '73':
            title: 测试任务
    """)


def test_intent_dai_state_set_list(sh: ShellTest, fake_home: Path):
    """意图: dai state --set 写入 lock 字段后 --free 可见。"""
    sh.assert_session("""
        $ dai state --set spaces./tmp/test.json.lock null
        $ dai state --free
        /tmp/test.json
    """)


def test_intent_dai_state_free(sh: ShellTest, fake_home: Path):
    """意图: dai state --free 列出 lock 为 null 或未注册的 space。"""
    sh.assert_session("""
        $ dai state --set spaces.~/a.lock null
        $ dai state --set spaces.~/b.lock null
        $ dai state --set spaces.~/a.lock '{"by":99,"area":"branch"}'
        $ dai state --free
        ~/b
    """)
