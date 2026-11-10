/**
 * chrome.tsx —— workbench 的**外壳**：标题栏 / 页面导航 / 通知 / 状态栏（##518 用户口径）。
 *
 * 为什么要有它：之前的界面直接铺满窗口，没有「工作台」的样子 ——
 *   没有标题栏（不知道自己在哪个实例、哪个页面）、没有页面导航（多页插件无处落脚）、
 *   没有通知区（toast 只在一行小字里闪一下，错过就没了）、没有状态栏（在跑几条 / 输出是否在刷）。
 *
 * 结构（自外向内）：
 *   TitleBar   ← 页面导航（`workbench.listPages()`）+ 实例名 + 通知徽标
 *   [ 主区 ]   ← 交给具体页面（本包目前只有「应用」一页）
 *   StatusBar  ← 在跑数 / 总条数 / 命令输出状态 / 最新一条通知
 *
 * 页面清单来自 workbench（`page.list`），不是写死的 —— 将来加页面（外部仓库独立页、
 * 事件流页、日志页…）只需注册插件，外壳不用改。
 */
import { useCallback, useEffect, useRef, useState } from "react";

export interface PageInfo {
    readonly id: string;
    readonly title: string;
    readonly description?: string;
}

export interface Notice {
    readonly id: number;
    readonly text: string;
    readonly at: number;
}

/** 页面清单（失败不炸：外壳降级成「只有一页」也比白屏强） */
export function usePages(load: () => Promise<PageInfo[]>): readonly PageInfo[] {
    const [pages, setPages] = useState<readonly PageInfo[]>([]);
    useEffect(() => {
        let alive = true;
        void load()
            .then((list) => {
                if (alive) setPages(list);
            })
            .catch(() => {
                if (alive) setPages([{ id: "dev", title: "应用" }]);
            });
        return () => {
            alive = false;
        };
    }, [load]);
    return pages;
}

export function TitleBar(props: {
    pages: readonly PageInfo[];
    active: string;
    onPick: (id: string) => void;
    instanceName: string;
    notices: readonly Notice[];
    onClearNotices: () => void;
}) {
    const [open, setOpen] = useState(false);
    const box = useRef<HTMLDivElement | null>(null);
    useEffect(() => {
        if (!open) return;
        const close = (event: MouseEvent): void => {
            if (box.current !== null && !box.current.contains(event.target as Node)) setOpen(false);
        };
        window.addEventListener("mousedown", close);
        return () => window.removeEventListener("mousedown", close);
    }, [open]);

    return (
        <header className="flex h-9 shrink-0 items-stretch border-b border-outline bg-surface-low">
            <div className="flex items-center gap-2 px-3">
                <span className="text-[12px] font-medium">dev</span>
                <span className="text-[10px] text-on-surface-variant">{props.instanceName}</span>
            </div>
            <nav className="flex items-stretch">
                {props.pages.map((page) => (
                    <button
                        key={page.id}
                        type="button"
                        onClick={() => props.onPick(page.id)}
                        title={page.description ?? page.id}
                        className={`border-b-2 px-3 text-[11px] ${
                            props.active === page.id
                                ? "border-primary text-on-surface"
                                : "border-transparent text-on-surface-variant hover:text-on-surface"
                        }`}
                    >
                        {page.title}
                    </button>
                ))}
            </nav>
            <div className="ml-auto flex items-center gap-1 px-2" ref={box}>
                <button
                    type="button"
                    onClick={() => setOpen((v) => !v)}
                    title="通知"
                    className="relative rounded px-2 py-[2px] text-[11px] hover:bg-surface-high"
                >
                    通知
                    {props.notices.length > 0 ? (
                        <span className="ml-1 rounded-full bg-primary px-1 text-[9px] text-on-primary">{props.notices.length}</span>
                    ) : null}
                </button>
                {open ? (
                    <div className="absolute right-2 top-9 z-10 max-h-[280px] w-[320px] overflow-auto rounded-lg border border-outline bg-surface p-1 shadow-lg">
                        {props.notices.length === 0 ? (
                            <div className="p-2 text-[11px] text-on-surface-variant">（没有通知）</div>
                        ) : (
                            <>
                                <button type="button" className="mb-1 w-full rounded px-2 py-1 text-left text-[10px] hover:bg-surface-high" onClick={props.onClearNotices}>
                                    清空
                                </button>
                                {[...props.notices].reverse().map((notice) => (
                                    <div key={notice.id} className="rounded px-2 py-1 text-[11px]">
                                        <span className="mr-1 text-[9px] text-on-surface-variant">
                                            {new Date(notice.at).toLocaleTimeString("zh-CN", { hour12: false })}
                                        </span>
                                        {notice.text}
                                    </div>
                                ))}
                            </>
                        )}
                    </div>
                ) : null}
            </div>
        </header>
    );
}

export function StatusBar(props: {
    running: number;
    total: number;
    externals: number;
    sessionRunning: boolean;
    lastLine: string;
}) {
    return (
        <footer className="flex h-6 shrink-0 items-center gap-3 border-t border-outline bg-surface-low px-3 text-[10px] text-on-surface-variant">
            <span>
                {props.running}/{props.total} 在跑
            </span>
            {props.externals > 0 ? <span>外部实例 {props.externals}</span> : null}
            <span className={props.sessionRunning ? "text-primary" : ""}>{props.sessionRunning ? "输出刷新中…" : "输出空闲"}</span>
            <span className="ml-auto truncate">{props.lastLine}</span>
        </footer>
    );
}

/** 通知列表的增删（外壳自己管，不污染业务 store） */
export function useNotices() {
    const [notices, setNotices] = useState<readonly Notice[]>([]);
    const seq = useRef(0);
    const push = useCallback((text: string) => {
        if (text.trim() === "") return;
        const notice: Notice = { id: ++seq.current, text, at: Date.now() };
        // 只留最近 50 条：这是「刚才干了什么」的回顾，不是审计日志
        setNotices((prev) => [...prev, notice].slice(-50));
    }, []);
    const clear = useCallback(() => setNotices([]), []);
    return { notices, push, clear };
}
