// src/ref/git.ts — git 子进程封装（clone / checkout / pull）
//
// 外部命令防御：requireGit() 在调用前检查 git 存在，缺失给安装提示而非裸报错。
// 镜像目录作为「只读源码快照」，**一律浅克隆（--depth 1）**：大仓库全历史经常下不下来，
// 而镜像只用于读源码，不需要历史。tag / 分支用 `--branch` 一次取到位；SHA 因为浅克隆按 ref
// 取（任意 commit 不在 want 里）走 init + `fetch --depth 1 <sha>`，远端拒绝时退回全量 clone。
//
// 日志策略（193 重写）：
//   - 长命令（clone / fetch / pull）走 exec.runStreaming + ProgressRenderer 实时渲染
//     （TTY 原地重绘、非 TTY 里程碑行、静默心跳提示），替代旧 spawnSync「跑完才 dump」黑屏；
//   - 短命令（--version / checkout / symbolic-ref）走 runBuffered 缓冲执行，
//     输出同样经 ProgressRenderer.info()（193 遗留 F4：不再直写 stderr，避免双通道交错）；
//   - 超时分级（190 第四节）：ls-remote 15s、单 ref fetch 60s；clone / pull 不设硬超时
//     （5caf645 加过 clone 180s 被 8b2ae9e 故意删除——会误杀大仓库），卡住由 Ctrl+C 中断；
//   - 统一注入 GIT_TERMINAL_PROMPT=0（见 exec.ts）。
//
// clone 时 ref 检出策略（--depth 1 隐含 --single-branch，只拉目标 ref 的 1 层历史）：
//   - 无版本 / main → 默认分支 HEAD（track origin/默认分支，后续 pull 增量快进）
//   - tag（含非 semver 如 nightly）/ SHA → detached 检出，后续不 pull
//   - 显式分支名（develop/feat.x 等，斜杠分支整体作 ref 名）→ `--branch <v>` 建本地 tracking 分支（后续可 pull）
//   - /tree/<分支>/<子目录> 天然歧义（分支 feat/foo 根 vs 分支 feat 下 foo 目录），一律按 ref 名整体解释，
//     失败时提示改用 @<分支> 精确形式

import { existsSync, mkdirSync, rmSync } from "node:fs";
import { dirname } from "node:path";
import { runBuffered, runStreaming, type ExecResult } from "../git/exec";
import { getDefaultRenderer, type ProgressRenderer } from "./render";
import { isShaVersion } from "./store";

export interface GitRunResult {
    ok: boolean;
    stdout: string;
    stderr: string;
    timedOut: boolean;
}

/** 把带 \r 刷屏的 git 输出整理成多行可读文本（错误消息用）。 */
function readable(s: string): string {
    return s
        .split(/[\r\n]+/)
        .map((x) => x.trim())
        .filter(Boolean)
        .join("\n");
}

/**
 * 短命令：回显 + 缓冲执行，结束后把命令回显 + 输出经 renderer 甩出（F4：与长命令同通道，
 * 输出内容不变，只换通道；渲染器取进程级单例，与 impl 的 sync 进度共用同一份状态）。
 * timeoutMs 可选（如 ls-remote 15s）。
 */
