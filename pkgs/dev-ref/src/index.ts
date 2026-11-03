// src/index.ts — 包入口：给宿主（dev app）用的能力面（##510 删 bin/dev 后新增）。
//
// 只导出「能力」，不导出 CLI 入口（`src/cli/index.ts` 有顶层 main()，import 即执行）。
// 宿主拿 refApi + bindRefHandlers 自建进程内 mem transport 调用（同 CLI 的机制）：
//
//   const { serverTx, clientTx } = createMemTransportPair();
//   bindRefHandlers(new ChannelServerBinding(serverTx), { home, cwd });
//   const ref = createTypedClient(new ChannelClientBinding(clientTx), refApi).ref;
//
// 为什么走 RPC 而不是直接调函数：ref/ 六个文件是「handler + schema」形态，一行不改地复用，
// 才保证 UI 与旧 CLI 走的是同一份编排（##510 判据 3）。

export { refApi, RefEntrySchema } from "./ref/api.js";
export type { RefEntry } from "./ref/api.js";
export { bindRefHandlers } from "./ref/impl.js";
export type { RefRuntime } from "./ref/impl.js";
export { readRuntimeConfig } from "./runtime.js";
export type { RuntimeConfig } from "./runtime.js";
