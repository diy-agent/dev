/**
 * client.ts —— dev 的**领域式 rpc 客户端**（##518 用户口径：UI 与 core 用 rpc 隔离，
 * UI 侧对这一堆方法名做一层领域封装，组件里不再出现字符串方法名）。
 *
 * 为什么要有这一层（而不是组件里到处 `invoke("start", {...})`）：
 *   1. **协议只在一个文件里**：主进程改了方法名 / 入参形状，编译期就在这层报错，
 *      而不是运行期在某个按钮里静默失败（前面真踩过：`Unknown method` 只在点开页签时才炸）；
 *   2. **入参收敛**：`LaunchRef` 这类结构由客户端补全/校验，组件只传业务语义（哪条 launch、哪个命令）；
 *   3. **可替换**：UI 包不 import core 的实现，只有类型；将来 core 换成 HTTP / 进程外插件，
 *      改这一个文件即可。
 *
 * 隔离边界：本包**只允许** import `@diy-agent/dev-core/shared` 的**类型**（编译后擦除），
 * 以及 `dev-fs/api` 的 schema（dev-fs 由 preload 递出的 transport 直连，不经 page 桥）。
 */

import type {
    BuildCommand,
    CommandSession,
    DevSnapshot,
    LaunchRef,
    OpenMode,
    RefOverview,
    RefSyncState,
} from "@diy-agent/dev-core/shared";
import { DEV_METHODS, REF_METHODS } from "@diy-agent/dev-core/shared";

/** 页面桥（workbench 宿主注入）：`pageId` = 本页插件 id */
export interface PageBridge {
    invoke(pageId: string, method: string, args?: unknown): Promise<unknown>;
}

/** 打开目录 / URL 的参数（与主进程 `open` 的入参一致） */
export interface OpenTarget {
    readonly worktree: string;
    readonly app: string;
    readonly launch: string;
    readonly which: "app" | "worktree" | "home" | "yaml";
    readonly mode: OpenMode;
}

export interface DevClient {
    /** 全域快照（launches / externals / worktreeInstances …） */
    snapshot(): Promise<DevSnapshot>;
    /** 当前命令输出会话（启动日志 / build 输出共用一条） */
    session(): Promise<CommandSession | null>;
    start(ref: LaunchRef): Promise<void>;
    stop(ref: LaunchRef): Promise<void>;
    focus(ref: LaunchRef): Promise<void>;
    revealCdp(ref: LaunchRef): Promise<void>;
    /** 在 app 目录跑一条白名单命令（build / check / …） */
    run(ref: LaunchRef, command: BuildCommand): Promise<CommandSession>;
    clearSession(): Promise<void>;
    openDir(target: OpenTarget): Promise<{ ok: boolean; reason: string }>;
    openUrl(url: string): Promise<{ ok: boolean; reason: string }>;
    /** devtools 插件代理：把插件要的方法名透传给目标实例的 rpc 端口 */
    trafficCall<T>(target: { port: number; method: string; args?: unknown }): Promise<T>;
    /** 外部仓库域（diy.yaml 跟着 worktree 走） */
    readonly ref: {
        overview(worktree: string): Promise<RefOverview>;
        add(worktree: string, url: string): Promise<{ ok: boolean; name: string; spec: string }>;
        remove(worktree: string, name: string): Promise<{ ok: boolean; removed: boolean }>;
        sync(worktree: string): Promise<RefSyncState>;
        syncState(worktree: string): Promise<RefSyncState>;
        open(path: string): Promise<void>;
    };
}

/** 主进程的 `start/stop/focus/revealCdp` 都回 `{ok, reason}` 或纯 void；这里统一成 void + 抛错 */
async function silent(promise: Promise<unknown>): Promise<void> {
    const result = (await promise) as { ok?: boolean; reason?: string } | null;
    if (result !== null && typeof result === "object" && result.ok === false) {
        throw new Error(result.reason ?? "操作被拒绝（主进程没给原因）");
    }
}

export function createDevClient(bridge: PageBridge, pageId = "dev"): DevClient {
    const call = <T>(method: string, args?: unknown): Promise<T> =>
        bridge.invoke(pageId, method, args) as Promise<T>;

    return {
        snapshot: () => call<DevSnapshot>(DEV_METHODS.snapshot),
        session: () => call<CommandSession | null>(DEV_METHODS.session),
        start: (ref) => silent(call(DEV_METHODS.start, ref)),
        stop: (ref) => silent(call(DEV_METHODS.stop, ref)),
        focus: (ref) => silent(call(DEV_METHODS.focus, ref)),
        revealCdp: (ref) => silent(call(DEV_METHODS.revealCdp, ref)),
        run: (ref, command) => call<CommandSession>(DEV_METHODS.run, { ...ref, command }),
        clearSession: async () => {
            await call(DEV_METHODS.clearSession);
        },
        openDir: (target) => call<{ ok: boolean; reason: string }>(DEV_METHODS.open, target),
        openUrl: (url) => call<{ ok: boolean; reason: string }>(DEV_METHODS.open, { url }),
        trafficCall: <T,>(target: { port: number; method: string; args?: unknown }): Promise<T> =>
            call<T>("trafficCall", target),
        ref: {
            overview: (worktree) => call<RefOverview>(REF_METHODS.overview, { worktree }),
            add: (worktree, url) => call(REF_METHODS.add, { worktree, url }),
            remove: (worktree, name) => call(REF_METHODS.remove, { worktree, name }),
            sync: (worktree) => call<RefSyncState>(REF_METHODS.sync, { worktree }),
            syncState: (worktree) => call<RefSyncState>(REF_METHODS.syncState, { worktree }),
            open: async (path) => {
                await call(REF_METHODS.open, { path });
            },
        },
    };
}
