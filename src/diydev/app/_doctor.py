"""健康自检 — 应用完整性检查 + 故障锁定。

分层检查体系：
  L1: App 状态 — Socket 存活 / 残留 / 未运行
  L2: 运行时 — Socket 完整性（dev/ino 对比）、多实例检测
  L3: 环境 — state.yaml 存在性与内容

锁定机制：
  - critical 问题触发 _in_lockdown → GUI 显示故障告示面板
  - 非 running 状态不检查运行时项
  - CLI `dai doctor` 和 app 内定时自检共用同一套引擎
"""

from __future__ import annotations

import os
import socket as _sock
import subprocess
from dataclasses import dataclass
from diydev._state import diy_home


@dataclass
class HealthIssue:
    severity: str  # "info" | "warning" | "critical"
    code: str
    message: str
    detail: str = ""


# ═══════════════════════════════════════════════════════
# 全局状态 — 锁定桥
# ═══════════════════════════════════════════════════════

_in_lockdown = False


def is_locked() -> bool:
    return _in_lockdown


def set_locked(v: bool) -> None:
    global _in_lockdown
    _in_lockdown = v


# ═══════════════════════════════════════════════════════
# 自检引擎 — 分层检查
# ═══════════════════════════════════════════════════════
#
# 层级：
# L1. App 状态 — 进程活着？socket 正常？
# L2. 运行时检查 — 仅 app 运行时：socket 完整性、多实例
# L3. 环境检查 — 始终：state.yaml
#
# ═══════════════════════════════════════════════════════

_SOCKET_PATH = str(diy_home() / "app.sock")


def run_check(sock_dev: int | None = None, sock_ino: int | None = None) -> list[HealthIssue]:
    """
    全项自检。
    从 app 内调用：传 (sock_dev, sock_ino)
    从 CLI 调用：不传（自动客户端模式）
    """
    issues: list[HealthIssue] = []

    # L1: App 状态
    app_status = _check_app_status(sock_dev, sock_ino)
    issues += app_status

    # L2: 运行时检查（仅 app 活着的状态）
    if _is_live(app_status):
        issues += _check_runtime(sock_dev, sock_ino)

    # L3: 环境检查
    issues += _check_state_file()

    return issues


def _is_live(statuses: list[HealthIssue]) -> bool:
    """根据 L1 结果判断 app 是否活着。"""
    for i in statuses:
        if i.code == "app_running":
            return True
    return False


# ═══════════════════════════════════════════════════════
# L1 — App 状态
# ═══════════════════════════════════════════════════════


def _check_app_status(sock_dev=None, sock_ino=None) -> list[HealthIssue]:
    """判断 app 是否在运行。有 server fd 则用 inode 对比，否则做客户端探针。"""
    # 有 server 上下文 → app 肯定活着
    if sock_dev is not None and sock_ino is not None:
        return [HealthIssue(
            severity="info",
            code="app_running",
            message=f"管控台运行中（pid={os.getpid()}）",
        )]

    # 客户端探针
    try:
        s = _sock.socket(_sock.AF_UNIX, _sock.SOCK_STREAM)
        s.settimeout(0.5)
        s.connect(_SOCKET_PATH)
        s.close()
        return [HealthIssue(severity="info", code="app_running", message="管控台运行中")]
    except FileNotFoundError:
        pass
    except ConnectionRefusedError:
        return [HealthIssue(
            severity="warning",
            code="app_stale",
            message="Socket 文件残留（无进程监听），建议清理后重启",
            detail=f"文件 {_SOCKET_PATH} 存在但无进程响应。可能是进程崩溃后未清理。可用 rm {_SOCKET_PATH} 清除。",
        )]
    except OSError as exc:
        return [HealthIssue(
            severity="warning",
            code="app_stale",
            message=f"Socket 检查异常: {exc}",
        )]

    return [HealthIssue(severity="info", code="app_not_running", message="管控台未运行")]


# ═══════════════════════════════════════════════════════
# L2 — 运行时检查（仅 app 运行时）
# ═══════════════════════════════════════════════════════


def _check_runtime(sock_dev: int | None, sock_ino: int | None) -> list[HealthIssue]:
    """Socket 完整性 + 多实例检测。"""
    results: list[HealthIssue] = []

    # Socket 被抢占？
    if sock_dev is not None and sock_ino is not None:
        try:
            st = os.stat(_SOCKET_PATH)
        except FileNotFoundError:
            results.append(HealthIssue(
                severity="critical",
                code="socket_missing",
                message="Socket 文件已被删除，进程已成孤岛",
                detail="进程仍在运行但无法接收外部请求。建议重启。",
            ))
            return results

        if st.st_dev != sock_dev or st.st_ino != sock_ino:
            results.append(HealthIssue(
                severity="warning",  # 降级：macOS AF_UNIX inode 比较不可靠
                code="socket_hijacked",
                message="Socket 文件已被其他进程替换",
                detail=(
                    f"我启动时 socket (dev={sock_dev}, ino={sock_ino})，"
                    f"当前文件系统 (dev={st.st_dev}, ino={st.st_ino})。"
                ),
            ))

    # 多实例
    results += _check_multiple_instances()
    return results


