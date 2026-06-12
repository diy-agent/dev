"""dai scan 意图测试 — CLI 级行为契约（issue #47）。

意图测试 = CLI transcript（$ 命令 → 完整输出）。水手读即知 CLI 外观。

扫描逻辑单元测试在 _dai_scan.py 中，意图测试通过 CLI 验证端到端。

运行：uv run python -m pytest tests/test_dai_scan_intent.py -v
"""

import os

from conftest import assert_intent

_PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DAI = f"uv run --project {_PROJECT} dai"


def test_intent_dai_scan_yaml_output(monkeypatch, tmp_path):
    """意图: dai scan 默认 YAML 输出 workspace + spaces。

    创建含 diy.yaml 和多个 .git 的临时目录结构，
    --path 指向该目录 → 预期的 YAML 输出。
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    ws = home / "git"
    ws.mkdir(parents=True)
    (ws / "diy.yaml").write_text("config: true\n")

    for name in ["_diy", "diy", "diyq"]:
        d = ws / name
        d.mkdir()
        (d / ".git").mkdir()

    ws_str = str(ws)
    assert_intent(f"""$ {_DAI} scan --path {ws_str}
---
workspace: {ws_str}
spaces:
  - path: {ws_str}/_diy
    name: _diy
  - path: {ws_str}/diy
    name: diy
  - path: {ws_str}/diyq
    name: diyq
""")


def test_intent_dai_scan_json_output(monkeypatch, tmp_path):
    """意图: dai scan --json 输出 JSON。"""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    ws = home / "git"
    ws.mkdir(parents=True)
    (ws / "diy.yaml").write_text("")

    for name in ["repo1", "repo2"]:
        d = ws / name
        d.mkdir()
        (d / ".git").mkdir()

    ws_str = str(ws)
    assert_intent(f"""$ {_DAI} scan --json --path {ws_str}
{{"workspace": "{ws_str}", "spaces": [{{"path": "{ws_str}/repo1", "name": "repo1"}}, {{"path": "{ws_str}/repo2", "name": "repo2"}}]}}
""")


def test_intent_dai_scan_no_diy_yaml(monkeypatch, tmp_path):
    """意图: dai scan 在 workspace 根外（无 diy.yaml）报错。

    不创建 diy.yaml → 预期非零退出。
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    empty = tmp_path / "empty"
    empty.mkdir()

    assert_intent(f"""$! {_DAI} scan --path {empty}
""")


def test_intent_dai_scan_empty_workspace(monkeypatch, tmp_path):
    """意图: workspace 下无 .git 目录时 spaces 为空列表。"""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    ws = home / "git"
    ws.mkdir(parents=True)
    (ws / "diy.yaml").write_text("")

    ws_str = str(ws)
    assert_intent(f"""$ {_DAI} scan --path {ws_str}
---
workspace: {ws_str}
spaces: []
""")


def test_intent_dai_scan_max_depth_boundary(monkeypatch, tmp_path):
    """意图: .git 深度超出 max_depth=3 时不被发现。"""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    ws = home / "git"
    ws.mkdir(parents=True)
    (ws / "diy.yaml").write_text("")

    # depth 4: a/b/c/d/.git → 应被排除
    deep = ws / "a" / "b" / "c" / "d"
    deep.mkdir(parents=True)
    (deep / ".git").mkdir()

    ws_str = str(ws)
    assert_intent(f"""$ {_DAI} scan --path {ws_str}
---
workspace: {ws_str}
spaces: []
""")


def test_intent_dai_scan_home_boundary(monkeypatch, tmp_path):
    """意图: diy.yaml 在 HOME 目录本身时应在 HOME 停住，不向上。

    在 $HOME 放 diy.yaml，期望扫描到 HOME 停止。
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    (home / "diy.yaml").write_text("")

    ws_str = str(home)
    assert_intent(f"""$ {_DAI} scan --path {ws_str}
---
workspace: {ws_str}
spaces: []
""")
