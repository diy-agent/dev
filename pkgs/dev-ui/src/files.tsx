/**
 * files.tsx —— 「文件」页签的 React 版（##518 试点，与 `pkgs/dev-page/src/files-view.ts` 同功能）
 *
 * 目的不是多一个页面，而是**同一功能的两种写法对照**：
 *   · 老写法：`@diy-agent/ui/browser` 的 `html.*` + `GenApp`，命令式建 DOM、手动挂容器、手动销毁；
 *   · 这里：React 组件 + hooks，树状态/选中文件/脏标记都是普通 state，编辑器用 ref 挂。
 *
 * 数据面完全一致：`@diy-agent/dev-fs` 的三个方法（list / read / write），
 * 走 preload 递出来的 `window.transport`（Electron IPC）。jail 在**主进程**，这里只是调用方。
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { EditorView, highlightActiveLine, keymap, lineNumbers } from "@codemirror/view";
import { defaultKeymap, indentWithTab } from "@codemirror/commands";
import { javascript } from "@codemirror/lang-javascript";
import { yaml } from "@codemirror/lang-yaml";
import { fsClient, type FsEntry } from "./fs.js";


/** 按扩展名选语言扩展（与老实现同口径） */
function langFor(path: string) {
    if (/\.(ts|tsx|js|jsx|mjs|cjs|json)$/.test(path)) return [javascript({ typescript: /\.tsx?$/.test(path) })];
    if (/\.(ya?ml)$/.test(path)) return [yaml()];
    return [];
}

/** 一层目录：展开才拉；已展开的目录缓存各自的子项 */
function useDir(worktree: string, path: string, enabled: boolean) {
    const [entries, setEntries] = useState<readonly FsEntry[]>([]);
    const [error, setError] = useState<string | null>(null);
    useEffect(() => {
        if (!enabled) return;
        let alive = true;
        void fsClient()
            .list({ worktree, path })
            .then((rows) => {
                if (!alive) return;
                // 目录在前，名字序（主进程已经排过，这里再稳一次）
                setEntries([...rows].sort((a, b) => (a.kind === b.kind ? a.name.localeCompare(b.name) : a.kind === "dir" ? -1 : 1)));
                setError(null);
            })
            .catch((e: unknown) => {
                if (alive) setError(e instanceof Error ? e.message : String(e));
            });
        return () => {
            alive = false;
        };
    }, [worktree, path, enabled]);
    return { entries, error };
}

function TreeRow(props: { worktree: string; entry: FsEntry; depth: number; selected: string | null; onPick: (path: string) => void }) {
    const [open, setOpen] = useState(false);
    const { entry } = props;
    const indent = { paddingLeft: `${String(6 + props.depth * 12)}px` };
    if (entry.kind === "dir") {
        return (
            <div>
                <button
                    type="button"
                    style={indent}
                    className="block w-full truncate py-[1px] text-left hover:bg-surface-high"
                    onClick={() => setOpen((v) => !v)}
                >
                    <span className="mr-1 inline-block w-2 text-on-surface-variant">{open ? "▾" : "▸"}</span>
                    {entry.name}
                </button>
                {open ? <DirList worktree={props.worktree} path={entry.path} depth={props.depth + 1} selected={props.selected} onPick={props.onPick} /> : null}
            </div>
        );
    }
    const active = props.selected === entry.path;
    return (
        <button
            type="button"
            style={indent}
            className={`block w-full truncate py-[1px] text-left hover:bg-surface-high ${active ? "bg-primary-container text-on-primary-container" : ""}`}
            onClick={() => props.onPick(entry.path)}
        >
            <span className="mr-1 inline-block w-2" />
            {entry.name}
        </button>
    );
}

function DirList(props: { worktree: string; path: string; depth: number; selected: string | null; onPick: (path: string) => void }) {
    const { entries, error } = useDir(props.worktree, props.path, true);
    if (error !== null) return <div style={{ paddingLeft: `${String(6 + props.depth * 12)}px` }} className="text-[10px] text-error">{error}</div>;
    return (
        <>
            {entries.map((entry) => (
                <TreeRow key={entry.path} worktree={props.worktree} entry={entry} depth={props.depth} selected={props.selected} onPick={props.onPick} />
            ))}
        </>
    );
}

