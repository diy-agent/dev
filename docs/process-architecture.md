# 进程管理架构

> 本文标注了 **✅ 已有** 和 **🔜 #90（方向）**。
> 当前实现仍为 app + agentd 两进程模型。#90 Phase 1 将演进为 core + ui + agentd 三进程。

## 当前架构（✅ 已实现）

```
dai CLI（薄透传壳）
  │  socket 透传 ("diy <cmd>")
  ▼
app (macOS PySide6 主进程)
  ├── socket server (~/.diy/app.sock)
  │   ├── GatewayCLI 解析 "diy <cmd>"
  │   │   ├── state/scan/profile/subject/task ← 业务命令（应为 core 职责）
  │   │   ├── tree/status/agents/node/doctor  ← UI 操纵命令
  │   │   └── agent spawn/send/kill           ← 转发到 agentd（通过 socketserver 线程）
  │   └── MainThread（Qt 主线程安全的 lambda 执行）
  ├── PySide6 UI（MainWindow + DetailView + AgentChatPanel）
  ├── agent_bridge.py（❌ 通过文件系统读 agent 状态）
  └── spawn/kill agentd（子进程）

agentd（子进程，Hermes venv）
  ├── socket server (~/.diy/agentd.sock)
  ├── SessionPool (AIAgent 线程池)
  └── 写 ~/.diy/agents/<uri>/status.json + progress.log（❌ 文件桥接）
```

agentd 是 app 的子进程，app 负责 spawn/kill。app 启动时先尝试连接已有 agentd socket（复用），连不上才启动新的。

## 目标架构（🔜 #90 Phase 1）

```
diy CLI（协议平面）  ← dai 是过渡名，后续合并回 diy
  ├── core.sock    → "diy task/state/scan/subject/profile"（业务命令）
  ├── ui.sock      → "diy tree/status/agents/node/doctor"（UI 操纵）
  └── agentd.sock  → "diy agent spawn/send/kill/list/stream"（AIAgent 管理）

所有 socket 统一以 `diy` 为协议前缀。
`diy` = v1，未来可扩展 `diy2` = v2，多版本共存在同一套 socket 上。

┌──────────────────┐      socket  text      ┌──────────────────┐
│  diy-core          │◄─────────────────────►│  diy-ui          │
│  (Linux 可部署)    │  CLI 协议              │  (macOS PySide6) │
│                    │                       │                  │
│  GatewayCLI (core) │  daemon stream         │  GatewayCLI (ui) │
│  _state / _dai_cli │◄─────────────────────  │  AgentChatPanel  │
│  _agent_pool       │                       │  TaskTree/Detail │
│                    │                       └──────────────────┘
│  spawn/kill        │
│  agentd            │      socket  text
│                    │◄─────────────────────
│                    │                       ┌──────────────────┐
│                    │                       │  agentd (Hermes) │
│                    │                       │  AIAgent 线程池  │
│                    │                       │  SessionPool     │
└──────────────────┘                       └──────────────────┘
```

## 单实例锁

两个进程各自用 socket 锁防止多实例（✅ 已有，#90 后扩展至三个进程）：

```
启动时:
  1. connect(socket_path) → 通 → "已有实例" → exit
  2. OSError → 清理残留 socket 文件 → bind 新的
```

socket 文件（bind）在操作系统层面独占，是最可靠的单实例锁——比 PID 文件可靠（PID 可能被回收重用）。

**#90 变化**：三个 socket 锁（core.lock / ui.lock / agentd.lock），各自独立。

## 自检与自愈

心跳线程每 5 秒 `os.stat(socket_path)`（✅ 已有）：

| 检测结果 | 行为 |
|---|------|
| `FileNotFoundError`（socket 被删） | 退出 |
| `(dev, ino)` 不匹配（socket 被替换） | 退出 |

core 和 agentd 都是。UI 发现 critical 时 `QApplication.instance().quit()`，不留 lockdown 面板。

## 退出生命周期

### 当前（✅ 已实现）

```
正常退出（用户关窗口 / Ctrl+C）:
  app → app.exec() 返回 → agentd.terminate()
       → wait(3) → 超时则 kill
       → agentd cleanup（unlink socket, 等 agent 跑完）

app crash / SIGKILL:
  agentd 变成孤儿（ppid=1），socket 仍然有效
  app 重启 → 连接 agentd socket → 复用（agent 状态保留）

app 重启后接孤儿 agentd:
  app 先 socket connect 探测 → 连上则复用
  → 不复用才 spawn 新的
  → 新 agentd 启动时 socket 锁检测已有 agentd → 退出
  → app 日志记录"agentd 已在运行"
```

### 目标（🔜 #90 Phase 1）

```
正常退出（用户关窗口 / Ctrl+C）:
  ui → 通知 core → core 存盘 state → core 通知 agentd 优雅退出
     → wait(3) → 超时则 kill
     → agentd cleanup（unlink socket, 等 agent 跑完）

core crash:
  agentd 变孤儿 → 5 秒心跳中断 → agentd 退出
  ui 发现 core.sock 断 → 显示"core 离线"提示 → 可选自动重启 core

ui crash (macOS):
  core 继续运行（Linux 部署的 headless 状态）
  ui 重启 → 连接 core.sock → 恢复任务树视图
```

## 通信方式

### 当前（✅ 已实现 — 部分需要废除）

| 通信方向 | 方式 | 状态 |
|---------|------|------|
| CLI → app | socket 短连接 | ✅ |
| app → agentd | socket 短连接（_dispatch_text） | ✅ |
| agentd → GUI | 文件系统桥（~/.diy/agents/） | ❌ #90 Phase 2 删除 |

### 目标（🔜 #90 Phase 2 — stream 协议）

所有通信统一走 CLI 协议 + socket 长连接：

| 通信方向 | 方式 | remark |
|---------|------|--------|
| CLI → core | socket 短连接（请求-响应） | ✅ |
| CLI → ui | socket 短连接（请求-响应） | ✅ |
| CLI → agentd | socket 短连接（请求-响应） | ✅ |
| GUI → core | socket stream 长连接（实时 agent 输出） | 🔜 `dai agent stream` |
| GUI → ui | socket stream 长连接（UI 事件） | 🔜 `dai ui events` |
| core → GUI (stream) | 无 | ❌ 不推送，GUI 依赖倒置主动拉 |

## 不使用的方案

- **PID 文件**：不必要。socket 锁 + inode 心跳覆盖了全部场景。
- **lockdown 面板**：已删。严重问题直接退出，日志留下记录。
- **agentd 检测父进程死亡**：不需要。孤儿 agentd 仍然可以通过 socket 被新 app 复用。
- **额外的 Runtime 进程层**：不需要。core 进程本身就是业务 gatekeeper。
- **message bus / event system**：不需要。socket 文本协议两进程间足够。
- **分布式 runtime**：单机模型，不做分布式。
- **agent_bridge.py 的文件系统桥接**：❌ #90 Phase 2 删除，全走 socket stream。
