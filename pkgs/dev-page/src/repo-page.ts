/**
 * repo-page.ts —— 「仓库」页的主进程侧（##518：像 VS Code 那样浏览 git 仓库）。
 *
 * 只做**读**：`git worktree list` / `git status --porcelain` / `git rev-list --count` / `git log -1`。
 * 不碰索引、不做提交 —— dev 是启动器，不是第二个 Git 客户端；这一页解决的是
 * 「我现在在哪个 worktree、它干净吗、落后远端多少、最近一次提交是什么」。
 *
 * 跨平台：全部走 git 自己的输出（`-c core.quotepath=false` 让中文路径可读），
 * 不做 `ls`/`dir` 那类平台分支。
 */
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { basename, resolve } from "node:path";
import type { RepoOverview, RepoStatus, WorktreeStatus } from "@diy-agent/dev-core/shared";

/** git 单次调用预算：探针类命令超过 3s 就当拿不到（工作区在跑构建时 git 也会慢） */
const GIT_TIMEOUT_MS = 3000;
/** 变更列表上限（一屏看几十条就够；再多说明该去终端了） */
const MAX_CHANGES = 200;

function git(cwd: string, args: readonly string[]): string | null {
    try {
        return execFileSync("git", ["-c", "core.quotepath=false", ...args], {
            cwd,
            encoding: "utf-8",
            timeout: GIT_TIMEOUT_MS,
            stdio: ["ignore", "pipe", "ignore"],
        });
    } catch {
        return null;
    }
}

/** 一个目录是不是 git 仓库（worktree 里 `.git` 是文件，所以只判存在） */
function isRepo(path: string): boolean {
    return existsSync(resolve(path, ".git"));
}

/** 力一个 worktree 的 git 状态 */
export function worktreeStatus(path: string, main: boolean): WorktreeStatus | null {
    if (!isRepo(path)) return null;
    const branchRaw = git(path, ["rev-parse", "--abbrev-ref", "HEAD"])?.trim() ?? "";
    const branch = branchRaw === "" || branchRaw === "HEAD" ? null : branchRaw;
    const statusRaw = git(path, ["status", "--porcelain"]) ?? "";
    const lines = statusRaw.split("\n").filter((line) => line !== "");
    const counts = git(path, ["rev-list", "--left-right", "--count", "@{upstream}...HEAD"]);
    let ahead: number | null = null;
    let behind: number | null = null;
    if (counts !== null) {
        const [b, a] = counts.trim().split(/\s+/);
        const behindN = Number(b);
        const aheadN = Number(a);
        if (Number.isFinite(behindN) && Number.isFinite(aheadN)) {
            behind = behindN;
            ahead = aheadN;
        }
    }
    const head = git(path, ["log", "-1", "--pretty=%h %s"])?.trim() || null;
    return {
        path: resolve(path),
        name: basename(path),
        branch,
        main,
        changes: lines.slice(0, MAX_CHANGES),
        truncated: lines.length > MAX_CHANGES,
        ahead,
        behind,
        head,
    };
}

/** 一个仓库：主工作树 + `git worktree list` 里的其余工作树 */
export function repoOf(root: string): RepoStatus | null {
    const abs = resolve(root);
    if (!isRepo(abs)) return null;
    const listRaw = git(abs, ["worktree", "list", "--porcelain"]) ?? "";
    const paths: string[] = [];
    for (const line of listRaw.split("\n")) {
        if (line.startsWith("worktree ")) paths.push(line.slice("worktree ".length).trim());
    }
    if (paths.length === 0) paths.push(abs);
    const worktrees: WorktreeStatus[] = [];
    for (const [index, path] of paths.entries()) {
        const status = worktreeStatus(path, index === 0);
        if (status !== null) worktrees.push(status);
    }
    return { root: abs, name: basename(abs), worktrees };
}

/**
 * 收所有仓库：本仓 + 已知 worktree 里出现的其它仓库根。
 *
 * 为什么不止本仓：dev 的交叉表本来就跨仓库（`_diy` 与 `diy` 是两个独立 git 仓），
 * 仓库页要能一起看，否则「我另一个仓的 worktree 干净吗」还得换目录。
 */
export function repoOverview(repoRoots: readonly string[]): RepoOverview {
    const seen = new Set<string>();
    const repos: RepoStatus[] = [];
    for (const root of repoRoots) {
        const abs = resolve(root);
        if (seen.has(abs)) continue;
        seen.add(abs);
        const repo = repoOf(abs);
        if (repo !== null) repos.push(repo);
    }
    return { repos };
}
