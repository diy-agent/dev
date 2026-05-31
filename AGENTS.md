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

## 硬规则

### sha.sh 规范

- 所有 diy 项目统一使用 `sha.common.sh`（`.` 分隔，非 `_`）
- `run()` 函数是无 `_` 前缀的公开 API
- 项目根目录的 `sha.sh` 通过 `source "sha.common.sh"` 引入

### Python 包安装

- **禁止直接使用 `pip install`**
- 必须使用 `uv add` 或 `uv run`

### 提交规范

- 提交前先 review: `git diff --stat`，确认不夹带密钥、token、无关文件
- 提交前先 review: 检查代码中是否错误使用了中文符号作为语法分隔符
- 提交信息遵循 Conventional Commits（`feat:`、`fix:`、`chore:`、`docs:` 等）
- **绝对不要自主 push**，必须等用户明确要求后再执行

## 常用命令

```bash
./sha.sh check    # ruff check + format check + pyright
./sha.sh test     # 单元测试
./sha.sh sync     # 环境同步 + skills 安装
./sha.sh clean    # 清理构建产物
```
