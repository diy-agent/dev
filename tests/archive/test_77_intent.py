# """dai vscode 意图测试 — CLI 级行为契约

# 意图测试 = CLI transcript（$ 命令 → 完整输出）。水手读即知 CLI 外观。

# dai vscode 是 Captain Bridge 的 CLI client，从 state.yaml 读连接信息，
# 封装所有 HTTP 细节。Captain 不直接 curl API。

# state.yaml 隔离由 conftest.py 的 _isolate_state 全局 fixture 保证。

# 运行：uv run python -m pytest tests/test_77_intent.py -v
# """

# import os

# from conftest import assert_intent

# _PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# _DAI = f"uv run --project {_PROJECT} dai"

# # ════════════════════════════════════════════════════════════════
# # dai vscode ensure
# # ════════════════════════════════════════════════════════════════


# def test_intent_vscode_ensure_offline():
#     """意图: Bridge 不在线时 exit != 0，stderr 含错误信息。

#     state.yaml 隔离生效（无 vscode 配置），
#     用默认 host:port 连不到服务 → 报错。
#     """
#     assert_intent(f"""$! {_DAI} vscode ensure
# """)


# def test_intent_vscode_ensure_online():
#     """意图: Bridge 在线时 exit 0 + stdout 含 ok。

#     端口 9876 当前正常（Captain Bridge 运行时）。
#     如果此测试失败 → Bridge 离线，ensure 能力本身是正确的（exit != 0）。
#     """
#     assert_intent(f"""$ {_DAI} vscode ensure
# ok
# """)


# # ════════════════════════════════════════════════════════════════
# # dai vscode status
# # ════════════════════════════════════════════════════════════════


# def test_intent_vscode_status_online():
#     """意图: status 输出综合状态 — 版本/终端数/信号队列数。默认 YAML。"""
#     assert_intent(f"""$ {_DAI} vscode status
# ---
# version: 0.2.0
# terminals: ...
# signals: ...
# """)


# def test_intent_vscode_status_json():
#     """意图: --json 输出 JSON 状态。"""
#     assert_intent("""$ {dai} vscode status --json
# {{"version": "...", "terminals": "...", "signals": "..."}}
# """.format(dai=_DAI))


# # ════════════════════════════════════════════════════════════════
# # dai vscode worker
# # ════════════════════════════════════════════════════════════════


# def test_intent_vscode_worker_start():
#     """意图: worker start <issue> 创建终端，返回 {id, name}。"""
#     assert_intent(f"""$ {_DAI} vscode worker start 77
# ---
# id: ...
# name: worker-77
# """)


# def test_intent_vscode_worker_list():
#     """意图: worker list 列出所有终端，含 id/name/issue。默认 YAML。"""
#     assert_intent(f"""$ {_DAI} vscode worker list
# ---
# - id: ...
#   name: ...
#   issue: ...
# """)


# def test_intent_vscode_worker_list_json():
#     """意图: --json 输出 JSON。"""
#     assert_intent("""$ {dai} vscode worker list --json
# [{{"id": "...", "name": "...", "issue": "..."}}]
# """.format(dai=_DAI))


# def test_intent_vscode_worker_focus():
#     """意图: worker focus <id> 切换用户视图到该终端。"""
#     assert_intent(f"""$ {_DAI} vscode worker focus terminal_1
# ok
# """)


# def test_intent_vscode_worker_send():
#     """意图: send <id> <text> 返回 ok。"""
#     assert_intent(f"""$ {_DAI} vscode worker send terminal_1 echo hello
# ok
# """)


# def test_intent_vscode_worker_output():
#     """意图: output <id> 返回终端输出，含之前 echo 的内容。"""
#     assert_intent(f"""$ {_DAI} vscode worker output terminal_1
# ...
# hello
# ...
# """)


# def test_intent_vscode_worker_output_lines():
#     """意图: -n <N> 控制输出行数。"""
#     assert_intent(f"""$ {_DAI} vscode worker output terminal_1 -n 3
# ...
# """)


# def test_intent_vscode_worker_kill():
#     """意图: kill <id> 销毁终端，返回 ok。"""
#     assert_intent(f"""$ {_DAI} vscode worker kill terminal_1
# ok
# """)


# def test_intent_vscode_worker_not_found():
#     """意图: 操作不存在的终端 → exit != 0。"""
#     assert_intent(f"""$! {_DAI} vscode worker output nosuch_terminal
# """)


# # ════════════════════════════════════════════════════════════════
# # dai vscode signal
# # ════════════════════════════════════════════════════════════════


# def test_intent_vscode_signal_pending():
#     """意图: signal pending 列出行队列（可能为空）。默认 YAML。"""
#     assert_intent(f"""$ {_DAI} vscode signal pending
# ---
# []
# """)


# def test_intent_vscode_signal_pending_issue():
#     """意图: signal pending <issue> 过滤结果。"""
#     assert_intent(f"""$ {_DAI} vscode signal pending 77
# ---
# []
# """)


# def test_intent_vscode_signal_pending_json():
#     """意图: --json 输出 JSON。"""
#     assert_intent(f"""$ {_DAI} vscode signal pending --json
# []
# """)


# def test_intent_vscode_signal_ack():
#     """意图: signal ack <issue> 确认处理，返回 ok。"""
#     assert_intent(f"""$ {_DAI} vscode signal ack 77
# ok
# """)


# def test_intent_vscode_signal_ack_all():
#     """意图: signal ack 无参 → 清空全部信号队列，返回 ok。"""
#     assert_intent(f"""$ {_DAI} vscode signal ack
# ok
# """)


# # ════════════════════════════════════════════════════════════════
# # 错误边界
# # ════════════════════════════════════════════════════════════════


# def test_intent_vscode_unknown_subcommand():
#     """意图: 未知子命令 → exit != 0。"""
#     assert_intent(f"""$! {_DAI} vscode nosuch
# """)


# def test_intent_vscode_missing_args():
#     """意图: 无参数 → 显示 help，exit 0。"""
#     assert_intent(f"""$ {_DAI} vscode
# 用法
# """)
