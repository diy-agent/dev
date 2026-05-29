---
name: diy-project-manager
description: >
  AI-Native Issue-Centric working memory model.
  Issue = task workspace (not just a ticket). Issue body = SSOT for design/tracking/retrospective.
  Trigger: creating/editing issues, task tracking, design discussion, retrospective, /commit, PR workflow.
---

# diy-project-manager

## 核心模型

```
Issue Body → 任务工作记忆（实时更新，任务生命周期内持续演化）
docs/      → 稳定沉淀（任务完成后提取的稳定结论，低频变更）
```

每个任务对应一个 GitHub Issue。Issue body 是该任务的唯一事实源（SSOT），替代散落的文档、评论、设计笔记。

---

## 内容存放决策表

| 内容类型 | 存放位置 | 原因 |
|---|---|---|
| 过程设计、决策、失败尝试 | Issue body | 有版本历史、任务绑定、worktree 间不受影响 |
| AI 推理过程、prompt 实验 | Issue body | 属于工作记忆 |
| 复盘、经验教训 | Issue body `## Retro` 段 | 任务生命周期闭环 |
| 稳定原则、ADR、架构决策 | `docs/` | 跨任务、低频变更 |
| 系统行为/约束 | tests/、notebook、scripts | 可验证、可执行 |
| 概念入口/导航 | `README.md` 或对应 `docs/` | 可发现性 |

原则：**任务进行中频繁变的 → Issue body。任务结束后不再变的 → docs/。**

---

## 文档规范

### 目录与命名

```
docs/
├── README.md              ← 文档索引（必须）
├── adr/                   ← Architecture Decision Records
│   └── 001-xxx.md         ← 编号-简短描述
├── goals/                 ← 战略目标说明
│   └── xxx.md
├── dev/
│   ├── dev-flow.md        ← 开发流程
│   ├── dev-framework.md   ← 框架选择与架构
│   └── ...
└── notes/                 ← 临时笔记（定期清理）
```

### 文档模板

```markdown
---
title: 标题
tags: [标签1, 标签2]
---

# 标题

## 问题
<!-- 为什么要写这个文档 -->

## 方案
<!-- 现在怎么做 -->

## 参考
- #N          ← 关联 issue
- org/repo#N  ← 外部 issue
```

### 编码规范（适用于所有文本和代码）

- **禁止中文标点符号**：用 ASCII 符号替代中文符号（如 `:` 不用 `：`、`,` 不用 `，`、`()` 不用 `（）`）
- **Emoji 仅用于需要视觉区分的关键标识**，不滥用
- 注释优先用英文（避免编码问题），中文注释需确认终端/编辑器兼容

---

## Issue 生命周期

### 任务拆分规则

1. 主任务（parent issue）承载完整设计，子任务只做工作分包记录
2. **从叶子任务向上领取完成**：先完成子任务，再关闭父任务
3. **禁止父子同步工作**：一个父任务的子任务同时只能有一个在 In progress
4. 如果发现任务拆分不当 → **不在已启动的任务上追加子任务**，而是在主任务重新拆分，并缩小之前分配错误的任务范围
5. 这些都需 dev 工具校验，而非靠人工检查

### 创建任务

```bash
dev new "描述"
```

自动：创建 issue → 关联 Project → 设置 Goal/Module/Priority/Type → Status=Backlog

Issue body 初始模板：
```markdown
## Why
<!-- 1-2 句话说明问题/目标 -->

## Design
<!-- 随任务演化持续更新 -->

## Refs
- #N          ← 关联 issue/PR
```

GitHub 自动链接语法：`#N` 同仓库引用、`org/repo#N` 跨仓库引用、commit hash 自动链接。

### 开始工作

```bash
dev start <issue>
```

自动：Status → In progress → 创建 worktree（`.worktree/<N>-<slug>`）→ 创建分支 → 推送远端

**禁止直接在 main 分支修改。**

### 开发中

- 设计变更直接更新 Issue body，不散落在 comments 里
- 新行为优先固化为 tests/notebook，而非 markdown 描述
- 行为表述优先级：**可验证代码 > Notebook（可运行观察） > 静态文档**

### 检查与测试

```bash
./sha.sh check    # lint + format + type check
./sha.sh test     # 单元测试
```

如果未定义则跳过（打印 `[SKIP]`），不阻塞流程。

### 提交

```bash
dev commit
```

执行链：`check` → `test` → git-cleanup 残留检查 → 生成 Conventional Commit message → git commit

**重要**：agent 必须使用 `uv run dev commit` 而非全局 `dev` 命令。全局 dev 可能在开发中切换版本导致行为不确定。

参数：`--skip-check` / `--skip-test` / `--type/-t` / `--scope/-s` / `--message/-m` / `--dry-run/-n`

### 创建 PR

```bash
dev pr
```

自动：推送 → 创建 PR（关联 issue）→ Status → In review

