# Agent Monitor — 可观测系统设计

## 概述

Agent Monitor 提供子进程级别的实时可观测性，覆盖三层协议：

```
┌─────────────────────────────────────────────────┐
│  Layer 3: 业务事件 (agent)                       │
│  text_delta / tool_call / agent_end             │
├─────────────────────────────────────────────────┤
│  Layer 2: 协议消息 (protocol)                    │
│  JSONL 行 / RPC 请求-响应 / header              │
├─────────────────────────────────────────────────┤
│  Layer 1: 字节流 (raw)                           │
│  原始 bytes / 字符数 / 活性心跳                   │
└─────────────────────────────────────────────────┘
```

## 架构

### 进程模型

```
dai CLI
  │  forward_to_app()
  ▼
app.sock (Unix socket)
  │
  ▼
GatewayCLI (app 进程)
  │  get_manager()
  ▼
AgentManager
  │
  ▼
PiRpcAgent / AcpAgent
  │  _push_event()
  ▼
InProcessAgentObserver
  │  AgentSnapshot / AgentEvent
  ▼
CLI 输出 / GUI Panel
```

### 接口边界

```python
class AgentObserver(ABC):
    async def list_agents() -> list[AgentSnapshot]
    async def snapshot(task_uri) -> AgentSnapshot | None
    async def stream(task_uri) -> AsyncIterator[AgentEvent]
```

接口是 async 协议，传输层可替换。当前实现 `InProcessAgentObserver` 直连 AgentManager。

## 数据模型

### AgentSnapshot

| 字段 | 类型 | 说明 |
|------|------|------|
| task_uri | str | 任务标识 |
| session_id | str | session ID |
| state | str | starting/idle/running/error/stopped |
| provider | str | LLM 提供商 |
| model | str | 模型名 |
| message_count | int | 对话消息数 |
| event_count | int | 本次 prompt 收到事件数 |
| last_event_type | str | 最后事件类型 |
| last_event_age | float | 距最后事件秒数 |
| prompt_elapsed | float | 当前 prompt 已运行秒数 |
| last_user_msg | str | 最后用户消息 |
| last_assistant_msg | str | 最后助手消息 |
| process | ProcessMetrics | 进程级指标 |

### AgentEvent

| 字段 | 类型 | 说明 |
|------|------|------|
| ts | float | 时间戳 |
| level | str | raw / protocol / agent / lifecycle / error |
| kind | str | stdout/stderr/text_delta/tool_call/... |
| source | str | pi / acp / sys |
| data | str | 事件数据 |
| size | int | 数据大小 |
| meta | dict | 额外信息 |

### ProcessMetrics

| 字段 | 类型 | 说明 |
|------|------|------|
| pid | int | 进程 PID |
| alive | bool | 是否存活 |
| status | str | running/sleeping/zombie |
| cpu_user | float | 用户 CPU 时间 |
| cpu_system | float | 系统 CPU 时间 |
| mem_rss | int | 物理内存 (bytes) |
| num_threads | int | 线程数 |
| num_fds | int | 文件描述符数 |

## 三层推送

### Layer 1: Raw 字节流

`PiRpcAgent._read_loop()` 读取 stdout/stderr 原始字节：

```python
data = await proc.stdout.read(4096)
self._push_event("raw", "pi", data.decode()[:500], size=len(data))
```

用途：知道子进程活着、有输出。

### Layer 2: Protocol 协议消息

JSONL 行解析后推送给 observer：

```python
self._push_event("protocol", "pi", line[:300], line_len=len(line))
```

用途：看完整的协议交互，不关心业务语义。

### Layer 3: Agent 业务事件

`_on_event()` 处理每个事件时推送：

```python
self._push_event("agent", "pi", txt[:200], event_type="text_delta")
```

用途：业务级别的事件流（文本、工具调用、错误）。

## IO 改造

### 旧方案（已废弃）

```python
proc = subprocess.Popen(args, stdout=PIPE, stderr=PIPE)
line = await asyncio.wait_for(
    loop.run_in_executor(None, proc.stdout.readline),  # 阻塞，线程泄漏
    timeout=1.0,
)
```

问题：
- readline 卡在半行 → 线程泄漏
- stderr 没读 → 缓冲区满卡死子进程

### 新方案

```python
proc = await asyncio.create_subprocess_exec(*args, stdout=PIPE, stderr=PIPE)
data = await proc.stdout.read(4096)  # 非阻塞，零线程
```

改进：
- read() 有数据就返回，不等完整行
- 独立 stderr reader
- EOF 后处理 buf 残留半行

## CLI 命令

```
dai agent monitor              # 列出所有 agent
dai agent monitor <uri>        # 详细监控单个
dai agent monitor --json       # JSON 输出
dai agent monitor -w           # 实时刷新（1s）
```

数据流：`dai agent monitor` → `forward_to_app(["diy", "agent", "monitor"])` → app.sock → GatewayCLI → AgentManager

## 后续任务

### P0 — 必须

1. ~~`dai agent stream` — 实时事件流推送（streaming socket），GUI Panel 用~~ ✅
2. ~~GUI AgentMonitorPanel — Qt Widget 实时显示 agent 列表 + 详情~~ ✅（复用 _agent_panel + _refresh_agents）
3. ~~意图测试 — 覆盖 `dai agent monitor` 命令~~ ✅

### P1 — 应该

4. **dai agent stream 接口** — GatewayCLI 新增 stream 命令，返回 event 流
5. **stderr 捕获完善** — PiRpcAgent stderr reader 推给 observer
6. ~~PiRpcAgent `_write` drain() 兼容 — Qt 事件循环下可能阻塞~~ ✅ 已修复（跳过 drain）
7. **AcpAgent 事件推送** — `_AcpClient.session_update()` 中的 `_push_event` 调用验证

### P2 — 可选

8. **psutil 增强** — `collect_process_metrics()` 加 psutil 支持（CPU/内存/线程）
9. **session 文件读取** — CLI 场景降级方案，读 `~/.diy/pi-sessions/*.jsonl` 获取历史数据
10. **agent 健康检查** — `dai agent health` 命令，定期检查子进程存活

## 关键约束

- agent 在 app 进程中运行，CLI 的 `dai agent chat` 是独立进程，monitor 看不到
- GatewayCLI 中不能用 `asyncio.run_until_complete()`（Qt 事件循环冲突），用 `self._main.invoke()` + 同步代码
- `forward_to_app()` 前缀是 `diy`，不是 `dai`
