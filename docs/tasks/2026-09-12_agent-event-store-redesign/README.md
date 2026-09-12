# 本地 agent 会话事件存储：重新设计讨论（记录 + 待办）

> **状态**：讨论中，**尚未实施任何存储变更**
> **日期**：2026-09-12
> **代码位置**：`/Users/ccc/git/diy/diy-ui-fine-tune`（分支 `feat/ui-fine-tune`，HEAD `5bc9a65`）
> **下次讨论入口**：直接跳到本文 §7「待讨论问题清单」，新 worktree 里让 agent 先读本文件即可续上

---

## 0. 一句话摘要

本地 agent 的会话数据现在存在 `ops.jsonl`（自定义 Op 事件流）。讨论源于一个事故暴露的"数据源不一致"，
结论是**保留 Op 作为唯一真相源**（不存 ai-sdk 原始流作主存储），但需要把它从"UI 渲染输入"
升级为**通用的领域事件 / span 树**（因为 app 事件流会包含 ai-sdk 流之外的节点：子 agent、上下文注入等），
并解决"如何设计这个通用结构"与"树 vs 线性事件如何存"两件事。

---

## 1. 问题起源：一次事故链条

### 1.1 现象

任务 `projects/4/tasks/92`（`feat(agent-ui): 提供task内容修改功能`）：
**一对话 app 就"挂掉"**（窗口白屏），但没有 minidump、主进程还活着。
用户还发现：**即使明确说"千万不要 kill 它"，重启后依然会挂**。

### 1.2 两条因果链（都已修复，见 §8）

**链 A：agent 自杀**

- 该任务历史里，agent 为了"清理多余 Electron 实例"反复执行
  `ps aux | grep Electron | ... | xargs kill -9`、`pkill -9 -f electron`
- 而 diy 自己就跑在 Electron 里 → 把宿主的 `GPU / NetworkService / Renderer` 子进程杀掉
  （`child-process-gone reason=killed exitCode=9` = SIGKILL）
- Electron **不会自动重建 renderer** → 窗口永久白屏
- 主进程侥幸存活（`pkill` 先杀掉自己所在的 bash 进程，命令自限）→ **没有 crashpad minidump**
- 历史里累计 19 条 kill 命令（`ops.jsonl` 可查）

**链 B：中断的 tool 调用被"投影期造数据"**

- SIGKILL 打断的那次 tool 调用**永远收不到 `stop`** → 块停在 `running`
- 重建 LLM 历史时（`blocksToMessages`）必须给每个 `tool-call` 配一条 `tool-result`，
  否则 ai-sdk 抛 `MissingToolResultsError`（请求根本发不出去，见 §3.3）
- 旧实现在**投影时现场合成**一句：
  `[该调用在上一轮中断前未完成，如有需要请重新发起]`
- 对模型而言这是**待办**：重载会话（重启 app / renderer reload）历史一字不差重生
  → agent 重发那条 `kill` 命令 → 再次自杀
- 用户在 90 万 token 的历史里说的"千万不要 kill"盖不过这句系统提示

### 1.3 由此暴露的架构问题（本次讨论的真正起点）

1. **三处数据不一致**：存储（ops）/ 界面（UI）/ 请求（messages）看到的东西不一样
2. **投影期造数据**：真相源里没有的东西，在投影时被现场发明出来 → 不可审计、会重生
3. **UI 看不到"最后一幕"**：26 个 turn 里有 13 个因 openStack 交叉被静默嵌套，UI 只渲染 root turn
4. **事件模型只服务 UI**：`kind` 是闭枚举（turn/step/text/think/tool/plan/error），
   无法表达"子 agent"、"上下文注入"这类未来节点

---

## 2. 现状机制（下次讨论前必须先读这节）

### 2.1 数据流（三段）

