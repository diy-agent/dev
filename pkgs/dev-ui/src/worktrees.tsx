/**
 * files-view.tsx（原 worktrees.tsx）—— 「文件」页：**一个视图里的三层树**（##518 用户口径）。
 *
 *   repo（git 仓库，独立 resource）
 *     └ worktree（叶子节点：可点「详情」打开「应用」页里那个可操作的 worktree 面板）
 *         └ 文件树（懒加载，jail = 该 worktree）
 *
 * 为什么合成一棵树而不是「左选 worktree / 右看文件」两栏：用户要的是**一眼看全**，
 * repo → worktree → 文件 本来就是三层从属关系，平铺成两栏反而要来回点。
 *
 * 数据面：worktree 清单来自快照（主进程扫出来的，含"在跑几个实例"）；文件树来自 dev-fs rpc
 * （list 按需拉，jail 在主进程按 worktree 做边界）。点文件在右侧预览（只读）——编辑仍去
 * 「应用」页的 worktree 详情（那里有 CodeMirror 与保存）。
 */
import { useEffect, useMemo, useState } from "react";
import { fsClient, type FsEntry } from "./fs.js";
import { selectSnapshot, useSlice, type UiContext } from "./app.js";

interface WorktreeNode {
    readonly path: string;
    readonly label: string;
    readonly branch: string | null;
    readonly running: number;
}

/** 派生：repo → worktree 列表（按仓库根分组，仓库内按路径排序） */
function useTree(ctx: UiContext) {
    const snapshot = useSlice(ctx, selectSnapshot);
    return useMemo(() => {
        if (snapshot === null) return new Map<string, WorktreeNode[]>();
        const byRepo = new Map<string, WorktreeNode[]>();
        for (const launch of snapshot.launches) {
            const list = byRepo.get(launch.repo) ?? [];
            if (!list.some((item) => item.path === launch.worktree)) {
                list.push({
                    path: launch.worktree,
                    label: launch.worktreePath,
                    branch: launch.branch,
                    running: (snapshot.worktreeInstances[launch.worktree] ?? []).length,
                });
            }
            byRepo.set(launch.repo, list);
        }
        for (const list of byRepo.values()) list.sort((a, b) => a.path.localeCompare(b.path));
        return new Map([...byRepo].sort(([a], [b]) => a.localeCompare(b)));
    }, [snapshot]);
}

/** 一层目录（展开才拉；目录在前，名字序） */
function DirChildren(props: {
    worktree: string;
    path: string;
    depth: number;
    onPickFile: (worktree: string, path: string, name: string) => void;
}) {
    const [entries, setEntries] = useState<readonly FsEntry[] | null>(null);
    const [error, setError] = useState<string | null>(null);
    useEffect(() => {
        let alive = true;
        void fsClient()
            .list({ worktree: props.worktree, path: props.path })
            .then((rows) => {
                if (!alive) return;
                setEntries([...rows].sort((a, b) => (a.kind === b.kind ? a.name.localeCompare(b.name) : a.kind === "dir" ? -1 : 1)));
            })
            .catch((e: unknown) => {
                if (alive) setError(e instanceof Error ? e.message : String(e));
            });
        return () => {
            alive = false;
        };
    }, [props.worktree, props.path]);

    const indent = { paddingLeft: `${String(8 + props.depth * 12)}px` };
    if (error !== null) return <div style={indent} className="text-[10px] text-error">{error}</div>;
    if (entries === null) return <div style={indent} className="text-[10px] text-on-surface-variant">读取中…</div>;
    return (
        <>
            {entries.map((entry) =>
                entry.kind === "dir" ? (
                    <DirNode key={entry.path} worktree={props.worktree} entry={entry} depth={props.depth} onPickFile={props.onPickFile} />
                ) : (
                    <button
                        key={entry.path}
                        type="button"
                        style={indent}
                        className="block w-full truncate py-[1px] text-left text-[11px] hover:bg-surface-high"
                        onClick={() => props.onPickFile(props.worktree, entry.path, entry.name)}
                    >
                        <span className="mr-1 inline-block w-2" />
                        {entry.name}
                    </button>
                ),
            )}
        </>
    );
}

function DirNode(props: { worktree: string; entry: FsEntry; depth: number; onPickFile: (worktree: string, path: string, name: string) => void }) {
    const [open, setOpen] = useState(false);
    const indent = { paddingLeft: `${String(8 + props.depth * 12)}px` };
    return (
        <>
            <button
                type="button"
                style={indent}
                className="block w-full truncate py-[1px] text-left text-[11px] hover:bg-surface-high"
                onClick={() => setOpen((v) => !v)}
            >
                <span className="mr-1 inline-block w-2 text-on-surface-variant">{open ? "▾" : "▸"}</span>
                {props.entry.name}
            </button>
            {open ? (
                <DirChildren worktree={props.worktree} path={props.entry.path} depth={props.depth + 1} onPickFile={props.onPickFile} />
            ) : null}
        </>
    );
}

