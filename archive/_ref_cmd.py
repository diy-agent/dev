"""dev ref - 查询本地源码镜像

ref.lock.yaml 是 diy sync 生成的平面 key→path 映射。
dev ref 提供对这个映射的查询接口。

Usage:
    dev ref list [--json]         列出所有 ref
    dev ref sync                  运行 diy sync 更新 ref.lock.yaml
"""

import os
from pathlib import Path
from typing import Annotated

from cyclopts import App, Parameter

from ._json_output import output_json
from ._log import info


def _find_project_root(start_dir: str) -> str:
    """向上查找项目根目录（包含 diy.yaml 或 .git 或 pyproject.toml）"""
    d = Path(start_dir).resolve()
    while True:
        if (
            (d / "diy.yaml").exists()
            or (d / "pyproject.toml").exists()
            or (d / ".git").exists()
        ):
            return str(d)
        if d.parent == d:
            return start_dir
        d = d.parent


def _read_ref_lock(project_root: str) -> dict[str, str] | None:
    """读取 ref.lock.yaml，返回 {key: path} 映射"""
    for ext in (".yaml", ".json"):
        p = Path(project_root) / ".diy" / f"ref.lock{ext}"
        if p.exists():
            break
    else:
        return None

    content = p.read_text()
    refs: dict[str, str] = {}

    if p.suffix == ".json":
        import json
        data = json.loads(content)
        for ws in data.get("workspaces", []):
            eco = ws.get("ecosystem", "")
            for dep in ws.get("dependencies", []):
                mirror = dep.get("mirrorPath", "")
                if mirror:
                    if mirror.startswith("."):
                        mirror = "~" + mirror[1:] if mirror[1:2] != "/" else "~/" + mirror[2:]
                    key = f"{eco}:{dep['name']}"
                    refs[key] = mirror
    else:
        # YAML: 简单行解析（避免依赖 yaml 库）
        for line in content.splitlines():
            s = line.strip()
            if not s or s.startswith("#") or s.startswith("version:") or s.startswith("generated:") or s == "refs:":
                continue
            # "  python:rich: ~/.diy/ref/..."
            # key 和 path 由 ": " （冒号+空格）分隔
            idx = s.find(": ")
            if idx > 0:
                key = s[:idx].strip()
                path = s[idx+2:].strip()
                if key and path:
                    refs[key] = path

    return refs


def ref_list(
    json_output: Annotated[
        bool,
        Parameter(
            ("--json",),
            help="以 JSON 格式输出",
        ),
    ] = False,
):
    """列出当前项目的所有本地源码镜像"""
    root = _find_project_root(os.getcwd())
    refs = _read_ref_lock(root)

    if refs is None:
        if json_output:
            output_json({"refs": {}, "count": 0}, "ref.lock.yaml 不存在，请先运行 dev ref sync")
        else:
            info("ref.lock.yaml 不存在，请先运行 dev ref sync")
        return

    if json_output:
        output_json({
            "refs": [{"key": k, "path": v} for k, v in sorted(refs.items())],
            "count": len(refs),
        }, f"共 {len(refs)} 个 ref")
    else:
        for k, v in sorted(refs.items()):
            print(f"  {k}: {v}")


def ref_sync():
    """运行 diy sync 更新本地源码镜像"""
    from diycli._sync import sync_dependencies

    sync_dependencies()
    # 打印更新后的 refs
    root = _find_project_root(os.getcwd())
    refs = _read_ref_lock(root)
    if refs:
        for k, v in sorted(refs.items()):
            print(f"  {k}: {v}")


# 创建 ref 子 App
ref_app = App(name="ref", help="查询本地源码镜像 (ref.lock.yaml)")
ref_app.command(ref_list, name="list")
ref_app.command(ref_sync, name="sync")
