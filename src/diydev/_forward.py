"""Forward a command to app.sock. Start app if not running."""

from __future__ import annotations

import os
import shlex
import socket as _sock
import subprocess
import sys
import time as _time

from diydev._lock import locked_file
from diydev._log import info, error
from diydev._state import diy_home


def _lock_path() -> str:
    """获取 app.lock 路径。"""
    return os.path.join(str(diy_home()), "app.lock")


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
                    chunk = data.decode("utf-8")
                    sys.stdout.write(chunk)
                    sys.stdout.flush()
            except _sock.timeout:
                continue
        s.close()
        return b"".join(buf).decode("utf-8") if not is_stream else ""
    except (FileNotFoundError, ConnectionRefusedError, OSError):
        return None


def _socket_path() -> str:
    """获取 app.sock 路径。"""
    return os.path.join(str(diy_home()), "app.sock")


def forward_to_app(args: list[str]) -> None:
    """Send args to app.sock. Start app if needed. Print response or error."""
    socket_path = _socket_path()
    payload = shlex.join(args) + "\n"

    # Step 1: try immediately — app may already be running
    resp = _send_to_socket(socket_path, payload)
    if resp is not None:
        sys.stdout.write(resp)
        return

    # Step 2: acquire lock to serialize the launch path
    lf = locked_file.try_lock(_lock_path(), timeout=3.0)
    if lf is None:
        info("等待管控台启动...")
        deadline = _time.time() + 10
        while _time.time() < deadline:
            _time.sleep(0.3)
            resp = _send_to_socket(socket_path, payload)
            if resp is not None:
                sys.stdout.write(resp)
                return
        error("app 启动超时（锁等待失败）")
        sys.exit(1)

    # Step 3: check again under lock — other process may have started app
    resp = _send_to_socket(socket_path, payload)
    if resp is not None:
        lf.__exit__(None, None, None)
        sys.stdout.write(resp)
        return

    # Step 4: launch app (socket 不可达，锁下启动唯一实例)
    info("正在启动管控台...")
    subprocess.Popen(
        [sys.executable, "-m", "diydev.app.main"],
        stdout=subprocess.DEVNULL,
        env={**os.environ},
    )

    # Step 5: release lock before waiting — 否则 app 的 Gateway.start() 无法获取同一文件锁，导致死锁
    lf.__exit__(None, None, None)

    # Step 6: wait for socket 就绪（不持有锁，避免阻塞 app 的 Gateway 初始化）
    deadline = _time.time() + 10
    while _time.time() < deadline:
        _time.sleep(0.3)
        resp = _send_to_socket(socket_path, payload)
        if resp is not None:
            sys.stdout.write(resp)
            return

    error("app 启动超时，请检查日志")
    sys.exit(1)
