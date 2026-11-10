/**
 * app.tsx —— dev 启动器的界面（##518：React 19 + 无框架 store + Slot 注册表 + M3 令牌）
 *
 * 分工（照 dsh 的 store/ui-slots/ui-renderer）：
 *   · 数据：`store.ts`（快照）与 `session`（命令输出）—— 组件不写订阅，只用 `useStoreSlice` 取切片；
 *   · 扩展点：`slots.ts` 的注册表（`detail` 已有一个 `runtime` 贡献作示范）；
 *   · 本文件只做**投影**：布局 + 交互 + 展示规则。
 *
 * 功能对齐基准是老的手写 DOM 版 `dev-page/src/renderer.ts`（已删，见 git 历史）；缺口清单在
 * `diy/docs/plans/2026-11-10-dev-ui-gap.md`。本文件覆盖那一版的 P0 部分。
 */
import { useCallback, useState, useSyncExternalStore, type MouseEvent as ReactMouseEvent, type ReactNode } from "react";
import {
    BUILD_COMMANDS,
    DEV_METHODS,
    type BuildCommand,
    type CommandSession,
    type DevSnapshot,
    type ExternalInstance,
    type LaunchRef,
    type LaunchStatus,
} from "@diy-agent/dev-core/shared";
import type { SnapshotStore } from "./store.js";
import type { SlotRegistry } from "./slots.js";
import { FilesPane } from "./files.js";
import { RefPane } from "./ref.js";

export interface UiContext {
    readonly store: SnapshotStore<DevSnapshot | null>;
    /** 命令输出（启动日志 / build 输出共用一条会话，与主进程 DevRunner 同口径） */
    readonly session: SnapshotStore<CommandSession | null>;
    readonly slots: SlotRegistry;
    readonly invoke: <T>(method: string, args?: unknown) => Promise<T>;
}

/** 唯一的 React ↔ store 桥（对任意 `SnapshotStore` 通用） */
function useStoreSlice<T, S>(store: SnapshotStore<T>, selector: (s: T) => S): S {
    const subscribe = useCallback((onChange: () => void) => store.subscribe(selector, onChange), [store, selector]);
    const getSnapshot = useCallback(() => store.read(selector), [store, selector]);
    return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}

function useSlice<T>(ctx: UiContext, selector: (s: DevSnapshot | null) => T): T {
    return useStoreSlice(ctx.store, selector);
}

const selectSnapshot = (s: DevSnapshot | null): DevSnapshot | null => s;

/** ⚠️ 空数组必须是**同一个常量**：`?? []` 每次都新建 ⇒ useSyncExternalStore 认为快照变了
 *  → 无限重渲染（React error #185，实测踩到过）。 */
const EMPTY_LINES: readonly string[] = [];
const selectSessionLines = (s: CommandSession | null): readonly string[] => s?.lines ?? EMPTY_LINES;
const selectSessionKey = (s: CommandSession | null): string =>
    s === null ? "" : `${String(s.id)}:${String(s.lines.length)}:${s.running ? "1" : "0"}`;

/** 选中态：一条 launch 或一个外部实例（UI 态，不进 store） */
export type Selection =
    | { readonly kind: "launch"; readonly launch: LaunchStatus }
    | { readonly kind: "external"; readonly pid: number }
    | null;

function refOf(launch: LaunchStatus): LaunchRef {
    return { worktree: launch.worktree, app: launch.app, launch: launch.launch };
}

function groupByWorktree(launches: readonly LaunchStatus[]): Map<string, LaunchStatus[]> {
    const out = new Map<string, LaunchStatus[]>();
    for (const launch of launches) {
        const list = out.get(launch.worktree);
        if (list === undefined) out.set(launch.worktree, [launch]);
        else list.push(launch);
    }
    return out;
}

const BTN = "rounded-md border border-outline px-2 py-[1px] text-[11px] hover:bg-surface-high disabled:opacity-40";
const DANGER = `${BTN} border-error/60 text-error hover:bg-error/10`;

