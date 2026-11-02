# _diy — diy 生态开发辅助仓

**这不是产品，是开发辅助仓。** 放不进主仓、又需要独立演进（或需要独立提交）的开发工具链。
产品代码仍在主 monorepo `../diy`。

## 定位

- 独立 git 仓（与 `../diy` 是两个仓，提交互不影响）
- 通过 **path 依赖**消费主仓的包，不发布、不 vendor
- 当前内容：`dev/` —— ref（本地源码镜像）CLI，为后续 dev 启动器铺路

## 目录

| 路径 | 说明 |
|------|------|
| `dev/` | `@diy-agent/dev`：ref 命令（add / sync / list / remove），入口 `bin/dev` |
| `docs/` | 历史架构文档（Python 时代，只读参考） |
| `skills/` | 项目级 skills（git-cleanup / win-file-unlock） |
| `archive/` | Python 时代 CLI 归档，只读 |
| `_shims/` | Python 时代 macOS 兼容 shim，只读 |
| `_research/` | 一次性调研脚本，只读 |
| `vendor/sha` | sha 脚本框架 submodule（`sha.sh` 依赖） |
| `sha.sh` | 本仓命令入口 |

## 依赖主仓（path 依赖）

`dev/package.json` 里：

```json
"@diy-agent/rpc":  "file:../../../diy/pkgs.ts/diy-rpc",
"@diy-agent/time": "file:../../../diy/pkgs.ts/diy-time"
```

- 主仓源码改了、或改了主仓包的构建产物，先回主仓重建：
  ```bash
  cd ../diy && ./sha.sh build-pkgs
  ```
- 然后在 `_diy` 里 `npm install` 让 workspace 链接刷新。
- 主仓包的 `types` 指 `src/`、`main` 指 `lib/`：类型检查读源码，运行时读 `lib/`。
- **zod 必须单实例**：`@diy-agent/rpc` 在加载时给 zod 打补丁（`.cliArg` / `.cliOption`），
  若本仓另装一份 zod，补丁打不到 dev 用的那份 → `.cliArg is not a function`。
  故 `dev` 的 `zod` 声明为 `file:../../../diy/node_modules/zod`（指向主仓那份，Node 按
  realpath 去重）。升级 zod 时改主仓，别在本仓另起一份。

## 命令

```bash
./sha.sh sync     # npm install + submodule 初始化
./sha.sh check    # tsc --noEmit + oxlint
./sha.sh test     # vitest
./sha.sh build    # 构建 dev CLI 到 dev/build/prod/cli
./sha.sh dev ...  # tsx 跑源码（cwd 即作用域）
```

单包命令也可直接进 `dev/` 用 `./sha.sh check|test|build`。

## 硬约束

- **cwd 即作用域**：`dev` 命令在哪个目录跑，就操作哪个目录的 `diy.yaml`；`bin/dev` 刻意不 cd 到包根
- 改 `ref.lock.yaml` 格式前先 `diy facts brief diydev.rule` —— 本仓是它全仓唯一写入方
- 历史文档（`docs/`、`archive/`）描述的是已归档的 Python 实现，**不要照它改现在的代码**
