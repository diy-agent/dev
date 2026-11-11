/**
 * main.tsx —— React 原型的挂载入口（##518 试点）
 *
 * 三件事：
 *   1. 建 store / slots / rpc 桥，装进 `UiContext`；
 *   2. **轮询在 store 外面**：每秒拉一次 snapshot 塞进 store，store 自己按切片去重通知；
 *   3. 注册第一个 Slot 贡献（`detail/runtime`）—— 证明「加一块 UI 不用改 app.tsx」。
 */
import { useCallback, useState } from "react";
import { createRoot } from "react-dom/client";
import type { CommandSession, DevSnapshot, LaunchStatus } from "@diy-agent/dev-core/shared";
import { createDevClient, type PageBridge } from "./client.js";
import { SnapshotStore } from "./store.js";
import { SlotRegistry } from "./slots.js";
import { App, useStoreSlice, type UiContext, type Selection } from "./app.js";
import { StatusBar, TitleBar, useNotices, type PageInfo } from "./chrome.js";
import { FilesViewPage } from "./worktrees.js";

interface WorkbenchBridge extends PageBridge {
    listPages(): Promise<PageInfo[]>;
}

const bridge = (window as unknown as { workbench?: WorkbenchBridge }).workbench;
if (bridge === undefined) throw new Error("preload 桥没注入 window.workbench");
/** 领域式客户端：方法名与入参形状全收在 `client.ts`，组件只谈业务语义 */
const client = createDevClient(bridge as PageBridge, "dev");

const store = new SnapshotStore<DevSnapshot | null>(null);
/** 命令输出（启动日志 / build 输出共用一条会话）—— 与快照分开：刷新节奏不同、变化来源不同 */
const session = new SnapshotStore<CommandSession | null>(null);
const slots = new SlotRegistry();
slots.declare("sidebar");
slots.declare("detail");

const ctx: UiContext = { store, session, slots, client };

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
        const [snap, sess] = await Promise.all([client.snapshot(), client.session()]);
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

// ── 选中态与 toast 都是 UI 态：留在 React 侧，不进 store（它们不是业务数据） ──────
let selection: Selection = null;
let toastText = "";
let toastTimer: ReturnType<typeof setTimeout> | null = null;

const container = document.getElementById("root");
if (container === null) throw new Error("index.html 缺 #root");
const root = createRoot(container);

const selectSnapshotAll = (s: DevSnapshot | null): DevSnapshot | null => s;
const selectSessionAll = (s: CommandSession | null): CommandSession | null => s;

function Shell(props: { bridge: WorkbenchBridge }) {
    // ⚠️ hook 必须在组件里：之前把这行写在模块顶层，React 直接报 dispatcher 为 null（白屏）
    const notices = useNotices();
    // 页面导航（##518）：目前是 dev-ui 自己的两个页面。
    // workbench 的 `page.list` 也接得上（多插件页时直接并进来），但单个插件内多页
    // 由插件自己管更直接 —— 外部仓库页将来若独立成插件，这里会自动多一项。
    const pages: readonly PageInfo[] = [
        { id: "app", title: "应用" },
        { id: "files", title: "文件" },
    ];
    const [active, setActive] = useState("app");
    // 稳定选择器（模块级常量）：内联箭头函数每次渲染都是新引用 ⇒ 订阅反复重建
    const snapshot = useStoreSlice(ctx.store, selectSnapshotAll);
    const session = useStoreSlice(ctx.session, selectSessionAll);
    return (
        <div className="flex h-full flex-col">
            <TitleBar
                pages={pages.length === 0 ? [{ id: "dev", title: "应用" }] : pages}
                active={active}
                onPick={setActive}
                instanceName={snapshot === null ? "" : `${snapshot.repoName} · ${String(snapshot.runningCount)} 在跑`}
                notices={notices.notices}
                onClearNotices={notices.clear}
            />
            <div className="min-h-0 flex-1">
                {active === "files" ? (
                    <FilesViewPage ctx={ctx} onOpenWorktree={(path) => {
                        selection = { kind: "worktree", path };
                        setActive("app");
                        render();
                    }} />
                ) : (
                <App
                    ctx={ctx}
                    selection={selection}
                    onSelect={(sel) => {
                        selection = sel;
                        render();
                    }}
                    notify={(text) => {
                        notices.push(text);
                        toastText = text;
                        render();
                        if (toastTimer !== null) clearTimeout(toastTimer);
                        toastTimer = setTimeout(() => {
                            toastText = "";
                            render();
                        }, 4000);
                    }}
                />
                )}
            </div>
            <StatusBar
                running={snapshot?.runningCount ?? 0}
                total={snapshot?.launches.length ?? 0}
                externals={snapshot?.externals.length ?? 0}
                sessionRunning={session?.running ?? false}
                lastLine={session?.lines.at(-1) ?? ""}
            />
        </div>
    );
}

function render(): void {
    root.render(<Shell bridge={bridge as WorkbenchBridge} />);
}
render();

