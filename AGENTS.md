# _diy

diy 生态的**开发工具元项目**。

`dev` CLI 已弃用。当前：`dai` CLI + PySide6 桌面 app + Unix socket 协议。

架构决策参考：[docs/architecture.md](./docs/architecture.md)
进程架构：[docs/process-architecture.md](./docs/process-architecture.md)

## dai 命令现状

所有命令平铺在 `dai` 根下（**无分组命名空间**），经 app.sock 透传，协议前缀 `diy` = v1。

| 命令 | 类型 | 说明 |
|------|------|------|
| `dai task create/list/show/edit/delete/link/unlink/archive/sync` | API | 任务 CRUD |
| `dai subject add/list/tree/show/remove/scan` | API | subject 树管理 |
| `dai state` | API | 全量输出/修改 ~/.diy/state.yaml |
| `dai profile list/show` | API | profile 预设 |
| `dai scan` | API | workspace 扫描 |
| `dai tree` / `status` / `agents` / `node <uri>` / `reload` / `doctor` | UI | 操纵/读取 app 视图状态 |
| `dai ui chat state` / `sessions` / `read` / `send <text>` / `select <task_uri>` | UI | AgentChatPanel 交互（type/send/read） |
| `dai restart` / `shutdown` | 本地 | 生命周期命令，不走 socket |

> ⚠️ 注意：`dai app` 作为**子命令已不存在**（被拍平）。详见 [docs/architecture.md](./docs/architecture.md)

人类 TUI 通过独立 `dev` 命令访问：
- `dev` — TUI 对话模式，输入消息 → app 弹通知
- `dev hello world` — 非交互发送消息
- `dev --help` — 查看 human 接口命令列表

## GUI

- `sha.sh app` — 启动 PySide6 桌面 app（`python -m diydev.app.main`）
| - 源码：`src/diydev/app/{main,task_tree,agent_bridge,_app_log,_log_panel,_activity_bar,_doctor}.py`
- Unix socket：`~/.diy/app.sock`，协议前缀 `diy` = v1
- `dai <cmd>` → `diy <cmd>` 透传，`dev <cmd>` → `human <cmd>` 透传

## 日志规范

格式按用途分离:

- **文件** → `~/.diy/app.log`（JSONL，可 jq/grep 查询）
- **终端** → stderr（纯文本）
- **GUI** → LogPanel（纯文本，可过滤级别 + 来源）

文件端 JSONL 字段:

| 字段 | 说明 | 示例 |
|------|------|------|
| `t` | 时间 (HH:MM:SS) | `18:30:15` |
| `l` | 级别 | `INFO` / `DEBUG` |
| `n` | logger 名 | `diy.app.watcher` |
| `c` | 分类前缀 | `watcher` / `timer` / `probe` |
| `m` | 消息正文 | `文件变化 → 全量重载` |

分类前缀 `[category]`:

| 前缀 | 触发点 | 级别 | 说明 |
|------|--------|------|------|
| `[watcher]` | `_on_agent_dir_changed` / `_on_file_changed` | INFO | 文件系统数据变化 |
| `[probe]` | socket 命令触发重载 | INFO | socket 命令触发重载 |
| `[timer]` | `_refresh_agents` 5s 定时 | DEBUG | 周期性 agent 状态检查 |
| `[health]` | `_on_health_check` 10s 定时 | DEBUG/WARN | 健康自检 |
| `[main]` | `_load()` | DEBUG | 全量重载统计 |
| `[panel]` | LogPanel 过滤/清空 | DEBUG | UI 操作 |

查询示例:
```bash
jq 'select(.c == "watcher")' ~/.diy/app.log
grep '"c":"watcher"' ~/.diy/app.log
```

新增日志时在消息开头加对应 `[category]` 前缀。新增来源类别时更新此处列表。

## 测试体系

意图测试（Intent Test）是需求的定义者。每个 CLI 命令的行为由其意图测试描述，测试即文档。

策略：
- 核心能力路径必须有意图测试覆盖（create → list → edit → delete 完整链路）
- 边界/异常路径用 `$!` 测试（错误输入、不存在资源）
- 不追求测试数量，关键路径有且仅有一个意图测试
- 验证标准：输出 YAML/JSON 结构匹配（不同于传统 assert 的精确匹配）

## 开发流程

```
intent test (代码即需求) → CLI 实现 → GUI 补充
```
