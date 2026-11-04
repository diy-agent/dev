// preload.ts — 唯一一座桥：把外壳的两个通道包成 window.workbench。
//
// contextIsolation + sandbox 打开时 renderer 拿不到 Node，只能走这里。
// 通道名来自 @diy-agent/workbench/channels（与主进程同一份常量，别手写字符串）。

import { contextBridge, ipcRenderer } from "electron";
import { createRendererTransport } from "@diy-agent/rpc/electron";
import {
    PAGE_INVOKE_CHANNEL,
    PAGE_LIST_CHANNEL,
    type PageInvokeRequest,
    type WorkbenchBridge,
} from "@diy-agent/workbench/channels";

const bridge: WorkbenchBridge = {
    listPages: () => ipcRenderer.invoke(PAGE_LIST_CHANNEL),
    invoke: (pageId, method, args) => {
        const request: PageInvokeRequest = { pageId, method, args };
        return ipcRenderer.invoke(PAGE_INVOKE_CHANNEL, request);
    },
};

contextBridge.exposeInMainWorld("workbench", bridge);

// ── rpc 通道（##518）──
// 文件读写走 @diy-agent/rpc 的 electron 传输：preload 只把 EnvelopeTransport 递出去，
// renderer 用 ChannelClientBinding + createTypedClient 就能拿到带 zod 校验的类型化方法。
// 与 workbench 的 page:invoke 并存：页面方法表管「页面行为」，rpc 管「独立的能力域」。
const transport = createRendererTransport();
contextBridge.exposeInMainWorld("transport", transport);
