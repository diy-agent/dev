"""dai subject — Subject 树管理意图测试。

命令前缀 ! 代替 $，避免 shell 变量混淆。
匹配策略：
  1. 整块嗅探 JSON/YAML → 结构比对（键序无关、缩进无关）
  2. 逐行字符串匹配：
     - {{*}}          → 匹配任意内容（行内/整行）
     - {{regex:...}}  → 正则匹配
"""

import json, os, subprocess, uuid, tempfile, re
from pathlib import Path


# ── sentinel ──

_RE_ANY = re.compile(r"\{\{\*\}\}")
_RE_REGEX = re.compile(r"\{\{regex:(.*?)\}\}")
_RE_SENTINEL = re.compile(r"\{\{\*\}\}|" + _RE_REGEX.pattern)


def _sentinel_to_regex(pattern: str) -> str | None:
    """将 sentinel 模式转为正则。返回 None 表示纯文本匹配。"""
    if _RE_ANY.fullmatch(pattern.strip()):
        return r".*?"
    m = _RE_REGEX.fullmatch(pattern.strip())
    if m:
        return m.group(1)
    return None


def _line_matches(expect: str, actual: str) -> bool:
    """逐行匹配，支持 sentinel。"""
    stripped = expect.strip()
    if stripped == "{{*}}":
        return True

    regex_parts = []
    last = 0
    for m in _RE_SENTINEL.finditer(expect):
        regex_parts.append(re.escape(expect[last : m.start()]))
        if m.group(0) == "{{*}}":
            regex_parts.append(r".*?")
        else:
            # {{regex:...}} → 捕获组在 group(1)
            regex_parts.append(m.group(1))
        last = m.end()
    regex_parts.append(re.escape(expect[last:]))

    pat = "^" + "".join(regex_parts) + "$"
    return bool(re.fullmatch(pat, actual))


# ── JSON/YAML 嗅探 ──

def _try_parse_json(text: str) -> object | None:
    try: return json.loads(text)
    except Exception: return None

def _try_parse_yaml(text: str) -> object | None:
    """尝试 YAML 解析（检查 --- 前缀或直接试）。"""
    import yaml
    try:
        # 去掉可能的围栏
        cleaned = text.strip()
        if cleaned.startswith("---"):
            cleaned = cleaned[3:].strip()
        data = yaml.safe_load(cleaned)
        if isinstance(data, (dict, list)):
            return data
        return None
    except Exception:
        return None


def _json_contains(expected, actual) -> bool:
    """递归结构包含匹配。expected 是约束集，actual 可有额外字段。"""
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        return all(k in actual and _json_contains(expected[k], actual[k]) for k in expected)
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return False
        if not expected:
            return True  # 空期望列表匹配任意
        remaining = list(actual)
        for ei in expected:
            for i, ai in enumerate(remaining):
                if _json_contains(ei, ai):
                    remaining.pop(i)
                    break
            else:
                return False
        return True
    # 标量：sentinel 匹配或精确匹配
    if isinstance(expected, str):
        pat = _sentinel_to_regex(expected)
        if pat and isinstance(actual, str):
            return bool(re.fullmatch(pat, str(actual)))
        return expected == actual
    return expected == actual


# ── assert_intent ──

def _run_blocks(blocks, cwd, env):
    full_env = os.environ.copy()
    if env: full_env.update(env)
    proc = subprocess.Popen(
        ["bash", "--norc"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, cwd=cwd, env=full_env,
    )
    assert proc.stdin and proc.stdout and proc.stderr
    try:
        for cmd, expected_lines in blocks:
            marker = f"__END_{uuid.uuid4().hex[:8]}__"
            proc.stdin.write(f"{cmd}\necho {marker} $?\n")
            proc.stdin.flush()
            out, exit_code = [], None
            for line in proc.stdout:
                if marker in line:
                    parts = line.strip().split()
                    exit_code = int(parts[-1]) if parts[-1].isdigit() else None
                    break
                out.append(line.rstrip("\n"))
            actual = "\n".join(out).strip()
            assert exit_code == 0, f"! {cmd}\nexit={exit_code}\nstderr: {proc.stderr.read()}"

            # 过滤注释和空行
            check = [ln for ln in expected_lines if ln.strip() and not ln.strip().startswith("#")]
            if not check:
                continue

            joined = "\n".join(check).strip()

            # 尝试整块嗅探 JSON
            ej = _try_parse_json(joined)
            aj = _try_parse_json(actual)
            if ej is not None and aj is not None:
                assert _json_contains(ej, aj), (
                    f"! {cmd}\nJSON 不匹配\n"
                    f"期望:\n{json.dumps(ej, indent=2, ensure_ascii=False)}\n"
                    f"实际:\n{json.dumps(aj, indent=2, ensure_ascii=False)}"
                )
                continue

            # 尝试整块嗅探 YAML
            ey = _try_parse_yaml(joined)
            ay = _try_parse_yaml(actual)
            if ey is not None and ay is not None:
                assert _json_contains(ey, ay), (
                    f"! {cmd}\nYAML 不匹配\n"
                    f"期望:\n{joined}\n"
                    f"实际:\n{actual[:600]}"
                )
                continue

            # 逐行字符串匹配
            actual_lines = actual.split("\n")
            ai = 0
            for el in check:
                s = el.strip()
                if not s:
                    continue
                # 纯 {{*}} 独占行 → 跳过一行实际
                if s == "{{*}}":
                    ai += 1
                    continue
                # 在剩余实际行中找匹配
                found = False
                while ai < len(actual_lines):
                    if _line_matches(el, actual_lines[ai]):
                        found = True
                        ai += 1
                        break
                    ai += 1
                assert found, f"! {cmd}\n期望含: {el!r}\n实际:\n{actual[:600]}"
    finally:
        proc.stdin.close(); proc.terminate(); proc.wait(5)


def assert_intent(session, cwd=None, env=None):
    lines = session.split("\n")
    indent = next((len(l) - len(l.lstrip()) for l in lines if l.lstrip().startswith("!")), 0)
    dedented = [(l[indent:] if len(l) >= indent and not l[:indent].strip() else l) for l in lines]
    blocks = []
    i = 0
    while i < len(dedented):
        if not dedented[i].startswith("!"):
            i += 1
            continue
        cmd = dedented[i][1:]
        exp = []
        i += 1
        while i < len(dedented) and not dedented[i].startswith("!"):
            exp.append(dedented[i]); i += 1
        blocks.append((cmd, exp))
    if blocks:
        _run_blocks(blocks, cwd=cwd, env=env)


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
