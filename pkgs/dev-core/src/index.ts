// index.ts — dev 启动器的业务层（##508 从主仓 apps/dev 搬来，纯搬运）。
//
// 三层分工，全部无 UI、无 Electron：
//   · shared.ts    —— 主进程与 renderer 共用的纯类型 + 协议常量
//   · discovery.ts —— 静态清单：`git worktree list` × `apps/*/app.yaml`（不读注册表）
//   · instances.ts —— 动态状态：注册表 `~/.diy-instances/*.json` 按 `(worktree, app, launch)` 对账
//   · actions.ts   —— 动作：启停 / 唤出 / 打开路径 / 跑白名单命令
//
// 包外只认这一个入口（装配器与 renderer 都从 `@diy-agent/dev-core` 取）。

export * from "./shared.js";
export * from "./discovery.js";
export * from "./instances.js";
export * from "./actions.js";
