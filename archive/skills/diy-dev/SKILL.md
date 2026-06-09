---
name: diy-dev
description: >
  AI Agent 使用 dev CLI 工具的操作指南，含设计理念、sha.sh 规范、dev 命令用法。
  触发词：创建 issue、开始工作、提交代码、创建 PR、合并 PR、查看状态、清理 worktree、
  关闭 issue、复盘、dev 命令用法咨询、任务拆分、Issue 工作流。
  任何涉及"dev start""dev commit""dev status""dev pr""dev merge""dev prune"等操作都触发此 skill。
---

# diy-dev — dev CLI 工具指南

> 生态全局信息（目录结构、全局约束、内容存放规则、依赖源码查找 `~/.diy/ref/`、
> Agent-Human 职责边界）在 `~/git/AGENTS.md`。
> 命令细节（交互绕过、故障排查、常用流程）在 `references/commands.md`。
> 本文件定义 dev 工作流的心智模型和行为规则。

## 设计理念

1. **Issue body 是任务唯一事实源（SSOT）**。设计变更直接改 body，不散落 comments。`dev retro` 写入复盘，修改 body 前自动备份到 `.diy/data/issue-backups/`
2. **不确定性问题脚本化**。不给 agent 裸 `gh` 命令，所有 GitHub 操作通过 `dev` 封装
3. **Worktree 隔离开发**。`dev start` 自动创建 worktree，main 分支不可直接修改
4. **Agent 永远不删分支**。`dev remove` 只移除 worktree，分支留给人类 `dev prune`

## dev / sha.sh 架构

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

# sha.sh — 当前项目，自动检测上下文
./sha.sh commit                # → dev commit $(current_issue)
./sha.sh pr                    # → dev pr $(current_issue)
./sha.sh test                  # 项目本地 test（不做 dev 封装）
```

sha.sh 标准子命令清单见 `~/git/AGENTS.md`。sha.sh 写作规则：用 `run <cmd>` 包装、不隐藏错误、文件末尾保留 `sha "$@"`、模板抄 `_diy/sha.common.sh`。

## 任务拆分规则

- 主任务承载完整设计，子任务只做工作分包
- **从叶子向上领取**：先完成子任务，再关闭父任务
- **禁止父子同步工作**：一个父任务的子任务同时只能一个 In progress
- 拆分不当 → 在主任务重新拆分，不在已启动任务上追加子任务

## 执行规则

- **始终使用 `uv run dev <command>`** 而非全局 `dev`，避免版本不一致
- **操作类命令必须提供 issue 编号或 worktree 名称**，dev 不猜上下文
- 列表类命令默认展示所有项目，当前 cwd 所属项目用图标标记
- 不要直接使用 `gh` 裸命令操作 issue/PR，通过 `dev` 封装命令
- 当前项目的快捷操作用 `./sha.sh <cmd>`
- 执行 dev 命令前先查 `dev <cmd> -h`，确保不落入交互模式
- **禁止跨 worktree 写文件**：当前 worktree 为 `_diy-N` 时，只允许写文件到该 worktree 目录下，严禁写文件到其他 `_diy-*` 目录。如果当前 worktree 缺少测试或文件，应创建新 issue/worktree 而非在无关 issue 中顺手添加。（事件复盘：Issue #57）

## 命令参考

详细命令用法、交互绕过表、常用流程、故障排查 → `references/commands.md`。
