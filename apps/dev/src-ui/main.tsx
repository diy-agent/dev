/**
 * main.tsx —— React 原型的挂载入口（##518 试点）
 *
 * 三件事：
 *   1. 建 store / slots / rpc 桥，装进 `UiContext`；
 *   2. **轮询在 store 外面**：每秒拉一次 snapshot 塞进 store，store 自己按切片去重通知；
 *   3. 注册第一个 Slot 贡献（`detail/runtime`）—— 证明「加一块 UI 不用改 app.tsx」。
 */
import { createRoot } from "react-dom/client";
import type { CommandSession, DevSnapshot, LaunchStatus } from "@diy-agent/dev-core/shared";
import { DEV_METHODS } from "@diy-agent/dev-core/shared";
import { SnapshotStore } from "./store.js";
import { SlotRegistry } from "./slots.js";
import { App, type UiContext } from "./app.js";

interface WorkbenchBridge {
    invoke(pageId: string, method: string, args?: unknown): Promise<unknown>;
}

const bridge = (window as unknown as { workbench?: WorkbenchBridge }).workbench;
if (bridge === undefined) throw new Error("preload 桥没注入 window.workbench");

async function invoke<T>(method: string, args?: unknown): Promise<T> {
    return (await bridge!.invoke("dev", method, args)) as T;
}

const store = new SnapshotStore<DevSnapshot | null>(null);
const slots = new SlotRegistry();
slots.declare("sidebar");
slots.declare("detail");

const ctx: UiContext = { store, slots, invoke };

// ── 第一个 Slot 贡献：运行时卡（证明扩展点能用，且不需要碰 app.tsx） ──────────
slots.register<{ ctx: UiContext; launch: LaunchStatus }>("detail", {
    id: "runtime",
    order: 10,
    render: ({ launch }) => {
        const runtime = launch.runtime;
        if (runtime === null) return <p className="text-[11px] text-on-surface-variant">（未运行）</p>;
        const minutes = Math.floor(runtime.uptimeMs / 60_000);
        return (
            <p className="text-[11px]">
                已运行 {minutes} 分钟 · 常驻 {runtime.memBytes === null ? "-" : `${Math.round(runtime.memBytes / 1024 / 1024)} MB`}
            </p>
        );
    },
});

// ── 轮询：主进程给什么就推什么；store 负责「没变就不通知」 ─────────────────
async function tick(): Promise<void> {
    try {
        store.set(await invoke<DevSnapshot>(DEV_METHODS.snapshot));
    } catch (error) {
        console.error("[ui] 取快照失败", error);
    }
}
void tick();
setInterval(() => void tick(), 1000);

// ── 选中态是 UI 态：留在 React 侧，不进 store ───────────────────────────────
let selected: LaunchStatus | null = null;
const container = document.getElementById("root");
if (container === null) throw new Error("index-react.html 缺 #root");
const root = createRoot(container);

function render(): void {
    root.render(
        <App
            ctx={ctx}
            selected={selected}
            onSelect={(launch) => {
                selected = launch;
                render();
            }}
        />,
    );
}
render();

// 会话（启动日志）也走同一条路：原型只把最后一行显示在状态栏，验证命令通道可用
setInterval(() => {
    void invoke<CommandSession | null>(DEV_METHODS.session).then((session) => {
        if (session === null) return;
        const bar = document.getElementById("ui-status");
        if (bar !== null) bar.textContent = session.lines.at(-1) ?? "";
    });
}, 1000);
