// ref-view.ts — 「外部仓库」页的界面（纯 DOM，无框架；##510）。
//
// 数据全来自 `page:invoke`（主进程的 ref 页插件）：左侧 = diy.yaml 里的 source 列表 + 添加，
// 右侧 = 概况 / 同步（进度行 + 全部同步）/ 选中仓库详情。
//
// 进度为轮询式：`sync` 在后台跑批，UI 每次 `poll()` 拉 `syncState` 的快照（page:invoke 是 unary，
// 没有推送通道；与「应用」页每秒拉快照同一套做法）。

import { REF_METHODS, type RefOverview, type RefRepo, type RefSyncState } from "@diy-agent/dev-core/shared";

/** 页面宿主：renderer 把「属于外壳的」东西传进来（不反向 import renderer，避免环形依赖） */
export interface RefHost {
    /** 左侧底部容器（外部仓库区，常驻；本视图接管其内容） */
    readonly refs: HTMLElement;
    /** 此刻右侧面板归不归本视图：不归时**不要碰 body**（否则会把 app 详情冲掉） */
    isVisible(): boolean;
    /** 右侧内容容器 */
    readonly body: HTMLElement;
    readonly headTitle: HTMLElement;
    readonly headBadge: HTMLElement;
    readonly headMeta: HTMLElement;
    invoke<T>(method: string, args?: unknown): Promise<T>;
    toast(text: string): void;
    /** 用户点了某个仓库：外壳该把右侧面板切到本视图 */
    onSelect?(): void;
}

export interface RefView {
    /** 挂到左侧容器（外壳启动时调一次；之后容器常驻，不再重画骨架） */
    mount(): void;
    /** 重画左右（外壳切到「外部仓库」面板时调用） */
    render(): void;
    /** 首次进入 / 切回本页：拉数据并重绘 */
    refresh(): Promise<void>;
    /** 每秒一次：同步中更快看进度，空闲时也顺带刷新列表 */
    poll(): void;
    /** 是否正在同步（外壳据此调轮询节奏） */
    isRunning(): boolean;
}

// ── DOM 小工具（与 renderer 的同类工具各自独立：两个模块的布局语言不同） ──

function el<K extends keyof HTMLElementTagNameMap>(tag: K, className = "", text?: string): HTMLElementTagNameMap[K] {
    const node = document.createElement(tag);
    if (className !== "") node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
}

function button(label: string, className: string, onclick: () => void): HTMLButtonElement {
    const node = el("button", className, label);
    node.type = "button";
    node.addEventListener("click", (event) => {
        event.stopPropagation();
        onclick();
    });
    return node;
}

function card(title: string, extra?: Node): HTMLElement {
    const box = el("div", "card");
    const head = el("h2", "", title);
    if (extra !== undefined) {
        const right = el("span", "r");
        right.append(extra);
        head.append(right);
    }
    box.append(head);
    return box;
}

function kv(label: string, value: Node | string): [HTMLElement, HTMLElement] {
    const dt = el("dt", "", label);
    const dd = el("dd");
    if (typeof value === "string") dd.textContent = value;
    else dd.append(value);
    return [dt, dd];
}

function errText(error: unknown): string {
    // page:invoke 的错误经 IPC 回来会被包一层，取出 message 就够
    return error instanceof Error ? error.message : String(error);
}

/** 版本是否为不可变（tag / SHA）：固定检出，没有「落后」概念 */
function isPinned(version: string | null): boolean {
    if (version === null) return false;
    return /^v?\d+(\.\d+)*$/.test(version) || /^[0-9a-f]{40}$/i.test(version);
}

function ago(iso: string | null): string {
    if (iso === null || iso === "") return "从未同步";
    const at = new Date(iso);
    if (Number.isNaN(at.getTime())) return iso;
    const diff = Date.now() - at.getTime();
    if (diff < 60_000) return "刚刚";
    if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`;
    if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`;
    const days = Math.floor(diff / 86_400_000);
    if (days < 30) return `${days} 天前`;
    const pad = (n: number): string => String(n).padStart(2, "0");
    return `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}`;
}

/** owner/repo（key 是 host/owner/repo，左侧只显示后两段） */
function shortName(repo: RefRepo): string {
    return repo.key.split("/").slice(-2).join("/");
}

