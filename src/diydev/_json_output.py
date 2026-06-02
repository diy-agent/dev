"""JSON 输出工具 — 为 --json 模式提供统一的输出格式

所有 --json 输出格式:
    成功: {"status": "success", "data": {...}, "message": "..."}
    错误: {"status": "error", "message": "..."}

模块自动检查输出是否为 TTY，非 JSON 模式时不影响已有行为。
"""

import json
import sys


def output_json(data: dict | list, message: str = "") -> None:
    """输出 JSON 成功响应到 stdout"""
    result = {"status": "success", "data": data}
    if message:
        result["message"] = message
    print(json.dumps(result, indent=2, ensure_ascii=False))


def error_json(message: str, exit_code: int = 1) -> None:
    """输出 JSON 错误并退出"""
    print(
        json.dumps(
            {"status": "error", "message": message}, indent=2, ensure_ascii=False
        )
    )
    sys.exit(exit_code)
