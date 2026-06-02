---
name: diy-dev
description: >
  AI Agent 使用 dev CLI 工具的操作指南，含设计理念与工具无法覆盖的补充规则。
  触发词：创建 issue、开始工作、提交代码、创建 PR、合并 PR、查看状态、清理 worktree、
  关闭 issue、复盘、dev 命令用法咨询、任务拆分、Issue 工作流。
  任何涉及"dev start""dev commit""dev status""dev pr""dev merge""dev prune"等操作都触发此 skill。
---

# diy-dev — dev CLI 工具指南

## 设计理念

dev 工具的设计遵循以下原则：

1. **Issue body 是任务唯一事实源（SSOT）**。设计变更直接改 body，不散落 comments。`dev retro` 写入复盘，修改 body 前自动备份到 `.diy/data/issue-backups/`
2. **不确定性问题脚本化**。不给 agent 裸 `gh` 命令，所有 GitHub 操作通过 `dev` 封装
3. **Worktree 隔离开发**。`dev start` 自动创建 worktree，main 分支不可直接修改
4. **Agent 永远不删分支**。`dev remove` 只移除 worktree，分支留给人类 `dev prune`
5. **命令行有参数 = agent 用，无参数 = TUI 人用**

### 任务拆分规则

- 主任务承载完整设计，子任务只做工作分包
- **从叶子向上领取**：先完成子任务，再关闭父任务
- **禁止父子同步工作**：一个父任务的子任务同时只能一个 In progress
- 拆分不当 → 在主任务重新拆分，不在已启动任务上追加子任务

---

## 执行规则

- **始终使用 `uv run dev <command>`** 而非全局 `dev`，避免版本不一致
- dev 命令默认在**当前 worktree 下**执行，涉及 git 操作会自动识别 worktree 上下文
- 不要直接使用 `gh` 裸命令操作 issue/PR，通过 `dev` 封装命令

---

## Agent 须知：交互命令与绕过方式

以下命令在**未提供必要 option 时会进入 stdin 交互模式**，可能导致 Agent 卡死。执行前务必先查 `dev <cmd> -h`。

| 命令 | 交互点 | 绕过方式 |
|------|--------|----------|
| `dev merge-pr` | 策略选择器 | `--method squash/merge/rebase` |
| `dev prune` | 确认清理 | `-y` |
| `dev commit` | 编辑器编辑 message | `-m "msg"` 或 `--type TYPE --scope SCOPE --message MSG` |
| `dev close` | 确认关闭 | `-y` |

**通用原则**：所有交互式 prompt 都有对应的 option 跳过。执行前先用 `-h` 查看，找不到再查 skill。

---

## 命令速查

### `dev new <描述>`

创建新 issue。

```bash
uv run dev new "优化登录页面性能"
```

自动：创建 issue → 关联 Project → 设置字段 → Status=Backlog

### `dev start <issue> [--priority P] [--size S]`

开始工作。

```bash
uv run dev start 42
uv run dev start 42 --priority P1 --size M
```

自动：Status → In progress → 创建 worktree（`.worktree/<N>-<slug>`）→ 创建分支 → 推送远端

### `dev status [--all/-a] [--issue N]`

查看 worktree 状态。

```bash
uv run dev status           # 树状概览所有 worktree
uv run dev status -a        # 展开详情（URL、拓扑图）
uv run dev status --issue 42  # 查询单个 issue
```

### `dev commit [--type TYPE] [--scope SCOPE] [--message MSG]`

提交代码。

```bash
uv run dev commit                          # 自动检测 type/scope+生成 message
uv run dev commit --type fix --scope cli --message "修复路径问题"
```

执行链：`check` → `test` → git-cleanup 检查 → Conventional Commit → git commit

### `dev doctor`

规范检查。

```bash
uv run dev doctor
```

检查 sha.sh/pyproject 是否符合规范。

### `dev pr`

创建 PR。

```bash
uv run dev pr
```

自动：推送 → 创建 PR（关联 issue）→ Status → In review

### `dev merge-pr [--method squash|merge]`

合并 PR。

```bash
uv run dev merge-pr                    # 默认 squash
uv run dev merge-pr --method merge     # 普通 merge
```

自动：GitHub squash merge → 拉取 main → 提示可清理

### `dev remove`

移除 worktree，**不删除本地分支**。

```bash
uv run dev remove
```

### `dev prune`

清理已合并分支（人类操作）。

```bash
uv run dev prune          # 清理远程已合并分支
uv run dev prune --local  # 一并清理本地分支
```

### `dev retro <issue>`

复盘，引导填写内容写入 Issue body 的 Retro 段落。

```bash
uv run dev retro 42
```

---

## 常用流程

```bash
# 新任务
uv run dev new "功能描述"
uv run dev start <N>
# ... 修改代码，设计变更直接改 Issue body
uv run dev commit
uv run dev pr

# 日常
uv run dev status -a      # 查看所有 worktree 状态
uv run dev doctor          # 检查规范

# 收尾
uv run dev merge-pr        # 合并 PR
uv run dev prune           # 清理
uv run dev retro <N>       # 复盘
```

---

## 故障排查

| 现象 | 原因 | 解决 |
|------|------|------|
| `dev` 命令不存在 | 未激活环境 | `uv sync; source .venv/bin/activate` |
| `dev status` 显示异常 | gh 未登录 | `gh auth status` |
| `dev start` 失败 | 分支或 worktree 冲突 | 检查 `git branch -l` 和 `git worktree list` |
| `dev commit` 跳过测试 | 项目无 test 入口 | 正常，日志打印 `[SKIP]` |

---

## 工具无法覆盖的补充规则

以下规则 dev 工具不强制执行，Agent 需自觉遵守。

### 内容存放

| 内容类型 | 位置 | 原因 |
|----------|------|------|
| 过程设计、决策、失败尝试 | Issue body | 版本历史、任务绑定 |
| 复盘、经验教训 | Issue body `## Retro` 段 | 生命周期闭环 |
| 稳定原则、ADR | `docs/` | 跨任务、低频变更 |
| 系统行为/约束 | tests/、notebook | 可验证、可执行 |

### Agent-Human 职责边界

Agent 可以直接做：
- 创建 issue、更新 body（设计/过程/复盘）
- 通过 `dev commit` / `dev pr` 提交和推送
- 更新 Project 字段（Status 除外）
- 运行 check / test

Agent 必须请求人类确认：
- Issue 状态变更（关闭/重开）— 不可逆
- 删除 issue / PR / 分支 — 不可逆
- 修改 main 分支 — 禁止
- 合并 PR — 人类选择合并策略

### 反模式

| 不要 | 应该 |
|------|------|
| parent issue 做目标容器 | Goal 字段 |
| 过程设计放 docs/ | Issue body |
| 行为用长篇 markdown | tests/notebook |
| 父子任务同步开发 | 叶子向上，禁止并行 |
| AI agent 删分支 | dev remove 只删 worktree |
| 给 agent 裸 gh 命令 | 通过 dev 工具封装 |
