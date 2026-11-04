// files-view.ts — worktree 详情页的「文件」页签（##518）：文件树 + 编辑器。
//
// 两个 diy 自家技术都用上了：
//   · **@diy-agent/ui**（`@diy-agent/ui/browser`）：文件树用 `html.*` Spec + `GenApp` 声明式渲染，
//     没有手写 document.createElement，也没有框架；
//   · **@diy-agent/rpc**：文件读写走 `ChannelClientBinding` + `createTypedClient(fsApi)`，
//     schema 来自 `@diy-agent/dev-fs`（zod 校验，主进程按 worktree 做路径 jail）。
//
// 编辑器是 CodeMirror 6（纯浏览器包，esbuild 直接打进去；不需要 VS Code / Monaco 那套 worker）。

import { GenApp, html } from "@diy-agent/ui/browser";
import { ChannelClientBinding, createTypedClient, type EnvelopeTransport } from "@diy-agent/rpc";
// 只取 schema（`/api` 子入口）：index 会带进 node:fs，渲染侧打包器不认
import { fsApi } from "@diy-agent/dev-fs/api";
import { EditorState } from "@codemirror/state";
import { EditorView, highlightActiveLine, keymap, lineNumbers } from "@codemirror/view";
import { defaultKeymap, indentWithTab } from "@codemirror/commands";
import { javascript } from "@codemirror/lang-javascript";
import { yaml } from "@codemirror/lang-yaml";

export interface FilesPaneOptions {
    readonly worktree: string;
    /** 右侧归不归本视图（不归时不要碰 body / 不要抢标题） */
    isVisible(): boolean;
    toast(text: string): void;
}

export interface FilesPane {
    /** 重新画（外壳切到本页签时调用） */
    render(): void;
    /** 销毁编辑器与事件（worktree 从清单里消失时） */
    destroy(): void;
}

/** 按扩展名选语言扩展（认不出来就纯文本） */
function langFor(path: string) {
    if (/\.(ts|tsx|js|jsx|mjs|cjs|json)$/.test(path)) return javascript({ typescript: /\.tsx?$/.test(path) });
    if (/\.(ya?ml)$/.test(path)) return yaml();
    return [];
}

