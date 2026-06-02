---
name: diy-project-manager
description: >
  AI-Native Issue-Centric 项目管理方法论。
  触发: 项目命名/结构讨论、重构/改名、包结构调整、代码组织方式讨论、
  任务拆分与追踪、Issue 创建与编辑、设计评审、复盘讨论、提交/PR 工作流、
  任何涉及"怎么组织代码""包名合不合理""要不要拆文件""项目结构设计"的问题。
---

# diy-project-manager

> 完整方法论文档：[docs/diy-project-manager.md](docs/diy-project-manager.md)

## 核心模型

```
Issue Body → 任务工作记忆（实时更新，持续演化）
docs/      → 稳定沉淀（任务完成后提取的结论，低频变更）
```

Issue body 是任务唯一事实源（SSOT），替代散落的文档、评论、设计笔记。

## 内容存放

| 内容类型 | 位置 | 原因 |
|----------|------|------|
| 过程设计、决策、失败尝试 | Issue body | 版本历史、任务绑定 |
| AI 推理、prompt 实验 | Issue body | 工作记忆 |
| 复盘、经验教训 | Issue body `## Retro` | 生命周期闭环 |
| 稳定原则、ADR | `docs/` | 跨任务、低频变更 |
| 系统行为/约束 | tests/、notebook | 可验证、可执行 |

## 命名规范

- 项目名用 `-` 分隔：`diy-cli`、`diy-ui`
- `_` 前缀为元/工具项目：`_diy`
- `/ref` 为外部引用：`diy/ref`
- Module 字段值与项目命名一致

## Issue 生命周期

### 任务拆分

1. 主任务承载完整设计，子任务只做工作分包
2. **从叶子向上领取**：先完成子任务，再关闭父任务
3. **禁止父子同步工作**：一个父任务的子任务同时只能一个 In progress
4. 拆分不当 → 在主任务重新拆分，不在已启动任务上追加子任务

### 常用流程（通过 dev-tool skill 执行）

```
dev new "描述"    → 创建 issue → Backlog
dev start <N>    → In progress → 创建 worktree + 分支
Dev 中             → 设计变更直接改 Issue body
dev commit       → check → test → cleanup → commit
dev pr           → 推送 → 创建 PR → In review
dev merge-pr     → squash merge → 更新状态
dev remove       → 移除 worktree（不删分支）
dev prune        → 人类清理已合并分支
dev retro <N>    → 复盘写入 Issue body
```

## Agent-Human 职责边界

### Agent 可以直接做

- 创建 issue、更新 body（设计/过程/复盘）
- 通过 `dev commit` / `dev pr` 提交和推送
- 更新 Project 字段（Status 除外）
- 运行 check / test

### Agent 必须请求人类确认

- Issue 状态变更（关闭/重开）— 不可逆
- 删除 issue / PR / 分支 — 不可逆
- 修改 main 分支 — 禁止
- 合并 PR — 人类选择合并策略

## 反模式

| 不要 | 应该 |
|------|------|
| parent issue 做目标容器 | Goal 字段 |
| 过程设计放 docs/ | Issue body |
| 行为用长篇 markdown | tests/notebook |
| 父子任务同步开发 | 叶子向上，禁止并行 |
| AI agent 删分支 | dev remove 只删 worktree |
| 给 agent 裸 gh 命令 | 通过 dev 工具封装 |

## 原则速查

1. Issue body 是 SSOT，设计变更直接改 body
2. 不确定性问题脚本化，不给 agent 裸命令
3. 可验证 > 可运行观察 > 静态文档
4. Worktree 隔离开发，main 不可直接修改
5. AI agent 永远不删分支
6. dev 命令行有参数=agent 用，无参数=TUI 人用
