"""健康自检 — 应用完整性检查 + 故障锁定。"""

from __future__ import annotations

import os
import socket as _sock
import subprocess
from dataclasses import dataclass


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
# 自检引擎
# ═══════════════════════════════════════════════════════

_SOCKET_PATH = os.path.expanduser("~/.diy/app.sock")


def run_check(sock_dev: int | None = None, sock_ino: int | None = None) -> list[HealthIssue]:
    """全项自检。传入 bind 时记下的 socket (dev, ino) 用于检测被抢占。"""
    issues: list[HealthIssue] = []
    issues += _check_socket_integrity(sock_dev, sock_ino)
    issues += _check_multiple_instances()
    issues += _check_state_file()
    return issues


# ── Socket 完整性检查 ──


def _check_socket_integrity(sock_dev: int | None = None, sock_ino: int | None = None) -> list[HealthIssue]:
    """对比 bind 时记下的 (dev, ino) 与文件系统当前值。"""
    results: list[HealthIssue] = []

    if sock_dev is None or sock_ino is None:
        return _check_socket_client_side()

    try:
        st = os.stat(_SOCKET_PATH)
    except FileNotFoundError:
        results.append(HealthIssue(
            severity="critical",
            code="socket_missing",
            message="Socket 文件已被删除",
            detail=f"路径 {_SOCKET_PATH} 不存在。进程仍在运行但无法接收外部请求。建议重启。",
        ))
        return results

    if st.st_dev != sock_dev or st.st_ino != sock_ino:
        results.append(HealthIssue(
            severity="critical",
            code="socket_hijacked",
            message="Socket 文件已被其他进程替换",
            detail=(
                f"我启动时 socket (dev={sock_dev}, ino={sock_ino})，"
                f"当前文件系统 (dev={st.st_dev}, ino={st.st_ino})。"
                f"说明另一个进程用同一路径创建了新 socket。"
                f"当前应用已处于孤岛状态——所有新连接都去了新进程。"
                f"建议关闭本窗口并重启。"
            ),
        ))

    return results


def _check_socket_client_side() -> list[HealthIssue]:
    """从客户端视角检查 socket（CLI `dai doctor` 无服务端 fd 时用）。"""
    results: list[HealthIssue] = []
    try:
        s = _sock.socket(_sock.AF_UNIX, _sock.SOCK_STREAM)
        s.settimeout(0.5)
        s.connect(_SOCKET_PATH)
        s.close()
    except FileNotFoundError:
        results.append(HealthIssue(
            severity="critical",
            code="socket_missing",
            message="Socket 文件不存在。管控台未运行。",
        ))
    except ConnectionRefusedError:
        results.append(HealthIssue(
            severity="critical",
            code="socket_dead",
            message="Socket 文件存在但无进程响应",
        ))
    except OSError as exc:
        results.append(HealthIssue(
            severity="warning",
            code="socket_unknown",
            message=f"Socket 检查异常: {exc}",
        ))
    return results


# ── 多实例检查 ──


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
            pid_str, comm = parts[0], parts[1]
            base = os.path.basename(comm)
            if "python" not in base.lower():
                continue
            if "diydev.app.main" not in line:
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
        message=f"发现 {len(others)} 个其他 diy 管控台进程",
        detail=(
            f"当前 pid={my_pid}。其他实例:\n{others_str}\n\n"
            f"只有一个管控台应有正常运行。建议检查各窗口，保留一个，kill 其他进程。"
        ),
    ))
    return results


# ── state.yaml 检查 ──


def _check_state_file() -> list[HealthIssue]:
    results: list[HealthIssue] = []
    state_path = os.path.expanduser("~/.diy/state.yaml")

    if not os.path.exists(state_path):
        results.append(HealthIssue(
            severity="critical",
            code="state_missing",
            message="state.yaml 不存在",
            detail=f"预期路径: {state_path}。应用无法正常运行。",
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

_CHECK_LABELS: dict[str, str] = {
    "socket_integrity":  "Socket 完整性",
    "socket_missing":    "Socket 存在性",
    "socket_dead":       "Socket 活跃性",
    "socket_hijacked":   "Socket 独占性",
    "multiple_instances":"多实例检测",
    "state_missing":     "state.yaml 存在性",
    "state_empty":       "state.yaml 内容",
    "state_parse_error": "state.yaml 内容",
}


def format_report(issues: list[HealthIssue]) -> str:
    """格式化所有检查项结果。无 issues 的不报错，列出 ✅ 通过。"""
    # 按固定顺序列出检查项
    check_order = [
        "socket_integrity", "socket_missing", "socket_dead",
        "socket_hijacked", "multiple_instances",
        "state_missing", "state_empty", "state_parse_error",
    ]
    reported = {i.code: i for i in issues}
    lines: list[str] = []

    for code in check_order:
        label = _CHECK_LABELS.get(code, code)
        if code in reported:
            i = reported[code]
            emoji = {"critical": "✗", "warning": "!"}.get(i.severity, "?")
            if i.detail:
                # 只取第一行
                detail_first = i.detail.split("\n")[0].strip()[:60]
                lines.append(f"  {emoji} {label} — {detail_first}")
            else:
                lines.append(f"  {emoji} {label} — {i.message}")
        else:
            lines.append(f"  ✓ {label}")

    critical = [i for i in issues if i.severity == "critical"]
    if not issues:
        lines.append("")
        lines.append("所有检查通过 ✓")
    elif critical:
        lines.append("")
        lines.append(f"🚨 {len(critical)} 个严重问题需要处理")
    else:
        lines.append("")
        lines.append(f"⚠️ {len(issues)} 个警告")

    return "\n".join(lines)
