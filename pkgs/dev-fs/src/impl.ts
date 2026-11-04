// impl.ts — 落地实现（纯 node:fs + 路径 jail），绑到任意 ServerBinding。
//
// 唯一的硬约束：**路径永远出不了 worktree**。渲染侧只能给相对路径，另加一道越界检查 ——
// 渲染进程是 sandbox 的、将来还可能跑在远程 UI 里，不能把它当可信调用方。

import { existsSync, readdirSync, readFileSync, realpathSync, statSync, writeFileSync } from "node:fs";
import { dirname, isAbsolute, join, resolve, sep } from "node:path";
import type { ServerBinding } from "@diy-agent/rpc";
import { fsApi, type FsEntryValue } from "./api.js";

/** 不往界面上列的东西（`.git` 内部结构对编辑器没有意义） */
const HIDDEN = new Set([".git"]);

/** 单次读取上限：编辑器的用途，不是 dump 大文件 */
const MAX_READ_BYTES = 1024 * 1024;

/**
 * 把「worktree + 相对路径」解析成绝对路径。
 *
 * 三道闸：① 根必须是 git worktree；② 不收绝对路径；③ resolve 后仍在根内；
 * ④ 再按真实路径（realpath）比一次 —— worktree 内部的符号链接不能把人带出去。
 */
export function jail(worktree: string, path: string): string {
    const root = resolve(worktree);
    if (!existsSync(join(root, ".git"))) throw new Error(`${root} 不是 git worktree（没有 .git）`);
    if (isAbsolute(path)) throw new Error("只接受相对 worktree 的路径");
    const abs = resolve(root, path === "" ? "." : path);
    if (abs !== root && !abs.startsWith(root + sep)) throw new Error(`路径越界：${path}`);

    // 真实路径比较：新文件还不存在，就取「存在的最深祖先」来比
    let probe = abs;
    while (!existsSync(probe)) {
        const up = dirname(probe);
        if (up === probe) break;
        probe = up;
    }
    const realRoot = realpathSync(root);
    const realProbe = realpathSync(probe);
    if (realProbe !== realRoot && !realProbe.startsWith(realRoot + sep)) {
        throw new Error(`路径越界（符号链接指到 worktree 外）：${path}`);
    }
    return abs;
}

/** 列一层目录：目录在前、按名字排序（不递归） */
export function listDir(worktree: string, path: string): FsEntryValue[] {
    const abs = jail(worktree, path);
    const raw = readdirSync(abs, { withFileTypes: true });
    const out: FsEntryValue[] = [];
    for (const item of raw) {
        if (HIDDEN.has(item.name)) continue;
        const childRel = path === "" ? item.name : `${path}/${item.name}`;
        if (item.isDirectory()) {
            out.push({ name: item.name, path: childRel, kind: "dir", size: null });
            continue;
        }
        if (!item.isFile()) continue; // 符号链接 / socket 一律不列：编辑器用不着
        let size: number | null = null;
        try {
            size = statSync(join(abs, item.name)).size;
        } catch {
            size = null;
        }
        out.push({ name: item.name, path: childRel, kind: "file", size });
    }
    out.sort((a, b) => (a.kind === b.kind ? a.name.localeCompare(b.name) : a.kind === "dir" ? -1 : 1));
    return out;
}

/** 读文本（超 1 MB 截断；含 NUL 判定为二进制，只回标记不送内容） */
export function readText(
    worktree: string,
    path: string,
): { path: string; text: string; size: number; truncated: boolean; binary: boolean } {
    const abs = jail(worktree, path);
    if (statSync(abs).isDirectory()) throw new Error(`${path} 是目录`);
    const buf = readFileSync(abs);
    const binary = buf.includes(0);
    const cut = buf.subarray(0, MAX_READ_BYTES);
    return {
        path,
        text: binary ? "" : cut.toString("utf-8"),
        size: statSync(abs).size,
        truncated: buf.length > MAX_READ_BYTES,
        binary,
    };
}

/** 整文件写回（父目录必须已存在：不替用户造目录） */
export function writeText(worktree: string, path: string, text: string): { ok: boolean; size: number } {
    const abs = jail(worktree, path);
    if (!existsSync(dirname(abs))) throw new Error(`目录不存在：${dirname(path)}`);
    writeFileSync(abs, text, "utf-8");
    return { ok: true, size: Buffer.byteLength(text, "utf-8") };
}

/** 把 fs 的三个方法绑到 binding（Electron IPC / mem / http 都行，与传输无关） */
export function bindFsHandlers(binding: ServerBinding): void {
    binding.on(fsApi.fs.list, ({ input }) => listDir(input.worktree, input.path));
    binding.on(fsApi.fs.read, ({ input }) => readText(input.worktree, input.path));
    binding.on(fsApi.fs.write, ({ input }) => writeText(input.worktree, input.path, input.text));
}
