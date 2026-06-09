"""dai subject — Subject 树管理。

路径自身表达层级：~/git/diy/_diy 的父级是 ~/git/diy，无需 parent 字段。

用法：
  dai subject add <path> [--desc <d>] [--type <t>]  注册 subject
  dai subject list                                    扁平列表（默认 YAML，--json）
  dai subject tree                                    树状（默认 YAML，--json）
  dai subject show <path>                             查看单个
  dai subject remove <path>                           删除
  dai subject scan                                    扫描文件系统发现 subject
"""

import json, os, subprocess, uuid, tempfile
from pathlib import Path


# ── assert_intent ──

def _try_parse_json(text: str) -> object | None:
    try: return json.loads(text)
    except Exception: return None

def _json_contains(expected, actual) -> bool:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        return all(k in actual and _json_contains(expected[k], actual[k]) for k in expected)
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return False
        if not expected:
            return not actual
        remaining = list(actual)
        for ei in expected:
            for i, ai in enumerate(remaining):
                if _json_contains(ei, ai):
                    remaining.pop(i)
                    break
            else:
                return False
        return True
    return expected == actual

def _run_blocks(blocks, cwd, env):
    full_env = os.environ.copy()
    if env: full_env.update(env)
    proc = subprocess.Popen(["bash", "--norc"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, cwd=cwd, env=full_env)
    assert proc.stdin and proc.stdout and proc.stderr
    try:
        for cmd, expected_lines in blocks:
            marker = f"__END_{uuid.uuid4().hex[:8]}__"
            proc.stdin.write(f"{cmd}\necho {marker} $?\n")
            proc.stdin.flush()
            out, actual = [], ""
            for line in proc.stdout:
                if marker in line:
                    parts = line.strip().split()
                    exit_code = int(parts[-1]) if parts[-1].isdigit() else None
                    break
                out.append(line.rstrip("\n"))
            actual = "\n".join(out).strip()
            assert exit_code == 0, f"$ {cmd}\nexit={exit_code}\nstderr: {proc.stderr.read()}"
            check = [ln for ln in expected_lines if ln.strip() and not ln.strip().startswith("#")]
            if not check: continue
            joined = "\n".join(check).strip()
            ej, aj = _try_parse_json(joined), _try_parse_json(actual)
            if ej is not None and aj is not None:
                assert _json_contains(ej, aj), f"$ {cmd}\n期望:\n{json.dumps(ej, indent=2, ensure_ascii=False)}\n实际:\n{json.dumps(aj, indent=2, ensure_ascii=False)}"
            else:
                ai = 0
                actual_lines = actual.split("\n")
                for el in check:
                    s = el.strip()
                    if not s: continue
                    if s == "...": ai += 1; continue
                    while ai < len(actual_lines) and s not in actual_lines[ai]: ai += 1
                    assert ai < len(actual_lines), f"期望含: {s!r}\n实际:\n{actual[:600]}"
                    ai += 1
    finally:
        proc.stdin.close(); proc.terminate(); proc.wait(5)

def assert_intent(session, cwd=None, env=None):
    lines = session.split("\n")
    indent = next((len(l) - len(l.lstrip()) for l in lines if l.lstrip().startswith("$ ")), 0)
    dedented = [(l[indent:] if len(l) >= indent and not l[:indent].strip() else l) for l in lines]
    blocks = []
    i = 0
    while i < len(dedented):
        if not dedented[i].startswith("$ "): i += 1; continue
        cmd = dedented[i][2:]
        exp = []
        i += 1
        while i < len(dedented) and not dedented[i].startswith("$ "):
            exp.append(dedented[i]); i += 1
        blocks.append((cmd, exp))
    if blocks: _run_blocks(blocks, cwd=cwd, env=env)


# ════════════════════════════════════════════════════════════════
# 测试
# ════════════════════════════════════════════════════════════════

_DIY = os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))
_DAI = f"uv run --project {_DIY} python -m diydev._dai_cli"


def test_intent_subject_add_and_list():
    """添加 subject → 扁平列表 → 树状。"""
    tmp = tempfile.mkdtemp(prefix="dai-")
    state = os.path.join(tmp, "state.yaml")

    assert_intent(f"""
$ export DIY_STATE_PATH={state}
# 路径自带层级，~/git/diy 的父级是 ~/git
$ {_DAI} subject add ~/git --desc "根目录"
---
status: success
data: {{}}

$ {_DAI} subject add ~/git/diy --desc "diy 生态根"
---
status: success
data: {{}}

$ {_DAI} subject add ~/git/diy/_diy --desc "核心工具" --type workspace
---
status: success
data: {{}}

# cat state.yaml 看结果
$ cat {state}
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
$ {_DAI} subject list
---
~/git: {{description: 根目录}}
~/git/diy: {{description: diy 生态根}}
~/git/diy/_diy: {{description: 核心工具, type: workspace}}

# 树状
$ {_DAI} subject tree
---
~/git:
  description: 根目录
  ~/git/diy:
    description: diy 生态根
    ~/git/diy/_diy:
      description: 核心工具
      type: workspace
""", cwd=_DIY, env={"DIY_STATE_PATH": state})


def test_intent_subject_remove():
    """删除 subject。"""
    tmp = tempfile.mkdtemp(prefix="dai-")
    state = os.path.join(tmp, "state.yaml")

    assert_intent(f"""
$ export DIY_STATE_PATH={state}
$ {_DAI} subject add ~/git
---
status: success
$ {_DAI} subject add ~/git/diy
---
status: success
$ {_DAI} subject add ~/git/diy/_diy
---
status: success

# 删除
$ {_DAI} subject remove ~/git/diy
---
status: success

# 确认已不存在
$ {_DAI} subject list
---
~/git: {{description: null}}
# 没有 ~/git/diy 和 ~/git/diy/_diy
$ {_DAI} subject show ~/git/diy 2>&1; echo $?
...
1
""", cwd=_DIY, env={"DIY_STATE_PATH": state})


def test_intent_subject_duplicate():
    """重复添加 → 报错。"""
    tmp = tempfile.mkdtemp(prefix="dai-")
    state = os.path.join(tmp, "state.yaml")

    assert_intent(f"""
$ export DIY_STATE_PATH={state}
$ {_DAI} subject add ~/git
---
status: success
$ {_DAI} subject add ~/git 2>&1; echo $?
...
1
""", cwd=_DIY, env={"DIY_STATE_PATH": state})


def test_intent_subject_scan():
    """scan 扫描文件系统发现 ~/git/ 下的 subject 树。"""
    tmp = tempfile.mkdtemp(prefix="dai-")
    state = os.path.join(tmp, "state.yaml")

    # 构建测试目录树
    repo = Path(tmp) / "repos"
    (repo / "alpha").mkdir(parents=True)
    (repo / "beta").mkdir()
    (repo / "beta" / "gamma").mkdir()
    (repo / "alpha" / ".git").touch()
    (repo / "beta" / ".git").touch()
    (repo / "beta" / "gamma" / ".git").touch()

    assert_intent(f"""
$ export DIY_STATE_PATH={state}
$ {_DAI} subject scan --root {repo}
---
status: success
data: {{}}

# scan 发现的 subject 树
$ {_DAI} subject tree
---
{str(repo)}:
  {str(repo / "alpha")}: {{}}
  {str(repo / "beta")}:
    {str(repo / "beta" / "gamma")}: {{}}
""", cwd=_DIY, env={"DIY_STATE_PATH": state})
