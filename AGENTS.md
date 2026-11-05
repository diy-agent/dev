# _diy — diy 生态开发辅助仓

**这不是产品，是开发辅助仓。** 放不进主仓、又需要独立演进（或需要独立提交）的开发工具链。
产品代码仍在主 monorepo `../diy`。

## 定位

- 独立 git 仓（与 `../diy` 是两个仓，提交互不影响）
- 通过 **path 依赖**消费主仓的包，不发布、不 vendor
- 当前内容：`pkgs/dev-ref`（ref 能力库）+ `pkgs/dev-core` / `pkgs/dev-page` / `apps/dev`（dev 启动器，##508 从主仓搬来；##510 把 ref 做成它的「外部仓库」页）

## 目录

| 路径 | 说明 |
|------|------|
| `pkgs/dev-ref/` | `@diy-agent/dev-ref`：ref 能力库（add / sync / list / remove）。**##510 起没有 `bin/dev`**：`src/ref/**` 六文件原样被 `pkgs/dev-page` 的「外部仓库」页复用，开发期可 `./sha.sh dev ref …`（tsx 直跑源码） |
| `pkgs/dev-core/` | `@diy-agent/dev-core`：dev 启动器业务层（静态发现 / 运行时对账 / 启停动作），无 UI 无 Electron |
| `pkgs/dev-page/` | `@diy-agent/dev-page`：dev 启动器页面插件，出两页 —— 「应用」（主进程方法表 + 裸 DOM renderer）与「外部仓库」（ref 同步 / 添加 / 移除） |
| `apps/dev/` | `@diy-agent/app-dev`：装配器（插件清单 + 窗口入口 + renderer 打包入口），≤100 行。命令：`./sha.sh build`（只出产物，固定 `build/app/`）、`./sha.sh run <launch> [--slot N]`（lab / staging；数据根 `build/<launch>/<slot>/home`）、`./sha.sh app list|new|stop`（多实例，自动分配槽位）、`./sha.sh -h` 看全部 |
| `docs/` | 历史架构文档（Python 时代，只读参考） |
| `skills/` | 项目级 skills（git-cleanup / win-file-unlock） |
| `archive/` | Python 时代 CLI 归档，只读 |
| `_shims/` | Python 时代 macOS 兼容 shim，只读 |
| `_research/` | 一次性调研脚本，只读 |
| `vendor/sha` | sha 脚本框架 submodule（`sha.sh` 依赖） |
| `sha.sh` | 本仓命令入口 |

## 依赖主仓（path 依赖）

`pkgs/dev-ref/package.json` 里：

```json
"@diy-agent/rpc":  "file:../../../diy/pkgs.ts/diy-rpc",
"@diy-agent/time": "file:../../../diy/pkgs.ts/diy-time"
```

`apps/dev/package.json` / `pkgs/dev-page/package.json` 里：

```json
"@diy-agent/workbench":    "file:../../../diy/pkgs.ts/workbench",
"@diy-agent/workbench-ui": "file:../../../diy/pkgs.ts/ui-workbench"
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
./sha.sh sync       # npm install + submodule 初始化
./sha.sh check      # 逐个 workspace（pkgs/* + apps/*）跑各自的 check
./sha.sh test       # vitest
./sha.sh build      # dev-ref / dev-core / dev-page 编 lib
./sha.sh exec <cmd> # 在每个 workspace 里跑一条命令（如 ./sha.sh exec npx tsc -p tsconfig.json）
./sha.sh dev ...    # tsx 跑源码（cwd 即作用域）
```

单包命令也可直接进目录用 `./sha.sh check|test|build`；dev 启动器：

```bash
cd apps/dev && ./sha.sh lab    # 构建（含依赖包 lib）后起 Electron；lab 变体 CDP 9223
```

## 硬约束

- **cwd 即作用域**：ref 操作哪个目录的 `diy.yaml` 由调用方传 `cwd`（dev app 传仓库根；`./sha.sh dev` 用当前目录）
- 改 `ref.lock.yaml` 格式前先 `diy facts brief diydev.rule` —— 本仓是它全仓唯一写入方
- 历史文档（`docs/`、`archive/`）描述的是已归档的 Python 实现，**不要照它改现在的代码**