/** 编辑器：CodeMirror 挂在 ref 上；换文件即重建（原型阶段不追求保留滚动位置） */
function Editor(props: { path: string | null; text: string; onChange: (text: string) => void }) {
    const host = useRef<HTMLDivElement | null>(null);
    const viewRef = useRef<EditorView | null>(null);
    const onChangeRef = useRef(props.onChange);
    onChangeRef.current = props.onChange;
    useEffect(() => {
        if (host.current === null || props.path === null) return;
        const view = new EditorView({
            doc: props.text,
            extensions: [
                // 与老实现同一套最小组合（不引 `codemirror` 元包，少一层依赖）
                lineNumbers(),
                highlightActiveLine(),
                keymap.of([...defaultKeymap, indentWithTab]),
                EditorView.lineWrapping,
                ...langFor(props.path),
                EditorView.updateListener.of((update) => {
                    if (update.docChanged) onChangeRef.current(update.state.doc.toString());
                }),
            ],
            parent: host.current,
        });
        viewRef.current = view;
        return () => {
            viewRef.current = null;
            view.destroy();
        };
        // 只在换文件时重建；内容到达（异步读盘）由下面那个 effect 灌进去
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [props.path]);

    /**
     * 内容后到：文件要 rpc 读盘，编辑器先挂空 doc —— 这里把到达的文本灌进去。
     * （不写这一步的后果实测过：文件明明有 31KB，编辑器里只有 1 行空。）
     * 只在**与当前 doc 不同**时替换，避免自己打字时被回灌覆盖。
     */
    useEffect(() => {
        const view = viewRef.current;
        if (view === null) return;
        const current = view.state.doc.toString();
        if (current === props.text) return;
        view.dispatch({ changes: { from: 0, to: current.length, insert: props.text } });
    }, [props.text]);
    if (props.path === null) return <div className="p-2 text-[11px] text-on-surface-variant">左边选一个文件</div>;
    return <div ref={host} className="h-full overflow-auto text-[11px]" />;
}

export function FilesPane(props: { worktree: string }) {
    const [selected, setSelected] = useState<string | null>(null);
    const [text, setText] = useState("");
    const [saved, setSaved] = useState("");
    const [message, setMessage] = useState<string | null>(null);
    const dirty = useMemo(() => selected !== null && text !== saved, [selected, text, saved]);

    useEffect(() => {
        if (selected === null) return;
        let alive = true;
        void fsClient()
            .read({ worktree: props.worktree, path: selected })
            .then((res) => {
                if (!alive) return;
                if (res.binary) {
                    setText("");
                    setSaved("");
                    setMessage("二进制文件不显示内容");
                    return;
                }
                setText(res.text);
                setSaved(res.text);
                setMessage(res.truncated ? "文件较大，只读取了前 1 MB" : null);
            })
            .catch((e: unknown) => setMessage(e instanceof Error ? e.message : String(e)));
        return () => {
            alive = false;
        };
    }, [props.worktree, selected]);

    const save = (): void => {
        if (selected === null) return;
        void fsClient()
            .write({ worktree: props.worktree, path: selected, text })
            .then((res) => {
                setSaved(text);
                setMessage(`已保存（${String(res.size)} 字节）`);
            })
            .catch((e: unknown) => setMessage(e instanceof Error ? e.message : String(e)));
    };

    return (
        <div className="flex h-full min-h-0 gap-2">
            <div className="w-[240px] shrink-0 overflow-auto border-r border-outline pr-1">
                <DirList worktree={props.worktree} path="" depth={0} selected={selected} onPick={setSelected} />
            </div>
            <div className="flex min-w-0 flex-1 flex-col">
                <div className="flex items-center gap-2 border-b border-outline pb-1 text-[11px]">
                    <span className="truncate font-mono text-on-surface-variant">{selected ?? "—"}</span>
                    {dirty ? <span className="text-error">未保存</span> : null}
                    <button
                        type="button"
                        className="ml-auto rounded-md border border-outline px-2 py-[1px] disabled:opacity-40"
                        disabled={!dirty}
                        onClick={save}
                    >
                        保存
                    </button>
                </div>
                {message !== null ? <div className="py-1 text-[10px] text-on-surface-variant">{message}</div> : null}
                <div className="min-h-0 flex-1">
                    <Editor path={selected} text={text} onChange={setText} />
                </div>
            </div>
        </div>
    );
}
