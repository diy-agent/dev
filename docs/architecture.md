# _diy 架构决策记录

## CLI 架构：AI-first 设计

### 命令分类

| 类型 | 例子 | 说明 |
|------|------|------|
| **API 指令** | `dai task/subject/state/profile/scan` | 核心数据操作，YAML 输出 |
| **UI 指令** | `dai tree/status/agents/node/doctor/reload/notify/shutdown` | 操纵/读取 app 视图状态 |

所有命令平铺在 `dai` 根下，**没有分组命名空间**（曾被设计为 `dai app` / `dai ui` 组，后因历史原因被拍平）。

### AI vs Human 分野

```
dai <cmd>              → AI-native（YAML/JSON 输出，参数严格，无交互）
dai <cmd> -H / --human → 人友好（默认参数提示，树形输出，颜色）
```

- **不分两组命令**（之前试过 `ai`/`ui` 前缀，已去掉）
- AI 和 Human 用同一套 CLI，区别仅在于 `-H` 标志
- 默认输出 YAML（AI 易解析），`--json` 可选
- 参数缺失时 AI 期望报错，Human 期望 TUI 列表选择

### 协议前缀

```
dai xxx    →  forward_to_app(["diy", "xxx"])    →  app.sock 解析 diy v1 协议
```

协议前缀 `diy` = v1。后续接口升级可增加 `diy2` 等版本，并行兼容。

### 协议前缀即 API 版本

```
diy <args>  →  forward_to_app(["diy", ...<args>])   →  <socket>.dispatch("diy <args>")
```

- **`diy`** = v1 协议前缀，所有 socket（core/ui/agentd）统一以此前缀识别
- **`diy2`** = v2（预留，多版本共存时可增加新 socket 或同一 socket 内按前缀分派）
- CLI 在 `forward_to_app()` 里按前缀路由目标 socket，**不解析内容**
- 版本前缀与目标 socket 解耦：`diy <cmd>` 可以走 core.sock 也可以走 ui.sock，前缀只标识协议版本
- 当前 CLI 命令名为 `dai`（过渡），后续合并回 `diy`。无论名称如何，协议前缀始终是 `diy`

### 历史

- 早期有 `ai.` 前缀（`ai tree` / `ai status`），在 GatewayCLI 重构时被去掉
- 之前有 `dai app` / `dai ui` 分组设计，因 commit `16d9a60` 被拍平
- 当前所有命令（包括原先的 UI 指令）直接注册在 `diy` CycloptsApp 根下

*参考：2026-06-18~19 与用户讨论 "AI-first CLI" 设计定稿*

---

## CLI 协议面（✅ 已确认，保持不变）

> **命名说明：当前命令是 `dai`（diy ai），后续将合并到 `diy` 作为唯一 CLI 入口。下文 CLI 均指这条命令，无论叫 `dai` 还是 `diy`。**

`dai` CLI 是薄壳，没有业务逻辑。所有命令经 socket 转发。

关键认知（2026-06-19 明确）：

> **CLI 不是 core 的专属透传壳。CLI 是整个系统的协议平面（protocol plane）。**
>
> CLI 同时连接多个下游 socket：
> - `core.sock` → task / state / scan / subject / profile 等业务命令（当前经 app.sock 转发，目标：专用 core.sock）
> - `ui.sock`  → tree / status / agents / reload / node / doctor 等 UI 操纵命令（当前 app.sock，目标：独立 ui.sock）
> - `agentd.sock` → spawn / send / kill / list / stream 等 AIAgent 管理（已有）
>
> CLI + 意图测试 = 人类和 agent 的最后工具，覆盖全系统的可观测 + 自动化。
> CLI 不自己做业务逻辑，但它知道命令该路由到哪个下游。

当前实现（`_forward.py`）：

```
dai tree          →  app.sock → GatewayCLI.dispatch("diy tree")
dai task list     →  app.sock → GatewayCLI.dispatch("diy task list")
dai doctor        →  app.sock → GatewayCLI.dispatch("diy doctor")
```

例外（本地执行，不走 socket）：
- `dai restart` — 重启管控台
- `dai shutdown` — 关闭管控台
- `dai doctor metrics` — 读取指标（本地 socket 探针）

**方向（🔜 #90 Phase 1）**：`_forward.py` 路由表增加 `core.sock` 目标，CLI 按命令类型智能路由。

---

## Gateway + GatewayCLI 架构

| 旧名 | 新名 | 职责 |
|------|------|------|
| `AppProbe` | `Gateway` | Unix socket server 管理（bind/cleanup/线程） |
| `ProbeCLI` | `GatewayCLI` | cyclopts 命令解析 + dispatch |
| `MainThread` | `MainThread`（不变） | 安全地在 Qt 主线程执行 lambda |

GatewayCLI 内部结构：

```
self._app (gateway)
  └── diy (CycloptsApp)
       ├── tree / status / agents / reload / node / doctor  ← UI 指令
       ├── state / scan / profile / subject / task           ← API 指令
       ├── agent / notify / title / metrics / shutdown       ← 杂项
       └── help
```

