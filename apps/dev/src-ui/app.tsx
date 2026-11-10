/**
 * app.tsx —— dev 的 **React 原型**（##518 试点：React 19 + 无框架 store + Slot 注册表 + M3 令牌）
 *
 * 这一版只做「左侧 worktree/launch 树 + 右侧详情」两块，用来验证四件事：
 *   1. React 只做投影：数据从 `store.ts` 来，组件不写订阅（订阅在 `useSlice` 一处）；
 *   2. 扩展点用 `slots.ts` 的注册表（`sidebar` / `detail`），不再往主文件里加 switch；
 *   3. 视觉真源是 **M3 令牌**：颜色全部走 `--md-sys-color-*` 的语义类，没有硬编码色值；
 *   4. 交互（启动/停止）直接打 rpc，不经过 DOM 里挖按钮。
 *
 * ⚠️ 这是**并行原型**：老的 `renderer.ts` 仍是默认界面，等原型对齐后再切。
 */
import { useCallback, useSyncExternalStore, type MouseEvent as ReactMouseEvent, type ReactNode } from "react";
import type { DevSnapshot, LaunchStatus } from "@diy-agent/dev-core/shared";
import type { SnapshotStore } from "./store.js";
import type { SlotRegistry } from "./slots.js";

export interface UiContext {
    readonly store: SnapshotStore<DevSnapshot | null>;
    readonly slots: SlotRegistry;
    readonly invoke: <T>(method: string, args?: unknown) => Promise<T>;
}

/** 唯一的 React ↔ store 桥：组件只选自己关心的切片，浅相等时不重渲染 */
function useSlice<T>(ctx: UiContext, selector: (s: DevSnapshot | null) => T): T {
    const subscribe = useCallback(
        (onChange: () => void) => ctx.store.subscribe(selector, onChange),
        // selector 由调用方保证稳定（模块级函数或 useMemo 包过）
        [ctx, selector],
    );
    const getSnapshot = useCallback(() => ctx.store.read(selector), [ctx, selector]);
    return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}

const selectSnapshot = (s: DevSnapshot | null): DevSnapshot | null => s;

/** worktree → 该工作区下的 launch（保持快照里的顺序；同 app 相邻） */
function groupByWorktree(launches: readonly LaunchStatus[]): Map<string, LaunchStatus[]> {
    const out = new Map<string, LaunchStatus[]>();
    for (const launch of launches) {
        const list = out.get(launch.worktree);
        if (list === undefined) out.set(launch.worktree, [launch]);
        else list.push(launch);
    }
    return out;
}

function LaunchChip(props: { ctx: UiContext; launch: LaunchStatus; selected: boolean; onSelect: () => void }) {
    const { launch } = props;
    const state = launch.starting ? "启动中" : launch.running ? "运行中" : "未启动";
    const onClick = (event: ReactMouseEvent): void => {
        event.stopPropagation();
        if (launch.starting) return;
        if (launch.running) void props.ctx.invoke("stop", { worktree: launch.worktree, app: launch.app, launch: launch.launch });
        else void props.ctx.invoke("start", { worktree: launch.worktree, app: launch.app, launch: launch.launch });
    };
    const ring = launch.running
        ? "bg-primary-container text-on-primary-container"
        : "bg-transparent text-on-surface-variant";
    return (
        <button
            type="button"
            onClick={onClick}
            onFocus={props.onSelect}
            title={`${launch.command}\n${state}${launch.running ? " · 点击停止" : " · 点击启动"}`}
            className={`rounded-md border border-outline px-2 py-0.5 text-[11px] ${ring} ${
                props.selected ? "outline outline-2 outline-primary" : ""
            }`}
        >
            <span className={`mr-1 inline-block h-1.5 w-1.5 rounded-full ${launch.running ? "bg-primary" : launch.starting ? "bg-on-surface-variant animate-pulse" : "bg-outline"}`} />
            {launch.launch}
            {launch.instances.length > 1 ? <span className="ml-1 opacity-70">×{launch.instances.length}</span> : null}
        </button>
    );
}

