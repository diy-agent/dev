#!/usr/bin/env python3
"""TUI 聊天窗口 — 发送消息到 diy 管控台弹通知。

输入一行 → socket → app.show_notification()
"""

import socket
import sys
import os
from pathlib import Path

SOCK = os.path.expanduser("~/.diy/app.sock")


def send(msg: str) -> str:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(3)
    s.connect(SOCK)
    # quote the message so cyclopts treats it as one arg
    import shlex
    line = f"notify {shlex.quote(msg)}\n"
    s.sendall(line.encode("utf-8"))
    s.shutdown(socket.SHUT_WR)
    buf = []
    while True:
        data = s.recv(4096)
        if not data:
            break
        buf.append(data.decode("utf-8"))
    s.close()
    return "".join(buf).strip()


def main():
    print("\033[2J\033[H", end="")  # clear screen
    print("╔══════════════════════════════════════════╗")
    print("║   TUI → diy 管控台 通知                  ║")
    print("║   输入消息回车发送，Ctrl+D 退出          ║")
    print("╚══════════════════════════════════════════╝")
    print()

    if not Path(SOCK).exists():
        print(f"\033[31m错误: app 未运行 ({SOCK} 不存在)\033[0m")
        sys.exit(1)

    while True:
        try:
            msg = input("\033[36m> \033[0m")
        except (EOFError, KeyboardInterrupt):
            print("\n退出")
            break
        if not msg.strip():
            continue
        try:
            result = send(msg)
            if result == "OK":
                print(f"\033[32m  已发送 ✓\033[0m")
            else:
                print(f"\033[33m  {result}\033[0m")
        except OSError as e:
            print(f"\033[31m  发送失败: {e}\033[0m")


if __name__ == "__main__":
    main()
