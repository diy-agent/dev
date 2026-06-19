# AgentChatPanel 交互流程重构

## 问题

用户在 #6 任务输入消息后，UI 没有任何反馈——没有新 session、没有回复、不知道发生了什么。

## 根因

### 1. 无反馈

`_send_text()` 调用 `steer_send()` + 后台 `_spawn_agent()` 后立即清空输入框。用户只看到输入框被清了，其他什么都没发生。没有 loading 状态、没有"已发送"回显、没有新 session 条目。

### 2. 无新 session 条目

`steer_send()` 只写文件（`~/.diy/agents/<uri>/steer.log`），没有在 UI 的 session 列表中创建条目。新 session 只有在 agentd 写入 `status.json` 后，`_refresh_sessions()` 定时器（3s 间隔）检测到时才出现。这中间有 3-15s 空白期。

### 3. 会话状态机问题

当前逻辑：有 state=running 的 session 就复用，否则创建新 agent。

用户期望：
- **有活跃 session** → 直接输入，消息送到该 session
- **无活跃 session（全部 done）** → 进入最后一个 session 的对话视图，输入框可用，输入时创建新 session
- **首次打开** → 空状态，输入框可用，输入时创建新 session

### 4. 布局不满足需求

```
当前布局：                   期望布局：
┌─────────────────┐         ┌─────────────────┐
│  Session 列表    │         │  Agent 信息栏    │
│ (QListWidget)   │         └─────────────────┘
├─────────────────┤         ┌─────────────────┐
│  对话 Log        │         │  Session 列表    │
│ (QTextEdit)     │         │  ...            │
│                 │         │  [+ 新会话]     │
├─────────────────┤         ├─────────────────┤
│  输入框          │         │  对话 Log        │
│  发送按钮        │         │  (QTextEdit)    │
└─────────────────┘         │                 │
                            ├─────────────────┤
                            │  输入框          │
                            │  发送按钮        │
                            └─────────────────┘
```

## 关键改动

### 1. 输入即创建 session（即时反馈）

用户按 Enter 时：
- 立即在 session 列表底部添加一个 `⏳ 新会话` item
- `_log` 清空，显示 `[你] 消息内容`
- 后台 spawn agent
- 收到 agent 回复后，session 条目更新状态，`_log` 追加回复

### 2. 打开任务时自动选中最后会话

`set_task(uri)` 时：
- 有 sessions → 选中最后一个（最晚的 session）→ 加载它的 steer.log 到 `_log`
- 无 sessions → 空状态

### 3. 入口始终是输入框

输入框始终 visible/enabled，placeholder 随状态变化：
- 有活跃 session → "输入消息..."
- 无活跃 → "输入新消息开始新对话..."

「➕ 新对话」按钮不需要——输入框就是入口。需要新建时直接输入。

### 4. "+" 图标在 session 列表底部

session 列表最下面固定一个 `[+ 新会话]` item，点击效果等于清空 `_log`、聚焦输入框（不创建 agent，等用户输入才创建）。

### 5. 去掉 `_update_mode` 的复杂状态机

只用两个状态：有活跃 / 无活跃。输入框始终可用。

## 实现步骤

- [x] `_send_text` 改为在 session 列表即时添加`⏳`条目
- [x] `set_task` 自动选中最后 session
- [x] 去掉 `_update_mode` 的 empty/history/history_view/active 四态
- [x] 输入框始终 visible
- [x] session 列表底部固定 [+ 新会话]
- [x] 新 session 消息回显到 `_log`
- [ ] agent 完成时更新 session 条目图标（⏳→✅/❌）— 由 3s timer 刷新覆盖