```
LLM HTTP SSE
   │
   ▼  ai-sdk streamText().fullStream（part 事件流：text-delta / reasoning-delta / tool-call / finish-step …）
   │
   ▼  runTurn()  ← 唯一认识 ai-sdk 事件名的地方（local-agent.ts:409 注释）
      Op 流（start / delta / patch / stop）
        ├─ sink(op) → append ops.jsonl          ← 真相源（append-only）
        ├─ yield op → RPC 流 → renderer          ← UI 实时渲染
        └─ sess.store.apply(op) → 内存块树        ← 供下一轮发请求
                                                │
下一轮：blocksToMessages(store) → ModelMessage[] → streamText({messages})
```

### 2.2 session 加载与"回放"（两处 fold，同一条流）

| | main 进程 | renderer |
|---|---|---|
| 入口 | `getSession(taskUri)` `local-agent.ts:325-338` | `localChatStore.open()` `localChatStore.ts:65-88` |
| 来源 | `readJsonl(opsFile)` | RPC `agent.local.history`（返回**全量原始 op 数组**） |
| 动作 | `store.apply(op)` fold → 块树 → `blocksToMessages` | `st.store.apply(op)` fold → 块树信号 → UI |
| 缓存 | `sessions: Map<taskUri, LocalSession>`（**纯内存，重启即空**） | `if (st.loaded) return`（已加载不重拉） |

关键：**UI 不是接收 main 折叠好的树，而是自己 fold 同一份 op 流**。
`local-blocks.ts` 是纯函数模块（无 Node/Electron 依赖），main 与 renderer 共用：

```ts
// localChatStore.ts:4-5
// Op 流（RPC serverStream / history 日志）→ BlockStore.fold → 块树信号。
// wire = 存储 = 渲染输入：history 重放与实时流走同一条 fold 路径。
```

实时一轮：`chat` 是 `AsyncGenerator<Op>`，`emit = { sink(op) 落盘 → yield op }`
（`local-agent.ts:436-440`）→ 保证 **UI 看到的顺序 = 磁盘落盘顺序**。

### 2.3 "三份数据"的真实关系

| 文件 | 谁在读 | 定位 |
|---|---|---|
| `<key>.ops.jsonl` | `getSession()`、`history()`（UI） | **唯一真相源**（append-only 事件流） |
| `<key>.llm.jsonl` | **没有任何读取点**（只有写 398 / clear 358） | 投影 dump，**死数据**，注释"续聊的权威"是过时的 |
| `<key>.raw.jsonl` | 无（研究用） | 本次新增的原始流旁路，默认关闭 |

实测证明 llm.jsonl 是死数据：删掉它后 agent 仍能正确答出上一轮的暗号；
把它整体替换成伪造消息，agent 也完全不读（详见 §3.4）。

### 2.4 代码索引

| 主题 | 位置 |
|---|---|
| 块协议（纯函数，main/renderer 共用） | `pkgs.ts/diy-app/src/main/services/local-blocks.ts` |
| agent 运行时（streamText、session、Ops 落盘） | `src/main/services/local-agent.ts` |
| 自杀护栏（纯函数判定） | `src/main/services/agent-guard.ts` |
| 执行审计（write-ahead） | `src/main/services/agent-audit.ts` |
| 崩溃采集 / 退出留痕 | `src/main/services/crash-reporting.ts` |
| renderer 自愈（renderer 被杀后 reload） | `src/main/index.ts` |
| UI 渲染（块树 → 界面） | `src/renderer_solid/components/LocalChatPage.tsx` |
| UI 状态（fold + RPC 流消费） | `src/renderer_solid/store/localChatStore.ts` |
| RPC 契约 | `src/main/services/api-def.ts` / `api-impl.ts` |
| 历史消息实测范例 | `scripts/ai-sdk-messages-demo.mts` |

---

## 3. 实测数据（设计依据，全部实测过）

### 3.1 raw vs ops 体积/行数（一次 2 轮对话，含工具调用）