**方向（🔜 #90 Phase 1）**：GatewayCLI 拆出 core 专用实例，运行在独立 `_core_main.py` 进程中。
当前 `main.py` 中的 Gateway（socket server）逻辑搬入 `_core_main.py`。
`main.py` 只保留 PySide6 UI + 到 core.sock 的客户端连接。

---

## 进程架构

参见 [process-architecture.md](./process-architecture.md)

要点：
- app 启动时 spawn agentd 子进程（Hermes venv）
- app 退出时不杀 agentd（agent 跨重启持久化）
- 两个 socket 锁（app.lock + agentd.lock）防多实例
- 心跳 inode 对比检测 socket 被抢

---

## 通信模型：依赖倒置的流式通信

**当前状态（待重构，❌ 不推荐继续依赖）**：

```
CLI ──socket──→ app GatewayCLI ←── 同时承载业务命令 + UI 命令

agent_bridge.py ──读文件→ ~/.diy/agents/<uri>/status.json    ❌ 多余的数据路径
agent_bridge.py ──读文件→ ~/.diy/agents/<uri>/progress.log   ❌
```

**方向（🔜 #90 Phase 2）**：

所有数据通过 CLI 协议获取。GUI 不直接读文件系统。

```
dai agent stream <uri>          → 长连接，持续输出 agent 实时输出行
dai task watch <uri>            → 长连接，任务变更事件流
dai ui events                   → 长连接，UI 事件流
```

**不需要 core → GUI 推送。GUI 自己决定何时开 stream、何时关（依赖倒置）。**

| 当前机制 | 目标机制 |
|---------|---------|
| `agent_bridge.py` 读 status.json + progress.log | ❌ `dai agent stream` 取代，删除 agent_bridge.py |
| FSEventWatcher 监控 agents/ 目录 | ❌ 删除，GUI 主动维持 stream 连接 |
| steer.log 文件桥接 | ❌ stream 自带 /steer 通道 |
| QFileSystemWatcher 监控任务数据 | ⚠️ 保留（任务数据在 ~/.diy/d/ 下，读文件比 socket 更快） |

---

## 日志系统

三路输出分离：

| 输出 | 格式 | 查询方式 |
|------|------|---------|
| `~/.diy/app.log` | JSONL `{t,l,n,c,m}` | `jq` / `grep` |
| stderr | 纯文本 `HH:MM:SS [LEVEL] [name] [cat] msg` | `grep` |
| LogPanel | 纯文本 + 双下拉框 | 级别 + 来源过滤 |

分类前缀约定：`[watcher]` `[timer]` `[probe]` `[health]` `[main]` `[panel]`

日志调节（未来）：
- `--log-level` 控制日志级别，默认不输出日志
- 不用 `-v/-vv` 做结果详细度（不用 git -vv 那套）
- 字段筛选用 `--fields` 明确指明

*参考：2026-06-18 日志体系三路分离讨论 & AGENTS.md*

---

## DetailView + AgentChatPanel UI

任务详情页布局（`MainWindow` + `DetailView`）：

```
QSplitter（水平）
  ├── 左侧：body（QWebEngineView HTML 渲染）
  └── 右侧：sidebar 纵向
       ├── 属性面板（URI / 状态 / Subject / parent）
       └── AgentChatPanel
            ├── session 列表（带状态图标）
            └── 对话区
```

AgentChatPanel 三态：

| 状态 | UI |
|------|----|
| 无 session | 输入框 + "输入消息开始新对话..."，首条消息即启动 agent |
| 有活跃 session | 自动选中活跃 session，输入框可发消息 |
| 只有历史 session | session 列表 + "新对话" 按钮，点击历史只读查看 |

**已去掉**：右键菜单中的"启动 agent"和"/steer 通信"。

---

## 不使用的方案（明确不做的）

- **额外的 Runtime 进程层** — app 本身是 gatekeeper，不需要 third layer
- **message bus / event system** — 两进程间 socket 文本协议足够
- **分布式 runtime** — 单机多进程是 OS 模型，不是分布式系统
- **每 agent 一个进程** — agentd 线程池正确
- **PID 文件** — socket lock + inode 心跳覆盖全部场景
- **lockdown 面板** — 严重问题直接退出，日志留下记录
- **agentd 检测父进程死亡** — 孤儿 agentd 通过 socket 可被新 app 复用
- **agent_bridge.py 的文件系统桥接**（✅ 确认删除，#90 Phase 2）— 全走 socket stream

## 未解决的问题

1. **命令拍平未恢复** — `dai app tree/status/agents/...` 本应作为分组，在 commit `16d9a60` 被拍平到 `diy` 根下。当前 `dai app tree` 路由到 `diy app tree`，而 server 端没有 `app` 子命令。
2. **OTEL 指标方案** — 健康自检循环日志（`[health] 自检通过`）暂以 LogPanel 替代，完整 OTEL 方案待开发。
3. **Hang/线程隔离** — terminal 工具可能卡死线程，目前是 ThreadPoolExecutor timeout 兜底，长期需 ACP 子进程方案。
4. **#90 Phase 2 stream 协议设计** — 动词定义、事件行格式、错误处理规范待定稿。