// ── 侧栏 ────────────────────────────────────────────────────────────

function LaunchChip(props: { launch: LaunchStatus; selected: boolean; onSelect: () => void }) {
    const { launch } = props;
    const state = launch.starting ? "启动中" : launch.running ? "运行中" : "未启动";
    // 点 chip **只选中**（右侧看详情/日志），启停交给详情里的显式按钮 ——
    // chip 就在正在跑的那一行上，点错一下就把它停了（实测踩到过，包括 dev 自己）。
    const onClick = (event: ReactMouseEvent): void => {
        event.stopPropagation();
        props.onSelect();
    };
    const look = launch.running ? "bg-primary-container text-on-primary-container" : "bg-transparent text-on-surface-variant";
    return (
        <button
            type="button"
            onClick={onClick}
            title={`${launch.command}\n${state}`}
            className={`rounded-md border border-outline px-2 py-0.5 text-[11px] ${look} ${
                props.selected ? "outline outline-2 outline-primary" : ""
            }`}
        >
            <span
                className={`mr-1 inline-block h-1.5 w-1.5 rounded-full ${
                    launch.running ? "bg-primary" : launch.starting ? "bg-on-surface-variant animate-pulse" : "bg-outline"
                }`}
            />
            {launch.launch}
            {launch.instances.length > 1 ? <span className="ml-1 opacity-70">×{launch.instances.length}</span> : null}
        </button>
    );
}