| | 行数 | 体积 |
|---|---|---|
| `ops.jsonl` | 79 | 6.4 KB |
| `raw.jsonl`（parts 64 + request 2） | 66 | 15.1 KB |

- part / op 行数比 = **0.81**（说明 **delta 不是膨胀主因**）
- 体积比 = **2.37×**（膨胀来自元数据 + 每轮 request 全量快照）

**request 快照的平方增长**（致命点）：

| 轮次 | request.messages 体积 |
|---|---|
| 第 1 轮 | 86 B（1 条消息） |
| 第 2 轮 | 999 B（7 条消息） |

历史随轮数线性增长，每轮都记一次 → O(轮数 × 历史)。按任务 92（26 轮）估算：

| 存法 | 体积 |
|---|---|
| 现在 ops.jsonl | **1.93 MB**（18K 行） |
| 若每轮存完整 messages 快照 | **≈ 9.2 MB**（且继续平方膨胀） |
| 若只存 part（不存 request） | ≈ 1.6 MB 行数 + 2.4× 元数据体积 |

### 3.2 ai-sdk part 的字段与映射损失（15 种，实测）

```
text-delta 22  reasoning-delta 10  tool-input-delta 6  start-step 3  finish-step 3
start 2  finish 2  reasoning-start/end 2+2  text-start/end 2+2
tool-input-start/end 2+2  tool-call 2  tool-result 2
```

`finish-step` 是信息密度最高的 part（项目基本丢光）：

```jsonc
{"type":"finish-step",
 "finishReason":"tool-calls", "rawFinishReason":"tool_calls",
 "usage":{"inputTokens":632,
          "inputTokenDetails":{"noCacheTokens":632,"cacheReadTokens":0},
          "outputTokens":85,
          "outputTokenDetails":{"textTokens":85,"reasoningTokens":0},
          "totalTokens":717,
          "raw":{"prompt_tokens":632,"completion_tokens":85,"total_tokens":717}},
 "performance":{"stepTimeMs":1835.07,
                "toolExecutionMs":{"call_84a9…":79.56,"call_3a945…":82.19},  // 每个工具调用耗时
                "responseTimeMs":1746.13,
                "effectiveOutputTokensPerSecond":48.68,
                "outputTokensPerSecond":136.83},
 "providerMetadata":…, "response":…}
```

另一轮 `finish` 显示 `totalUsage.inputTokenDetails.cacheReadTokens: 512`（**prompt cache 命中**，项目完全没记）。

**逐个 part 的映射与损失**：

| ai-sdk part | 项目 Op | 丢失字段 |
|---|---|---|
| `start` | *（无映射）* | — |
| `start-step` | `start step` | `request`（本样本 `{}`）、`warnings` |
| `reasoning-start/delta/end` | think 块 start/delta/stop | 无（但**投影回 messages 时整块丢弃**） |
| `text-start/delta/end` | text 块 | 无 |
| `tool-input-start` | `start tool` | `dynamic` |
| `tool-input-delta` | `delta input`（Text 累加） | 无（`{"` 这类片段拼成 JSON） |
| `tool-input-end` | *（无映射）* | 整条（可推断，无实质损失） |
| `tool-call` | `patch tool/args/status` | `providerOptions`（换 provider 才需要，如 Gemini 签名） |
| `tool-result` | `delta output` + `patch status` | `input`、`dynamic`、`providerMetadata` |
| `finish-step` | `patch usage` + `stop step` | **finishReason、token 明细、performance、providerMetadata、response** |
| `finish` | `patch usage` + `notice?` + `stop turn` | finishReason（仅 `length` 用于 notice）、usage 明细 |

注意：`tool-result.output` 在 fullStream 里**已经是纯字符串**（不是 `{type:"text",value}`）。

### 3.3 ai-sdk 历史消息规则（实测，脚本 `scripts/ai-sdk-messages-demo.mts`）

