// main.ts — Electron 主进程入口（dev 启动器的装配入口）。
//
// 只做装配：窗口 / IPC / 插件由外壳（@diy-agent/workbench）负责，本文件只交清单。
// 窗口落点与「启动不抢焦点」也由外壳按环境变量统一处理（dev 环境自动开在副屏）。

import { app } from "electron";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { cdpSwitchValue, createWorkbench, readDevToolsPort } from "@diy-agent/workbench";
import { ChannelServerBinding, type EnvelopeTransport } from "@diy-agent/rpc";
import { bindFsHandlers } from "@diy-agent/dev-fs";
import { ipcMain } from "electron";
import { ASSEMBLY } from "./index.js";

// lab 变体开 CDP。**端口不再写死**（##518）：写死 9223 时，第二个 dev 实例会
// `bind() failed: Address already in use`，CDP 静默不可用（实例照常注册，人以为能 attach）。
// 现在与 diy-app 同构：缺省 `0`（Chromium 自己挑空闲端口），实际端口从
// `<userData>/DevToolsActivePort` 读（口径收在 @diy-agent/workbench 的 cdp.ts）。
// 必须在 app ready 之前 append。
const cdpFromArgv = process.argv.some((arg) => arg.startsWith("--remote-debugging-port"));
if (process.env["DIY_VARIANT"] === "lab" && !cdpFromArgv) {
    app.commandLine.appendSwitch("remote-debugging-port", cdpSwitchValue());
}

const here = dirname(fileURLToPath(import.meta.url)); // build/<variant>/main

// ⚠️ 不要用顶层 await（Electron 的 ESM 入口里会让 app ready 永不触发，见 apps/chat 的同一条注释）
app.whenReady().then(() => {
    // Chromium 异步写 DevToolsActivePort：轮询几次再打，避免日志里出现空地址
    void (async () => {
        const { waitDevToolsPort } = await import("@diy-agent/workbench");
        const port = await waitDevToolsPort(app.getPath("userData"));
        console.log(port === null ? "[dev] CDP 未启用" : `[dev] CDP ws://127.0.0.1:${String(port)}/devtools/browser (实际端口见 DevToolsActivePort)`);
    })();
});

createWorkbench({
    title: ASSEMBLY.title,
    // 实例注册表里的 app 短名：它自己也该出现在「谁活着」里
    app: "diy-dev",
    // launch = app.yaml 里那条启动命令（dev 启动器拉起的会注入 DIY_LAUNCH）；
    // 手工 `./sha.sh lab` 没有这个变量 ⇒ 缺省 lab，否则注册表里 launch=null，启动器永远显示「未启动」
    launch: process.env["DIY_LAUNCH"] ?? "lab",
    plugins: ASSEMBLY.plugins,
    preloadFile: join(here, "../preload/index.cjs"),
    // ##518：界面已切到 React（`src-ui/`）；老的手写 DOM 入口连同 dev-page 的 renderer 一起删了。
    rendererFile: join(here, "..", "renderer", "index.html"),
    width: 1180,
    height: 820,
})
    .then((workbench) => {
        // 文件能力（##518）：@diy-agent/rpc 的 electron 传输 —— preload 递出 transport，
        // 这里把 dev-fs 的三个方法绑上去。页面方法表（page:invoke）不受影响，两者并存。
        // main 侧 transport 自己写（不用 @diy-agent/rpc/electron）：那个模块顶层同时 import 了
        // ipcRenderer，而主进程的 electron 没有这个导出 ⇒ 加载即 SyntaxError。
        // 语义与它一致：同名 channel、webContents.send 下行、ipcMain.on 上行、窗口销毁即 onClose。
        const FS_CHANNEL = "dev-fs-rpc";
        const mainTransport: EnvelopeTransport = (() => {
            const handlers = new Set<(msg: unknown) => void>();
            const close = new Set<() => void>();
            ipcMain.on(FS_CHANNEL, (_event, payload: unknown) => {
                for (const handler of handlers) handler(payload);
            });
            const contents = () => workbench.window()?.webContents;
            contents()?.on("destroyed", () => {
                for (const cb of close) cb();
            });
            return {
                send: (payload: unknown) => {
                    try {
                        contents()?.send(FS_CHANNEL, payload);
                    } catch {
                        for (const cb of close) cb();
                    }
                },
                on: (handler: (msg: never) => void) => {
                    handlers.add(handler as (msg: unknown) => void);
                    return () => handlers.delete(handler as (msg: unknown) => void);
                },
                onClose: (cb: () => void) => {
                    close.add(cb);
                    return () => close.delete(cb);
                },
            };
        })();
        const binding = new ChannelServerBinding(mainTransport);
        bindFsHandlers(binding);
        app.once("will-quit", () => binding.destroy());
        app.on("window-all-closed", () => {
            workbench.dispose();
            app.quit();
        });
    })
    .catch((cause: unknown) => {
        console.error("✗ 工作台启动失败：", cause);
        app.exit(1);
    });