function run(args: string[], cwd?: string, timeoutMs?: number): GitRunResult {
    const prog = getDefaultRenderer();
    prog.info(`$ git ${args.join(" ")}${cwd ? `  # ${cwd}` : ""}`);
    const r = runBuffered(args, { cwd, timeoutMs });
    const out = r.stdout.trim();
    const err = r.stderr.trim();
    // 成功也放出来：用户要看到 git 是否进行中，而不只是失败时
    if (out) prog.info(out);
    if (err) prog.info(err);
    if (r.error) prog.info(r.error);
    return { ok: r.ok, stdout: out, stderr: err, timedOut: r.timedOut };
}

/**
 * 流式跑长命令：命令回显 + stderr 进度实时进 renderer（无 renderer 用进程级默认），
 * 结束后吐残留缓冲。stdout（如 pull 合并摘要）结束时补一行。
 */
async function runStream(
    args: string[],
    opts: { cwd?: string; timeoutMs?: number; prog?: ProgressRenderer },
): Promise<ExecResult> {
    const prog = opts.prog ?? getDefaultRenderer();
    prog.info(`$ git ${args.join(" ")}${opts.cwd ? `  # ${opts.cwd}` : ""}`);
    const res = await runStreaming(args, {
        cwd: opts.cwd,
        timeoutMs: opts.timeoutMs,
        onData: (chunk) => prog.feed(chunk),
        onIdle: (silentMs) => prog.waiting(silentMs),
    });
    prog.drain();
    const out = res.stdout.trim();
    if (out) prog.info(out);
    return res;
}

/** 检查 git 命令可用；缺失 throw 带安装提示的错误。 */
export function requireGit(): void {
    if (!run(["--version"]).ok) {
        throw new Error("缺少外部命令: git\n  安装 git 后重试：brew install git");
    }
}

/**
 * 校验 URL 是可达的 git 仓库（git ls-remote --heads）。
 * 仅供 add 阶段预检；15s 硬超时（190 核对表 #1）；不可达即 throw。
 */
export function verifyRemoteUrl(url: string): void {
    const res = run(["ls-remote", "--heads", "--", url], undefined, 15_000);
    if (!res.ok) {
        const why = res.timedOut
            ? "git ls-remote 超时（15s），网络过慢或不可达"
            : res.stderr || res.stdout || "git ls-remote 请求失败";
        throw new Error(`URL 无法访问或不是 git 仓库: ${url}\n  ${why}`);
    }
}

/** 浅克隆深度：只取目标 ref 的最新快照，不拉全历史（大仓库全量 clone 经常下不下来）。 */
const SHALLOW_DEPTH = "1";

/** 删除（可能是半成品的）镜像目录；失败不掩盖原始错误。 */
function rmDir(dir: string): void {
    try {
        rmSync(dir, { recursive: true, force: true });
    } catch {
        /* ignore */
    }
}

export interface MirrorOpts {
    /** 镜像目标目录（绝对路径） */
    dir: string;
    /** 仓库 URL（https / git@ssh 均可） */
    url: string;
    /**
     * 目标 ref：@ 后段 / /tree/ 后段 / releases / commit 统归一处。null/空 → 保持默认分支 HEAD；
     * SHA / tag → detached 检出；其余看作分支名检出。
     */
    version: string | null;
    /** 进度渲染器；缺省用进程级默认（stderr） */
    prog?: ProgressRenderer;
}

/**
 * clone 到 dir 并按 version 检出 ref（**浅克隆 --depth 1**）。
 * 目录已含 git 仓库则跳过（交由 updateMirror 增量处理）。
 * clone 不设硬超时（190 第四节），进度实时渲染 + 心跳提示。
 */
export async function cloneMirror(opts: MirrorOpts): Promise<void> {
    const url = opts.url.trim();
    if (url.length === 0) throw new Error("git URL 为空");
    if (existsSync(`${opts.dir}/.git`)) return;

    mkdirSync(dirname(opts.dir), { recursive: true });
    const prog = opts.prog ?? getDefaultRenderer();
    const v = (opts.version ?? "").trim();

    // SHA：浅克隆按 ref 取，任意 commit 不在 want 里 → 单独走 init + fetch --depth 1 <sha>
    if (isShaVersion(v)) {
        await cloneAtSha({ dir: opts.dir, url, sha: v, prog });
        return;
    }

    // 无版本 / main → 默认分支 HEAD；tag / 分支 → --branch 直接取（tag 检出 detached，
    // 分支建本地 tracking），clone 一步到位，不再 clone 后 checkout。
    const args = ["clone", "--depth", SHALLOW_DEPTH, "--progress"];
    if (v.length > 0 && v !== "main") args.push("--branch", v, "--single-branch");
    args.push("--", url, opts.dir);

    const cl = await runStream(args, { prog });
    if (!cl.ok) {
        rmDir(opts.dir);
        const why = readable(cl.stderr) || readable(cl.stdout) || "git clone 失败";
        const hint =
            v.length > 0 && v !== "main"
                ? `\n  确认仓库存在 '${v}'；若从 /tree/ 复制且地址含子目录如 …/tree/<分支>/<子目录>，请改用 @<分支> 精确形式`
                : "";
        throw new Error(`clone 失败: ${why}${hint}`);
    }
}

/**
 * 按 commit SHA 取单层快照：init + `fetch --depth 1 <sha>` + detached 检出。
 * 部分远端不允许按 sha fetch（allowReachableSHA1InWant=false）→ 退回全量 clone（历史必需，别无他法）。
 */
async function cloneAtSha(opts: {
    dir: string;
    url: string;
    sha: string;
    prog: ProgressRenderer;
}): Promise<void> {
    const { dir, url, sha, prog } = opts;
    mkdirSync(dir, { recursive: true });
    run(["init", "-q", dir]);
    run(["-C", dir, "remote", "add", "origin", url]);

    // 单 ref fetch：60s 硬超时（超时分级，与既有 fetch 一致；clone 才不设超时）
    const f = await runStream(["-C", dir, "fetch", "--depth", SHALLOW_DEPTH, "--progress", "origin", sha], {
        prog,
        timeoutMs: 60_000,
    });
    if (f.ok) {
        const co = run(["-C", dir, "checkout", "-q", "FETCH_HEAD"]);
        if (!co.ok) throw new Error(`checkout '${sha}' 失败: ${co.stderr || ""}`);
        return;
    }

    // 回退：全量 clone（半成品目录先清掉）
    prog.info(`按 commit 浅取失败，回退全量 clone（${sha}）`);
    rmDir(dir);
    mkdirSync(dirname(dir), { recursive: true });
    const cl = await runStream(["clone", "--progress", "--", url, dir], { prog });
    if (!cl.ok) {
        rmDir(dir);
        const why = readable(cl.stderr) || readable(cl.stdout) || "git clone 失败";
        throw new Error(`clone 失败: ${why}`);
    }
    const co = run(["-C", dir, "checkout", "-q", sha]);
    if (!co.ok) throw new Error(`checkout '${sha}' 失败（仓库无该 commit）: ${co.stderr || ""}`);
}

export interface UpdateOutcome {
    /** true=已执行 pull/更新；false=tag 固定未动 */
    updated: boolean;
    note?: string;
    /** true=本条目未执行任何 git 命令（如 tag 直接跳过），调用方 done 时不显示耗时列（F1） */
    noTiming?: boolean;
}

/**
 * 更新已有镜像，对齐增量策略：
 *   - tag / SHA（不可变）→ 不 pull
 *   - 分支 / 无版本（track 默认分支）→ git pull --ff-only 快进到远端最新
 * 安全网：detached HEAD（SHA / 非 semver tag 检出，正则初判漏网时）一律不 pull。
 * 跳过原因经 note 返回，由调用方（impl）渲染条目行——本函数不再直写 stderr。
 */
export async function updateMirror(
    dir: string,
    isTag: boolean,
    prog?: ProgressRenderer,
): Promise<UpdateOutcome> {
    if (isTag) return { updated: false, note: "tag 固定，跳过 pull", noTiming: true };
    if (!run(["-C", dir, "symbolic-ref", "-q", "HEAD"]).ok) {
        return { updated: false, note: "detached HEAD，跳过 pull" };
    }
    const res = await runStream(["-C", dir, "pull", "--progress", "--ff-only", "origin"], {
        prog,
    });
    if (!res.ok) {
        const why = readable(res.stderr) || readable(res.stdout) || "git pull 失败";
        throw new Error(`git pull 失败（${dir}）: ${why}`);
    }
    return { updated: true };
}