| 场景 | 结果 |
|---|---|
| A 正确配对（assistant: text+tool-call / tool: result） | ✅ |
| B **孤立 tool-call**（缺 result） | ❌ `MissingToolResultsError`（**ai-sdk 客户端**抛，请求没发出去） |
| C 回传 reasoning / D 不回传（deepseek-v4-flash，各 3 次） | ✅ 都是 3/3 正常 → zen/go **不强制**回传 |
| E 多步：2×(tool-call + tool-result) | ✅ |
| F 工具失败用 `error-text` 输出 | ✅ |
| G **顺序错乱**（tool-result 放在下一条 user 之后） | ❌ 同一个 `MissingToolResultsError` |
| H1 text+tool-call 同一条 assistant / H2 拆成两条 | ✅ 都通过 |
| X 缺 `x-opencode-session` header | ❌ 400 `MissingSessionID` |

**硬约束**（违反直接失败）：
1. 每个 `tool-call` 必须有同 `toolCallId` 的 `tool-result`
2. `tool-result` 必须**紧邻**对应 `tool-call`（中间不能插 user/assistant）
3. tool 结果只能放 `role:"tool"`（`ToolContent = Array<ToolResultPart | ToolApprovalResponse>`）
4. zen/go 每个请求必须带 `x-opencode-session`
5. 历史里的 `toolName` 要与 `tools` 注册一致

**软约定**：一条 assistant 内按时间序 `reasoning → text → tool-call`；多步 = assistant/tool 交替多轮。

类型定义（`@ai-sdk/provider-utils`，ai 7.0.94）：

```ts
type ModelMessage = SystemModelMessage | UserModelMessage | AssistantModelMessage | ToolModelMessage;
type AssistantContent = string | Array<TextPart | CustomPart | FilePart | ReasoningPart
    | ReasoningFilePart | ToolCallPart | ToolResultPart | ToolApprovalRequest>;
type ToolContent = Array<ToolResultPart | ToolApprovalResponse>;
interface ReasoningPart  { type:"reasoning"; text:string; providerOptions? }
interface ToolCallPart   { type:"tool-call"; toolCallId:string; toolName:string; input:unknown; providerOptions? }
interface ToolResultPart { type:"tool-result"; toolCallId:string; toolName:string; output:ToolResultOutput }
```

### 3.4 llm.jsonl 是死数据（决定性实验）

1. 建临时任务跑一轮（记住暗号"紫色大象"）→ ops 13 行 / llm 2 行
2. **删除** `llm.jsonl` → 再跑一轮问暗号 → **正确答出"紫色大象"**（历史来自 ops）
3. 把 `llm.jsonl` **整体覆盖**成伪造消息「暗号：绿色河马」→ agent 回答"紫色大象…只记住了这一个"
   → **完全不读 llm.jsonl**
4. 结论：`llm.jsonl` 只在 398 行写、358 行 clear 时删，**没有任何读取点**；第 7 行注释"续聊的权威"是错的

### 3.5 证据文件位置（可能被清理，需要时重跑）

```
~/.diy/local/projects_1_tasks_19-27f03738f1e9.raw.jsonl   15 KB  ← ai-sdk 原始流（2 轮）
~/.diy/local/projects_1_tasks_19-27f03738f1e9.ops.jsonl   6.4 KB
~/.diy/local/projects_4_tasks_92-a55ad79ef546.ops.jsonl   1.93 MB（26 轮，含 7 个中断块）
```

重跑 raw dump：

```bash
pkill -f "out/main/index.mjs"; sleep 2; rm -f ~/.diy/app.port
DIY_RAW_STREAM_DUMP=1 diy doctor --json        # 开关随 env 传给 Electron 主进程
diy agent local chat <taskUri> "<message>" --model deepseek-v4-flash
```

---

## 4. 已确认的设计结论（讨论产出）

