#!/usr/bin/env python3
"""dev — 人类 TUI，通过 socket 和 diy 管控台对话。

用法: dev [消息...]
  dev              TUI 对话模式
  dev hello world  直接发送消息（非交互）
  dev help         帮助
"""

import os
import shutil
import socket
import sys


SOCK = os.path.expanduser("~/.diy/app.sock")


def _raw_send(line: str) -> str:
    """发送任意命令到 socket。"""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(3)
    s.connect(SOCK)
    s.sendall((line + "\n").encode("utf-8"))
    s.shutdown(socket.SHUT_WR)
    buf = []
    while True:
        data = s.recv(4096)
        if not data:
            break
        buf.append(data.decode("utf-8"))
    s.close()
    return "".join(buf).strip()


def _check():
    if not os.path.exists(SOCK):
        print("错误: diy 管控台未运行", file=sys.stderr)
        sys.exit(1)


def tui():
    """全屏 TUI 对话模式。"""
    _check()
    width = min(shutil.get_terminal_size().columns, 80)
    history: list[tuple[str, str]] = []

    def redraw():
        th = shutil.get_terminal_size().lines
        sys.stdout.write("\033[2J\033[H")
        bar = "━" * width
        sys.stdout.write(f"\033[36m╭{bar}╮\033[0m\n")
        sys.stdout.write(f"\033[36m│\033[1m TUI → diy 管控台 \033[0m\033[36m{' ' * (width - 17)}│\033[0m\n")
        sys.stdout.write(f"\033[36m╰{bar}╯\033[0m\n")
        chat_area = min(th - 5, 20)
        for role, text in history[-chat_area:]:
            if role == "system":
                sys.stdout.write(f"\033[33m● {text}\033[0m\n")
            else:
                sys.stdout.write(f"\033[32m> {text}\033[0m\n")
        sys.stdout.write(f"\033[36m{'─' * width}\033[0m\n")
        sys.stdout.write(f"\033[36m│\033[0m 输入消息回车发送  Ctrl+D 退出 \033[36m│\033[0m\n")

    redraw()
    while True:
        try:
            msg = input("\033[36m📝 \033[0m")
        except (EOFError, KeyboardInterrupt):
            sys.stdout.write("\n\033[2J\033[H退出\n")
            break
        if not msg.strip():
            redraw()
            continue
        result = _raw_send(f"human notify {msg}")
        history.append(("user", msg))
        history.append(("system", "✓ 已发送" if result == "OK" else result))
        redraw()


def main():
    if len(sys.argv) > 1:
        if sys.argv[1] in ("help", "--help", "-h"):
            sys.stdout.write(_raw_send("human --help") + "\n")
            return
        _check()
        msg = " ".join(sys.argv[1:])
        result = _raw_send(f"human notify {msg}")
        if result == "OK":
            print(f"✓ 已发送: {msg}")
        else:
            print(result)
    else:
        tui()


if __name__ == "__main__":
    main()