function Sidebar(props: { ctx: UiContext; selectedKey: string | null; onSelect: (launch: LaunchStatus | null) => void }) {
    const snapshot = useSlice(props.ctx, selectSnapshot);
    if (snapshot === null) return <div className="p-3 text-on-surface-variant">正在读取快照…</div>;
    const groups = groupByWorktree(snapshot.launches);
    return (
        <div className="flex h-full flex-col gap-2 overflow-auto p-2">
            {[...groups].map(([worktree, launches]) => {
                const running = snapshot.worktreeInstances[worktree] ?? [];
                return (
                    <section key={worktree} className="rounded-lg border border-outline bg-surface-low p-2">
                        <header className="mb-1 flex items-baseline gap-2">
                            <span className="truncate font-medium">{launches[0]?.worktreePath ?? worktree}</span>
                            <span className="shrink-0 text-[10px] text-on-surface-variant">{launches[0]?.branch ?? ""}</span>
                        </header>
                        <div className="flex flex-wrap gap-1">
                            {launches.map((launch) => (
                                <LaunchChip
                                    key={launch.key}
                                    ctx={props.ctx}
                                    launch={launch}
                                    selected={props.selectedKey === launch.key}
                                    onSelect={() => props.onSelect(launch)}
                                />
                            ))}
                        </div>
                        {running.length > 0 ? (
                            <div className="mt-1 flex flex-wrap gap-1 text-[10px] text-on-surface-variant">
                                {running.map((inst) => (
                                    <span key={inst.pid} className="rounded bg-surface-high px-1 py-0.5" title={`${inst.diyHome}\npid ${inst.pid}`}>
                                        {inst.displayName}
                                    </span>
                                ))}
                            </div>
                        ) : null}
                    </section>
                );
            })}
        </div>
    );
}

function Detail(props: { ctx: UiContext; launch: LaunchStatus | null }) {
    const { launch } = props;
    if (launch === null) return <div className="p-3 text-on-surface-variant">选一个 launch 看详情</div>;
    const rows: readonly (readonly [string, string])[] = [
        ["命令", launch.command],
        ["数据根", launch.home],
        ["工作区", launch.worktree],
        ["状态", launch.running ? "运行中" : launch.starting ? "启动中" : "未启动"],
        ["端口", launch.runtime?.port === null || launch.runtime === null ? "-" : String(launch.runtime.port)],
        ["PID", launch.runtime === null ? "-" : String(launch.runtime.pid)],
    ];
    return (
        <div className="flex h-full flex-col gap-2 overflow-auto p-3">
            <h1 className="text-[14px] font-medium">
                {launch.app}.{launch.launch}
            </h1>
            <div className="grid grid-cols-[72px_1fr] gap-x-3 gap-y-1 text-[11px]">
                {rows.map(([k, v]) => (
                    <Fragment2 key={k} label={k} value={v} />
                ))}
            </div>
            {launch.configIssues.length > 0 ? (
                <div className="rounded-md border border-error p-2 text-[11px] text-error">
                    {launch.configIssues.map((issue) => (
                        <div key={issue.code}>{issue.message}</div>
                    ))}
                </div>
            ) : null}
            {props.ctx.slots.contributions<{ ctx: UiContext; launch: LaunchStatus }>("detail").map((c) => (
                <div key={c.id}>{c.render({ ctx: props.ctx, launch }) as ReactNode}</div>
            ))}
        </div>
    );
}

function Fragment2(props: { label: string; value: string }) {
    return (
        <>
            <span className="text-on-surface-variant">{props.label}</span>
            <span className="break-all font-mono">{props.value}</span>
        </>
    );
}

export interface AppProps {
    readonly ctx: UiContext;
    /** 选中态由宿主持有（不进 store：它是 UI 态，不是业务数据） */
    readonly selected: LaunchStatus | null;
    readonly onSelect: (launch: LaunchStatus | null) => void;
}

export function App(props: AppProps) {
    return (
        <div className="grid h-full grid-cols-[minmax(260px,340px)_1fr]">
            <aside className="border-r border-outline">
                <Sidebar ctx={props.ctx} selectedKey={props.selected?.key ?? null} onSelect={props.onSelect} />
            </aside>
            <main className="min-w-0">
                <Detail ctx={props.ctx} launch={props.selected} />
            </main>
        </div>
    );
}