export function createFilesPane(options: FilesPaneOptions, host: { body: HTMLElement; headTitle: HTMLElement; headBadge: HTMLElement; headMeta: HTMLElement }): FilesPane {
    const transport = (window as unknown as { transport?: EnvelopeTransport }).transport;
    if (transport === undefined) throw new Error("preload 没递出 window.transport（rpc 通道缺失）");
    const fs = createTypedClient(new ChannelClientBinding(transport), fsApi).fs;

    const box = document.createElement("div");
    box.className = "filespane";
    const treeRoot = document.createElement("div");
    treeRoot.className = "filetree";
    const main = document.createElement("div");
    main.className = "filemain";
    const bar = document.createElement("div");
    bar.className = "filebar";
    const editorHost = document.createElement("div");
    editorHost.className = "fileeditor";
    main.append(bar, editorHost);
    box.append(treeRoot, main);

    /** 已展开的目录（相对 worktree） */
    const expanded = new Set<string>([""]);
    /** 目录 → 子项缓存 */
    const dirs = new Map<string, Awaited<ReturnType<typeof fs.list>>>();
    let current: { path: string; text: string } | null = null;
    let dirty = false;
    let view: EditorView | null = null;

    const status = document.createElement("span");
    status.className = "filehint";
    const saveBtn = document.createElement("button");
    saveBtn.type = "button";
    saveBtn.className = "small";
    saveBtn.textContent = "保存";
    saveBtn.addEventListener("click", () => void save());
    bar.append(status, saveBtn);

    function setStatus(text: string): void {
        status.textContent = text;
        saveBtn.disabled = !dirty;
    }

    async function loadDir(path: string): Promise<void> {
        try {
            dirs.set(path, await fs.list({ worktree: options.worktree, path }));
        } catch (error) {
            options.toast(`列目录失败：${error instanceof Error ? error.message : String(error)}`);
            dirs.set(path, []);
        }
    }

    async function openFile(path: string): Promise<void> {
        if (dirty && current !== null && !window.confirm(`${current.path} 有未保存改动，丢弃？`)) return;
        try {
            const file = await fs.read({ worktree: options.worktree, path });
            if (file.binary) {
                options.toast(`${path} 是二进制文件，编辑器不打开`);
                return;
            }
            current = { path, text: file.text };
            dirty = false;
            mountEditor(file.text, path);
            setStatus(`${path}${file.truncated ? "（已截断，只读前 1 MB）" : ""}`);
            renderTree();
        } catch (error) {
            options.toast(`打开失败：${error instanceof Error ? error.message : String(error)}`);
        }
    }

    function mountEditor(text: string, path: string): void {
        view?.destroy();
        view = new EditorView({
            parent: editorHost,
            state: EditorState.create({
                doc: text,
                extensions: [
                    lineNumbers(),
                    highlightActiveLine(),
                    keymap.of([
                        { key: "Mod-s", preventDefault: true, run: () => (void save(), true) },
                        indentWithTab,
                        ...defaultKeymap,
                    ]),
                    langFor(path),
                    EditorView.updateListener.of((update) => {
                        if (update.docChanged) {
                            dirty = true;
                            setStatus(`${path} · 未保存`);
                        }
                    }),
                ],
            }),
        });
    }

    async function save(): Promise<void> {
        if (view === null || current === null) return;
        try {
            const text = view.state.doc.toString();
            const result = await fs.write({ worktree: options.worktree, path: current.path, text });
            current = { ...current, text };
            dirty = false;
            setStatus(`${current.path} · 已保存（${String(result.size)} B）`);
            options.toast(`已保存 ${current.path}`);
            // 文件大小可能变了，重列父目录
            const parent = current.path.includes("/") ? current.path.slice(0, current.path.lastIndexOf("/")) : "";
            await loadDir(parent);
            renderTree();
        } catch (error) {
            options.toast(`保存失败：${error instanceof Error ? error.message : String(error)}`);
        }
    }

    /**
     * 文件树：目录可展开、文件点开。
     * 结构完全由 @diy-agent/ui 的 Spec 描述（`text` 是叶子文本；点按走 props.onclick），
     * 这里不出现 document.createElement。
     */
    function renderTree(): void {
        const app = new GenApp({ mount: treeRoot });
        const items: ReturnType<typeof html.div>[] = [];

        const walk = (path: string): void => {
            for (const entry of dirs.get(path) ?? []) {
                const isOpen = expanded.has(entry.path);
                const icon = entry.kind === "dir" ? (isOpen ? "▾" : "▸") : "·";
                items.push(
                    html.div({
                        class: `fitem ${entry.kind}${entry.path === current?.path ? " sel" : ""}`,
                        style: `padding-left:${String(8 + path.split("/").filter(Boolean).length * 12)}px`,
                        title: entry.path,
                        text: `${icon} ${entry.name}`,
                        onclick: () => {
                            if (entry.kind === "file") {
                                void openFile(entry.path);
                                return;
                            }
                            if (isOpen) {
                                expanded.delete(entry.path);
                                renderTree();
                                return;
                            }
                            expanded.add(entry.path);
                            if (dirs.has(entry.path)) renderTree();
                            else void loadDir(entry.path).then(renderTree);
                        },
                    }),
                );
                if (entry.kind === "dir" && isOpen) walk(entry.path);
            }
        };
        walk("");

        app.render(html.div({ class: "filetree-inner" }, function* () {
            for (const item of items) yield item;
        }));
    }

    return {
        render(): void {
            if (!options.isVisible()) return;
            host.headTitle.textContent = `${options.worktree.split("/").pop() ?? options.worktree} · 文件`;
            host.headBadge.className = "badge stop";
            host.headBadge.textContent = current === null ? "—" : dirty ? "● 未保存" : "○ 已保存";
            host.headMeta.textContent = current?.path ?? "选一个文件开始编辑（Ctrl/Cmd+S 保存）";
            host.body.replaceChildren(box);
            if (!dirs.has("")) {
                void loadDir("").then(() => {
                    renderTree();
                    if (current !== null) mountEditor(current.text, current.path);
                });
            } else {
                renderTree();
                if (current !== null && view === null) mountEditor(current.text, current.path);
            }
            setStatus(current === null ? "未打开文件" : dirty ? `${current.path} · 未保存` : current.path);
        },
        destroy(): void {
            view?.destroy();
            view = null;
        },
    };
}
