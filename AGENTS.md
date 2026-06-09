# _diy

diy 生态的**开发工具元项目**。

`dai` CLI + Panel GUI app，正在开发中。

`dev` CLI 已弃用。

## dai 命令

| 命令 | 说明 |
|------|------|
| `dai state` | 全量输出/修改 ~/.diy/state.yaml |
| `dai profile list/show` | profile 预设 |
| `dai tree --sync` | 注入 AGENTS.md |
| `dai subject add <path> [--desc] [--type]` | 注册 subject |
| `dai subject list [--json]` | 扁平列表 |
| `dai subject tree [--json]` | 树状展示 |
| `dai subject show <path> [--json]` | 查看单个 |
| `dai subject remove <path> [--json]` | 删除 subject |
| `dai subject scan --root <dir> [--json]` | 文件系统扫描 |

根文件 `~/git/AGENTS.md` 包含生态全局约束。
