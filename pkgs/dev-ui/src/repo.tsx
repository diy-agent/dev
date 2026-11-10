/**
 * repo.tsx —— 「仓库」页（##518 用户口径：像 VS Code 一样浏览各 git 仓库）。
 *
 * 这一页是**只读**视图：主工作树 + 它的 worktree、分支、脏文件、ahead/behind、最近提交。
 * 不做 stage / commit / diff —— 真要看 diff 就点「终端」或「打开代码」（那才是 VS Code 的地界）。
 *
 * 数据每 3s 刷新一次（git 是本地命令，但 status 在大仓上并不便宜；3s 是「够新」与「不吵」的折中）。
 */
import { useEffect, useState } from "react";
import type { RepoOverview, WorktreeStatus } from "@diy-agent/dev-core/shared";
import type { DevClient } from "./client.js";

const POLL_MS = 3000;

function fmtHead(head: string | null): string {
    return head ?? "（读不到 HEAD）";
}

function WorktreeRow(props: { item: WorktreeStatus; onOpen: (path: string) => void }) {
    const { item } = props;
    const [open, setOpen] = useState(false);
    const dirty = item.changes.length > 0;
    return (
        <div className="border-b border-outline/50">
            <div className="flex items-baseline gap-2 px-2 py-1 text-[11px]">
                <button
                    type="button"
                    className="w-3 shrink-0 text-on-surface-variant"
                    onClick={() => setOpen((v) => !v)}
                    disabled={!dirty}
                    title={dirty ? "展开变更" : "工作区干净"}
                >
                    {dirty ? (open ? "▾" : "▸") : "·"}
                </button>
                <span className="shrink-0 font-medium">{item.branch ?? "（detached）"}</span>
                {item.main ? <span className="shrink-0 text-[9px] text-on-surface-variant">主</span> : null}
                <span className="truncate font-mono text-[10px] text-on-surface-variant">{item.path}</span>
                <span className="ml-auto flex shrink-0 items-baseline gap-2 text-[10px]">
                    {dirty ? <span className="text-error">{item.changes.length} 变更</span> : <span className="text-on-surface-variant">干净</span>}
                    {item.ahead !== null && item.ahead > 0 ? <span>↑{item.ahead}</span> : null}
                    {item.behind !== null && item.behind > 0 ? <span>↓{item.behind}</span> : null}
                    <button type="button" className="rounded border border-outline px-1 hover:bg-surface-high" onClick={() => props.onOpen(item.path)}>
                        打开
                    </button>
                </span>
            </div>
            <div className="px-6 pb-1 text-[10px] text-on-surface-variant">{fmtHead(item.head)}</div>
            {open ? (
                <div className="max-h-[200px] overflow-auto px-6 pb-1">
                    {item.changes.map((line) => (
                        <div key={line} className="font-mono text-[10px]">
                            <span className="mr-1 text-on-surface-variant">{line.slice(0, 2)}</span>
                            {line.slice(3)}
                        </div>
                    ))}
                    {item.truncated ? <div className="text-[10px] text-error">（变更太多，只显示前 200 条）</div> : null}
                </div>
            ) : null}
        </div>
    );
}

export function RepoPage(props: { client: DevClient; onOpenPath: (path: string) => void; onOpenWorktree: (path: string) => void }) {
    const [overview, setOverview] = useState<RepoOverview | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let alive = true;
        const tick = (): void => {
            void props.client.repo
                .overview()
                .then((next) => {
                    if (!alive) return;
                    setOverview(next);
                    setError(null);
                })
                .catch((e: unknown) => {
                    if (alive) setError(e instanceof Error ? e.message : String(e));
                });
        };
        tick();
        const timer = setInterval(tick, POLL_MS);
        return () => {
            alive = false;
            clearInterval(timer);
        };
    }, [props.client]);

    if (error !== null) return <div className="p-3 text-[11px] text-error">读 git 状态失败：{error}</div>;
    if (overview === null) return <div className="p-3 text-[11px] text-on-surface-variant">正在读 git…</div>;
    if (overview.repos.length === 0) return <div className="p-3 text-[11px] text-on-surface-variant">没有找到 git 仓库</div>;

    return (
        <div className="flex h-full flex-col overflow-auto">
            {overview.repos.map((repo) => {
                const dirty = repo.worktrees.filter((w) => w.changes.length > 0).length;
                return (
                    <section key={repo.root}>
                        <header className="sticky top-0 flex items-baseline gap-2 border-b border-outline bg-surface-low px-2 py-1 text-[11px]">
                            <span className="font-medium">{repo.name}</span>
                            <span className="truncate font-mono text-[10px] text-on-surface-variant">{repo.root}</span>
                            <span className="ml-auto shrink-0 text-[10px] text-on-surface-variant">
                                {repo.worktrees.length} worktree · {dirty > 0 ? `${dirty} 个有改动` : "全部干净"}
                            </span>
                        </header>
                        {repo.worktrees.map((item) => (
                            <WorktreeRow
                                key={item.path}
                                item={item}
                                onOpen={(path) => {
                                    props.onOpenPath(path);
                                    props.onOpenWorktree(path);
                                }}
                            />
                        ))}
                    </section>
                );
            })}
        </div>
    );
}
