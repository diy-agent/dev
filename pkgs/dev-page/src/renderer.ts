// renderer.ts — dev 启动器的界面（纯 DOM，无框架）。
//
// 两页（##510）：顶部 tab 切换「应用」与「外部仓库」。
//   · 应用：四层树（##502 第二轮）worktree → app → launch → entries。
//   · 外部仓库：diy.yaml 里的 source + 同步（实现见 ref-view.ts）。
// 数据全部来自 `page:invoke`（主进程插件）：每秒拉一次快照，所以「启动后自己刷新成运行中」
// 不靠额外推送。分隔条来自 @diy-agent/workbench-ui 的 createSplitPane（260–520px）。

import { createSplitPane } from "@diy-agent/workbench-ui";
import { createRefView, type RefView } from "./ref-view.js";
import {
    BUILD_COMMANDS,
    DEV_METHODS,
    type BuildCommand,
    type CommandSession,
    type DevSnapshot,
    type LaunchRef,
    type LaunchStatus,
    type OpenMode,
} from "@diy-agent/dev-core/shared";

interface WorkbenchBridge {
    invoke(pageId: string, method: string, args?: unknown): Promise<unknown>;
}

declare global {
    interface Window {
        workbench?: WorkbenchBridge;
    }
}

function requireEl(id: string): HTMLElement {
    const node = document.getElementById(id);
    if (node === null) throw new Error(`index.html 缺 #${id}`);
    return node;
}

const bridge = window.workbench;
if (!bridge) throw new Error("preload 桥没注入 window.workbench");
const tree = requireEl("tree");
const body = requireEl("body");
const runningLabel = requireEl("running");
const repoLabel = requireEl("repo");
const headTitle = requireEl("head-title");
const headBadge = requireEl("head-badge");
const headMeta = requireEl("head-meta");
const toastLabel = requireEl("toast");
const filterToggle = requireEl("filter-running");
const gateway = bridge;

async function invoke<T>(method: string, args?: unknown): Promise<T> {
    return (await gateway.invoke("dev", method, args)) as T;
}

let snapshot: DevSnapshot | null = null;
let session: CommandSession | null = null;
let selectedKey: string | null = null;
/** worktree 详情：点分支名进入（右栏看该 worktree 的 app / launch / 命令）。与 selectedKey 二选一 */
let selectedWorktree: string | null = null;
/** 当前页签（应用 / 外部仓库）；两侧轮询与绘制按它分流 */
let mode: "app" | "ref" = "app";
let polling = false;
/** 「只显示运行中」过滤（titlebar 的 toggle；只影响左侧树） */
let onlyRunning = false;

const FILTER_KEY = "dev.onlyRunning";
try {
    onlyRunning = window.localStorage.getItem(FILTER_KEY) === "1";
} catch {
    onlyRunning = false;
}

// ── DOM 小工具 ───────────────────────────────────────────────

/**
 * 配色规则：**行（分支）决定色相，列（app）决定明度阶梯**。
 *
 * 理由（用户裁定）：矩阵里最需要「一眼分清谁是谁」的是**分支**——同一 app 在不同分支上
 * 长得一模一样，靠列色区分反而把人绕晕。所以：
 *   · 每个分支一个色相（行内所有格子共享，跨行不重复）
 *   · 列只做明度递减（色阶），同一行内也能看出格子属于第几列，但不抢分支的辨识度
 */
const BRANCH_HUES = [210, 25, 145, 275, 45, 190, 330, 100, 250, 0, 165, 300];

/**
 * 第 i 列的明度（%）：越靠右越深，但**只做浅色域的微差**。
 *
 * 跨度必须收窄（总跨度 ≤ 18）：色阶一深，色相就看不出来了，分支的辨识度反而被列抢走。
 * 实测 92→44（原来的算法）后半段变成深色块，和「主要分辨分支」的意图正好相反。
 */
function columnLightness(index: number, total: number): number {
    if (total <= 1) return 94;
    const span = Math.min(4.5, 18 / (total - 1));
    return Math.round(94 - index * span);
}

/** 路径最后一段（renderer 是浏览器侧，不能用 node:path） */
function basename(path: string): string {
    return path.split(/[\\/]/).filter((seg) => seg !== "").pop() ?? path;
}

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

function kv(label: string, value: Node | string): [HTMLElement, HTMLElement] {
    const dt = el("dt", "", label);
    const dd = el("dd");
    if (typeof value === "string") dd.textContent = value;
    else dd.append(value);
    return [dt, dd];
}

function formatUptime(ms: number): string {
    const sec = Math.floor(ms / 1000);
    if (sec < 60) return `${sec} 秒`;
    const min = Math.floor(sec / 60);
    if (min < 60) return `${min} 分钟`;
    const hour = Math.floor(min / 60);
    if (hour < 48) return `${hour} 小时 ${min % 60} 分`;
    return `${Math.floor(hour / 24)} 天 ${hour % 24} 小时`;
}

