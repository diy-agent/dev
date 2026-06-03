"""dev sandbox 纯函数单元测试

测试 _sandbox_cmd.py 中不依赖 macOS sandbox-exec 的纯函数：
  - _find_template_path: 目录树上溯查找 .sandbox.sb
  - _get_template: 模板优先级（项目模板 vs 内置模板）
  - _resolve_dirs: 路径规范化、去重、顺序保持
  - _build_workdirs_rules: 策略规则段生成（读/写/防删）
  - _build_policy: 完整策略模板替换
  - _detect_sandbox_marker: 环境变量检测
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from diydev._sandbox_cmd import (
    _build_policy,
    _build_workdirs_rules,
    _detect_sandbox_marker,
    _find_template_path,
    _get_template,
    _resolve_dirs,
)


# ============================================================================
# _find_template_path — 目录树上溯查找 .sandbox.sb
# ============================================================================


def test_find_template_in_current_dir():
    """当前目录存在 .sandbox.sb → 找到"""
    with tempfile.TemporaryDirectory() as tmp:
        tmpl = Path(tmp) / ".sandbox.sb"
        tmpl.write_text("(version 1)\n")
        result = _find_template_path(tmp)
        assert result == tmpl.resolve()


def test_find_template_in_parent_dir():
    """子目录中查找 → 上溯到父目录的 .sandbox.sb"""
    with tempfile.TemporaryDirectory() as tmp:
        tmpl = Path(tmp) / ".sandbox.sb"
        tmpl.write_text("(version 1)\n")
        child = Path(tmp) / "sub" / "deep"
        child.mkdir(parents=True)
        result = _find_template_path(str(child))
        assert result == tmpl.resolve()


def test_find_template_not_found():
    """目录树上溯到根也找不到 → None"""
    with tempfile.TemporaryDirectory() as tmp:
        result = _find_template_path(tmp)
        assert result is None


def test_find_template_nearest_wins():
    """多层都有 .sandbox.sb → 最近的（最深）优先"""
    with tempfile.TemporaryDirectory() as tmp:
        parent_tmpl = Path(tmp) / ".sandbox.sb"
        parent_tmpl.write_text("parent\n")
        child_dir = Path(tmp) / "sub"
        child_dir.mkdir()
        child_tmpl = child_dir / ".sandbox.sb"
        child_tmpl.write_text("child\n")
        result = _find_template_path(str(child_dir))
        assert result == child_tmpl.resolve()


# ============================================================================
# _get_template — 模板优先级
# ============================================================================


def test_get_template_prefers_project():
    """存在项目模板 → 使用项目模板"""
    with tempfile.TemporaryDirectory() as tmp:
        tmpl = Path(tmp) / ".sandbox.sb"
        tmpl.write_text(";; project template")
        content, source = _get_template(tmp)
        assert content == ";; project template"
        assert "项目模板" in source


def test_get_template_falls_back_to_builtin():
    """无项目模板 → 使用内置模板"""
    with tempfile.TemporaryDirectory() as tmp:
        content, source = _get_template(tmp)
        assert "(version 1)" in content
        assert "内置" in source


# ============================================================================
# _resolve_dirs — 路径规范化和去重
# ============================================================================


def test_resolve_dirs_no_duplicates():
    """无重复 → 保持顺序"""
    cwd = "/Users/test/project"
    extra = ["/Users/test/lib"]
    result = _resolve_dirs(cwd, extra)
    assert result == [cwd] + extra


def test_resolve_dirs_removes_duplicates():
    """cwd 和 extra 重复 → 去重，保留第一次出现"""
    d1 = os.path.realpath("/tmp/proj")
    d2 = os.path.realpath("/tmp/other")
    result = _resolve_dirs("/tmp/proj", ["/tmp/proj", "/tmp/other"])
    assert result == [d1, d2]


def test_resolve_dirs_empty_extra():
    """无 extra dirs → 只返回 cwd"""
    result = _resolve_dirs("/tmp/proj", [])
    assert result == [os.path.realpath("/tmp/proj")]


def test_resolve_dirs_resolves_symlinks():
    """通过 realpath 解析符号链接"""
    with tempfile.TemporaryDirectory() as tmp:
        real_dir = Path(tmp) / "real"
        real_dir.mkdir()
        link_dir = Path(tmp) / "link"
        os.symlink(str(real_dir), str(link_dir))
        result = _resolve_dirs(str(link_dir), [])
        assert result == [str(real_dir.resolve())]


def test_resolve_dirs_dedup_across_symlinks():
    """同一目录通过 symlink 出现两次 → 只保留一次"""
    with tempfile.TemporaryDirectory() as tmp:
        real_dir = Path(tmp) / "real"
        real_dir.mkdir()
        link_dir = Path(tmp) / "link"
        os.symlink(str(real_dir), str(link_dir))
        result = _resolve_dirs(str(real_dir), [str(link_dir)])
        assert result == [str(real_dir.resolve())]


def test_resolve_dirs_expands_home():
    """~ 展开为用户主目录"""
    home = os.path.expanduser("~")
    result = _resolve_dirs("/tmp/proj", ["~/Documents"])
    assert result[0] == os.path.realpath("/tmp/proj")
    assert result[1] == os.path.realpath(os.path.join(home, "Documents"))


# ============================================================================
# _build_workdirs_rules — 策略规则段生成
# ============================================================================


def test_build_workdirs_rules_read_only_extra():
    """读白名单：只有 extra dirs，不含 cwd（cwd 由 WORKDIR 变量覆盖）"""
    read_seg, write_seg, deny_seg = _build_workdirs_rules(
        [os.path.realpath("/tmp/proj"), "/tmp/lib", "/tmp/data"]
    )
    # 读白名单：跳过 dirs[0]（cwd），只有 dirs[1:]
    assert '/tmp/lib' in read_seg
    assert '/tmp/data' in read_seg
    assert '/tmp/proj' not in read_seg


def test_build_workdirs_rules_write_all_dirs():
    """写白名单：包含所有目录"""
    read_seg, write_seg, deny_seg = _build_workdirs_rules(
        ["/tmp/proj", "/tmp/lib"]
    )
    assert '/tmp/proj' in write_seg
    assert '/tmp/lib' in write_seg


def test_build_workdirs_rules_deny_unlink_all():
    """防删保护：每个目录 + .git 都有 deny file-write-unlink"""
    read_seg, write_seg, deny_seg = _build_workdirs_rules(
        ["/tmp/proj", "/tmp/lib"]
    )
    assert '(deny file-write-unlink (literal "/tmp/proj"))' in deny_seg
    assert '(deny file-write-unlink (literal "/tmp/proj/.git"))' in deny_seg
    assert '(deny file-write-unlink (literal "/tmp/lib"))' in deny_seg
    assert '(deny file-write-unlink (literal "/tmp/lib/.git"))' in deny_seg


def test_build_workdirs_rules_single_dir():
    """只有一个工作目录 → 读白名单为空"""
    read_seg, write_seg, deny_seg = _build_workdirs_rules(["/tmp/proj"])
    assert read_seg.strip() == ""
    assert '/tmp/proj' in write_seg
    assert '(deny file-write-unlink (literal "/tmp/proj"))' in deny_seg


# ============================================================================
# _build_policy — 完整策略生成
# ============================================================================


def test_build_policy_substitutes_home():
    """${HOME} 替换为用户主目录"""
    policy = _build_policy("/Users/test", "/tmp/proj", [])
    assert '"/Users/test"' in policy or "/Users/test" in policy


def test_build_policy_substitutes_workdir():
    """${WORKDIR} 替换为工作目录"""
    policy = _build_policy("/home/user", "/tmp/my-project", [])
    assert '"/tmp/my-project"' in policy or "/tmp/my-project" in policy


def test_build_policy_injects_read_dirs():
    """${WORKDIRS_READ} 注入附加目录读白名单"""
    policy = _build_policy("/home/user", "/tmp/proj", ["/tmp/lib"])
    assert "/tmp/lib" in policy


def test_build_policy_injects_write_dirs():
    """${WORKDIRS_WRITE} 注入所有目录写白名单"""
    policy = _build_policy("/home/user", "/tmp/proj", ["/tmp/lib"])
    assert "/tmp/proj" in policy
    assert "/tmp/lib" in policy


def test_build_policy_injects_deny_unlinks():
    """${DENY_UNLINKS} 注入防删保护"""
    policy = _build_policy("/home/user", "/tmp/proj", [])
    real_proj = os.path.realpath("/tmp/proj")
    assert f'(deny file-write-unlink (literal "{real_proj}"))' in policy
    assert f'(deny file-write-unlink (literal "{real_proj}/.git"))' in policy


def test_build_policy_uses_project_template():
    """存在项目模板时使用项目模板"""
    with tempfile.TemporaryDirectory() as tmp:
        tmpl = Path(tmp) / ".sandbox.sb"
        tmpl.write_text(";; CUSTOM POLICY\n(deny default)\n")
        policy = _build_policy("/home/user", tmp, [])
        assert ";; CUSTOM POLICY" in policy


def test_build_policy_no_leftover_placeholders():
    """策略中没有残留的未替换模板变量"""
    policy = _build_policy("/home/user", "/tmp/proj", ["/tmp/lib"])
    assert "${HOME}" not in policy
    assert "${WORKDIR}" not in policy
    assert "${WORKDIRS_READ}" not in policy
    assert "${WORKDIRS_WRITE}" not in policy
    assert "${DENY_UNLINKS}" not in policy


# ============================================================================
# _detect_sandbox_marker — 环境变量检测
# ============================================================================


def test_detect_marker_dev():
    """DIY_DEV_INSIDE_SANDBOX=1 → dev sandbox 标记"""
    with patch.dict(os.environ, {"DIY_DEV_INSIDE_SANDBOX": "1"}, clear=True):
        result = _detect_sandbox_marker()
        assert result is not None
        assert "dev sb" in result


def test_detect_marker_pi():
    """PI_INSIDE_SANDBOX=1 → pi sandbox 标记"""
    with patch.dict(os.environ, {"PI_INSIDE_SANDBOX": "1"}, clear=True):
        result = _detect_sandbox_marker()
        assert result is not None
        assert "pi sandbox" in result


def test_detect_marker_none():
    """两个环境变量都未设置 → None"""
    with patch.dict(os.environ, {}, clear=True):
        result = _detect_sandbox_marker()
        assert result is None


def test_detect_marker_dev_priority():
    """两个都设置 → dev 优先（代码中先检查 DIY_DEV_INSIDE_SANDBOX）"""
    with patch.dict(os.environ, {
        "DIY_DEV_INSIDE_SANDBOX": "1",
        "PI_INSIDE_SANDBOX": "1",
    }, clear=True):
        result = _detect_sandbox_marker()
        assert result is not None
        assert "dev sb" in result
