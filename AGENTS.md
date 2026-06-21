# _diy — 开发元项目

diy 生态的开发工具项目。包含 `dai` CLI、`dev` TUI、PySide6 桌面 app 和 Unix socket 协议实现。

## 目录结构

| 路径 | 说明 |
|------|------|
| `src/diydev/` | Python 包源码 |
| `src/diydev/app/` | PySide6 桌面 app（main.py, task_tree, agent_bridge, log_panel 等） |
| `src/diydev/_dai_cli.py` | `dai` CLI 入口 |
| `src/diydev/dev_tui.py` | `dev` 人类 TUI 入口 |
| `docs/` | 架构文档（architecture.md, process-architecture.md） |
| `tests/` | 意图测试 + 单元测试 |
| `skills/` | 项目级 skills |
| `sha.sh` | 开发入口脚本，`./sha.sh --help` 查看子命令 |

## CLI

**`dai`** — Python 包 `diydev` 提供。入口 `dai = "diydev._dai_cli:main"`。
运行 `dai --help` 查看命令。主要分类：
- `dai task ...` — 任务 CRUD（create/list/show/edit/delete/link/unlink/star/unstar/sync）
- `dai subject ...` — subject 树管理（add/list/tree/show/remove/scan）
- `dai profile ...` — profile 预设管理
- `dai ui ...` — UI 交互（chat state/sessions/read/send）
- `dai doctor` — 健康自检

**`dev`** — 同上包，人类 TUI 接口。`dev --help` 查看命令。

## 架构要点

- 所有跨进程通信走 Unix socket（`~/.diy/app.sock`），协议前缀 `diy` = v1
- 核心状态存 `~/.diy/state.yaml`
- PySide6 桌面 app: `sha.sh app` 启动
- 日志: 文件端 JSONL（`~/.diy/app.log`），终端 stderr，GUI LogPanel 三路一致
