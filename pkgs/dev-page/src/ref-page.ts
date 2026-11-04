// ref-page.ts — 外部仓库域的主进程侧（##510 建，##518 从独立页并入 dev 页）：把 ref 域摆成方法表。
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
import { existsSync } from "node:fs";
import { join, resolve } from "node:path";
import { ChannelClientBinding, ChannelServerBinding, createMemTransportPair, createTypedClient } from "@diy-agent/rpc";
import { bindRefHandlers, readRuntimeConfig, refApi, type RefEntry } from "@diy-agent/dev-ref";
import { openPath } from "@diy-agent/dev-core";
import { REF_METHODS, type RefOverview, type RefRepo, type RefSyncState, type RefSyncSummary } from "@diy-agent/dev-core/shared";
import { repoRootOf, type PageContribution } from "@diy-agent/workbench";

/** 进度行上限（长同步不会把内存撑爆） */
const MAX_LINES = 400;

/**
 * ref 域的作用域：cwd = **哪个 worktree**（它的 `diy.yaml`），home = 数据根（镜像落 `<home>/ref`）。
 *
 * ##518 第三轮（用户裁）：`diy.yaml` 跟着 **worktree** 走 —— 同一仓库的不同 worktree 各有一份，
 * source 列表与锁定版本都可能不同。所以 worktree 由调用方（worktree 详情页）传进来，
 * 这里不猜 `repoRootOf()`（那只会得到 dev 自己所在的那个 worktree）。
 */
function scope(worktree: string): { home: string; cwd: string } {
    const cwd = worktree.trim() === "" ? repoRootOf() : resolve(worktree);
    if (!existsSync(join(cwd, "diy.yaml"))) {
        throw new Error(`${cwd} 没有 diy.yaml（这个 worktree 还没声明外部仓库）`);
    }
    return { home: readRuntimeConfig().home, cwd };
}

/** 每次调用建一对新的进程内 transport（轻量；不共享状态，避免在飞调用互相干扰） */
function refClient(worktree: string) {
    const { home, cwd } = scope(worktree);
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

// ── sync 的进度状态（按仓库分：同一时刻每个仓库只跑一批） ──────

const states = new Map<string, RefSyncState>();
const EMPTY_STATE: RefSyncState = { running: false, lines: [], summary: null, error: null };

function stateOf(worktree: string): RefSyncState {
    return states.get(worktree) ?? EMPTY_STATE;
}

function setState(worktree: string, next: RefSyncState): void {
    states.set(worktree, next);
}

function push(worktree: string, text: string): void {
    const state = stateOf(worktree);
    const lines = [...state.lines, text];
    setState(worktree, { ...state, lines: lines.length > MAX_LINES ? lines.slice(-MAX_LINES) : lines });
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

async function runSync(worktree: string): Promise<void> {
    setState(worktree, { running: true, lines: ["开始同步（diy.yaml 里的 source）…"], summary: null, error: null });
    try {
        const stream = await refClient(worktree).sync({});
        for await (const frame of stream) {
            if (frame.action === "done") {
                const summary: RefSyncSummary | null = frame.summary ?? null;
                setState(worktree, { ...stateOf(worktree), summary });
                push(
                    worktree,
                    summary === null
                        ? "同步结束"
                        : `同步结束：更新 ${summary.synced} / 跳过 ${summary.tagSkipped} / 失败 ${summary.errors.length}（共 ${summary.total}）`,
                );
                continue;
            }
            push(worktree, describeFrame(frame));
        }
    } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        setState(worktree, { ...stateOf(worktree), error: message });
        push(worktree, `✗ 同步中断：${message}`);
    } finally {
        setState(worktree, { ...stateOf(worktree), running: false });
    }
}

// ── 方法实现 ────────────────────────────────────────────────

async function overview(worktree: string): Promise<RefOverview> {
    const { home, cwd } = scope(worktree);
    const entries = await refClient(worktree).list({});
    return { root: cwd, home, repos: entries.map(toRepo) };
}

function requireString(args: unknown, field: string): string {
    const value = (args as Record<string, unknown> | null | undefined)?.[field];
    if (typeof value !== "string" || value.trim() === "") {
        throw new Error(`${field} 不能为空`);
    }
    return value.trim();
}

/**
 * 外部仓库的方法表（##518：已并入 dev 页，不再单独出一页）。
 *
 * 为什么还留在这个文件：ref 域用的是进程内 mem transport + typed client（##510 的复用方式），
 * 与 app 域的 spawn / 注册表逻辑没有交集，混进 page.ts 只会让两边都难读。
 */
export const refMethods: PageContribution["methods"] = {
        [REF_METHODS.overview]: async (args): Promise<RefOverview> => overview(requireString(args, "worktree")),

        [REF_METHODS.add]: async (args) => {
            const worktree = requireString(args, "worktree");
            const result = await refClient(worktree).add({ url: requireString(args, "url") });
            return { ok: true, name: result.data.name, spec: result.data.spec };
        },

        [REF_METHODS.remove]: async (args) => {
            const worktree = requireString(args, "worktree");
            const result = await refClient(worktree).remove({ name: requireString(args, "name") });
            return { ok: true, removed: result.data.removed };
        },

        // 立即返回当前快照；真正跑批在后台（running=false 时才起）
        [REF_METHODS.sync]: (args): RefSyncState => {
            const worktree = requireString(args, "worktree");
            if (!stateOf(worktree).running) void runSync(worktree);
            return stateOf(worktree);
        },

        [REF_METHODS.syncState]: (args): RefSyncState => stateOf(requireString(args, "worktree")),

        [REF_METHODS.open]: (args) => openPath(requireString(args, "path"), "finder"),
};