function formatBytes(bytes: number | null): string {
    if (bytes === null) return "—";
    return `${Math.round(bytes / (1024 * 1024))} MB`;
}

function formatStartedAt(iso: string): string {
    const at = new Date(iso);
    if (Number.isNaN(at.getTime())) return iso || "—";
    const pad = (n: number): string => String(n).padStart(2, "0");
    return `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())} ${pad(at.getHours())}:${pad(at.getMinutes())}:${pad(at.getSeconds())}`;
}

function copyText(text: string): void {
    const fallback = (): void => {
        const area = document.createElement("textarea");
        area.value = text;
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.append(area);
        area.select();
        try {
            document.execCommand("copy");
        } catch {
            /* 两条路都失败：原文仍在面板上，可手动选中 */
        }
        area.remove();
    };
    if (navigator.clipboard === undefined) {
        fallback();
        return;
    }
    void navigator.clipboard.writeText(text).catch(fallback);
}

let toastTimer: number | undefined;
function toast(message: string): void {
    toastLabel.textContent = message;
    if (toastTimer !== undefined) window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => {
        toastLabel.textContent = "";
    }, 5000);
}

function refOf(launch: LaunchStatus): LaunchRef {
    return { worktree: launch.worktree, app: launch.app, launch: launch.launch };
}

function openUrl(url: string): void {
    void invoke<{ ok: boolean; reason: string }>(DEV_METHODS.open, { url })
        .then((result) => toast(result.ok ? `已打开：${result.reason}` : `打开失败：${result.reason}`))
        .catch((error: unknown) => toast(`打开失败：${String(error)}`));
}

function openDir(launch: LaunchStatus, which: "app" | "worktree" | "home" | "yaml", mode: OpenMode): void {
    void invoke<{ ok: boolean; reason: string }>(DEV_METHODS.open, {
        worktree: launch.worktree,
        app: launch.app,
        launch: launch.launch,
        which,
        mode,
    })
        .then((result) => toast(result.ok ? `已打开：${result.reason}` : `打开失败：${result.reason}`))
        .catch((error: unknown) => toast(`打开失败：${String(error)}`));
}

// ── 左侧树 ───────────────────────────────────────────────────

function hoverActions(launch: LaunchStatus): HTMLElement {
    const acts = el("div", "acts");
    if (launch.running) {
        acts.append(
            button("聚焦", "", () => void focusLaunch(launch)),
            button("关闭", "stop", () => void stopLaunch(launch)),
        );
    } else if (launch.starting) {
        acts.append(el("span", "hint", "启动中…"));
    } else {
        acts.append(button("启动", "", () => void startLaunch(launch)));
    }
    return acts;
}

interface WorktreeGroup {
    readonly worktree: string;
    readonly sample: LaunchStatus;
    readonly apps: Map<string, LaunchStatus[]>;
}

/** 按 worktree → app 分组，保持快照里的出现顺序 */
function groupByWorktree(launches: readonly LaunchStatus[]): WorktreeGroup[] {
    const byWorktree = new Map<string, Map<string, LaunchStatus[]>>();
    const order: string[] = [];
    for (const launch of launches) {
        let apps = byWorktree.get(launch.worktree);
        if (apps === undefined) {
            apps = new Map();
            byWorktree.set(launch.worktree, apps);
            order.push(launch.worktree);
        }
        const list = apps.get(launch.app);
        if (list === undefined) apps.set(launch.app, [launch]);
        else list.push(launch);
    }
    return order
        .map((worktree) => {
            const apps = byWorktree.get(worktree);
            const sample = apps === undefined ? undefined : [...apps.values()][0]?.[0];
            return sample === undefined || apps === undefined ? null : { worktree, sample, apps };
        })
        .filter((item): item is WorktreeGroup => item !== null);
}

/** 该 app 列的色相（同一 app 在表头与所有单元格里用同一个色相，方便横向对位） */
/**
 * 一个 launch 的 chip：**单击只选中**（看详情），启停交给悬停出现的按钮。
 *
 * 为什么不再「单击即启停」（##518）：chip 同时是选中入口，想读详情的人一按就把 app 起来/杀掉，
 * 误操作代价太大；启停是破坏性动作，必须落在明确的按钮上。
 */