function Sidebar(props: { ctx: UiContext; selection: Selection; onSelect: (sel: Selection) => void }) {
    const snapshot = useSlice(props.ctx, selectSnapshot);
    if (snapshot === null) return <div className="p-3 text-on-surface-variant">正在读取快照…</div>;
    const groups = groupByWorktree(snapshot.launches);
    return (
        <div className="flex h-full flex-col gap-2 overflow-auto p-2">
            <div className="text-[10px] text-on-surface-variant">
                {snapshot.runningCount} 个 launch 在跑 · {snapshot.launches.length} 条 · {snapshot.worktreeCount} 个 worktree
            </div>
            {[...groups].map(([worktree, launches]) => {
                const running = snapshot.worktreeInstances[worktree] ?? [];
                return (
                    <section key={worktree} className="rounded-lg border border-outline bg-surface-low p-2">
                        <header className="mb-1 flex items-baseline gap-2">
                            <span className="truncate font-medium">{launches[0]?.worktreePath ?? worktree}</span>
                            <span className="shrink-0 text-[10px] text-on-surface-variant">{launches[0]?.branch ?? ""}</span>
                            {launches[0]?.built === false ? <span className="shrink-0 text-[10px] text-error">未构建</span> : null}
                        </header>
                        <div className="flex flex-wrap gap-1">
                            {launches.map((launch) => (
                                <LaunchChip
                                    key={launch.key}
                                    launch={launch}
                                    selected={props.selection?.kind === "launch" && props.selection.launch.key === launch.key}
                                    onSelect={() => props.onSelect({ kind: "launch", launch })}
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
            {snapshot.externals.length > 0 ? (
                <section className="rounded-lg border border-outline bg-surface-low p-2">
                    <header className="mb-1 text-[10px] text-on-surface-variant">外部实例（不属于任何 worktree 的 launch · 只读）</header>
                    <div className="flex flex-col gap-0.5">
                        {snapshot.externals.map((item) => (
                            <button
                                key={item.pid}
                                type="button"
                                onClick={() => props.onSelect({ kind: "external", pid: item.pid })}
                                className={`flex items-baseline gap-2 rounded px-1 py-0.5 text-left text-[11px] hover:bg-surface-high ${
                                    props.selection?.kind === "external" && props.selection.pid === item.pid ? "bg-primary-container text-on-primary-container" : ""
                                }`}
                            >
                                <span className="font-mono">{item.pid}</span>
                                <span className="truncate">{item.app ?? "?"}</span>
                                {item.production ? <span className="shrink-0 text-[10px] text-error">生产</span> : null}
                                <span className="ml-auto shrink-0 truncate text-[10px] text-on-surface-variant">{item.diyHome}</span>
                            </button>
                        ))}
                    </div>
                </section>
            ) : null}
        </div>
    );
}

// ── 详情：卡与动作 ──────────────────────────────────────────────────

function Card(props: { title: string; right?: ReactNode; children: ReactNode }) {
    return (
        <section className="rounded-lg border border-outline bg-surface-low p-2">
            <header className="mb-1 flex items-baseline gap-2">
                <h2 className="text-[11px] font-medium text-on-surface-variant">{props.title}</h2>
                {props.right === undefined ? null : <span className="ml-auto text-[10px] text-on-surface-variant">{props.right}</span>}
            </header>
            {props.children}
        </section>
    );
}

function KV(props: { label: string; value: ReactNode }) {
    return (
        <div className="grid grid-cols-[72px_1fr] gap-x-3 text-[11px]">
            <span className="text-on-surface-variant">{props.label}</span>
            <span className="break-all">{props.value}</span>
        </div>
    );
}

function formatUptime(ms: number): string {
    const total = Math.floor(ms / 1000);
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    return h > 0 ? `${String(h)}h${String(m)}m` : m > 0 ? `${String(m)}m${String(s)}s` : `${String(s)}s`;
}

function formatBytes(bytes: number | null): string {
    if (bytes === null) return "-";
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatStartedAt(iso: string | null): string {
    if (iso === null) return "-";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "-";
    const p = (n: number) => String(n).padStart(2, "0");
    return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

type OpenWhich = "app" | "worktree" | "home" | "yaml";
type OpenMode = "finder" | "editor" | "terminal";

function ActionBar(props: { ctx: UiContext; launch: LaunchStatus; notify: (text: string) => void }) {
    const { ctx, launch, notify } = props;
    const ref = refOf(launch);
    const call = (method: string, args?: unknown) => (): void => {
        void ctx.invoke<{ ok?: boolean; reason?: string }>(method, args ?? ref)
            .then((res) => {
                if (res?.ok === false) notify(res.reason ?? "操作失败");
            })
            .catch((e: unknown) => notify(e instanceof Error ? e.message : String(e)));
    };
    const restart = (): void => {
        void ctx
            .invoke(DEV_METHODS.stop, ref)
            .then(() => ctx.invoke(DEV_METHODS.start, ref))
            .then(() => notify("已重启"))
            .catch((e: unknown) => notify(`重启失败：${e instanceof Error ? e.message : String(e)}`));
    };
    const copyPid = (): void => {
        const pid = launch.runtime?.pid;
        if (pid === undefined) return;
        void navigator.clipboard.writeText(String(pid)).then(() => notify(`PID 已复制：${String(pid)}`));
    };
    const open = (which: OpenWhich, mode: OpenMode) => () => {
        void ctx
            .invoke<{ ok: boolean; reason: string }>(DEV_METHODS.open, { ...ref, which, mode })
            .then((res) => notify(res.ok ? `已打开：${res.reason}` : `打开失败：${res.reason}`))
            .catch((e: unknown) => notify(`打开失败：${e instanceof Error ? e.message : String(e)}`));
    };
    return (
        <div className="flex flex-wrap items-center gap-1">
            {launch.running ? (
                <>
                    <button type="button" className={BTN} onClick={call(DEV_METHODS.focus)}>
                        聚焦窗口
                    </button>
                    <button type="button" className={BTN} onClick={restart}>
                        重启
                    </button>
                    <button
                        type="button"
                        className={BTN}
                        onClick={() => {
                            void ctx
                                .invoke<{ ok: boolean; reason: string }>(DEV_METHODS.revealCdp, ref)
                                .then((res) => notify(res.ok ? `已打开：${res.reason}` : `打不开 CDP：${res.reason}`));
                        }}
                    >
                        打开 CDP
                    </button>
                    <button type="button" className={DANGER} onClick={call(DEV_METHODS.stop)}>
                        停止
                    </button>
                </>
            ) : (
                <button type="button" className={BTN} disabled={launch.starting} onClick={call(DEV_METHODS.start)}>
                    {launch.starting ? "启动中…" : "启动"}
                </button>
            )}
            <span className="mx-1 h-4 w-px bg-outline" />
            <button type="button" className={BTN} onClick={open("app", "editor")}>
                打开代码
            </button>
            <button type="button" className={BTN} onClick={open("home", "finder")}>
                打开数据根
            </button>
            <button type="button" className={BTN} onClick={open("worktree", "terminal")}>
                终端
            </button>
            <button type="button" className={BTN} disabled={launch.runtime === null} onClick={copyPid}>
                复制 PID
            </button>
        </div>
    );
}

function EntriesCard(props: { launch: LaunchStatus; onOpenUrl: (url: string) => void }) {
    const { launch } = props;
    if (launch.entries.length === 0) return null;
    return (
        <Card title="入口">
            <div className="flex flex-col gap-1">
                {launch.entries.map((entry, index) => (
                    <div key={`${entry.kind}-${String(index)}`} className="text-[11px]">
                        <span className="text-on-surface-variant">{entry.title ?? entry.kind}</span>
                        {entry.href === null ? (
                            <span className="ml-2">（未就绪）</span>
                        ) : (
                            <button type="button" className="ml-2 underline" onClick={() => props.onOpenUrl(entry.href!)}>
                                {entry.href}
                            </button>
                        )}
                        {entry.portMismatch && entry.configuredUrl !== null ? (
                            <span className="ml-2 text-[10px] text-error">配置写的是 {entry.configuredUrl}</span>
                        ) : null}
                    </div>
                ))}
            </div>
        </Card>
    );
}

function InstancesCard(props: { launch: LaunchStatus }) {
    const { launch } = props;
    if (launch.instances.length <= 1) return null;
    return (
        <Card title="在跑的实例" right={`${String(launch.instances.length)} 份`}>
            <div className="flex flex-col gap-0.5 text-[11px]">
                {launch.instances.map((inst) => (
                    <div key={inst.pid} className="flex items-baseline gap-2">
                        <span className="font-mono">{inst.pid}</span>
                        <span>{inst.displayName}</span>
                        <span className="truncate text-[10px] text-on-surface-variant">{inst.diyHome}</span>
                        <span className="ml-auto text-[10px] text-on-surface-variant">{formatStartedAt(inst.startedAt)}</span>
                    </div>
                ))}
            </div>
        </Card>
    );
}

function BuildCard(props: { ctx: UiContext; launch: LaunchStatus; notify: (text: string) => void }) {
    const [busy, setBusy] = useState<string | null>(null);
    const run = (command: BuildCommand): void => {
        setBusy(command);
        void props.ctx
            .invoke(DEV_METHODS.run, { ...refOf(props.launch), command })
            .then(() => props.notify(`已开始 ${command}`))
            .catch((e: unknown) => props.notify(`命令启动失败：${e instanceof Error ? e.message : String(e)}`))
            .finally(() => setBusy(null));
    };
    return (
        <Card title="构建 / 检查" right={props.launch.built ? "已构建" : "未构建"}>
            <div className="flex flex-wrap gap-1">
                {BUILD_COMMANDS.map((command) => (
                    <button key={command} type="button" className={BTN} disabled={busy !== null} onClick={() => run(command)}>
                        {busy === command ? `${command}…` : command}
                    </button>
                ))}
            </div>
        </Card>
    );
}

function LogCard(props: { ctx: UiContext }) {
    // 两段式订阅：行数不变就不重画；变了只取尾部 300 行
    useStoreSlice(props.ctx.session, selectSessionKey);
    const lines = useStoreSlice(props.ctx.session, selectSessionLines);
    return (
        <Card
            title="命令输出"
            right={
                <button type="button" className={BTN} onClick={() => void props.ctx.invoke(DEV_METHODS.clearSession)}>
                    清空
                </button>
            }
        >
            {lines.length === 0 ? (
                <div className="text-[11px] text-on-surface-variant">（没有输出）</div>
            ) : (
                <pre className="max-h-[240px] overflow-auto whitespace-pre-wrap break-all rounded-md bg-surface-high p-2 font-mono text-[10px] leading-[1.45]">
                    {lines.slice(-300).join("\n")}
                </pre>
            )}
        </Card>
    );
}

function LaunchDetail(props: { ctx: UiContext; launch: LaunchStatus; notify: (text: string) => void }) {
    const { launch, ctx } = props;
    const [tab, setTab] = useState<"info" | "files" | "ref">("info");
    const runtime = launch.runtime;
    const tabBtn = (id: "info" | "files" | "ref", label: string) => (
        <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={`border-b-2 px-3 py-1 text-[11px] ${
                tab === id ? "border-primary text-on-surface" : "border-transparent text-on-surface-variant hover:text-on-surface"
            }`}
        >
            {label}
        </button>
    );
    const tabs = (
        <div className="mb-2 flex items-center gap-1 border-b border-outline">
            {tabBtn("info", "详情")}
            {tabBtn("files", "文件")}
            {tabBtn("ref", "外部仓库")}
            <span className="ml-auto truncate text-[10px] text-on-surface-variant">{launch.worktree}</span>
        </div>
    );
    if (tab === "files") {
        return (
            <div className="flex h-full min-h-0 flex-col p-2">
                {tabs}
                <div className="min-h-0 flex-1">
                    <FilesPane worktree={launch.worktree} />
                </div>
            </div>
        );
    }
    if (tab === "ref") {
        return (
            <div className="flex h-full min-h-0 flex-col p-2">
                {tabs}
                <div className="min-h-0 flex-1">
                    <RefPane worktree={launch.worktree} invoke={ctx.invoke} />
                </div>
            </div>
        );
    }
    return (
        <div className="flex h-full flex-col gap-2 overflow-auto p-2">
            {tabs}
            <div className="flex items-baseline gap-2">
                <h1 className="text-[14px] font-medium">
                    {launch.app}.{launch.launch}
                </h1>
                <span className="text-[11px] text-on-surface-variant">{launch.launchTitle}</span>
            </div>
            <ActionBar ctx={ctx} launch={launch} notify={props.notify} />

            {launch.configIssues.length > 0 ? (
                <div className="rounded-md border border-error p-2 text-[11px] text-error">
                    {launch.configIssues.map((issue) => (
                        <div key={issue.code} className="mb-1 last:mb-0">
                            <div>{issue.message}</div>
                            <div className="opacity-80">修法：{issue.fix}</div>
                        </div>
                    ))}
                </div>
            ) : null}

            <Card title="概况">
                <div className="flex flex-col gap-0.5">
                    <KV label="命令" value={<span className="font-mono">{launch.command}</span>} />
                    <KV label="工作区" value={<span className="font-mono">{launch.worktree}</span>} />
                    <KV label="数据根" value={<span className="font-mono">{launch.home}</span>} />
                    <KV label="环境" value={Object.keys(launch.env).length === 0 ? "-" : JSON.stringify(launch.env)} />
                    <KV label="URI" value={launch.uri === null ? "（未启动过）" : <span className="font-mono">{launch.uri}</span>} />
                </div>
            </Card>

            <EntriesCard
                launch={launch}
                onOpenUrl={(url) => {
                    void ctx
                        .invoke<{ ok: boolean; reason: string }>(DEV_METHODS.open, { url })
                        .then((res) => props.notify(res.ok ? `已打开：${res.reason}` : `打开失败：${res.reason}`))
                        .catch((e: unknown) => props.notify(`打开失败：${e instanceof Error ? e.message : String(e)}`));
                }}
            />
            <InstancesCard launch={launch} />

            {runtime !== null ? (
                <Card title="运行时">
                    <div className="flex flex-col gap-0.5">
                        <KV label="PID" value={String(runtime.pid)} />
                        <KV label="端口" value={runtime.port === null ? "-" : String(runtime.port)} />
                        <KV label="已运行" value={formatUptime(runtime.uptimeMs)} />
                        <KV label="常驻" value={formatBytes(runtime.memBytes)} />
                        <KV label="命令行" value={<span className="font-mono">{runtime.cmdline}</span>} />
                        <KV label="cwd" value={<span className="font-mono">{runtime.cwd}</span>} />
                    </div>
                </Card>
            ) : null}

            <BuildCard ctx={ctx} launch={launch} notify={props.notify} />
            {ctx.slots.contributions<{ ctx: UiContext; launch: LaunchStatus }>("detail").map((c) => (
                <div key={c.id}>{c.render({ ctx, launch }) as ReactNode}</div>
            ))}
            <LogCard ctx={ctx} />
        </div>
    );
}

function ExternalDetail(props: { item: ExternalInstance }) {
    const { item } = props;
    return (
        <div className="flex h-full flex-col gap-2 overflow-auto p-2">
            <div className="flex items-baseline gap-2">
                <h1 className="text-[14px] font-medium">{item.app ?? "未知 app"}</h1>
                {item.production ? <span className="text-[11px] text-error">真生产（只读，不提供停止）</span> : <span className="text-[11px] text-on-surface-variant">外部实例</span>}
            </div>
            <Card title="概况">
                <div className="flex flex-col gap-0.5">
                    <KV label="PID" value={String(item.pid)} />
                    <KV label="launch" value={item.launch ?? "-"} />
                    <KV label="数据根" value={<span className="font-mono">{item.diyHome}</span>} />
                    <KV label="worktree" value={<span className="font-mono">{item.worktree ?? "-"}</span>} />
                    <KV label="端口" value={item.port === null ? "-" : String(item.port)} />
                    <KV label="启动" value={formatStartedAt(item.startedAt)} />
                </div>
            </Card>
            <div className="text-[10px] text-on-surface-variant">
                它不属于这个 dev 管的任何 worktree（手工起的 / 生产 / 别的 checkout）—— dev 只观测，不动它。
            </div>
        </div>
    );
}

export interface AppProps {
    readonly ctx: UiContext;
    readonly selection: Selection;
    readonly onSelect: (sel: Selection) => void;
    readonly notify: (text: string) => void;
}

export function App(props: AppProps) {
    const snapshot = useSlice(props.ctx, selectSnapshot);
    // 外部实例每次快照可能换对象 ⇒ 按 pid 重新查，别把 selection 里的旧对象直接渲染（会显示过期数据）
    const externalPid = props.selection?.kind === "external" ? props.selection.pid : null;
    const external = externalPid === null ? null : (snapshot?.externals.find((item) => item.pid === externalPid) ?? null);
    return (
        <div className="grid h-full grid-cols-[minmax(260px,340px)_1fr]">
            <aside className="border-r border-outline">
                <Sidebar ctx={props.ctx} selection={props.selection} onSelect={props.onSelect} />
            </aside>
            <main className="min-w-0">
                {props.selection?.kind === "launch" ? (
                    <LaunchDetail ctx={props.ctx} launch={props.selection.launch} notify={props.notify} />
                ) : external !== null ? (
                    <ExternalDetail item={external} />
                ) : (
                    <div className="p-3 text-[11px] text-on-surface-variant">左边选一条 launch 或一个外部实例</div>
                )}
            </main>
        </div>
    );
}
