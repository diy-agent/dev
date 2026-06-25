"""Shim: 使用系统 Node.js，不依赖 nodejs-wheel-binaries 的编译。"""
from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Any, Iterable

_NODE = shutil.which("node") or "node"


def node(args: Iterable[str] | None = None, return_completed_process: bool = False, **kwargs: Any) -> int:
    if args is None:
        args = sys.argv[1:]
    r = subprocess.run([_NODE, *args], **kwargs)  # type: ignore[arg-type]
    return r.returncode if not return_completed_process else r  # type: ignore[return-value]
