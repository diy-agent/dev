/**
 * ref.tsx —— 「外部仓库」页签的 React 版（##518 试点，与 `pkgs/dev-page/src/ref-view.ts` 同功能）
 *
 * 数据面一行没改：主进程侧 `ref-page.ts` 仍是「进程内 mem transport + typed client」调用
 * `dev-ref` 的六个方法；这里只是换渲染层，用 `page:invoke` 打同一批方法名
 * （overview / add / remove / sync / syncState / open）。
 *
 * 作用域：**diy.yaml 跟 worktree 走** —— 这个页签吃的就是当前 launch 所在 worktree。
 */
import { useCallback, useEffect, useRef, useState } from "react";

export interface RefRepo {
    readonly key: string;
    readonly url: string;
    readonly version: string | null;
    readonly dir: string;
    readonly exists: boolean;
    readonly lastSync: string | null;
    readonly behind: number | null;
}

export interface RefOverview {
    readonly root: string;
    readonly home: string;
    readonly repos: readonly RefRepo[];
}

export interface RefSyncState {
    readonly running: boolean;
    readonly lines: readonly string[];
    readonly summary: { readonly synced: number; readonly tagSkipped: number; readonly total: number } | null;
}

const M = { overview: "overview", add: "add", remove: "remove", sync: "sync", syncState: "syncState", open: "open" } as const;

function fmtTime(iso: string | null): string {
    if (iso === null) return "从未";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "—";
    const p = (n: number) => String(n).padStart(2, "0");
    return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

export function RefPane(props: { worktree: string; invoke: <T>(method: string, args?: unknown) => Promise<T> }) {
    const { worktree, invoke } = props;
    const [overview, setOverview] = useState<RefOverview | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [url, setUrl] = useState("");
    const [sync, setSync] = useState<RefSyncState | null>(null);
    const [busy, setBusy] = useState(false);
    const logRef = useRef<HTMLPreElement | null>(null);

    const reload = useCallback(async (): Promise<void> => {
        try {
            setOverview(await invoke<RefOverview>(M.overview, { worktree }));
            setError(null);
        } catch (e) {
            setOverview(null);
            setError(e instanceof Error ? e.message : String(e));
        }
    }, [invoke, worktree]);

    useEffect(() => {
        void reload();
    }, [reload]);

    // 同步在后台跑（主进程），这里轮询拿进度 —— 与老视图同一机制
    useEffect(() => {
        if (sync?.running !== true) return;
        const timer = setInterval(() => {
            void invoke<RefSyncState>(M.syncState, { worktree }).then((next) => {
                setSync(next);
                if (!next.running) void reload();
            });
        }, 800);
        return () => clearInterval(timer);
    }, [sync?.running, invoke, worktree, reload]);

    useEffect(() => {
        if (logRef.current !== null) logRef.current.scrollTop = logRef.current.scrollHeight;
    }, [sync?.lines.length]);

    const runSync = (): void => {
        setSync({ running: true, lines: ["开始同步…"], summary: null });
        void invoke<RefSyncState>(M.sync, { worktree }).then(setSync);
    };

    const add = async (): Promise<void> => {
        const value = url.trim();
        if (value === "") return;
        setBusy(true);
        try {
            await invoke(M.add, { worktree, url: value });
            setUrl("");
            await reload();
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        } finally {
            setBusy(false);
        }
    };

    const remove = async (name: string): Promise<void> => {
        setBusy(true);
        try {
            await invoke(M.remove, { worktree, name });
            await reload();
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        } finally {
            setBusy(false);
        }
    };

    const cls = "rounded-md border border-outline px-2 py-[1px] text-[11px] hover:bg-surface-high disabled:opacity-40";
    return (
        <div className="flex h-full min-h-0 flex-col gap-2">
            <div className="flex items-center gap-2 text-[11px]">
                <input
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    placeholder="https://github.com/org/repo@v1.0.0"
                    className="min-w-0 flex-1 rounded-md border border-outline bg-transparent px-2 py-[2px] font-mono"
                />
                <button type="button" className={cls} disabled={busy || url.trim() === ""} onClick={() => void add()}>
                    添加
                </button>
                <button type="button" className={cls} disabled={sync?.running === true} onClick={runSync}>
                    {sync?.running === true ? "同步中…" : "同步"}
                </button>
            </div>

            {error !== null ? <div className="rounded-md border border-error px-2 py-1 text-[11px] text-error">{error}</div> : null}

            {overview !== null ? (
                <div className="text-[10px] text-on-surface-variant">
                    作用域 <span className="font-mono">{overview.root}</span> · 镜像 <span className="font-mono">{overview.home}/ref</span>
                </div>
            ) : null}

            <div className="min-h-0 flex-1 overflow-auto">
                {overview === null ? null : overview.repos.length === 0 ? (
                    <div className="p-2 text-[11px] text-on-surface-variant">这个 worktree 的 diy.yaml 里还没有 source</div>
                ) : (
                    <table className="w-full text-[11px]">
                        <tbody>
                            {overview.repos.map((repo) => (
                                <tr key={repo.key} className="border-b border-outline/60">
                                    <td className="py-1 pr-2">
                                        <div className="font-mono">{repo.key}</div>
                                        <div className="text-[10px] text-on-surface-variant">
                                            {repo.version ?? "跟随分支"} · {fmtTime(repo.lastSync)}
                                            {repo.behind === null ? "" : ` · 落后 ${String(repo.behind)}`}
                                            {repo.exists ? "" : " · 未克隆"}
                                        </div>
                                    </td>
                                    <td className="w-[1%] whitespace-nowrap py-1 text-right">
                                        <button type="button" className={cls} onClick={() => void invoke(M.open, { path: repo.dir })}>
                                            打开
                                        </button>
                                        <button
                                            type="button"
                                            className={`${cls} ml-1`}
                                            disabled={busy}
                                            onClick={() => void remove(repo.key.split("/").slice(1).join("/"))}
                                        >
                                            移除
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>

            {sync !== null ? (
                <div className="shrink-0">
                    <div className="text-[10px] text-on-surface-variant">
                        {sync.running ? "同步中…" : sync.summary === null ? "已结束" : `已同步 ${String(sync.summary.synced)} / ${String(sync.summary.total)}（跳过 tag ${String(sync.summary.tagSkipped)}）`}
                    </div>
                    <pre ref={logRef} className="max-h-[160px] overflow-auto rounded-md bg-surface-high p-2 font-mono text-[10px] leading-[1.45]">
                        {sync.lines.slice(-120).join("\n")}
                    </pre>
                </div>
            ) : null}
        </div>
    );
}
