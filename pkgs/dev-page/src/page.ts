// page.ts — 主进程侧的页面插件：静态发现 + 运行时对账 + 启停 / 打开 / 跑命令。
//
// 分工（##502 第二轮；##508 从 apps/dev 搬进本包）：
//   · 静态清单：`@diy-agent/dev-core` 的 discovery（git worktree list × apps/*/app.yaml）—— 不读注册表
//   · 动态状态：dev-core 的 instances（注册表按 `(worktree, app, launch)` 对上）
//   · 动作：dev-core 的 actions（spawn / kill / 打开 / 白名单命令）
//
// renderer 只负责画 DOM 与调 `page:invoke`；spawn / kill / 读注册表都是宿主能力。

import { existsSync } from "node:fs";
import { join, resolve } from "node:path";
import { repoRootOf, type PageContribution } from "@diy-agent/workbench";
import { refMethods } from "./ref-page.js";
import {
    DevRunner,
    DEFAULT_HOME,
    DEV_METHODS,
    buildSnapshot,
    cdpUrl,
    devLogDir,
    discoverAppsIn,
    focusPid,
    isBuildCommand,
    isOpenMode,
    launchKey,
    listWorktrees,
    matchRecord,
    memoryOf,
    openPath,
    readRecords,
    registryDir,
    type AppSpec,
    type DevSnapshot,
    type LaunchRef,
} from "@diy-agent/dev-core";

const runner = new DevRunner(devLogDir());

/** 仓库根：从产物目录往上找到带 `.git` 的那一层（worktree / 主仓都能命中） */
export const REPO_ROOT = repoRootOf();

/** 静态发现的结果（每次 snapshot 都重扫：新加 app.yaml / 新开 worktree 立刻出现） */
interface Discovery {
    readonly worktrees: ReturnType<typeof listWorktrees>;
    readonly appsByWorktree: Map<string, readonly AppSpec[]>;
    /** worktree 路径 → 它所属的仓库根（多仓库合并扫描时区分归属） */
    readonly repoByWorktree: Map<string, string>;
    readonly problems: readonly string[];
}

/**
 * 额外要扫的仓库根。
 *
 * 为什么需要：`_diy` 与主仓 `diy` 是两个独立 git 仓，`git worktree list` 只看自己那个。
 * 但 dev 启动器的职责是「本机有哪些 app 可以起」—— 主仓的 apps（chat / diy-app / minimal / web）
 * 同样该出现在同一张表里。
 *
 * 来源：`DIY_DEV_EXTRA_REPOS`（冒号分隔）优先；否则默认扫同级 `../diy`（存在 apps/ 才算）。
 */
function extraRepoRoots(): string[] {
    const env = process.env["DIY_DEV_EXTRA_REPOS"];
    if (env !== undefined && env !== "") {
        return env.split(":").map((x) => x.trim()).filter((x) => x !== "");
    }
    const sibling = join(REPO_ROOT, "..", "diy");
    return existsSync(join(sibling, "apps")) ? [sibling] : [];
}

function discover(): Discovery {
    const roots = [REPO_ROOT, ...extraRepoRoots()];
    const worktrees = roots.flatMap((root) => listWorktrees(root));
    const appsByWorktree = new Map<string, readonly AppSpec[]>();
    // 归属必须在这里记：一旦 flatMap 合并，`git worktree list` 的来源就丢了 ——
    // `_diy` 与主仓 `diy` 是两个独立 git 仓，混成一张表就分不清谁是谁（UI 无法按仓库分表）。
    const repoByWorktree = new Map<string, string>();
    const problems: string[] = [];
    for (const root of roots) {
        for (const worktree of listWorktrees(root)) repoByWorktree.set(worktree.path, root);
    }
    for (const worktree of worktrees) {
        const found = discoverAppsIn(worktree.path);
        appsByWorktree.set(worktree.path, found.apps);
        problems.push(...found.problems);
    }
    return { worktrees, appsByWorktree, repoByWorktree, problems };
}

