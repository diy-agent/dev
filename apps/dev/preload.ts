// preload.ts — 唯一一座桥（2026-11-05 B2 起底部通道换成 @diy-agent/rpc）。
//
// 两条通道各管一摊，互不干扰：
//   · `workbench-rpc`：外壳自己的桥（页面清单 / page:invoke / 意图测试命令）——
//     由 `@diy-agent/workbench/preload` 的 createPreloadBridge 装配，别再手写 ipcRenderer 调
//     （B1 把旧的两个 IPC 常量换成了 rpc，手写 `page:invoke` 会撞 No handler registered）。
//   · `dev-fs-rpc`：dev 自己的文件能力（fs.list/read/write），主进程侧 bindFsHandlers 绑这条。

import { contextBridge } from "electron";
import { createRendererTransport } from "@diy-agent/rpc/electron/renderer";
import { RPC_CHANNEL } from "@diy-agent/workbench";
import { createPreloadBridge } from "@diy-agent/workbench/preload";

const workbench = createPreloadBridge(createRendererTransport(RPC_CHANNEL));
contextBridge.exposeInMainWorld("workbench", workbench.bridge);

const FS_CHANNEL = "dev-fs-rpc";
contextBridge.exposeInMainWorld("transport", createRendererTransport(FS_CHANNEL));
