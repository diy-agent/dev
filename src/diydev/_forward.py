"""Forward a command to app.sock. Start app if not running."""

from __future__ import annotations

import fcntl
import os
import socket as _sock
import subprocess
import sys
import time as _time


_LOCK_PATH = os.path.expanduser("~/.diy/app.lock")


def _acquire_lock(timeout: float = 3.0) -> int | None:
    """Acquire exclusive lock on app.lock. Returns fd or None on timeout.

    LOCK_NB first, then fall back to blocking with timeout.
    """
    os.makedirs(os.path.dirname(_LOCK_PATH), exist_ok=True)
    fd = os.open(_LOCK_PATH, os.O_RDWR | os.O_CREAT, 0o644)
    deadline = _time.time() + timeout
    while _time.time() < deadline:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except BlockingIOError:
            _time.sleep(0.05)
    os.close(fd)
    return None


def _send_to_socket(socket_path: str, payload: str) -> str | None:
    """Try sending payload. Returns response text, or None if unreachable."""
    try:
        s = _sock.socket(_sock.AF_UNIX, _sock.SOCK_STREAM)
        s.settimeout(5)
        s.connect(socket_path)
        s.sendall(payload.encode("utf-8"))
        s.shutdown(_sock.SHUT_WR)
        buf: list[bytes] = []
        while True:
            data = s.recv(4096)
            if not data:
                break
            buf.append(data)
        s.close()
        return b"".join(buf).decode("utf-8")
    except (FileNotFoundError, ConnectionRefusedError, OSError):
        return None


def forward_to_app(args: list[str]) -> None:
    """Send args to app.sock. Start app if needed. Print response or error."""
    socket_path = os.path.expanduser("~/.diy/app.sock")
    payload = " ".join(args) + "\n"
    script = os.path.join(os.path.dirname(__file__), "..", "..", "sha.sh")
    script = os.path.abspath(script)

    # Step 1: try immediately — app may already be running
    resp = _send_to_socket(socket_path, payload)
    if resp is not None:
        sys.stdout.write(resp)
        return

    # Step 2: acquire lock to serialize the launch path
    lock_fd = _acquire_lock(timeout=3.0)
    if lock_fd is None:
        # Lock timeout — another process may be launching; wait for socket
        print("⏳ 等待 diy 管控台启动...", file=sys.stderr)
        deadline = _time.time() + 10
        while _time.time() < deadline:
            _time.sleep(0.3)
            resp = _send_to_socket(socket_path, payload)
            if resp is not None:
                sys.stdout.write(resp)
                return
        print("错误: app 启动超时（锁等待失败）", file=sys.stderr)
        sys.exit(1)

    # Step 3: check again under lock — another process may have started app
    resp = _send_to_socket(socket_path, payload)
    if resp is not None:
        os.close(lock_fd)
        sys.stdout.write(resp)
        return

    # Step 4: launch app
    if not os.path.exists(script):
        os.close(lock_fd)
        print("错误: 找不到 sha.sh", file=sys.stderr)
        sys.exit(1)

    print("⏳ 正在启动 diy 管控台...", file=sys.stderr)
    subprocess.Popen(
        ["bash", script, "app"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Step 5: wait for socket — lock keeps other launchers waiting
    deadline = _time.time() + 10
    while _time.time() < deadline:
        _time.sleep(0.3)
        resp = _send_to_socket(socket_path, payload)
        if resp is not None:
            os.close(lock_fd)
            sys.stdout.write(resp)
            return

    os.close(lock_fd)
    # 超时 — 检查 app 是否崩溃
    error_path = os.path.expanduser("~/.diy/app.error")
    if os.path.exists(error_path):
        with open(error_path) as _f:
            _error = _f.read().strip()
        os.unlink(error_path)
        print(f"错误: app 启动失败\n{_error}", file=sys.stderr)
    else:
        print("错误: app 启动超时，请检查日志", file=sys.stderr)
    sys.exit(1)