function builtOf(worktree: string): boolean {
    return existsSync(join(worktree, "build"));
}

export function snapshot(): DevSnapshot {
    const found = discover();
    return buildSnapshot(found.worktrees, {
        repoRoot: REPO_ROOT,
        worktrees: found.worktrees,
        repoOf: (worktree) => found.repoByWorktree.get(worktree) ?? REPO_ROOT,
        appsOf: (worktree) => found.appsByWorktree.get(worktree) ?? [],
        records: readRecords(registryDir()),
        starting: runner.starting(),
        problems: found.problems,
        builtOf,
        memOf: memoryOf,
        registry: registryDir(),
    });
}

/** 解析 `(worktree, app, launch)` 三元组，拿到静态声明（找不到 = 参数不对） */
function resolveLaunch(ref: LaunchRef): { app: AppSpec; launch: AppSpec["launches"][number] } | null {
    const found = discoverAppsIn(ref.worktree).apps.find((app) => app.name === ref.app);
    if (found === undefined) return null;
    const launch = found.launches.find((item) => item.id === ref.launch);
    if (launch === undefined) return null;
    return { app: found, launch };
}

function recordOf(ref: LaunchRef) {
    return readRecords(registryDir()).find((rec) => matchRecord(rec, ref)) ?? null;
}

export function startLaunch(ref: LaunchRef): { ok: boolean; pid: number | null; logFile: string; reason: string } {
    const resolved = resolveLaunch(ref);
    if (resolved === null) return { ok: false, pid: null, logFile: "", reason: `没有这个 launch：${ref.app}.${ref.launch}` };
    const started = runner.start({
        key: launchKey(ref.worktree, ref.app, ref.launch),
        appDir: resolved.app.dir,
        launch: resolved.launch,
        // 声明的数据根必须真的生效（否则 UI 按声明显示、进程按自己的缺省根跑，两边分叉）
        home: resolve(ref.worktree, resolved.launch.home ?? DEFAULT_HOME),
    });
    return {
        ok: started.pid !== null,
        pid: started.pid,
        logFile: started.logFile,
        reason: started.pid === null ? "spawn 没有拿到 pid" : `已启动（pid ${started.pid}）`,
    };
}

export async function stopLaunch(ref: LaunchRef & { pid?: number }): Promise<{ ok: boolean; killed: number[]; forced: boolean; reason: string }> {
    const resolved = resolveLaunch(ref);
    if (resolved === null) return { ok: false, killed: [], forced: false, reason: `没有这个 launch：${ref.app}.${ref.launch}` };
    const key = launchKey(ref.worktree, ref.app, ref.launch);
    // 多实例（lab/1、lab/2）：带上 pid 就精确杀那一份；不带就按 launch 找第一份
    const records = readRecords(registryDir());
    const record =
        typeof ref.pid === "number"
            ? (records.find((item) => item.pid === ref.pid) ?? null)
            : recordOf(ref);
    if (record === null && !runner.starting().has(key)) {
        return { ok: false, killed: [], forced: false, reason: "该 launch 没有在运行" };
    }
    const result = await runner.stop(key, record);
    return {
        ok: true,
        killed: result.killed,
        forced: result.forced,
        reason: `已发 SIGTERM：${result.killed.join(", ") || "（无）"}${result.forced ? "；未退出，已 SIGKILL" : ""}`,
    };
}

export function focusLaunch(ref: LaunchRef): { ok: boolean; reason: string } {
    if (resolveLaunch(ref) === null) return { ok: false, reason: `没有这个 launch：${ref.app}.${ref.launch}` };
    const record = recordOf(ref);
    if (record === null) return { ok: false, reason: "该 launch 没有在运行" };
    return focusPid(record.pid);
}