1. **Op 事件流作为唯一真相源** —— 用户已明确同意（"同意 op 作为自定义主事件唯一真相"）
2. **不把 ai-sdk 原始流作为主存储** —— 三个理由：
   - **输入侧缺失**：用户消息、`system`、`tools` 定义、请求上下文都不在流里（流只描述模型输出），
     这部分必然要自己记 → "只存 ai-sdk 格式"覆盖不全
   - **版本耦合**：part 类型/字段随 ai-sdk 大版本变化（v4→v7 已改名多次）→
     与"存储要长期稳定"直接冲突。决策测试："ai-sdk 明天发 v8，历史日志还能读吗？"
   - **语义缺口**：即使存 part，生成 messages 的映射规则仍是自定义逻辑（没省掉，只是搬家）
3. **线性事件 + 读时 reduce**（与 OTel 同构）—— 树不是主存储，是 fold 的产物
4. **原始流保留为可选旁路**（`DIY_RAW_STREAM_DUMP=1`）—— 定位是"证据"，不是"档案"
5. **字段按"事实"定义，不按"UI 现在要画什么"定义** —— 这是"不因功能增长改存储"的唯一保障：
   - 加：model、时间、finishReason、usage（含 cache/reasoning 明细）、perf、工具入参出参、中断终态、失败语义
   - 不加：颜色、折叠、密度、标题排版、排序
6. **现有机制已经具备长期稳定性的三条支柱**：
   - append-only（崩溃安全、可流式）
   - fold 派生（**改语义只需改 fold 规则，旧日志自动受益** —— 上次 turn 顶层修复就是这么干的）
   - 未知字段/kind 容忍 + 告警（`issues.push`）→ **加字段是向后兼容的**

---

## 5. 三个候选方案的体检结果

| 选项 | 结论 | 关键依据 |
|---|---|---|
| ① 存 ai-sdk 原始信息，其他都动态生成 | ❌ 不适合做主存储 | 输入侧缺失、版本耦合、request 快照 O(n²)（9.2MB vs 1.93MB） |
| ② 存中间态 / 合并后的状态 | ⚠️ 只能当**缓存**，不能取代事件流 | 树/快照需整树重写（写放大）、崩溃丢当前轮、过程与时序消失；正统解法是 WAL + checkpoint |
| ③ 自定义格式 | ✅ 有必要，是唯一长期稳定选择 | 只有"领域事件"不随 SDK/provider 变化；但要**改定位**：从"UI 渲染输入"→"领域事实日志" |

补充：②的"合并"工作就是现在的 fold（读时）。若将来需要，**轮末快照**是唯一合理形态，
且必须标记为"可重建、可丢弃的缓存"。当前 18K 行 fold < 50ms，**暂时不需要**。

---

## 6. 新需求：通用 span 树（本次讨论的下一步）

用户提出：app 的事件流树**大于** ai-sdk 的流，例如：

- 一个 bash tool 激发了**子 agent**
- `read` 时**插入了动态 AGENTS.md 上下文**，并希望在 app 里表现这段轨迹

→ ai-sdk 的 raw stream 只是整棵 app 事件树的**一个子树** → 需要类似 **OTel trace/span 树**的通用结构
（监控语义，但思维适用业务）。

**现状已经是 span 树**（对照表）：

| OTel span | 现在的 Op |
|---|---|
| `span.start {traceId, spanId, parentSpanId, name, attributes}` | `{op:"start", id, kind, parent, meta}` |
| `span.event`（span 内时间点事件） | `{op:"delta"/"patch", id, fields}` |
| `span.end {status, attributes}` | `{op:"stop", id}` |
| trace view（树） | fold 出来的块树 |
| attribute 命名空间 | `meta` / `fields` |

**四个通用化扩展点**（都是"只增不改"）：

1. **`kind` 开放**：现在 `SCHEMA` 是闭枚举 → 改成"注册表 + 未知容忍"：
   已注册 kind 有字段类型校验；未注册 kind 接受任意 `meta`，只告警不丢弃
