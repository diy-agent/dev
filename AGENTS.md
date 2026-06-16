# _diy

diy 生态的**开发工具元项目**。

`dev` CLI 已弃用。当前：`dai` CLI + PySide6 桌面 app + Unix socket 探针。

## dai 命令现状

| 命令 | 状态 | 说明 |
|------|------|------|
| `dai state` | ✅ | 全量输出/修改 ~/.diy/state.yaml |
| `dai profile list/show` | ✅ | profile 预设 |
| `dai tree --sync` | ✅ | 注入 AGENTS.md |
| `dai subject add/list/tree/show/remove/scan` | ✅ | subject 树管理，路径自带层级，is_git 实时检测 |
| `dai task` | ✅ | 任务 CRUD：create/list/show/edit/delete/import。数据存 ~/.diy/tasks/<id>/AGENTS.md |
| `dai app` | ✅ | 管控台探针 — 透传到 app socket（连不上自动启动 app） |

`dai app` 子命令：
- `tree` / `status` / `node <id>` / `agents` / `reload` — AI 接口
- 支持 `--help` 查看完整列表

人类 TUI 通过独立 `dev` 命令访问：
- `dev` — TUI 对话模式，输入消息 → app 弹通知
- `dev hello world` — 非交互发送消息
- `dev --help` — 查看 human 接口命令列表

## GUI

- `sha.sh app` — 启动 PySide6 桌面 app（`python -m diydev.app.main`）
- 源码：`src/diydev/app/{main,task_tree,agent_bridge,_app_log,_log_panel,_activity_bar}.py`
- Unix socket 探针：`~/.diy/app.sock`
- 命令路由：`ai.*` (agent) / `human.*` (人类)
- `dai app <cmd>` 自动加 `ai` 前缀，`dev` 自动加 `human` 前缀

## 测试体系

- `tests/_assert_intent.py` — 引擎：命令前缀 `!`，sentinel `{{*}}` `{{regex:...}}`，JSON/YAML 嗅探
- `tests/test_assert_intent_unit.py` — 引擎单元测试 17 条
- `tests/test_assert_intent_intent.py` — 引擎意图测试 14 条（边界/外观）
- `tests/test_subject_intent.py` — subject 命令意图测试 4 条

## 开发流程

```
intent test (代码即需求) → CLI 实现 → GUI 补充
```

根文件 `~/git/AGENTS.md` 包含生态全局约束。

<!-- diy:tree:begin -->
```json
{
  "tasks": [
    {
      "number": "73",
      "title": "测试任务",
      "state": "pending"
    }
  ],
  "locks": {
    "/tmp/test.json": null,
    "~/a": {
      "by": 99,
      "area": "branch"
    },
    "~/b": null
  }
}
```
<!-- diy:tree:end -->
