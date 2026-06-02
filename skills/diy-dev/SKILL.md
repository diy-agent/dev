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

## 🚧 dev / sha.sh 架构（开发中）

| | dev | sha.sh |
|---|---|---|
| 范围 | 全局、跨项目 | 仅当前项目 |
| 列表类默认 | **展示所有**，当前 cwd 标记图标 | — |
| 操作类参数 | **必须显式参数**，不猜上下文 | 自动检测当前 issue → 调 `dev <cmd> <issue>` |
| 类比 | 全局控制面板 | 本地快捷键（thin wrapper） |

```bash
# dev — 跨项目，必须显式
uv run dev status              # 所有项目 worktree 概览
uv run dev list --label bug    # 所有项目 issue 过滤
uv run dev commit 32           # 提交 issue 32 关联的 worktree
uv run dev pr 32               # 为 issue 32 创建 PR
uv run dev close 32            # 关闭 issue 32
uv run dev ref rich            # 查依赖源码 mirror 路径

# sha.sh — 当前项目，自动检测上下文
./sha.sh commit                # → dev commit $(current_issue)
./sha.sh pr                    # → dev pr $(current_issue)
./sha.sh test                  # 项目本地 test（不做 dev 封装）
./sha.sh sync                  # 同步 skills/env
```

### sha.sh 标准子命令

所有 diy 项目应实现以下命令。未定义的打印 `[SKIP]`，不阻塞流程。

| 命令 | 职责 | 说明 |
|------|------|------|
| `check` | lint + format + type check | ruff check / ruff format --check / pyright |
| `test` | 单元测试 | pytest |
| `test-all` | 全量测试（含慢速） | test + 集成/端到端 |
| `fix` | 自动修复格式 | ruff check --fix + ruff format |
| `clean` | 清理构建产物 | .venv / .ruff_cache / build / dist |
| `sync` | 同步环境 | uv sync + submodule + skill 安装 |
| `build` | 构建产物 | uv build / npm build（项目指定） |
| `ci` | CI 入口 | check + test（或 check + test-all） |
| **以下为 dev 桥接（thin wrapper）** | | |
| `commit` | 提交代码 | → `dev commit $(current_issue)` |
| `pr` | 创建 PR | → `dev pr $(current_issue)` |

**原则**：
- sha.sh 所有命令都是当前项目操作，不跨项目
- 和 GitHub 交互的（commit/pr/close）通过 sha.sh → dev 桥接
- 纯本地任务（test/build/check）sha.sh 直接执行，不走 dev
- 详细模板和初始化规范见 `diy-workspace-spec` skill

### 任务拆分规则

- 主任务承载完整设计，子任务只做工作分包
- **从叶子向上领取**：先完成子任务，再关闭父任务
- **禁止父子同步工作**：一个父任务的子任务同时只能一个 In progress
- 拆分不当 → 在主任务重新拆分，不在已启动任务上追加子任务

---

## 执行规则

- **始终使用 `uv run dev <command>`** 而非全局 `dev`，避免版本不一致
- **操作类命令必须提供 issue 编号或 worktree 名称**，dev 不猜上下文
- 列表类命令默认展示所有项目，当前 cwd 所属项目用图标标记
- 不要直接使用 `gh` 裸命令操作 issue/PR，通过 `dev` 封装命令
- 当前项目的快捷操作用 `./sha.sh <cmd>`，它会自动检测上下文并调 `dev`

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

### `dev status [--issue N]`

查看所有项目的 worktree 状态。当前 cwd 所属项目/worktree 标记图标。

```bash
uv run dev status             # 所有项目 worktree 概览
uv run dev status --issue 42  # 查询单个 issue
```

### `dev commit <issue> [--type TYPE] [--scope SCOPE] [--message MSG]`

提交代码。**必须指定 issue 编号**。

```bash
uv run dev commit 42                                # 自动检测 type/scope+生成 message
uv run dev commit 42 --type fix --scope cli         # 指定 type/scope
uv run dev commit 42 -m "修复路径问题"              # 完全指定
```

执行链：`check` → `test` → git-cleanup 检查 → Conventional Commit → git commit

快捷方式：在 worktree 内用 `./sha.sh commit`，自动检测当前 issue 并调 `dev commit <N>`。

### `dev doctor`

规范检查。

```bash
uv run dev doctor
```

检查 sha.sh/pyproject 是否符合规范。

### `dev pr <issue>`

创建 PR。**必须指定 issue 编号**。

```bash
uv run dev pr 42
```

自动：推送 → 创建 PR（关联 issue）→ Status → In review

快捷方式：`./sha.sh pr`

### `dev merge-pr [--method squash|merge]`

合并 PR。

```bash
uv run dev merge-pr                    # 默认 squash
uv run dev merge-pr --method merge     # 普通 merge
```

自动：GitHub squash merge → 拉取 main → 提示可清理

### `dev remove <issue>`

移除 worktree，**不删除本地分支**。**必须指定 issue 编号或 worktree 名称**。

```bash
uv run dev remove 42
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
# 新任务（dev 显式参数）
uv run dev new "功能描述"
uv run dev start <N>
# ... 修改代码，设计变更直接改 Issue body

# 当前项目快捷操作（sha.sh 自动检测上下文）
./sha.sh commit              # → dev commit $(current_issue)
./sha.sh pr                  # → dev pr $(current_issue)

# 全局查看
uv run dev status             # 所有项目 worktree 概览
uv run dev list --label bug   # 跨项目 issue 过滤

# 规范检查
uv run dev doctor

# 收尾
uv run dev merge-pr <PR#>     # 合并 PR
uv run dev prune              # 清理
uv run dev retro <N>          # 复盘
uv run dev close <N>          # 关闭 issue
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