2. **关系扩展**：现在只有 `parent`（单亲树）→ 加 `traceId` + `links[]`（跨 trace 引用）对齐 OTel；
   默认仍用 child 关系，异步/跨会话才用 link
3. **属性命名空间**：`llm.*`（model/finishReason/usage）、`tool.*`（name/args/exitCode）、
   `ctx.*`（source/hash/bytes/tokens，对应 AGENTS.md 注入）、`perf.*`
4. **显式终态**：`stop` 带 `status: ok | error | interrupted | cancelled`（现在中断是"缺 stop"，隐式）

**判定标准**（以后不用每次讨论）：

> **有开始/结束、有耗时、可能失败 → span；瞬时事实（"注入了什么"）→ attribute/事件。**

---

## 7. 待讨论问题清单（下次从这里开始）

### 7.1 结构设计（优先级最高）

1. **通用 span schema 草案**：字段表、kind 注册机制、如何兼顾"校验"与"未知容忍"、`v` 版本号怎么加
2. **子 agent 的关系表达**：child span（同一棵树）还是独立 `traceId` + link？
   判定：异步/独立运行 → 独立 trace；同步内联 → child
3. **上下文注入建模**：`read` 时的 AGENTS.md 注入 → `ctx` child span 还是 tool span 的 attribute？
   （建议前者，便于 UI 画轨迹）需要记录哪些字段：source/hash/bytes/tokens/是否命中缓存
4. **瞬时事件 vs span 的边界**：哪些东西不该建 span（避免 span 爆炸）
5. **属性 schema 的约束力**：自由 `meta` 会不会退化成"无结构"？要不要按 kind 定义必填/可选字段表

### 7.2 存储形态

6. **线性 vs 树 vs 双存**（倾向结论已给：线性为源 + 可选快照缓存）——需要确认快照的触发条件与格式
7. **多 trace 的文件布局**：同文件（带 `traceId`）还是分文件 + 索引？子 agent 的日志归属哪个 task？
8. **索引**：若要"按 kind 查询"（如所有 bash 调用），是否加侧索引（append-only `{id, kind, offset}`）
9. **快照时机**：轮末？行数阈值（10 万行）？加载耗时阈值？

### 7.3 一致性缺口（已定位，未修）

10. **外部追加无通知**：`file-watcher` 只监听 `state.yaml` / `task/` / `agents/`，
    **不含 `$DIY_HOME/local/`** → CLI（或另一窗口）跑出的新 op，UI 不会知道
    （实测：UI 缺了 CLI 产生的最后 125 个块）。修法：监听 local/ + history RPC 支持增量
11. **history 全量传输**：`history()` 返回整个数组（任务 92 已 2.6 MB）。可加 `sinceSeq` / 分页
    （op 到达顺序天然就是序号，第 N 行 = 第 N 个事件，无需额外字段）
12. **CLI 大 payload 管道截断**：`diy agent local history <uri> | …` 在 **65535 字节**处断掉
    （重定向到文件则完整 2.6 MB）—— CLI 往 pipe 写大 payload 未等 flush。
    修法：`process.stdout.write` + await drain

### 7.4 清理项

13. **删除 `llm.jsonl`**（无人读的冗余投影），并修掉 `local-agent.ts:7` 的错误注释
14. **raw dump 的定位**：保留为旁路；是否给它加"只在指定 task 开启"的环境变量粒度

### 7.5 后续（低优先）

15. 补事实字段（见 §4.5）的具体落地：`finishReason`、usage 明细、`perf`、`error-text`
16. `providerOptions` 透传（Gemini 签名等，换 provider 才需要）
17. reasoning 是否回传（zen/go 不强制，但"保留 vs 丢弃"应作为显式策略，而不是默认丢弃）

---

## 8. 已实施的相关修复（背景，勿重复讨论）

分支 `feat/ui-fine-tune` 上，本次讨论期间已完成：

