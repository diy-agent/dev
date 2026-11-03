// ref-page.ts — 「外部仓库」页的主进程侧（##510）：把 @diy-agent/dev-ref 的 ref 域摆成页面方法表。
//
// 复用方式：不重写 ref 逻辑，而是按 CLI 的同一机制建**进程内 mem transport**
// （ChannelServerBinding + ChannelClientBinding），把 `bindRefHandlers` 注册上去再用 typed client 调。
// 好处：`src/ref/**` 六个文件一行不改，UI 与旧 CLI 走同一份编排（##510 判据 3）。
//
// 作用域：`cwd` = 仓库根（worktree 根，diy.yaml 在那儿），`home` = `$DIY_HOME`（镜像落 $DIY_HOME/ref）。
//
// 进度：`ref.sync` 是 serverStream，逐 source 一个帧（cloned/pulled/tagSkipped/error/done）。
// page:invoke 是 unary，所以 sync 在后台跑、帧写进模块级状态，UI 轮询 `syncState` 拿进度
// （git 自己的百分比进度仍走 stderr = 终端，不进 UI，见 ref/render.ts 的定位说明）。

import { execFileSync } from "node:child_process";
import { ChannelClientBinding, ChannelServerBinding, createMemTransportPair, createTypedClient } from "@diy-agent/rpc";
import { bindRefHandlers, readRuntimeConfig, refApi, type RefEntry } from "@diy-agent/dev-ref";
import { openPath } from "@diy-agent/dev-core";
import { REF_METHODS, type RefOverview, type RefRepo, type RefSyncState, type RefSyncSummary } from "@diy-agent/dev-core/shared";
import { repoRootOf, type PageContribution } from "@diy-agent/workbench";

/** 进度行上限（长同步不会把内存撑爆） */
const MAX_LINES = 400;

/** ref 域的作用域：cwd = 仓库根（diy.yaml），home = 数据根（镜像目录的父） */
function scope(): { home: string; cwd: string } {
    return { home: readRuntimeConfig().home, cwd: repoRootOf() };
}

/** 每次调用建一对新的进程内 transport（轻量；不共享状态，避免在飞调用互相干扰） */
function refClient() {
    const { home, cwd } = scope();
    const { serverTx, clientTx } = createMemTransportPair();
    bindRefHandlers(new ChannelServerBinding(serverTx), { home, cwd });
    return createTypedClient(new ChannelClientBinding(clientTx), refApi).ref;
}

/** 本地落后多少个提交：读不到（未 clone / tag 固定 / 无 upstream）返回 null，不当错误 */
function behindOf(dir: string, exists: boolean): number | null {
    if (!exists) return null;
    try {
        const out = execFileSync("git", ["-C", dir, "rev-list", "--count", "HEAD..@{upstream}"], {
            encoding: "utf-8",
            timeout: 3000,
            stdio: ["ignore", "pipe", "ignore"],
        }).trim();
        const count = Number(out);
        return Number.isFinite(count) ? count : null;
    } catch {
        return null;
    }
}

function toRepo(entry: RefEntry): RefRepo {
    return {
        key: entry.key,
        url: entry.url,
        version: entry.version,
        dir: entry.dir,
        exists: entry.exists,
        lastSync: entry.lastSync,
        // tag / SHA 是固定检出，没有「落后」概念（rev-list 本来也会失败）
        behind: behindOf(entry.dir, entry.exists),
    };
}

// ── sync 的进度状态（模块级：同一时刻只跑一批） ──────────────

let state: RefSyncState = { running: false, lines: [], summary: null, error: null };

function push(text: string): void {
    const lines = [...state.lines, text];
    state = { ...state, lines: lines.length > MAX_LINES ? lines.slice(-MAX_LINES) : lines };
}

function describeFrame(frame: {
    spec: string;
    action: "cloned" | "pulled" | "tagSkipped" | "error" | "done";
    message?: string;
}): string {
    switch (frame.action) {
        case "cloned":
            return `✓ ${frame.spec} 首次克隆`;
        case "pulled":
            return `↻ ${frame.spec} 已更新`;
        case "tagSkipped":
            return `= ${frame.spec} 固定版本，跳过${frame.message ? `（${frame.message}）` : ""}`;
        case "error":
            return `✗ ${frame.spec} 失败：${frame.message ?? "未知错误"}`;
        case "done":
            return "同步结束";
    }
}

async function runSync(): Promise<void> {
    state = { running: true, lines: ["开始同步（diy.yaml 里的 source）…"], summary: null, error: null };
    try {
        const stream = await refClient().sync({});
        for await (const frame of stream) {
            if (frame.action === "done") {
                const summary: RefSyncSummary | null = frame.summary ?? null;
                state = { ...state, summary };
                push(
                    summary === null
                        ? "同步结束"
                        : `同步结束：更新 ${summary.synced} / 跳过 ${summary.tagSkipped} / 失败 ${summary.errors.length}（共 ${summary.total}）`,
                );
                continue;
            }
            push(describeFrame(frame));
        }
    } catch (error) {
        state = { ...state, error: error instanceof Error ? error.message : String(error) };
        push(`✗ 同步中断：${state.error}`);
    } finally {
        state = { ...state, running: false };
    }
}

// ── 方法实现 ────────────────────────────────────────────────

async function overview(): Promise<RefOverview> {
    const { home, cwd } = scope();
    const entries = await refClient().list({});
    return { root: cwd, home, repos: entries.map(toRepo) };
}

function requireString(args: unknown, field: string): string {
    const value = (args as Record<string, unknown> | null | undefined)?.[field];
    if (typeof value !== "string" || value.trim() === "") {
        throw new Error(`${field} 不能为空`);
    }
    return value.trim();
}

export const refPage: PageContribution = {
    id: "ref",
    title: "外部仓库",
    icon: "📦",
    methods: {
        [REF_METHODS.overview]: (): Promise<RefOverview> => overview(),

        [REF_METHODS.add]: async (args) => {
            const result = await refClient().add({ url: requireString(args, "url") });
            return { ok: true, name: result.data.name, spec: result.data.spec };
        },

        [REF_METHODS.remove]: async (args) => {
            const result = await refClient().remove({ name: requireString(args, "name") });
            return { ok: true, removed: result.data.removed };
        },

        // 立即返回当前快照；真正跑批在后台（running=false 时才起）
        [REF_METHODS.sync]: (): RefSyncState => {
            if (!state.running) void runSync();
            return state;
        },

        [REF_METHODS.syncState]: (): RefSyncState => state,

        [REF_METHODS.open]: (args) => openPath(requireString(args, "path"), "finder"),
    },
};

export default refPage;
