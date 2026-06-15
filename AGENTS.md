# _diy

diy 生态的**开发工具元项目**。

`dev` CLI 已弃用。当前：`dai` CLI + Panel GUI app。

## dai 命令现状

| 命令 | 状态 | 说明 |
|------|------|------|
| `dai state` | ✅ | 全量输出/修改 ~/.diy/state.yaml |
| `dai profile list/show` | ✅ | profile 预设 |
| `dai tree --sync` | ✅ | 注入 AGENTS.md |
| `dai subject add/list/tree/show/remove/scan` | ✅ | subject 树管理，路径自带层级，is_git 实时检测 |
| `dai task` | ✅ | 任务 CRUD：create/list/show/edit/delete |

## 测试体系

- `tests/_assert_intent.py` — 引擎：命令前缀 `!`，sentinel `{{*}}` `{{regex:...}}`，JSON/YAML 嗅探
- `tests/test_assert_intent_unit.py` — 引擎单元测试 17 条
- `tests/test_assert_intent_intent.py` — 引擎意图测试 14 条（边界/外观）
- `tests/test_subject_intent.py` — subject 命令意图测试 4 条

## GUI

开发在 `diy-agent/_diy-work`：
- `sha.sh app` — dev 模式启动 Panel + pywebview
- 双栏布局：左 Tabulator subject 树（行点击选中），右详情 + 删除
- 自动轮询 state.yaml mtime，2 秒刷新

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
      "number": 28,
      "title": "status 重构",
      "state": "active",
      "parent": 58
    },
    {
      "number": 44,
      "title": "sha.sh 架构重构",
      "state": "active",
      "parent": 58
    },
    {
      "number": 47,
      "title": "项目发现机制",
      "state": "done",
      "parent": 58
    },
    {
      "number": 57,
      "title": "防 agent 跨 worktree 污染",
      "state": "active",
      "parent": 58
    },
    {
      "number": 58,
      "title": "Epic: dev架构更新 — dev 全局感知",
      "state": "active"
    },
    {
      "number": 61,
      "title": "start 跨项目 worktree",
      "state": "active",
      "parent": 58
    },
    {
      "number": 62,
      "title": "profile化",
      "state": "done",
      "parent": 58
    },
    {
      "number": 65,
      "title": "--all 层级感知",
      "state": "active",
      "parent": 58
    },
    {
      "number": 67,
      "title": "devflow 动态开发模式",
      "state": "active",
      "parent": 58
    },
    {
      "number": 68,
      "title": "sandbox 完善",
      "state": "shelved",
      "parent": 58
    },
    {
      "number": 72,
      "title": "run() 命令注入安全审计",
      "state": "new",
      "parent": 58
    },
    {
      "number": 73,
      "title": "测试任务",
      "state": "pending",
      "parent": 58
    },
    {
      "number": 74,
      "title": "dev 人类壳包装",
      "state": "new",
      "parent": 58
    },
    {
      "number": 77,
      "title": "dai vscode CLI",
      "state": "cancelled",
      "parent": 58
    },
    {
      "number": 79,
      "title": "Panel GUI Hello World 验证",
      "state": "new",
      "parent": 58
    },
    {
      "number": 80,
      "title": "app --port 不生效",
      "state": "new",
      "parent": 58
    },
    {
      "number": 81,
      "title": "app.py state 路径重复",
      "state": "new",
      "parent": 58
    },
    {
      "number": 82,
      "title": "tree --sync 不从 workspace 根",
      "state": "new",
      "parent": 58
    },
    {
      "number": 83,
      "title": "tree --sync 默认 True 语义",
      "state": "new",
      "parent": 58
    },
    {
      "number": 84,
      "title": "代码整洁 cleanup",
      "state": "new",
      "parent": 58
    },
    {
      "number": 85,
      "title": "ShellTest → _diy_test 公共包",
      "state": "pending"
    },
    {
      "number": 119,
      "title": "diy-llm 整体重设计 (v0.2.0)",
      "state": "done"
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