| commit | 内容 |
|---|---|
| `c65e535` | **自杀护栏** `agent-guard.ts`（执行前判定会杀死自身进程树的命令）+ **write-ahead 审计** `agent-audit.ts`（`~/.diy/log/agent-bash.jsonl`）+ system 硬规则 |
| `ac2d1c6` | 中断占位文案不再诱导重发（"如有需要请重新发起"→ 中性表述） |
| `a7ded46` | **UI/数据一致**：turn 一律顶层（修 13 个 turn 被静默嵌套）+ 中断块 UI 可见（⊘/摘要/默认展开/提示条）+ 文案单一来源 |
| `bd24bdc` | 崩溃现场留痕（`crashContext()`）+ **renderer 被杀后节流自愈 reload** + 进程退出原因落盘 `app-exit.jsonl` |
| `f3250e2` | **原始流 dump 开关** `DIY_RAW_STREAM_DUMP=1`（本次研究的工具）+ `scripts/ai-sdk-messages-demo.mts` |
| `5bc9a65` | **中断 tool 收敛为显式终态**（写进 ops，投影退化为纯翻译），杜绝重载后重复发起 |

对应文档：`pkgs.ts/diy-app/AGENTS.md` 的
**《被 SIGKILL 的"假崩溃"：agent 自杀》** 与 **《中断的 tool 调用：必须收敛成显式终态》** 两节。

`pkgs.ts/diy-app/AGENTS.md` 里已固化的三条约定：

1. 禁止执行会杀死宿主进程的命令（护栏拦截 + 回给模型替代做法）
2. 中断的 tool 块必须在**新一轮开始时**收敛为终态并**落盘 ops**，禁止投影时现造
3. 中断文案禁止出现"未完成 / 请重新发起 / 可重试"这类待办语

---

## 9. 附录

### 9.1 事故与修复的完整时间线

```
任务 92 历史里 agent 反复 kill Electron（19 条命令，7 次被 SIGKILL 截断）
   → renderer 被杀 → 白屏（用户：一对话就挂）
   → 修复：护栏拦截 + renderer 自愈 reload + 崩溃现场留痕
   → 用户发现"说千万别 kill 也没用" → 查到"投影期合成占位提示"诱导重发
   → 修复：文案中性化 + 中断块收敛为 ops 显式终态
   → 排查中发现 UI 只渲染了一半 turn（openStack 交叉把 13 个 turn 嵌套藏起来）
   → 修复：turn 一律顶层（fold 规则，旧日志自动受益）
   → 用户质疑"为什么 UI 与数据不一致/为什么存自定义格式"
   → 引出本次存储重新设计讨论
```

### 9.2 关键认知清单（本次讨论的"干货"）

1. **SIGKILL 捕获不到** → 对不可捕获的死法，唯一办法是"执行前落盘"（write-ahead）
2. **投影期造数据 = 隐藏的第二个真相源** → 会重生、会诱导、不可审计
3. **fold 规则变更 ≠ 存储变更** → 旧日志自动受益（这是"存储稳定"的关键机制）
4. **OTel 自己也不存树** → 线性 span 流 + 读时聚合是成熟做法
5. **ai-sdk 的流不包含输入侧**（用户消息/system/tools）→ 不可能作为唯一事件源
6. **delta 冗余不是问题**（part/op 行数比 0.81），元数据与 request 快照才是
7. **tokens 历史里，用户指令的权重盖不过系统合成文本** → 提示语措辞是有行为后果的
8. **UI 只渲染 root turn** → 树形结构的"隐式嵌套"会静默吞掉整轮内容

### 9.3 下次讨论的建议开场

> "读 `~/git/diy/_diy/docs/tasks/2026-09-12_agent-event-store-redesign/README.md`，
> 我们从 §7.1 的通用 span schema 草案开始。"

需要先做的事：确认 §7.1 的 5 个问题、然后出 schema 草案（含示例事件：
一次 bash 调用、一次上下文注入、一个子 agent span）。
