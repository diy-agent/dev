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
| `dai task` | ✅ | 任务 CRUD：create/list/show/edit/delete。URI 标识（local/task/1），数据存 ~/.diy/d/ |
| `dai app` | ✅ | 管控台探针 — 透传到 app socket（连不上自动启动 app） |

`dai app` 子命令：
- `tree` / `status` / `node <uri>` / `agents` / `reload` — AI 接口
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
      "uri": "local/task/120",
      "title": "任务详情字段评估",
      "state": "done",
      "source": {
        "type": "local",
        "uri": "local/task/120"
      }
    },
    {
      "uri": "local/task/121",
      "title": "任务存储重构 — ~/.diy/tasks/ 方案验证",
      "state": "done",
      "source": {
        "type": "local",
        "uri": "local/task/121"
      }
    },
    {
      "uri": "local/task/28",
      "title": "status 重构",
      "state": "active",
      "source": {
        "type": "local",
        "uri": "local/task/28"
      },
      "parent": 58
    },
    {
      "uri": "local/task/44",
      "title": "sha.sh 架构重构",
      "state": "active",
      "source": {
        "type": "local",
        "uri": "local/task/44"
      },
      "parent": 58
    },
    {
      "uri": "local/task/47",
      "title": "项目发现机制",
      "state": "done",
      "source": {
        "type": "local",
        "uri": "local/task/47"
      },
      "parent": 58
    },
    {
      "uri": "local/task/57",
      "title": "防 agent 跨 worktree 污染",
      "state": "active",
      "source": {
        "type": "local",
        "uri": "local/task/57"
      },
      "parent": 58
    },
    {
      "uri": "local/task/58",
      "title": "Epic: dev架构更新 — dev 全局感知",
      "state": "active",
      "source": {
        "type": "local",
        "uri": "local/task/58"
      }
    },
    {
      "uri": "local/task/61",
      "title": "start 跨项目 worktree",
      "state": "active",
      "source": {
        "type": "local",
        "uri": "local/task/61"
      },
      "parent": 58
    },
    {
      "uri": "local/task/62",
      "title": "profile化",
      "state": "done",
      "source": {
        "type": "local",
        "uri": "local/task/62"
      },
      "parent": 58
    },
    {
      "uri": "local/task/65",
      "title": "--all 层级感知",
      "state": "active",
      "source": {
        "type": "local",
        "uri": "local/task/65"
      },
      "parent": 58
    },
    {
      "uri": "local/task/67",
      "title": "devflow 动态开发模式",
      "state": "active",
      "source": {
        "type": "local",
        "uri": "local/task/67"
      },
      "parent": 58
    },
    {
      "uri": "local/task/68",
      "title": "sandbox 完善",
      "state": "shelved",
      "source": {
        "type": "local",
        "uri": "local/task/68"
      },
      "parent": 58
    },
    {
      "uri": "local/task/72",
      "title": "run() 命令注入安全审计",
      "state": "new",
      "source": {
        "type": "local",
        "uri": "local/task/72"
      },
      "parent": 58
    },
    {
      "uri": "local/task/73",
      "title": "测试任务",
      "state": "pending",
      "source": {
        "type": "local",
        "uri": "local/task/73"
      },
      "parent": 58
    },
    {
      "uri": "local/task/74",
      "title": "dev 人类壳包装",
      "state": "done",
      "source": {
        "type": "local",
        "uri": "local/task/74"
      },
      "parent": 58
    },
    {
      "uri": "local/task/77",
      "title": "dai vscode CLI",
      "state": "cancelled",
      "source": {
        "type": "local",
        "uri": "local/task/77"
      },
      "parent": 58
    },
    {
      "uri": "local/task/79",
      "title": "Panel GUI Hello World 验证",
      "state": "done",
      "source": {
        "type": "local",
        "uri": "local/task/79"
      },
      "parent": 58
    },
    {
      "uri": "local/task/80",
      "title": "app --port 不生效",
      "state": "cancelled",
      "source": {
        "type": "local",
        "uri": "local/task/80"
      },
      "parent": 58
    },
    {
      "uri": "local/task/81",
      "title": "app.py state 路径重复",
      "state": "cancelled",
      "source": {
        "type": "local",
        "uri": "local/task/81"
      },
      "parent": 58
    },
    {
      "uri": "local/task/82",
      "title": "tree --sync 不从 workspace 根",
      "state": "new",
      "source": {
        "type": "local",
        "uri": "local/task/82"
      },
      "parent": 58
    },
    {
      "uri": "local/task/83",
      "title": "tree --sync 默认 True 语义",
      "state": "new",
      "source": {
        "type": "local",
        "uri": "local/task/83"
      },
      "parent": 58
    },
    {
      "uri": "local/task/84",
      "title": "代码整洁 cleanup",
      "state": "new",
      "source": {
        "type": "local",
        "uri": "local/task/84"
      },
      "parent": 58
    },
    {
      "uri": "local/task/85",
      "title": "ShellTest → _diy_test 公共包",
      "state": "pending",
      "source": {
        "type": "local",
        "uri": "local/task/85"
      }
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