/** 状态一句话（左侧副标题 / 右侧详情共用） */
function statusText(repo: RefRepo): string {
    if (!repo.exists) return "未同步（待克隆）";
    if (isPinned(repo.version)) return `固定版本 · ${ago(repo.lastSync)}`;
    if (repo.behind === null) return `已同步 · ${ago(repo.lastSync)}`;
    if (repo.behind === 0) return `已是最新 · ${ago(repo.lastSync)}`;
    return `落后 ${repo.behind} 个提交 · ${ago(repo.lastSync)}`;
}

export function createRefView(host: RefHost): RefView {
    let overview: RefOverview | null = null;
    let sync: RefSyncState | null = null;
    let selected: string | null = null;
    let busy = false;
    let ticks = 0;

    // 左侧骨架建一次：输入行常驻（轮询重绘不清掉用户正在敲的 URL），列表容器按数据重画
    const addRow = el("div", "refadd");
    const addInput = el("input", "refinput");
    addInput.type = "text";
    addInput.placeholder = "https://github.com/org/repo[@版本]";
    addInput.spellcheck = false;
    const addButton = button("添加", "", () => void addRepo());
    addRow.append(addInput, addButton);
    const list = el("div", "reflist");

    addInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter") void addRepo();
    });

    // ── 数据 ────────────────────────────────────────────────

    async function refreshOverview(): Promise<void> {
        try {
            const next = await host.invoke<RefOverview>(REF_METHODS.overview);
            overview = next;
            if (selected === null && next.repos.length > 0) selected = next.repos[0].key;
            if (selected !== null && !next.repos.some((repo) => repo.key === selected)) selected = null;
        } catch (error) {
            list.replaceChildren(el("div", "empty", `读取外部仓库失败：${errText(error)}`));
            return;
        }
        renderLeft();
        renderRight();
    }

    async function refreshState(): Promise<void> {
        try {
            const next = await host.invoke<RefSyncState>(REF_METHODS.syncState);
            const wasRunning = sync?.running === true;
            sync = next;
            renderRight();
            // 刚跑完一批：列表里的「落后 N 个提交 / 最后同步」要重算
            if (wasRunning && !next.running) await refreshOverview();
        } catch (error) {
            host.toast(`读取同步状态失败：${errText(error)}`);
        }
    }

    // ── 绘制 ────────────────────────────────────────────────

    function renderLeft(): void {
        list.replaceChildren();
        if (overview === null) return;
        if (overview.repos.length === 0) {
            list.append(el("div", "empty", "diy.yaml 里还没有 source\n上面填一个仓库 URL 加进来"));
            return;
        }
        for (const repo of overview.repos) {
            const row = el("div", `entry${repo.key === selected ? " sel" : ""}`);
            row.title = repo.url;
            row.append(el("span", `dot ${repo.exists ? "on" : "off"}`));
            const name = el("span", "nm", shortName(repo));
            name.append(el("span", "", statusText(repo)));
            row.append(name);
            row.addEventListener("click", () => {
                selected = repo.key;
                renderLeft();
                // 先由外壳把右侧切到「外部仓库」，再画（isVisible 依赖它）
                host.onSelect?.();
                renderRight();
            });
            list.append(row);
        }
    }

    function renderRight(): void {
        // 右侧不归本视图时不画：否则轮询会把正在看的 app 详情整块冲掉
        if (!host.isVisible()) return;
        host.headTitle.textContent = "外部仓库";
        const running = sync?.running === true;
        host.headBadge.className = `badge ${running ? "wait" : "stop"}`;
        host.headBadge.textContent = running ? "● 同步中" : "○ 空闲";
        host.headMeta.textContent =
            overview === null
                ? ""
                : `${overview.repos.length} 个 source · ${overview.repos.filter((repo) => repo.exists).length} 个已同步 · ${overview.root}`;

        host.body.replaceChildren();

        // 概况
        const info = card("概况", el("span", "hint", "diy.yaml 里的 source → 镜像到 $DIY_HOME/ref/"));
        const dl = el("dl", "kv");
        dl.append(...kv("作用域", overview?.root ?? "—"));
        dl.append(...kv("镜像根", overview?.home ?? "—"));
        info.append(dl);
        host.body.append(info);

        // 同步
        const syncBox = card(
            `同步 · ${running ? "运行中…" : sync?.error ? "失败" : "空闲"}`,
            button(running ? "同步中…" : "全部同步", running ? "" : "pri small", () => void startSync()),
        );
        const hint = el(
            "div",
            "hint",
            "「全部同步」= 未 clone 的克隆、分支类的 git pull、tag / SHA 固定不动（写回 diy.yaml 与 .diy/ref.lock.yaml）。",
        );
        syncBox.append(hint);
        if (sync !== null && sync.error !== null) {
            syncBox.append(el("div", "hint", `错误：${sync.error}`));
        }
        const log = el("div", "log");
        const lines = sync?.lines ?? [];
        log.textContent = lines.length === 0 ? "点「全部同步」，逐仓库进度会出现在这里。" : lines.join("\n");
        syncBox.append(log);
        host.body.append(syncBox);
        requestAnimationFrame(() => {
            log.scrollTop = log.scrollHeight;
        });

        // 选中仓库详情
        const repo = overview?.repos.find((item) => item.key === selected) ?? null;
        if (repo !== null) host.body.append(renderRepoCard(repo));
    }

    function renderRepoCard(repo: RefRepo): HTMLElement {
        const box = card("仓库", el("span", "hint", repo.key));
        const dl = el("dl", "kv");
        dl.append(...kv("source", repo.url));
        dl.append(...kv("版本", repo.version === null ? "main（分支，sync 时 pull）" : repo.version));
        const dir = el("span", "", repo.dir);
        const openWrap = el("span", "open");
        openWrap.append(button("打开", "", () => void openDir(repo.dir)));
        dir.append(openWrap);
        dl.append(...kv("镜像目录", dir));
        dl.append(...kv("最后同步", repo.lastSync === null ? "—" : `${repo.lastSync}（${ago(repo.lastSync)}）`));
        dl.append(...kv("状态", statusText(repo)));
        box.append(dl);

        const acts = el("div", "acts");
        acts.append(
            button("移除注册", "danger small", () => {
                if (window.confirm(`从 diy.yaml 移除 ${shortName(repo)}？（本地镜像保留）`)) void removeRepo(repo);
            }),
        );
        box.append(acts);
        return box;
    }

    // ── 动作 ────────────────────────────────────────────────

    async function addRepo(): Promise<void> {
        const url = addInput.value.trim();
        if (url === "" || busy) return;
        busy = true;
        addButton.disabled = true;
        try {
            const result = await host.invoke<{ name: string; spec: string }>(REF_METHODS.add, { url });
            addInput.value = "";
            host.toast(`已注册：${result.name}`);
            selected = result.name.includes("/") ? findKeyOf(result.name) : selected;
            await refreshOverview();
            renderLeft();
            renderRight();
        } catch (error) {
            host.toast(`添加失败：${errText(error)}`);
        } finally {
            busy = false;
            addButton.disabled = false;
        }
    }

    function findKeyOf(name: string): string | null {
        const hit = overview?.repos.find((repo) => repo.key.endsWith(`/${name}`));
        return hit?.key ?? null;
    }

    async function removeRepo(repo: RefRepo): Promise<void> {
        try {
            await host.invoke(REF_METHODS.remove, { name: repo.key });
            host.toast(`已移除：${repo.key}`);
            if (selected === repo.key) selected = null;
            await refreshOverview();
        } catch (error) {
            host.toast(`移除失败：${errText(error)}`);
        }
    }

    async function startSync(): Promise<void> {
        if (busy) return;
        try {
            sync = await host.invoke<RefSyncState>(REF_METHODS.sync);
            renderRight();
            void refreshState();
        } catch (error) {
            host.toast(`同步启动失败：${errText(error)}`);
        }
    }

    async function openDir(path: string): Promise<void> {
        try {
            const result = await host.invoke<{ ok: boolean; reason: string }>(REF_METHODS.open, { path });
            if (!result.ok) host.toast(`打开失败：${result.reason}`);
        } catch (error) {
            host.toast(`打开失败：${errText(error)}`);
        }
    }

    return {
        mount(): void {
            host.refs.replaceChildren(addRow, list);
            renderLeft();
        },
        render(): void {
            renderLeft();
            renderRight();
        },
        async refresh(): Promise<void> {
            await Promise.all([refreshOverview(), refreshState()]);
        },
        poll(): void {
            ticks += 1;
            if (sync?.running === true) {
                void refreshState();
                return;
            }
            // 空闲：每 3 秒顺带刷一次列表（git 侧可能被终端改动过）
            if (ticks % 3 === 0) void refreshOverview();
        },
        isRunning(): boolean {
            return sync?.running === true;
        },
    };
}
