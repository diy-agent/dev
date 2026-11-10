/**
 * worktrees.tsx —— 「文件」页（##518 用户口径：**不读 git**，就是各 worktree 的目录浏览）。
 *
 * 和「应用」页的 worktree 详情里的「文件」页签是同一个组件（`files.tsx`），
 * 区别只在入口：这里是**全机所有 worktree 的目录总览**，不用先选中某条 launch。
 *
 * 数据面走 `@diy-agent/dev-fs`（list / read / write），jail 在主进程 —— 每个 worktree 各自一条边界，
 * 渲染侧永远只传相对路径。
 */
import { useMemo, useState } from "react";
import { FilesPane } from "./files.js";
import { selectSnapshot, useSlice, type UiContext } from "./app.js";

/**
 * 去重后的 worktree 列表（按路径排序；带上分支与在跑实例数，便于认人）。
 *
 * ⚠️ 派生放在 `useMemo` 里，**不能**直接写成 useSlice 的选择器：选择器每次返回新数组，
 * useSyncExternalStore 会认为快照一直在变 ⇒ 无限重渲染（本仓库已踩过一次，React error #185）。
 */
function useWorktrees(ctx: UiContext) {
    const snapshot = useSlice(ctx, selectSnapshot);
    return useMemo(() => {
        if (snapshot === null) return [];
        const seen = new Map<string, { path: string; label: string; branch: string | null; running: number }>();
        for (const launch of snapshot.launches) {
            if (seen.has(launch.worktree)) continue;
            seen.set(launch.worktree, {
                path: launch.worktree,
                label: launch.worktreePath,
                branch: launch.branch,
                running: (snapshot.worktreeInstances[launch.worktree] ?? []).length,
            });
        }
        return [...seen.values()].sort((a, b) => a.path.localeCompare(b.path));
    }, [snapshot]);
}

export function WorktreesPage(props: { ctx: UiContext }) {
    const worktrees = useWorktrees(props.ctx);
    const [picked, setPicked] = useState<string | null>(null);
    const active = picked !== null && worktrees.some((item) => item.path === picked) ? picked : (worktrees[0]?.path ?? null);

    if (worktrees.length === 0) return <div className="p-3 text-[11px] text-on-surface-variant">还没有任何 worktree</div>;

    return (
        <div className="flex h-full min-h-0">
            <aside className="w-[220px] shrink-0 overflow-auto border-r border-outline">
                {worktrees.map((item) => (
                    <button
                        key={item.path}
                        type="button"
                        onClick={() => setPicked(item.path)}
                        title={item.path}
                        className={`block w-full px-2 py-1 text-left text-[11px] hover:bg-surface-high ${
                            active === item.path ? "bg-primary-container text-on-primary-container" : ""
                        }`}
                    >
                        <div className="flex items-baseline gap-1">
                            <span className="truncate font-medium">{item.branch ?? (item.path.split("/").at(-1) ?? "?")}</span>
                            {item.running > 0 ? <span className="ml-auto shrink-0 text-[10px]">● {item.running}</span> : null}
                        </div>
                        <div className="truncate text-[10px] text-on-surface-variant">{item.label}</div>
                    </button>
                ))}
            </aside>
            <div className="min-h-0 min-w-0 flex-1 p-2">
                {active === null ? (
                    <div className="p-2 text-[11px] text-on-surface-variant">左边选一个 worktree</div>
                ) : (
                    <FilesPane worktree={active} />
                )}
            </div>
        </div>
    );
}
