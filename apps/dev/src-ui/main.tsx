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
/** 命令输出（启动日志 / build 输出共用一条会话）—— 与快照分开：刷新节奏不同、变化来源不同 */
const session = new SnapshotStore<CommandSession | null>(null);
const slots = new SlotRegistry();
slots.declare("sidebar");
slots.declare("detail");

const ctx: UiContext = { store, session, slots, invoke };

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
        const [snap, sess] = await Promise.all([
            invoke<DevSnapshot>(DEV_METHODS.snapshot),
            invoke<CommandSession | null>(DEV_METHODS.session),
        ]);
        store.set(snap);
        // 会话按「行数 + running」判等：内容没长就不必惊动订阅者
        session.set(sess, (a, b) =>
            a === b ||
            (a !== null &&
                b !== null &&
                a.id === b.id &&
                a.running === b.running &&
                a.lines.length === b.lines.length),
        );
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

// 状态栏：只显示会话最后一行（不参与主界面重绘）
setInterval(() => {
    const bar = document.getElementById("ui-status");
    if (bar === null) return;
    const lines = ctx.session.read((s) => s?.lines ?? []);
    bar.textContent = lines.at(-1) ?? "";
}, 500);