function WorktreeNodeView(props: {
    item: WorktreeNode;
    onOpenDetail: (path: string) => void;
    onPickFile: (worktree: string, path: string, name: string) => void;
}) {
    const [open, setOpen] = useState(false);
    const { item } = props;
    return (
        <>
            <div className="flex items-baseline gap-1 px-2 py-[2px] text-[11px] hover:bg-surface-high">
                <button type="button" className="w-3 shrink-0 text-on-surface-variant" onClick={() => setOpen((v) => !v)}>
                    {open ? "▾" : "▸"}
                </button>
                <span className="truncate font-medium">{item.branch ?? (item.path.split("/").at(-1) ?? "?")}</span>
                {item.running > 0 ? <span className="shrink-0 text-[10px] text-primary">●{item.running}</span> : null}
                <span className="truncate text-[10px] text-on-surface-variant">{item.label}</span>
                <button
                    type="button"
                    className="ml-auto shrink-0 rounded border border-outline px-1 text-[10px] hover:bg-surface-high"
                    title="打开「应用」页里这个 worktree 的可操作面板"
                    onClick={() => props.onOpenDetail(item.path)}
                >
                    详情
                </button>
            </div>
            {open ? <DirChildren worktree={item.path} path="" depth={1} onPickFile={props.onPickFile} /> : null}
        </>
    );
}

/** 右侧预览：只读，给「点一下看看里面是什么」用；编辑去应用页 */
function FilePreview(props: { pick: { worktree: string; path: string; name: string } | null }) {
    const [text, setText] = useState<string | null>(null);
    const [note, setNote] = useState<string | null>(null);
    useEffect(() => {
        if (props.pick === null) return;
        let alive = true;
        setNote(null);
        setText(null);
        void fsClient()
            .read({ worktree: props.pick.worktree, path: props.pick.path })
            .then((res) => {
                if (!alive) return;
                setText(res.binary ? "（二进制文件，不显示内容）" : res.text);
                setNote(res.truncated ? "文件较大，只读了前 1 MB" : null);
            })
            .catch((e: unknown) => {
                if (alive) setNote(e instanceof Error ? e.message : String(e));
            });
        return () => {
            alive = false;
        };
    }, [props.pick]);

    if (props.pick === null) return <div className="p-2 text-[11px] text-on-surface-variant">左边点一个文件</div>;
    return (
        <div className="flex h-full min-h-0 flex-col">
            <div className="flex items-baseline gap-2 border-b border-outline px-2 py-1 text-[10px] text-on-surface-variant">
                <span className="truncate font-mono">{props.pick.path}</span>
                {note !== null ? <span className="ml-auto">{note}</span> : null}
            </div>
            <pre className="min-h-0 flex-1 overflow-auto p-2 font-mono text-[10px] leading-[1.45]">{text ?? "读取中…"}</pre>
        </div>
    );
}

export function FilesViewPage(props: { ctx: UiContext; onOpenWorktree: (path: string) => void }) {
    const tree = useTree(props.ctx);
    const [collapsedRepos, setCollapsedRepos] = useState<readonly string[]>([]);
    const [pick, setPick] = useState<{ worktree: string; path: string; name: string } | null>(null);

    if (tree.size === 0) return <div className="p-3 text-[11px] text-on-surface-variant">还没有任何 worktree</div>;

    return (
        <div className="flex h-full min-h-0">
            <aside className="w-[320px] shrink-0 overflow-auto border-r border-outline py-1">
                {[...tree].map(([repo, worktrees]) => {
                    const open = !collapsedRepos.includes(repo);
                    return (
                        <section key={repo}>
                            <button
                                type="button"
                                className="flex w-full items-baseline gap-1 px-2 py-1 text-left text-[11px] hover:bg-surface-high"
                                title={repo}
                                onClick={() =>
                                    setCollapsedRepos(open ? [...collapsedRepos, repo] : collapsedRepos.filter((item) => item !== repo))
                                }
                            >
                                <span className="w-3 shrink-0 text-on-surface-variant">{open ? "▾" : "▸"}</span>
                                <span className="truncate font-medium">{repo.split("/").at(-1) ?? repo}</span>
                                <span className="ml-auto shrink-0 text-[10px] text-on-surface-variant">{worktrees.length} worktree</span>
                            </button>
                            {open
                                ? worktrees.map((item) => (
                                      <WorktreeNodeView
                                          key={item.path}
                                          item={item}
                                          onOpenDetail={props.onOpenWorktree}
                                          onPickFile={(worktree, path, name) => setPick({ worktree, path, name })}
                                      />
                                  ))
                                : null}
                        </section>
                    );
                })}
            </aside>
            <div className="min-w-0 flex-1">
                <FilePreview pick={pick} />
            </div>
        </div>
    );
}
