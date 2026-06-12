"""dai 管控台 — pywebview 壳。

在后台启动 panel serve，在前面弹出原生窗口。
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import webview

_HERE = Path(__file__).parent
_APP_PATH = _HERE / "app.py"
_PANEL_PORT = 5006
_POLL_INTERVAL = 0.2
_POLL_TIMEOUT = 15


def _panel_up(url: str) -> bool:
    try:
        urllib.request.urlopen(url, timeout=1)
        return True
    except Exception:
        return False


def main(dev: bool = False) -> None:
    # panel 在 venv bin 里，从 sys.executable 反推路径
    panel_path = Path(sys.executable).parent / "panel"

    print(f"▶ panel: {panel_path}")
    print(f"▶ app: {_APP_PATH}")

    cmd = [
        str(panel_path),
        "serve",
        str(_APP_PATH),
        "--port", str(_PANEL_PORT),
        "--session-history", "0",
    ]
    if dev:
        cmd.append("--dev")

    print(f"▶ 启动: {' '.join(cmd)}")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        preexec_fn=os.setsid if hasattr(os, "setsid") else None,
    )

    url = f"http://localhost:{_PANEL_PORT}/app"

    # 等待 panel 就绪
    print(f"▶ 等待 {url} ...")
    deadline = time.time() + _POLL_TIMEOUT
    while time.time() < deadline:
        if _panel_up(url):
            print("▶ panel 就绪")
            break
        time.sleep(_POLL_INTERVAL)
    else:
        # 读 panel stderr 诊断（非阻塞）
        stderr_lines = "(non-blocking read)"
        try:
            import select as _sel
            if _sel.select([proc.stderr], [], [], 0.5)[0]:
                data = proc.stderr.read(4096)
                stderr_lines = data.decode(errors="replace") if data else ""
        except Exception:
            pass
        print(f"[✗] 超时 ({_POLL_TIMEOUT}s): {url}", file=sys.stderr)
        print(f"[✗] panel stderr: {stderr_lines}", file=sys.stderr)
        proc.kill()
        sys.exit(1)

    # 打开原生窗口
    window = webview.create_window("diy 管控台", url, width=1200, height=800)
    webview.start()

    # 窗口关闭 → 清理 panel 进程
    pgid = os.getpgid(proc.pid) if hasattr(os, "getpgid") else proc.pid
    try:
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, AttributeError):
        proc.terminate()
    proc.wait(timeout=5)


if __name__ == "__main__":
    main(dev="--dev" in sys.argv)
