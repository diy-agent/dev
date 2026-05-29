---
name: diy-project-manager
description: >
  AI-Native 项目管理与开发流技能。
  基于 GitHub Issues + Project V2 + Worktree 的任务工作记忆模型（Issue-Centric Working Memory）。
  用于需求启动、研究探索、设计更新、AI Agent 开发、测试、PR、复盘、知识沉淀与任务循环。
  核心思想：Issue 是任务工作空间（Workspace），Issue Body 是实时唯一事实源（SSOT），优先使用可执行知识（Tests/Tools）替代长文档。
  触发词：项目管理、新建任务、开始开发、提交 PR、流程指引、工作记忆、复盘、开发流、diydev 使用。
---

# diy-project-manager

本技能定义了基于 **Issue-Centric Working Memory（以 Issue 为中心的任务工作记忆）** 的 AI-Native 工程体系。
目标是：减少静态文档漂移，让 AI 与人类共享实时工作记忆，并通过**可执行知识**替代长篇大论的描述。

TODO: 还未考虑工作流的责任安排, 谁能做什么等事项, 后续补充。

---

## 核心理念分层

### 1. Execution Layer（实时执行层）
GitHub Issue 是 **Task Workspace（任务工作空间）**，而不仅是任务卡片。
Issue 聚合了：当前需求、最新设计、实验记录、AI 推理过程 (Reasoning)、Prompt、PR、测试结果和复盘。
**Issue Body 是当前任务的唯一事实源 (SSOT)**。所有的设计变更和中间结论都直接在 Issue 中更新，而不是散落在代码库的各个文档中。

### 2. Executable Knowledge（可执行知识层）
原则：**Behavior > Description（行为胜于描述）**。
优先通过以下形式表达系统行为，而不是写大量的 markdown 文档：
`Tests > Doctor Tools > Generators > Skills/Scripts > Notebook > Static Docs`
测试必须是人类和 AI 都易于观察的（Human Observable），并且是面向意图的（Intent Oriented）。

### 3. Stable Principles（长期稳定层）
只在代码库中沉淀长期稳定、低频变化的知识，必须脱离具体任务：
- ADR (Architecture Decision Records)
- 核心架构图
- 稳定的设计原则
- 最简化的复盘结论 (Minimal Postmortem Conclusions)

---

## 任务生命周期与 diydev CLI 工具链

### 1. 新需求 / 想法孵化 (Backlog)
无论是用户需求、研究灵感、Bug 还是上一次的复盘结论，一律作为新任务创建。
```bash
dev new "描述你的想法或需求"
```
*自动行为：创建 Issue，加入 GitHub Project，并初始化基本字段。*

### 2. 任务工作空间初始化 (Workspace Setup)
在开始写代码前，必须初始化 Issue Body。它应该包含：
- Problem (要解决什么问题)
- Goal (目标是什么)
- Constraints (约束条件)
- Design / Plan (初步设计和计划)
*注意：在后续的探索和开发中，**持续直接编辑更新 Issue Body**，保持它是唯一的最新状态，这让 Worktree 隔离开发时 AI 能随时获取最新上下文。*

### 3. 开始开发 (Start Working)
**禁止直接在 main 分支开发。**
```bash
dev start <issueNum> [分支后缀]
```
*自动行为：根据 Issue 编号创建独立的 Git Worktree 和分支，更新 Issue 状态为 In Progress。*

### 4. 迭代与测试验证 (Development & Tests First)
- **更新工作记忆**：将 Failed attempts、Benchmark、AI Reasoning 持续记录在 Issue 中。
- **固化可执行知识**：优先编写 Tests、Notebook Demo 或更新 CLI 工具，而不是写说明文档。

### 5. 提交审查 (Pull Request)
当任务完成并通过测试后：
```bash
dev pr  [empty==current | issueNum]
```
*自动行为：推送代码，创建 PR 并关联当前 Issue，状态变更为 In review。*
*要求：PR 必须小而聚焦，易于 Review 和 Rollback。*

### 6. 合并代码 (Merge)
```bash
dev merge-pr  [empty==current | issueNum]
```
*自动行为：Squash Merge PR 保持主线干净，并清理本地 Worktree 和分支。*

### 7. 复盘与知识沉淀 (Retrospective)
复盘是任务生命周期的闭环部分，而不是长期文档。
复盘内容直接写在当前 Issue 的评论区或作为子 Issue（什么有效、什么失败、AI 为何受阻、如何避免）。
如果有具备长期价值的架构决策，提炼为极短的 **ADR (仅记录：现在是什么 + 为什么这样 + 权衡)** 并入 `docs/`。
如果复盘产生了新想法，则回到步骤 1。

```bash
dev retro [empty==current | issueNum]
```

AI(TODO 还未实现):
1. 分析事故...
2. 吸取教训：
   - 缺少熔断机制
   - 超时配置未与下游 SLA 对齐
3. 更新 xxx.md （加入熔断策略）
4. 更新 xxx.md （新增“超时配置反模式” ADR 条目）
5. 创建新 issue：
   - 标题：实现熔断器
   - 标签：improvement
6. 任务跟随型复盘更新总结到主issue, 专项复盘更新到所属issue,需要有总结和输出项及引用

---

## 知识与视图管理原则

### GitHub Project V2 切片 (Slicing)
看板用于多维度的任务切片，而不是构建知识树。核心字段：
- **Goal**: 长期战略方向（替代“父 Issue 容器”）
- **Module**: 技术域（如 cli, core, tui）
- **Priority**: 优先级 (P0-P3)
- **Status**: 生命周期状态

### Parent/Sub-Issue 树形陷阱与依赖图谱
- **严禁**：用父 Issue 当作长期目标容器、知识分类或认知树。
- **允许**：仅用于一个明确 Sprint 内的 **真实工作拆解 (Work Breakdown)**。
- **依赖表达**：优先在 Issue Body 中使用文本关联形成网状图结构：
  ```markdown
  Depends on #N
  Blocks #N
  Related #N
  ```

### 核心反模式警告 (Anti-Patterns)
❌ 不要用 Issue 当长期目标。
❌ 不要用代码库里的 Markdown 存实时设计（会因为 Worktree 隔离导致版本漂移）。
❌ 不要用大篇幅文本描述系统行为（去写测试或工具）。
❌ 不要写繁重的 Agents.md 指令集。
❌ 不要把 GitHub Discussion 当作日常高频执行流引擎。
