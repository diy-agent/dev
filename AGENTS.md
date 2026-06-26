# _diy — 开发辅助项目

diy 生态的开发辅助项目。通过 path 依赖消费主 monorepo 的包（diy-core、diy-app、diy-cli）。

## 目录结构

| 路径 | 说明 |
|------|------|
| `docs/` | 架构文档（architecture.md, process-architecture.md） |
| `skills/` | 项目级 skills |
| `_shims/` | macOS 12 兼容 shim（nodejs-wheel-shim） |
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
- `_diy/` 保留架构文档、项目级 skills
- 意图测试已迁至 `diy/tests/`
- `src/diydev/` 旧代码已清理