function launchChip(launch: LaunchStatus, hue: number): HTMLElement {
    const cls = [
        "chip",
        launch.running ? "on" : "",
        launch.starting ? "wait" : "",
        launch.built ? "" : "unbuilt",
        launch.configIssues.length > 0 ? "warn" : "",
        launch.key === selectedKey ? "sel" : "",
    ]
        .filter((s) => s !== "")
        .join(" ");
    const chip = el("button", cls);
    chip.type = "button";
    chip.dataset["key"] = launch.key;
    chip.style.setProperty("--h", String(hue));
    chip.title = `${launch.worktree} · apps/${launch.app} · ${launch.launch}\n${launch.command}\n${
        launch.starting ? "启动中…" : launch.running ? "运行中" : "未启动"
    }${launch.configIssues.length > 0 ? `\n⚠ ${launch.configIssues.map((item) => item.message).join("\n⚠ ")}` : ""}\n点击看详情`;
    chip.append(el("span", `dot ${launch.running ? "on" : launch.starting ? "wait" : "off"}`));
    chip.append(el("span", "chip-nm", launch.launch));
    chip.addEventListener("click", (event) => {
        event.stopPropagation();
        selectedKey = launch.key;
        selectedWorktree = null;
        render();
    });
    return chip;
}

/** 单元格 = chip + 悬停才出现的启停按钮（破坏性动作不藏在单击里） */
function launchCell(launch: LaunchStatus, hue: number): HTMLElement {
    const wrap = el("span", "cx-launch");
    wrap.append(launchChip(launch, hue));
    wrap.append(hoverActions(launch));
    return wrap;
}

function renderTree(): void {
    tree.replaceChildren();
    if (snapshot === null) return;

    if (snapshot.launches.length === 0) {
        tree.append(el("div", "empty", "（清单为空）"));
        return;
    }
    // 「只显示运行中」= 只隐藏**未运行的单元格**，行（worktree）与列（app）都保留：
    // 否则想找出「哪个没跑」得先关过滤，且整个 worktree 会从眼前消失（##518）
    renderTreeCross(groupByWorktree(snapshot.launches));
}

/**
 * 交叉表视图：**行 = 分支（worktree），列 = app，cell = 该组合下的 launch**。
 *
 * 一张表一个仓库 —— 本机同时扫多个 git 仓（`_diy` 与主仓 `diy` 各是独立仓、各有 worktree），
 * 混进同一张表时分不清某条分支属于谁，所以按 `launch.repo` 拆开，每个仓库一个可折叠区块。
 */
function renderTreeCross(groups: readonly WorktreeGroup[]): void {
    // 按仓库分组，保持第一次出现的顺序
    const byRepo = new Map<string, WorktreeGroup[]>();
    for (const group of groups) {
        const list = byRepo.get(group.sample.repo);
        if (list === undefined) byRepo.set(group.sample.repo, [group]);
        else list.push(group);
    }

    let repoIndex = 0;
    for (const [repo, repoGroups] of byRepo) {
        // 列 = 该仓库下 app 名并集（按首次出现排序，避免每次刷新列序跳动）
        const columns: string[] = [];
        const seen = new Set<string>();
        for (const group of repoGroups) {
            for (const appName of group.apps.keys()) {
                if (!seen.has(appName)) {
                    seen.add(appName);
                    columns.push(appName);
                }
            }
        }
        // 列只决定明度阶梯（见 columnLightness）；色相跟行走
        const lightOf = (colIndex: number): number => columnLightness(colIndex, columns.length);
        void repoIndex;

        const section = el("section", "cx-sec");
        // 标题即折叠开关：仓库名 + 分支数 / app 数
        const head = el("button", "cx-head");
        head.type = "button";
        head.title = repo;
        head.append(el("span", "cx-arrow", collapsed.has(repo) ? "▸" : "▾"));
        head.append(el("span", "cx-repo-nm", basename(repo)));
        head.append(el("span", "cx-meta", `${repoGroups.length} 分支 · ${columns.length} app`));
        head.addEventListener("click", () => {
            if (collapsed.has(repo)) collapsed.delete(repo);
            else collapsed.add(repo);
            saveCollapsed();
            renderTree();
        });
        section.append(head);

        if (!collapsed.has(repo)) {
            const table = el("table", "cx");
            const thead = table.createTHead();
            const headRow = thead.insertRow();
            headRow.append(el("th", "cx-br", "分支"));
            columns.forEach((col, i) => {
                const th = el("th", "cx-col", col);
                th.title = `apps/${col}`;
                th.style.setProperty("--l", String(lightOf(i)));
                headRow.append(th);
            });

            const body = table.createTBody();
            for (const [rowIndex, group] of repoGroups.entries()) {
                const row = body.insertRow();
                // 每个分支一个色相：同表内按行序轮转色板，保证相邻行不同色
                const rowHue = BRANCH_HUES[rowIndex % BRANCH_HUES.length] ?? 210;
                const branchCell = el("th", "cx-br");
                branchCell.style.setProperty("--h", String(rowHue));
                if (group.worktree === selectedWorktree) branchCell.classList.add("sel");
                // 分支名可点：进该 worktree 的详情页（不点 launch 也能 build / sync / 看详情）
                const branchBtn = el("button", "cx-br-btn", group.sample.branch ?? basename(group.sample.worktree));
                branchBtn.type = "button";
                branchBtn.title = `${group.sample.worktreePath}\n点击查看该 worktree 详情`;
                branchBtn.addEventListener("click", () => {
                    selectedWorktree = group.worktree;
                    selectedKey = null;
                    render();
                });
                branchCell.append(branchBtn);
                row.append(branchCell);
                columns.forEach((col, i) => {
                    const cell = row.insertCell();
                    cell.className = "cx-cell";
                    cell.style.setProperty("--h", String(rowHue));
                    cell.style.setProperty("--l", String(lightOf(i)));
                    const launches = group.apps.get(col);
                    if (launches === undefined) {
                        cell.classList.add("na");
                        return;
                    }
                    const shown = launches.filter((item) => !onlyRunning || item.running || item.starting);
                    if (shown.length === 0) {
                        // 过滤态下的空格子：不显示 chip，但仍可从分支详情页启动
                        cell.classList.add("na");
                        return;
                    }
                    for (const launch of shown) cell.append(launchCell(launch, rowHue));
                });
            }
            section.append(table);
        }
        tree.append(section);
    }
}

