# _diy — 开发测试项目

diy 生态的开发测试项目。通过 path 依赖消费主 monorepo 的包（diy-core、diy-app、diy-cli）。

## 目录结构

| 路径 | 说明 |
|------|------|
| `src/diydev/` | 旧 Python 包源码（待清理，代码已移至 `diy/pkgs/`） |
| `docs/` | 架构文档（architecture.md, process-architecture.md） |
| `tests/` | 意图测试 + ShellTest 框架 |
| `skills/` | 项目级 skills |
| `sha.sh` | 开发入口脚本，`./sha.sh --help` 查看子命令 |

## CLI

通过 path 依赖的 `diy-cli` 包提供统一 CLI：
```
uv run diy --help
```
命令与主 monorepo 一致，详见 `diy/AGENTS.md`。

## 与主 monorepo 的关系

```
_diy/pyproject.toml                       diy/pyproject.toml (workspace)
  ├── diy-core = { path = ../diy/... }      ├── pkgs/diy-core/
  ├── diy-app  = { path = ../diy/... }      ├── pkgs/diy-app/
  └── diy-cli  = { path = ../diy/... }      └── pkgs/diy-cli/
```

- 代码逻辑都在 `diy/pkgs/` 中
- `_diy/` 仅保留意图测试、架构文档、项目级 skills
- 不影响主 monorepo 的独立开发环境

## 架构要点

- 所有跨进程通信走 Unix socket（`~/.diy/app.sock`），协议前缀 `diy` = v1
- 核心状态存 `~/.diy/state.yaml`
- PySide6 桌面 app: `sha.sh app` 启动
- 日志: 文件端 JSONL（`~/.diy/app.log`），终端 stderr，GUI LogPanel 三路一致
