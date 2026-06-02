# _diy Agent Instructions

## What This Repo Is

`_diy` 是 diy 生态的**开发工具元项目**，承载所有 diy 系列项目的共享基础设施：

- `src/diydev/` — `dev` CLI 工具（issue 管理、worktree 开发流程）
- `skills/` — 给 AI agent 使用的规范与流程 skill
- `docs/` — 跨项目的稳定设计文档与 ADR
- `sha.common.sh` — sha.sh 脚本引擎的**权威模板**

其他 diy 项目的 `sha.common.sh` 以此文件为规范来源。

## 命名规范

| 命名 | 含义 |
|------|------|
| `_diy` | 开发工具元项目 |
| `diydev` | `dev` CLI 工具包名 |
| `sha` | 脚本调度引擎（`vendor/sha/`） |

`_` 前缀表示元/工具项目。Module 字段值应与项目命名一致。