/** 折叠状态：按仓库根路径记（localStorage；隐私模式下降级为本次会话） */
const collapsed = new Set<string>();
const COLLAPSE_KEY = "dev.collapsedRepos";
try {
    const raw = window.localStorage.getItem(COLLAPSE_KEY);
    if (raw !== null) for (const repo of JSON.parse(raw) as string[]) collapsed.add(repo);
} catch {
    /* 忽略：折叠状态丢了不影响功能 */
}

function saveCollapsed(): void {
    try {
        window.localStorage.setItem(COLLAPSE_KEY, JSON.stringify([...collapsed]));
    } catch {
        /* 隐私模式：本次会话内生效即可 */
    }
}

/** worktree 行的名字：目录名（分支名与目录名不同时补在括号里） */
function worktreeName(launch: LaunchStatus): string {
    const base = launch.worktreePath.split("/").filter(Boolean).pop() ?? launch.worktreePath;
    return launch.branch !== null && launch.branch !== base ? `${base}（${launch.branch}）` : base;
}

// ── 右侧详情 ─────────────────────────────────────────────────

function openButtons(launch: LaunchStatus, which: "app" | "worktree" | "home" | "yaml"): HTMLElement {
    const wrap = el("span", "open");
    const modes: readonly (readonly [string, OpenMode])[] = [
        ["open", "finder"],
        ["VS Code", "editor"],
        ["终端", "terminal"],
    ];
    for (const [label, mode] of modes) wrap.append(button(label, "", () => openDir(launch, which, mode)));
    return wrap;
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

/** 配置错误卡：错在哪 + 怎么改 + 打开 app.yaml（配置错不该默默按缺省跑） */
function renderConfigCard(launch: LaunchStatus): HTMLElement | null {
    if (launch.configIssues.length === 0) return null;
    const box = card("⚠ 配置问题（app.yaml 需要修）", el("span", "hint", `${String(launch.configIssues.length)} 条`));
    for (const issue of launch.configIssues) {
        const item = el("div", "cfgissue");
        item.append(el("div", "cfgmsg", issue.message));
        item.append(el("div", "cfgfix", `修法：${issue.fix}`));
        box.append(item);
    }
    const acts = el("div", "cmdgrid");
    acts.append(button("打开 app.yaml", "", () => openDir(launch, "yaml", "editor")));
    box.append(acts);
    return box;
}

function renderEntriesCard(launch: LaunchStatus): HTMLElement | null {
    if (launch.entries.length === 0) return null;
    const box = card("入口", el("span", "hint", "静态声明（app.yaml）"));
    const list = el("dl", "kv");
    for (const entry of launch.entries) {
        const value = el("span");
        if (entry.kind === "web" && entry.href !== null) {
            const link = el("a", "link", entry.href);
            link.href = "#";
            link.addEventListener("click", (event) => {
                event.preventDefault();
                openUrl(entry.href ?? "");
            });
            value.append(link);
            if (entry.portMismatch && entry.configuredUrl !== null) {
                value.append(el("span", "muted", `（配置 ${entry.configuredUrl}）`));
            }
        } else {
            value.append(document.createTextNode(entry.title ?? "Electron 窗口"));
            value.append(el("span", "muted", "（桌面窗口，用「聚焦」拉前台）"));
        }
        list.append(...kv(entry.kind === "web" ? "浏览器" : "窗口", value));
    }
    box.append(list);
    return box;
}

function renderUriCard(launch: LaunchStatus): HTMLElement {
    const box = card("实例 URI（出问题时 copy 给 agent）");
    const uri = el("div", "uri");
    if (launch.uri === null) {
        uri.append(
            document.createTextNode(`—（数据根还没有 instance-id：${launch.home}）`),
        );
    } else {
        uri.append(document.createTextNode(launch.uri));
        uri.append(
            button("复制", "", () => {
                copyText(launch.uri ?? "");
                toast("实例 URI 已复制");
            }),
        );
    }
    box.append(uri);
    return box;
}

function renderParamsCard(launch: LaunchStatus): HTMLElement {
    const box = card("启动参数", el("span", "hint", `launch ${launch.launch}`));
    const list = el("dl", "kv");
    list.append(...kv("标题", launch.launchTitle));
    list.append(...kv("启动命令", launch.command));
    // 环境变量（app.yaml 的 env；没有就如实写「无」）
    const envKeys = Object.keys(launch.env);
    list.append(
        ...kv(
            "环境变量",
            envKeys.length === 0
                ? "—（app.yaml 未声明）"
                : envKeys.map((key) => `${key}=${launch.env[key]}`).join("  "),
        ),
    );
    const dir = el("span", "", launch.appDir);
    dir.append(openButtons(launch, "app"));
    list.append(...kv("工作目录", dir));
    const home = el("span", "", launch.home);
    home.append(openButtons(launch, "home"));
    list.append(...kv("数据根", home));
    const yaml = el("span", "", launch.yamlPath);
    yaml.append(openButtons(launch, "yaml"));
    list.append(...kv("app.yaml", yaml));
    const wt = el("span", "", launch.worktree);
    wt.append(openButtons(launch, "worktree"));
    list.append(...kv("worktree", wt));
    list.append(...kv("构建状态", launch.built ? "已构建（有 build/ 产物）" : "未构建（先用下面的「构建」）"));
    box.append(list);
    return box;
}

function renderRuntimeCard(launch: LaunchStatus): HTMLElement {
    const runtime = launch.runtime;
    if (runtime === null) {
        const box = card("运行时", el("span", "hint", launch.starting ? "启动中" : "未启动"));
        box.append(
            el(
                "div",
                "hint",
                launch.starting
                    ? "进程已拉起，正在等待它写实例注册表……"
                    : launch.built
                      ? "点左上「启动」把它拉起来。"
                      : "该 worktree 还没构建过 —— 先点下面「构建」，再启动。",
            ),
        );
        if (!launch.starting) box.append(button("启动", "pri", () => void startLaunch(launch)));
        return box;
    }
    const box = card("运行时", el("span", "hint", `已运行 ${formatUptime(runtime.uptimeMs)}`));
    const list = el("dl", "kv");
    const pidValue = el("span", "", String(runtime.pid));
    const copy = el("span", "open");
    copy.append(
        button("copy", "", () => {
            copyText(String(runtime.pid));
            toast("PID 已复制");
        }),
    );
    pidValue.append(copy);
    list.append(...kv("PID", pidValue));
    list.append(...kv("端口", runtime.port === null ? "—（未回填）" : String(runtime.port)));
    list.append(...kv("启动于", formatStartedAt(runtime.startedAt)));
    list.append(...kv("内存", formatBytes(runtime.memBytes)));
    list.append(...kv("命令行", runtime.cmdline || "—"));
    list.append(...kv("数据根", runtime.diyHome || "—"));
    box.append(list);
    const acts = el("div", "acts");
    acts.append(
        button("聚焦窗口", "pri", () => void focusLaunch(launch)),
        button("重启", "", () => void restartLaunch(launch)),
        button("打开 CDP", "", () => {
            void invoke<{ ok: boolean; reason: string }>(DEV_METHODS.revealCdp, refOf(launch))
                .then((result) => toast(result.ok ? `已打开：${result.reason}` : `打不开 CDP：${result.reason}`))
                .catch((error: unknown) => toast(`打不开 CDP：${String(error)}`));
        }),
        button("停止", "danger", () => void stopLaunch(launch)),
    );
    box.append(acts);
    return box;
}

function renderBuildCard(launch: LaunchStatus): HTMLElement {
    const box = card("构建与检查", el("span", "hint", `在 ${launch.appDir} 下执行`));
    if (!launch.built) {
        const hint = el("div", "hint", "该 worktree 还没有 build/ 目录（未构建）—— 建议先跑 build。");
        box.append(hint);
    }
    const grid = el("div", "cmdgrid");
    for (const command of BUILD_COMMANDS) {
        grid.append(button(command, "", () => void runCommand(launch, command)));
    }
    box.append(grid);
    return box;
}

function renderLogCard(): HTMLElement {
    const clear = button("清空", "small", () => {
        void invoke(DEV_METHODS.clearSession).then(() => {
            session = null;
            render();
        });
    });
    const status = session === null ? "（还没有输出）" : session.running ? "运行中…" : "已结束";
    const box = card(`日志 · ${status}`, clear);
    const log = el("div", "log");
    if (session === null || session.lines.length === 0) {
        log.textContent = session === null ? "点上面的构建按钮，输出会出现在这里。" : "";
    } else {
        log.textContent = session.lines.slice(-300).join("\n");
        requestAnimationFrame(() => {
            log.scrollTop = log.scrollHeight;
        });
    }
    box.append(log);
    return box;
}

/** worktree 详情的一个 app 节：launch 列表（启/停/聚焦）+ app 级命令 */
function renderAppSection(group: WorktreeGroup, appName: string, launches: readonly LaunchStatus[]): HTMLElement {
    const sample = launches[0];
    const running = launches.filter((item) => item.running).length;
    const issues = launches.reduce((n, item) => n + item.configIssues.length, 0);
    const box = card(
        `apps/${appName}${sample?.appTitle !== undefined ? ` · ${sample.appTitle}` : ""}`,
        el("span", issues > 0 ? "hint bad" : "hint", issues > 0 ? `⚠ ${String(issues)} 条配置问题` : launches.length === 1 ? (running > 0 ? "运行中" : "未启动") : `${running}/${launches.length} 在跑`),
    );

    // launch 行：状态点 + launch id + 命令 + 启停/聚焦
    const rows = el("div", "wt-launches");
    for (const launch of launches) {
        const row = el("div", "wt-launch");
        row.append(el("span", `dot ${launch.running ? "on" : launch.starting ? "wait" : "off"}`));
        const name = el("button", "wt-launch-nm", launch.launch);
        name.type = "button";
        name.title = `${launch.command}\n点击看这条 launch 的详情`;
        name.addEventListener("click", () => {
            selectedWorktree = null;
            selectedKey = launch.key;
            render();
        });
        row.append(name);
        row.append(el("span", "wt-launch-cmd", launch.command));
        row.append(el("span", "wt-launch-uri", launch.uri ?? "—"));
        if (launch.configIssues.length > 0) {
            const warn = el("button", "wt-warn", `⚠ ${String(launch.configIssues.length)}`);
            warn.type = "button";
            warn.title = launch.configIssues.map((issue) => issue.message).join("\n");
            warn.addEventListener("click", () => {
                selectedWorktree = null;
                selectedKey = launch.key;
                render();
            });
            row.append(warn);
        }
        const acts = el("span", "acts");
        if (launch.running) {
            acts.append(
                button("聚焦", "small", () => void focusLaunch(launch)),
                button("停止", "small stop", () => void stopLaunch(launch)),
            );
        } else if (launch.starting) {
            acts.append(el("span", "hint", "启动中…"));
        } else {
            acts.append(button("启动", "small", () => void startLaunch(launch)));
        }
        row.append(acts);
        rows.append(row);
    }
    box.append(rows);

    // 命令：app 级（不依赖某条 launch），输出进下面的日志卡
    const grid = el("div", "cmdgrid");
    for (const command of BUILD_COMMANDS) {
        grid.append(button(command, "", () => void runAppCommand(group.worktree, appName, command)));
    }
    box.append(grid);
    return box;
}

/** worktree 详情页：路径 / 分支 / 仓库 + 该 worktree 下每个 app 的 launch 与命令 */
function renderWorktreeDetail(worktree: string): void {
    const group = groupByWorktree(snapshot?.launches ?? []).find((item) => item.worktree === worktree);
    if (group === undefined) {
        body.append(el("div", "empty", "这个 worktree 已经不在清单里了（刷新后重选）"));
        return;
    }
    const sample = group.sample;
    const running = [...group.apps.values()].flat().filter((item) => item.running).length;
    headTitle.textContent = worktreeName(sample);
    headBadge.className = `badge ${running > 0 ? "run" : "stop"}`;
    headBadge.textContent = running > 0 ? `● ${running} 个在跑` : "○ 全部未启动";
    headMeta.textContent = sample.worktreePath;

    const info = card("worktree", el("span", "hint", `${group.apps.size} 个 app`));
    const list = el("dl", "kv");
    list.append(...kv("路径", sample.worktreePath));
    list.append(...kv("分支", sample.branch ?? "（detached HEAD）"));
    list.append(...kv("仓库", sample.repo));
    list.append(...kv("构建状态", sample.built ? "已构建（有 build/ 产物）" : "未构建"));
    const open = el("span", "open");
    for (const [label, mode] of [
        ["open", "finder"],
        ["VS Code", "editor"],
        ["终端", "terminal"],
    ] as const) open.append(button(label, "", () => openDir(sample, "worktree", mode)));
    list.append(...kv("打开", open));
    info.append(list);
    body.append(info);

    for (const [appName, launches] of group.apps) body.append(renderAppSection(group, appName, launches));
    body.append(renderLogCard());
}

function renderDetail(): void {
    body.replaceChildren();
    if (snapshot === null) return;
    if (selectedWorktree !== null) {
        renderWorktreeDetail(selectedWorktree);
        return;
    }
    const launch = snapshot.launches.find((item) => item.key === selectedKey) ?? null;
    if (launch === null) {
        body.append(el("div", "empty", "左侧选一个启动项（点分支名可看整个 worktree）"));
        return;
    }
    headTitle.textContent = `${launch.app} · ${launch.launchTitle}`;
    headBadge.className = `badge ${launch.running ? "run" : launch.starting ? "wait" : "stop"}`;
    headBadge.textContent = launch.running ? "● 运行中" : launch.starting ? "● 启动中" : "○ 未启动";
    headMeta.textContent =
        launch.running && launch.runtime !== null
            ? `PID ${launch.runtime.pid}${launch.runtime.port === null ? "" : ` · :${launch.runtime.port}`}`
            : launch.command;
    const config = renderConfigCard(launch);
    if (config !== null) body.append(config);
    const entries = renderEntriesCard(launch);
    if (entries !== null) body.append(entries);
    body.append(
        renderUriCard(launch),
        renderParamsCard(launch),
        renderRuntimeCard(launch),
        renderBuildCard(launch),
        renderLogCard(),
    );
}

/** 上一次画出来的样子：内容没变就不重绘（1s 轮询不该把滚动 / hover / 焦点冲掉） */
let lastPaint = "";

function render(): void {
    // 「外部仓库」页不归本函数画；轮询的旧结果晚到也不该盖掉它
    if (mode !== "app") return;
    const issueCount = snapshot?.launches.reduce((n, item) => n + item.configIssues.length, 0) ?? 0;
    // 指纹里要把**每次都变**的运行时数字抹平：uptime 精确到 5s、内存到 8MB。
    // 否则 1s 轮询永远“内容变了”，重绘照旧，滚动位置白保（##518 自检时踩到）。
    const paint = JSON.stringify([mode, snapshot, selectedKey, selectedWorktree, onlyRunning, session?.lines.length ?? -1], (key, value) => {
        if (key === "uptimeMs" && typeof value === "number") return Math.round(value / 5000);
        if (key === "memBytes" && typeof value === "number") return Math.round(value / 8_000_000);
        return value;
    });
    if (paint === lastPaint) return;
    lastPaint = paint;
    if (snapshot !== null) {
        runningLabel.textContent = `${snapshot.runningCount} 个在跑`;
        repoLabel.textContent = `${snapshot.worktreeCount} worktree · ${snapshot.appCount} app${issueCount > 0 ? ` · ⚠ ${String(issueCount)} 配置问题` : ""}`;
        const problems = [...snapshot.problems, ...snapshot.launches.flatMap((item) => item.configIssues.map((issue) => `${item.app}.${item.launch}：${issue.message}`))];
        repoLabel.title = problems.length > 0 ? problems.join("\n") : "";
        repoLabel.classList.toggle("bad", issueCount > 0);
    }
    const treeTop = tree.scrollTop;
    const bodyTop = body.scrollTop;
    renderTree();
    renderDetail();
    tree.scrollTop = treeTop;
    body.scrollTop = bodyTop;
}

// ── 动作 ─────────────────────────────────────────────────────

async function startLaunch(launch: LaunchStatus): Promise<void> {
    try {
        const result = await invoke<{ ok: boolean; reason: string }>(DEV_METHODS.start, refOf(launch));
        toast(result.ok ? `已启动：${result.reason}` : `启动失败：${result.reason}`);
    } catch (error) {
        toast(`启动失败：${String(error)}`);
    }
    await refresh();
}

async function stopLaunch(launch: LaunchStatus): Promise<void> {
    try {
        const result = await invoke<{ ok: boolean; reason: string; forced: boolean }>(DEV_METHODS.stop, refOf(launch));
        toast(result.reason);
    } catch (error) {
        toast(`停止失败：${String(error)}`);
    }
    await refresh();
}

async function restartLaunch(launch: LaunchStatus): Promise<void> {
    await invoke(DEV_METHODS.stop, refOf(launch));
    await invoke(DEV_METHODS.start, refOf(launch));
    await refresh();
}

async function focusLaunch(launch: LaunchStatus): Promise<void> {
    try {
        const result = await invoke<{ ok: boolean; reason: string }>(DEV_METHODS.focus, refOf(launch));
        toast(result.ok ? `已聚焦：${result.reason}` : `聚焦失败：${result.reason}`);
    } catch (error) {
        toast(`聚焦失败：${String(error)}`);
    }
}

async function runCommand(launch: LaunchStatus, command: BuildCommand): Promise<void> {
    try {
        session = await invoke<CommandSession>(DEV_METHODS.run, { ...refOf(launch), command });
        render();
    } catch (error) {
        toast(`命令启动失败：${String(error)}`);
    }
}

/** worktree 详情里的命令：app 级（不带 launch）；输出进同一张日志卡 */
async function runAppCommand(worktree: string, app: string, command: BuildCommand): Promise<void> {
    try {
        session = await invoke<CommandSession>(DEV_METHODS.run, { worktree, app, command });
        render();
    } catch (error) {
        toast(`命令启动失败：${String(error)}`);
    }
}

// ── 轮询 ─────────────────────────────────────────────────────

async function refresh(): Promise<void> {
    if (polling) return;
    polling = true;
    try {
        const [next, nextSession] = await Promise.all([
            invoke<DevSnapshot>(DEV_METHODS.snapshot),
            invoke<CommandSession | null>(DEV_METHODS.session),
        ]);
        snapshot = next;
        session = nextSession;
        // 选中态三态：worktree 详情（优先级高） / 单条 launch / 未选
        if (selectedWorktree !== null && !next.launches.some((item) => item.worktree === selectedWorktree)) {
            selectedWorktree = null;
        }
        if (selectedWorktree === null && selectedKey === null && next.launches.length > 0) {
            selectedKey = next.launches[0].key;
        }
        if (selectedKey !== null && !next.launches.some((item) => item.key === selectedKey)) selectedKey = null;
        render();
    } catch (error) {
        body.replaceChildren(el("div", "empty", `读取清单失败：${String(error)}`));
    } finally {
        polling = false;
    }
}

// ── 挂载 ─────────────────────────────────────────────────────

const side = requireEl("side");
const split = createSplitPane(side, { min: 260, max: 520, initial: 360, storageKey: "dev.splitWidth" });
split.handle.id = "split";
side.after(split.handle);

// 「只显示运行中」：只改左侧树的可见集，选中项与右侧面板不动
function syncFilterToggle(): void {
    filterToggle.setAttribute("aria-pressed", onlyRunning ? "true" : "false");
    filterToggle.classList.toggle("on", onlyRunning);
    filterToggle.textContent = onlyRunning ? "只显示运行中 · 开" : "只显示运行中";
}
filterToggle.addEventListener("click", () => {
    onlyRunning = !onlyRunning;
    try {
        window.localStorage.setItem(FILTER_KEY, onlyRunning ? "1" : "0");
    } catch {
        /* 隐私模式：本次会话内生效即可 */
    }
    syncFilterToggle();
    renderTree();
});
syncFilterToggle();

// ── 页签：应用 / 外部仓库（##510） ─────────────────────────────

const tabApp = requireEl("tab-app");
const tabRef = requireEl("tab-ref");
const MODE_KEY = "dev.mode";

try {
    mode = window.localStorage.getItem(MODE_KEY) === "ref" ? "ref" : "app";
} catch {
    mode = "app";
}

/** 外部仓库页的宿主：它只拿容器与桥，不反向依赖本文件的绘制逻辑 */
const refView: RefView = createRefView({
    tree,
    body,
    headTitle,
    headBadge,
    headMeta,
    invoke: <T>(method: string, args?: unknown): Promise<T> => gateway.invoke("ref", method, args) as Promise<T>,
    toast,
});

function applyMode(next: "app" | "ref"): void {
    mode = next;
    try {
        window.localStorage.setItem(MODE_KEY, next);
    } catch {
        /* 隐私模式：本次会话内生效即可 */
    }
    tabApp.classList.toggle("on", next === "app");
    tabRef.classList.toggle("on", next === "ref");
    // 「只显示运行中」是应用页的过滤，外部仓库页没有它
    filterToggle.style.display = next === "app" ? "" : "none";
    if (next === "app") {
        void refresh();
    } else {
        // 外部仓库页会把 body 整个换掉：作废“上一次画的样子”，切回应用页时才会重画
        lastPaint = "";
        headTitle.textContent = "外部仓库";
        headBadge.className = "badge stop";
        headBadge.textContent = "—";
        headMeta.textContent = "";
        refView.mount();
        void refView.refresh();
    }
}

tabApp.addEventListener("click", () => applyMode("app"));
tabRef.addEventListener("click", () => applyMode("ref"));

applyMode(mode);
setInterval(() => {
    if (mode === "ref") refView.poll();
    else void refresh();
}, 1000);
