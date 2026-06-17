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
<!-- diy:tree:begin -->
```json
{
  "tasks": [
    {
      "uri": "github.com/diy-agent/_diy/issues/28",
      "title": "dev status 重构：展示所有 worktree 状态",
      "state": "active",
      "source": {
        "type": "github_issue",
        "uri": "github.com/diy-agent/_diy/issues/28"
      },
      "parent": "github.com/diy-agent/_diy/issues/58"
    },
    {
      "uri": "github.com/diy-agent/_diy/issues/44",
      "title": "dev/sha.sh 架构重构：dev 去掉隐式上下文，sha.sh 变成 thin wrapper 只代理当前项目",
      "state": "active",
      "source": {
        "type": "github_issue",
        "uri": "github.com/diy-agent/_diy/issues/44"
      },
      "parent": "github.com/diy-agent/_diy/issues/58"
    },
    {
      "uri": "github.com/diy-agent/_diy/issues/47",
      "title": "dev 项目发现机制：沿 cwd 向上追溯 diy.yaml 定义项目根，搜所有子项目",
      "state": "done",
      "source": {
        "type": "github_issue",
        "uri": "github.com/diy-agent/_diy/issues/47"
      },
      "parent": "github.com/diy-agent/_diy/issues/58"
    },
    {
      "uri": "github.com/diy-agent/_diy/issues/57",
      "title": "防止 agent 跨 worktree 污染 — test_sandbox.py 事件复盘",
      "state": "active",
      "source": {
        "type": "github_issue",
        "uri": "github.com/diy-agent/_diy/issues/57"
      },
      "parent": "github.com/diy-agent/_diy/issues/58"
    },
    {
      "uri": "github.com/diy-agent/_diy/issues/58",
      "title": "Epic: dev架构更新, 全局项目/repo管理 — dev 全局感知 diy.yaml 项目",
      "state": "active",
      "source": {
        "type": "github_issue",
        "uri": "github.com/diy-agent/_diy/issues/58"
      }
    },
    {
      "uri": "github.com/diy-agent/_diy/issues/61",
      "title": "dev start 支持跨项目 worktree — issue 在 A 项目，代码在 B 项目时无法用 dev 流程",
      "state": "active",
      "source": {
        "type": "github_issue",
        "uri": "github.com/diy-agent/_diy/issues/61"
      },
      "parent": "github.com/diy-agent/_diy/issues/58"
    },
    {
      "uri": "github.com/diy-agent/_diy/issues/62",
      "title": "与其纠结agent worktree/main分支开发不如profile化",
      "state": "done",
      "source": {
        "type": "github_issue",
        "uri": "github.com/diy-agent/_diy/issues/62"
      },
      "parent": "github.com/diy-agent/_diy/issues/58"
    },
    {
      "uri": "github.com/diy-agent/_diy/issues/65",
      "title": "dev 体系增加层级感知：默认当前项目，--all 递归到根 diy.yaml",
      "state": "active",
      "source": {
        "type": "github_issue",
        "uri": "github.com/diy-agent/_diy/issues/65"
      },
      "parent": "github.com/diy-agent/_diy/issues/58"
    },
    {
      "uri": "github.com/diy-agent/_diy/issues/67",
      "title": "dev start 支持 --devflow 参数，提供多种开发模式并带全局状态锁",
      "state": "active",
      "source": {
        "type": "github_issue",
        "uri": "github.com/diy-agent/_diy/issues/67"
      },
      "parent": "github.com/diy-agent/_diy/issues/58"
    },
    {
      "uri": "github.com/diy-agent/_diy/issues/68",
      "title": "dev sandbox: 完善沙箱能力，解决无人值守 worker 的审批/交互阻塞",
      "state": "active",
      "source": {
        "type": "github_issue",
        "uri": "github.com/diy-agent/_diy/issues/68"
      },
      "parent": "github.com/diy-agent/_diy/issues/58"
    },
    {
      "uri": "github.com/diy-agent/_diy/issues/72",
      "title": "安全审计：run() 命令注入风险 — 彻查所有 f-string 拼接 shell 命令",
      "state": "active",
      "source": {
        "type": "github_issue",
        "uri": "github.com/diy-agent/_diy/issues/72"
      },
      "parent": "github.com/diy-agent/_diy/issues/58"
    },
    {
      "uri": "github.com/diy-agent/_diy/issues/74",
      "title": "dev 人类壳包装",
      "state": "active",
      "source": {
        "type": "github_issue",
        "uri": "github.com/diy-agent/_diy/issues/74"
      },
      "parent": "github.com/diy-agent/_diy/issues/58"
    },
    {
      "uri": "github.com/diy-agent/_diy/issues/77",
      "title": "dai vscode: Captain Bridge CLI",
      "state": "active",
      "source": {
        "type": "github_issue",
        "uri": "github.com/diy-agent/_diy/issues/77"
      },
      "parent": "github.com/diy-agent/_diy/issues/58"
    },
    {
      "uri": "github.com/diy-agent/_diy/issues/79",
      "title": "dai task 管控台 v0：Panel GUI Hello World 验证",
      "state": "active",
      "source": {
        "type": "github_issue",
        "uri": "github.com/diy-agent/_diy/issues/79"
      },
      "parent": "github.com/diy-agent/_diy/issues/58"
    },
    {
      "uri": "github.com/diy-agent/_diy/issues/80",
      "title": "dai app --port 参数不生效 — shell.py 硬编码 5006",
      "state": "active",
      "source": {
        "type": "github_issue",
        "uri": "github.com/diy-agent/_diy/issues/80"
      },
      "parent": "github.com/diy-agent/_diy/issues/58"
    },
    {
      "uri": "github.com/diy-agent/_diy/issues/81",
      "title": "app.py state 路径与 _state.py 重复 — 应复用 _state_path()",
      "state": "active",
      "source": {
        "type": "github_issue",
        "uri": "github.com/diy-agent/_diy/issues/81"
      },
      "parent": "github.com/diy-agent/_diy/issues/58"
    },
    {
      "uri": "github.com/diy-agent/_diy/issues/82",
      "title": "dai tree --sync 不从 workspace 根找 AGENTS.md",
      "state": "active",
      "source": {
        "type": "github_issue",
        "uri": "github.com/diy-agent/_diy/issues/82"
      },
      "parent": "github.com/diy-agent/_diy/issues/58"
    },
    {
      "uri": "github.com/diy-agent/_diy/issues/83",
      "title": "dai tree --sync 默认 True 语义混淆",
      "state": "active",
      "source": {
        "type": "github_issue",
        "uri": "github.com/diy-agent/_diy/issues/83"
      },
      "parent": "github.com/diy-agent/_diy/issues/58"
    },
    {
      "uri": "github.com/diy-agent/_diy/issues/84",
      "title": "dai 代码整洁：Any 未导入、profile 测试命名、VerboseFlag 覆盖不全",
      "state": "active",
      "source": {
        "type": "github_issue",
        "uri": "github.com/diy-agent/_diy/issues/84"
      },
      "parent": "github.com/diy-agent/_diy/issues/58"
    },
    {
      "uri": "local/task/1",
      "title": "PySide6 provider: 设计评审 + 改造路线图",
      "state": "pending",
      "source": {
        "type": "local",
        "uri": "local/task/1"
      }
    },
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