PR 应保持小、可 review、可 rollback。

### 合并

```bash
dev merge-pr
```

自动：squash merge → 更新 issue 状态

### 关闭 worktree

```bash
dev remove
```

仅移除 worktree，**不删除本地分支**。分支留给人类通过 `dev prune` 集中清理。

**AI agent 永远不主动删除分支。** 这是 AI-native 工作流的关键安全边界——保留足够的恢复备份。

### 复盘

```bash
dev retro <issue>
```

复盘属于任务生命周期闭环。执行后，如果产生稳定原则/ADR → 写入 `docs/`。

---

## Project V2 字段

| 字段 | 用途 | 更新方式 |
|---|---|---|
| **Type** | bug/task/feature（GitHub 原生） | issue 创建时设定 |
| **Goal** | 长期战略方向（选项带 30-50 字描述） | `dev` 参数或 TUI |
| **Module** | 代码域/技术域 | `dev` 参数或 TUI |
| **Priority** | P0-P3 | `dev` 参数或 TUI |
| **Status** | Backlog → Ready → In progress → In review → Done | 生命周期自动流转 |
| **Size** | XS/S/M/L/XL | `dev` 参数或 TUI |
| **Labels** | 字段不足时的补充标签 | 按需手动 |

Goal 不是 issue，是 Project 字段选项——永远不关闭、不污染 sprint 视图。

### dev 工具字段更新策略

- **有参数** → agent 自动化调用（如 `dev start 14 --priority P1 --size M`）
- **无参数** → 启动 TUI 交互填写，严格标注必填/选填

---

## Parent/Sub-Issue 规则

- 仅用于真正的工作分解（父和子都是可完成的）
- 禁止用作长期目标容器 → 用 Goal 字段
- 禁止用作知识分类树
- 跨 issue 依赖用 body 内链接：`Depends on #N`、`Blocks #N`

---

## Issue 备份

**规则**：修改 Issue body 前自动备份。

**备份位置**：`.diy/data/issue-backups/<repo>/<issue-N>/`

**文件命名**：`YYYYMMDD-HHMMSS.json`

**无需担心并发冲突**：同一时间一个 issue 只有一个开发实例。

**通过 dev 工具脚本化实现**，不暴露 `gh` 裸命令给 agent。

---

## Agent-Human 职责边界

Issue 是人类和 Agent 沟通的核心桥梁。人类不可能阅读 Agent 所有消息，因此**对 Issue 的修改（尤其是状态变更）必须有明确的权限边界**。

### Agent 可以直接做

| 操作 | 条件 |
|---|---|
| 创建 issue | body 按模板初始化 |
| 更新 issue body（设计/过程/复盘） | 有版本历史，可恢复 |
| `git add` + `git commit` + `git push` | 通过 `dev commit` |
| 创建 PR | 通过 `dev pr` |
| 更新 Project 字段（Status 除外） | 通过 `dev` 参数 |
| 运行 check / test | 日志可见 |

### Agent 必须请求人类确认

| 操作 | 原因 |
|---|---|
| Issue 状态变更（关闭/重开） | 不可逆、有语义差别（completed/not planned/duplicate） |
| 批量关闭 issue | 风险高 |
| 删除 issue / PR / 分支 | 不可逆 |
| 修改 main 分支 | 禁止 |
| 合并 PR | 通过 `dev merge-pr`（人类执行合并策略选择） |

### 确认方式

Agent 应打印建议操作和原因，让人类自行执行。例如：

```
建议关闭以下 issue（已被 #17 覆盖）：
  gh issue close 5  --repo diy-agent/_diy -r "not planned" -c "Covered by #17"
  gh issue close 8  --repo diy-agent/_diy -r "not planned" -c "Covered by #17"
```

TODO(#19): dev close 命令（opencode 式交互确认）

---

## 反模式

| 不要 | 应该 |
|---|---|
| 用 parent issue 做目标容器 | Goal 字段 |
| 过程设计放 docs/ | Issue body |
| 行为用 markdown 长篇描述 | tests/notebook 可执行证明 |
| Discussion 放任务关键设计 | Issue body（Discussion 缺少 Project/PR/worktree 连接） |
| 父子任务同步开发 | 叶子向上领取，禁止并行父子 |
| AI agent 删除本地分支 | 只 dev remove，分支留给人类 dev prune |
| 给 agent 裸 gh 命令 | 通过 dev 工具封装 |

---

## 原则速查

1. Issue body 是 SSOT，设计变更直接改 body
2. 不确定性问题 → dev 工具脚本化，不给 agent 留裸命令
3. 可验证 > 可运行观察 > 静态文档
4. Worktree 隔离开发，main 不可直接修改
5. AI agent 永远不删分支，留恢复备份
6. 中文文本禁止中文标点符号
7. dev 命令行严格标注必填/选填，有参数=agent 用，无参数=TUI 人用
