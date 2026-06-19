"""Forward a command to app.sock. Start app if not running."""

from __future__ import annotations

import fcntl
import os
import shlex
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
    """发送消息到 app.sock。流式命令（chat wait）增量推送。"""
    is_stream = " chat wait " in payload
    try:
        s = _sock.socket(_sock.AF_UNIX, _sock.SOCK_STREAM)
        s.settimeout(5 if not is_stream else 0.3)
        s.connect(socket_path)
        s.sendall(payload.encode("utf-8"))
        s.shutdown(_sock.SHUT_WR)
        buf: list[bytes] = []
        while True:
            try:
                data = s.recv(4096)
                if not data:
                    break
                buf.append(data)
                if is_stream:
                    # Write incrementally for streaming commands
                    chunk = data.decode("utf-8")
                    sys.stdout.write(chunk)
                    sys.stdout.flush()
            except _sock.timeout:
                # No data yet, keep polling
                continue
        s.close()
        return b"".join(buf).decode("utf-8") if not is_stream else ""
    except (FileNotFoundError, ConnectionRefusedError, OSError):
        return None


def forward_to_app(args: list[str]) -> None:
    """Send args to app.sock. Start app if needed. Print response or error."""
    socket_path = os.path.expanduser("~/.diy/app.sock")
    payload = shlex.join(args) + "\n"
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

    # Step 4: launch app (socket不可达，锁下启动唯一实例)
    if not os.path.exists(script):
        os.close(lock_fd)
        print("错误: 找不到 sha.sh", file=sys.stderr)
        sys.exit(1)

    print("⏳ 正在启动 diy 管控台...", file=sys.stderr)
    subprocess.Popen(
        ["bash", script, "app"],
        stdout=subprocess.DEVNULL,
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
    print("错误: app 启动超时，请检查日志", file=sys.stderr)
    sys.exit(1)
