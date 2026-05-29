---
name: diy-project-manager
description: >
  针对 diy 及其生态项目（diy, diyq, sha, 及关联的 research 项目）的项目管理、流程规范及 Github Project V2 协作管理技能。
  基于 dev 命令行工具，通过 worktree 隔离模式推动 AI-Native 开发流。
  触发词：项目管理、新建任务、开始开发、提交 PR、流程指引、issue 归类、看板管理、dev 使用。
---

# diy-project-manager

此技能专门指导开发者及 AI Agent 如何进行项目管理、使用 `dev` CLI 开发流工具以及基于 GitHub Project 进行团队协作。

## 项目生态全景视图

当前工作区 `_diy` 独立于原业务项目，核心使命是：**建立并维护开发流工具 (`dev`)、开发规范、项目管理体系，推动 AI-Native 开发进程。**

主要纳管的项目矩阵包括：
1. **主线产品项目**：
   - `diy` / `diyq` / `sha` (核心业务与辅助工具)
2. **探索/研究项目**：
   - `diy-research` / `diyq-research` (用于前期探路、原型验证、AI 实验沉淀)
3. **元项目 (当前项目)**：
   - `_diy` (包含 `dev` CLI 开发、`dev-flow` 规范、Agent Skills)

## 核心心智模型：短生命周期执行与多维聚合

1. **Issue 作为短生命周期执行单元 (Ephemeral)**
   - Issue 必须有明确结束状态（可被 Done / Close）。
   - 不要把 Issue 当作“长效目标”或“容器”。
   - 包含具体的任务边界、复现步骤或详细设计（过程设计文档直接写在 Issue Body，具有时间性和版本历史）。
   
2. **Goal 与 Docs 作为长期知识库 (Persistent)**
   - 长期愿景和规划写在 `docs/goals/*.md` 或项目内对应的活文档中。
   - 任务完成后，有价值的架构变更、核心逻辑抽象应沉淀到 `docs/` 或各自仓库中。
   
3. **Project Fields 作为多维切片 (Slicing)**
   - 使用 GitHub Project 自定义字段（`Status`, `Priority`, `Module`, `Size`）取代复杂的 Parent/Child 树形结构，通过 Query / View 进行聚合。

## AI-Native 驱动的敏捷开发流 (基于 `dev`)

在团队规范下，开发一律采用 **Git Worktree 隔离模式**，禁止直接在主分支（main）提交修改。所有执行动作依赖 `dev` CLI 工具和 GitHub CLI (`gh`) 自动化。

### 标准生命周期与指令表

| 阶段 | 状态 (Status) | `dev` CLI | `gh` / `git` 底层操作 | 描述 |
| --- | --- | --- | --- | --- |
| **创建任务** | Backlog | `dev new "描述"` | `gh issue create` | 创建新 Issue，默认进入 Project Backlog。 |
| **分配/排期** | Ready | (手动或看板操作) | `gh project item-edit` | 评审后确定优先级 (P0-P3) 与模块 (Module)。 |
| **开始开发** | In progress | `dev start <issueNum> [分支名]` | 创建 `.worktree/`、切换分支并推送到远端，项目状态联动。 | 自动创建本地独立沙盒，不污染主线。 |
| **开发中** | In progress | 进入 `.worktree/<num>` | 编辑代码，运行测试 | 设计变更与 AI 对话思路沉淀在 Issue comment 或同级 MD 中。 |
| **提交审查** | In review | `dev pr` | `gh pr create` | 将当前 worktree 的代码发起 Pull Request。 |
| **合并代码** | Done | `dev merge-pr` | `gh pr merge --squash` | 合并 PR (优先 Squash 保持主线提交历史干净)。 |
| **清理环境** | - | `dev prune` | 删除 worktree 及分支 | 开发环境整洁无冗余(不删除本地分支预防误操作恢复TODO)。 |

## Project 字段体系与分类标准

| 字段 | 用途 | 选项规范 |
| --- | --- | --- |
| **Status** | 生命周期流转 | Backlog → Ready → In progress → In review → Done |
| **Priority** | 优先级判定 | P0 (紧急阻断), P1 (核心特性/重要Bug), P2 (普通增强), P3 (低优/体验) |
| **Module** | 代码/功能域 | 依据对应项目架构划分（例如 dev, cli, core 等） |
| **Size** | 工作量预估 | XS (<1d), S (1-2d), M (3-5d), L (1w+), XL |

## Issue 管理与操作规约

1. **信息完备性检查**
   - 任何新创建的 Issue 必须经过整理（Triage），分配至 GitHub Project，并完善 `Priority` 和 `Module`和`Type`。
   - 避免模糊和发散，如果没有对应的 `Goal` 属性则需补充上下文或文档记录。

2. **Parent-Child 嵌套使用红线**
   - **允许**：用于一个明确交付任务拆解（真正的 Work Breakdown,当前看板模式没有Sprint拆解）。
   - **禁止**：用于跨领域的长期战略目标组织（如“2026年CLI体验优化”应采用 Goal 字段，而非一个永不关闭的父 Issue）。

3. **依赖关系声明**
   - 不滥用 sub-issue 表达依赖，推荐在 Body 描述区通过 `Depends on #<Num>`, `Blocks #<Num>`, `Related: #<Num>` 明确构建图结构依赖关系。

## 维护与清理清单（定期自检）

建议定期执行以下自查操作：
- [ ] GitHub Project 中是否有 `Status=Backlog` 但长期未处理且无 `Priority` 标记的任务？
- [ ] 是否存在长期活跃、不会被直接完成的“伪 Issue”（当做容器使用的 Parent Issue）？需转为文档/看板查询。
- [ ] 本地 `.worktree/` 目录：是否存在已经合并不再维护的废弃分支？（需使用 `dev prune` 清理）
- [ ] 针对 AI-Native 过程：在 `diy-research` 等仓库验证完毕的实验代码，是否已有效抽象并入主库？

## Agent 交互指引

- 当用户要求开发新特性或修复问题时，应优先引导其走规范工作流：先使用 `dev new` 生成 Issue -> `dev start` 开启环境。
- 若问题属于前瞻性研究、技术选型验证或具有高度不确定性，建议推荐其在关联的 `-research` 项目中拉取沙盒环境验证，完成后再汇总方案合并到正式项目的 Issue 内。
