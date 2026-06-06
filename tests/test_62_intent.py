"""dai profile list/show 意图测试 — CLI 级行为契约

意图测试 = CLI transcript（$ 命令 → 完整输出）。水手读即知 CLI 外观。

state.yaml 隔离由 conftest.py 的 _isolate_state 全局 fixture 保证。

运行：uv run python -m pytest tests/test_62_intent.py -v
"""

import os

from conftest import assert_intent

_PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DAI = f"uv run --project {_PROJECT} dai"


def test_intent_profile_list_default_yaml():
    """意图: dai profile list 默认 YAML 输出三个预设 profile。

    水手实现：quick/standard/reviewed 三行，各有 area/merge/approval。
    """
    assert_intent("""$ {dai} profile list
---
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
""".format(dai=_DAI))


def test_intent_profile_list_json():
    """意图: dai profile list --json 输出 JSON 格式。

    JSON 结构匹配：用 { } 表达预期片段，assert_intent 做递归包含检查。
    """
    assert_intent("""$ {dai} profile list --json
{{
  "quick": {{"area": "main", "merge": "direct", "approval": null}},
  "standard": {{"area": "branch", "merge": "pr", "approval": "self"}},
  "reviewed": {{"area": "worktree", "merge": "pr", "approval": "human"}}
}}
""".format(dai=_DAI))


def test_intent_profile_show_existing():
    """意图: dai profile show quick 输出单个 profile YAML。
    """
    assert_intent("""$ {dai} profile show quick
---
area: main
merge: direct
approval: null
""".format(dai=_DAI))


def test_intent_profile_show_json():
    """意图: dai profile show quick --json 输出单个 profile JSON。
    """
    assert_intent("""$ {dai} profile show quick --json
{{"area": "main", "merge": "direct", "approval": null}}
""".format(dai=_DAI))


def test_intent_profile_show_nonexistent():
    """意图: dai profile show 不存在的 profile → exit ≠ 0，stderr 含名称。
    """
    assert_intent("""$! {dai} profile show nonexistent
""".format(dai=_DAI))
