"""dai state 意图测试 — CLI 级行为契约

意图测试 = CLI transcript（$ 命令 → 完整输出）。水手读即知 CLI 外观。

state.yaml 隔离由 conftest.py 的 _isolate_state 全局 fixture 保证。

运行：uv run python -m pytest tests/test_dai_state_intent.py -v
"""

import os

from conftest import assert_intent

_PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DAI = f"uv run --project {_PROJECT} dai"


def test_intent_dai_state_default_output():
    """意图：dai state 默认输出 state，含 profiles/tasks/spaces。

    水手实现：`dai state` 默认 YAML 格式，输出三个 profile + 空 tasks/spaces。
    """
    assert_intent("""$ {dai} state
---
profiles:
  quick:
    area: main
    merge: direct
    approval:
  standard:
    area: branch
    merge: pr
    approval: self
  reviewed:
    area: worktree
    merge: pr
    approval: human
tasks: {{}}
spaces: {{}}
""".format(dai=_DAI))


def test_intent_dai_state_set():
    """意图: dai state --set 写入字段后 dai state 可见。

    写入 tasks.73.title="测试任务"，再次输出确认。
    """
    assert_intent("""$ {dai} state --set tasks.73.title 测试任务
$ {dai} state
---
profiles:
  ...
  reviewed:
    ...
tasks:
  '73':
    title: 测试任务
""".format(dai=_DAI))


def test_intent_dai_state_set_list():
    """意图: dai state --set 写入 lock 字段后 --free 可见。

    spaces key 可含 . 径，field 是 lock。
    """
    assert_intent("""$ {dai} state --set spaces./tmp/test.json.lock null
$ {dai} state --free
/tmp/test.json
""".format(dai=_DAI))


def test_intent_dai_state_free():
    """意图: dai state --free 列出 lock 为 null 或未注册的 space。

    注册两个 space，一个锁定一个不锁，--free 只输出未锁的。
    """
    assert_intent("""$ {dai} state --set spaces.~/a.lock null
$ {dai} state --set spaces.~/b.lock null
# 锁定 a
$ {dai} state --set spaces.~/a.lock '{{"by":99,"area":"branch"}}'
$ {dai} state --free
~/b
""".format(dai=_DAI))