# ── 多实例 ──


def _find_other_instances() -> list[dict]:
    """扫描其他 diydev.app.main 实例。返回 [{pid, cmdline}]。"""
    others: list[dict] = []
    my_pid = os.getpid()
    try:
        proc = subprocess.run(
            ["ps", "-eo", "pid=,comm=", "-o", "args="],
            capture_output=True, text=True, timeout=5,
        )
        for line in proc.stdout.strip().split("\n"):
            parts = line.strip().split(None, 2)
            if len(parts) < 2:
                continue
            pid_str = parts[0]
            args_line = parts[2] if len(parts) > 2 else parts[1]
            if "diydev.app.main" not in args_line and "diydev.app.main" not in line:
                continue
            first_word = args_line.split(None, 1)[0] if " " in args_line else args_line
            if "python" not in first_word.lower():
                continue
            try:
                pid = int(pid_str)
            except ValueError:
                continue
            if pid == my_pid:
                continue
            others.append({"pid": pid, "cmdline": line.strip()})
    except (subprocess.TimeoutExpired, OSError):
        pass
    return others


def _check_multiple_instances() -> list[HealthIssue]:
    results: list[HealthIssue] = []
    others = _find_other_instances()
    if len(others) == 0:
        return results

    my_pid = os.getpid()
    others_str = "\n".join(f"  pid={o['pid']} {o['cmdline']}" for o in others)
    results.append(HealthIssue(
        severity="warning",
        code="multiple_instances",
        message=f"发现 {len(others)} 个其他管控台进程",
        detail=(
            f"当前 pid={my_pid}。其他实例:\n{others_str}\n\n"
            f"建议检查各窗口，保留一个，kill 其他进程。"
        ),
    ))
    return results


# ═══════════════════════════════════════════════════════
# L3 — 环境检查
# ═══════════════════════════════════════════════════════


def _check_state_file() -> list[HealthIssue]:
    results: list[HealthIssue] = []
    state_path = str(diy_home() / "state.yaml")

    if not os.path.exists(state_path):
        results.append(HealthIssue(
            severity="info" if not _in_lockdown else "critical",
            code="state_missing",
            message="state.yaml 不存在",
            detail=f"预期路径: {state_path}。应用可能未初始化。",
        ))
        return results

    try:
        import yaml
        with open(state_path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if data is None:
            results.append(HealthIssue(
                severity="warning",
                code="state_empty",
                message="state.yaml 为空",
            ))
    except Exception as exc:
        results.append(HealthIssue(
            severity="warning",
            code="state_parse_error",
            message="state.yaml 解析失败",
            detail=f"错误: {exc}",
        ))

    return results


# ═══════════════════════════════════════════════════════
# 格式化输出
# ═══════════════════════════════════════════════════════


def format_report(issues: list[HealthIssue]) -> str:
    """按层级输出检查报告。"""
    # 分组
    l1 = [i for i in issues if i.code in ("app_running", "app_stale", "app_not_running")]
    l2 = [i for i in issues if i.code in ("socket_missing", "socket_hijacked", "multiple_instances")]
    l3 = [i for i in issues if i.code in ("state_missing", "state_empty", "state_parse_error")]

    lines: list[str] = []

    # L1: App 状态
    app_issue = l1[0] if l1 else None
    if app_issue:
        emoji = {"info": "ℹ️", "warning": "!", "critical": "✗"}.get(app_issue.severity, "?")
        lines.append(f"  {emoji} App 状态 — {app_issue.message}")
        if app_issue.detail:
            for dl in app_issue.detail.strip().split("\n"):
                lines.append(f"    {dl}")
    else:
        lines.append("  ✓ App 状态")

    # L2: 运行时（缩进一层）
    if l2:
        for issue in l2:
            emoji = {"info": "ℹ️", "warning": "!", "critical": "✗"}.get(issue.severity, "?")
            lines.append(f"    {emoji} {issue.message}")
            if issue.detail:
                for dl in issue.detail.strip().split("\n"):
                    lines.append(f"      {dl}")
    else:
        # app 运行时才显示 ✓
        if app_issue and app_issue.code == "app_running":
            lines.append("    ✓ Socket 健康")
            lines.append("    ✓ 单实例")

    # L3: 环境
    if l3:
        for issue in l3:
            emoji = {"info": "ℹ️", "warning": "!", "critical": "✗"}.get(issue.severity, "?")
            lines.append(f"  {emoji} state.yaml — {issue.message}")
            if issue.detail:
                for dl in issue.detail.strip().split("\n"):
                    lines.append(f"    {dl}")
    else:
        lines.append("  ✓ state.yaml")

    # 摘要
    critical = [i for i in issues if i.severity == "critical"]
    warnings = [i for i in issues if i.severity == "warning"]
    if not issues:
        lines.append("")
        lines.append("所有检查通过 ✓")
    elif critical:
        lines.append("")
        lines.append(f"🚨 {len(critical)} 个严重问题需要处理")
    elif warnings:
        lines.append("")
        lines.append(f"⚠️ {len(warnings)} 个警告")
    else:
        lines.append("")
        lines.append("所有检查通过 ✓")

    return "\n".join(lines)
