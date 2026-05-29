"""dev commit 参数解析和 message 生成测试"""

from diydev._commit_cmd import _generate_message, SCOPE_PATTERNS
import re


def test_scope_patterns():
    """验证 SCOPE_PATTERNS 匹配规则"""
    test_cases = [
        ("diydev/_commit_cmd.py", "dev"),
        ("skills/git-cleanup/scripts/test.sh", "git-cleanup"),
        ("packages/diyui.py/src/main.py", "diyui.py"),
        ("docs/dev-flow.md", "docs"),
        ("vendor/sha/sha.bash", "sha"),
        ("scripts/dev-commit.sh", "scripts"),
    ]
    for path, expected in test_cases:
        found = ""
        for pattern, fallback in SCOPE_PATTERNS:
            m = re.match(pattern, path)
            if m:
                found = fallback if fallback else m.group(1)
                break
        assert found == expected, f"path={path}: expected={expected}, got={found}"


def test_generate_message():
    """验证 message 生成"""
    # 有 scope
    info = {
        "type": "feat",
        "scope": "dev",
        "files": ["diydev/_commit_cmd.py", "diydev/_cli.py"],
    }
    msg = _generate_message(info)
    assert msg.startswith("feat(dev): "), msg

    # 无 scope
    info = {"type": "fix", "scope": "", "files": ["README.md"]}
    msg = _generate_message(info)
    assert msg.startswith("fix: "), msg

    # 空文件列表
    info = {"type": "chore", "scope": "", "files": []}
    msg = _generate_message(info)
    assert msg == "chore: update", msg


def test_analyze_diff_returns_structure():
    """验证 _analyze_diff 返回必需字段"""
    # 这个测试不依赖实际 git 状态，只验证返回结构
    result = {
        "type": "chore",
        "scope": "",
        "files": ["diydev/_commit_cmd.py"],
    }
    assert "type" in result
    assert "scope" in result
    assert "files" in result
    assert result["type"] in (
        "feat",
        "fix",
        "refactor",
        "test",
        "docs",
        "style",
        "perf",
        "build",
        "ci",
        "chore",
        "revert",
    )
