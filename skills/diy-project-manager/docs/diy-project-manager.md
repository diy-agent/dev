# diy Project Manager — 方法论文档

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

**原则：任务进行中频繁变的 → Issue body。任务结束后不再变的 → docs/。**

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

---

## 命名规范

| 命名 | 含义 | 示例 |
|------|------|------|
| `diy` | diy 主 mono 仓库 | - |
| `diy/ref` | diy 仓库的参考源码同步 | diy.yaml sources |
| `diy-cli` | diy CLI 工具（Python） | dev 命令 |
| `diy-cli/ref` | diy-cli 的参考实现 | - |
| `diyui.py` | Python TUI 库 | panel/pane 组件 |
| `diyui.ts` | TypeScript TUI 库 | - |
| `diyq` | 量化交易项目 | - |
| `_diy` | 开发工具元项目 | skills/sha 等 |
| `sha` | 脚本调度引擎（vendor/sha） | sha.bash |

### 命名规则

- 项目名用 `-` 分隔，如 `diy-cli`、`diyui.py`
- `xxx/ref` 表示引用的外部源码/参考实现
- `_xxx` 前缀表示元/工具项目
- Module 字段值应与项目命名一致

### 编码规范（适用于所有文本和代码）

- **禁止中文标点符号**：用 ASCII 符号替代中文符号
- **Emoji 仅用于需要视觉区分的关键标识**，不滥用
- 注释优先用英文（避免编码问题），中文注释需确认终端/编辑器兼容

---

## Issue 生命周期

### 任务拆分规则

1. 主任务（parent issue）承载完整设计，子任务只做工作分包记录
2. **从叶子任务向上领取完成**：先完成子任务，再关闭父任务
3. **禁止父子同步工作**：一个父任务的子任务同时只能有一个在 In progress
4. 如果发现任务拆分不当 → **不在已启动的任务上追加子任务**，而是在主任务重新拆分，并缩小之前分配错误的任务范围
5. 这些需由 dev 工具校验，而非靠人工检查

### Parent/Sub-Issue 规则

- 仅用于真正的工作分解（父和子都是可完成的）
- 禁止用作长期目标容器 → 用 Goal 字段
- 禁止用作知识分类树
- 跨 issue 依赖用 body 内链接：`Depends on #N`、`Blocks #N`

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

Agent 应打印建议操作和原因，让人类自行执行。

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