/** 打开：URL（浏览器）或某个路径（app 目录 / worktree 根 / app.yaml / 数据根） */
export function openTarget(args: unknown): { ok: boolean; reason: string } {
    const input = (args ?? {}) as {
        url?: unknown;
        which?: unknown;
        worktree?: unknown;
        app?: unknown;
        launch?: unknown;
        mode?: unknown;
    };
    if (typeof input.url === "string" && input.url !== "") {
        return openPath(input.url, "finder");
    }
    if (typeof input.worktree !== "string" || typeof input.app !== "string") {
        return { ok: false, reason: "open 需要 url 或 (worktree, app, which)" };
    }
    if (!isOpenMode(input.mode)) return { ok: false, reason: `不支持打开方式：${String(input.mode)}` };
    const apps = discoverAppsIn(input.worktree).apps;
    const app = apps.find((item) => item.name === input.app);
    if (app === undefined) return { ok: false, reason: `找不到 app：${input.app}` };
    let path: string;
    switch (input.which) {
        case "worktree":
            path = input.worktree;
            break;
        case "yaml":
            path = join(app.dir, "app.yaml");
            break;
        case "home": {
            const launch =
                typeof input.launch === "string" ? app.launches.find((item) => item.id === input.launch) : undefined;
            path = resolve(input.worktree, launch?.home ?? DEFAULT_HOME);
            break;
        }
        case "app":
        default:
            path = app.dir;
            break;
    }
    return openPath(path, input.mode);
}

/**
 * 在**某个 app 目录**里跑白名单命令。
 *
 * `launch` 可选：worktree 详情页按 app 给按钮（build / check / test / sync 都是 app 级的，
 * 不依赖某个 launch），此时 session key 用 `launch=""`，与任何具体 launch 互不干扰。
 */
export function runBuild(args: unknown): ReturnType<DevRunner["run"]> {
    const input = (args ?? {}) as { worktree?: unknown; app?: unknown; launch?: unknown; command?: unknown };
    if (typeof input.worktree !== "string" || typeof input.app !== "string" || !isBuildCommand(input.command)) {
        throw new Error(`run 参数不合法（要 worktree + app + 白名单命令）：${JSON.stringify(args)}`);
    }
    const apps = discoverAppsIn(input.worktree).apps;
    const app = apps.find((item) => item.name === input.app);
    if (app === undefined) throw new Error(`找不到 app：${input.app}`);
    const launch = typeof input.launch === "string" ? input.launch : "";
    return runner.run(launchKey(input.worktree, input.app, launch), app.dir, input.command);
}

export function revealCdp(ref: LaunchRef): { ok: boolean; reason: string } {
    const record = recordOf(ref);
    const url = cdpUrl(record?.port ?? null);
    if (url === null) return { ok: false, reason: "该实例没有可用的调试端口（未就绪 / 未注册）" };
    return openPath(url, "finder");
}

/** 主进程页面插件（workbench 的 `pages` 形状） */
export const page: PageContribution = {
    id: "dev",
    title: "dev 启动器",
    icon: "⚙",
    methods: {
        // 外部仓库（原「ref」页）并进来（##518）：同一页两个区，方法表合成一张
        ...refMethods,
        [DEV_METHODS.snapshot]: () => snapshot(),
        [DEV_METHODS.start]: (args) => startLaunch(args as LaunchRef),
        [DEV_METHODS.stop]: (args) => stopLaunch(args as LaunchRef),
        [DEV_METHODS.focus]: (args) => focusLaunch(args as LaunchRef),
        [DEV_METHODS.open]: (args) => openTarget(args),
        [DEV_METHODS.run]: (args) => runBuild(args),
        [DEV_METHODS.session]: () => runner.sessionSnapshot(),
        [DEV_METHODS.clearSession]: () => {
            runner.clearSession();
            return { ok: true, reason: "日志已清空" };
        },
        [DEV_METHODS.revealCdp]: (args) => revealCdp(args as LaunchRef),
    },
};

export default page;
