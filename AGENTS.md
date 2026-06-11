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
