// api.ts — dev-fs 的**声明式 API**（@diy-agent/rpc）：schema 即文档，客户端类型从它推导。
//
// 三个方法都是 unary：编辑器的读写是一次一次的请求，没有流式语义。
// `worktree` 必填且第一参数：路径 jail 的根，**渲染侧永远给不了绝对路径**（只能给相对 worktree 的 path）。

import { z } from "zod";
import { RpcSchema } from "@diy-agent/rpc";

const Worktree = z.string().min(1).describe("worktree 根（绝对路径；路径 jail 的边界）");
const RelPath = z.string().describe("相对 worktree 根（`''` = 根；不接受绝对路径 / `..`）");

export const FsEntry = z.object({
    name: z.string(),
    /** 相对 worktree 根，可直接回传给 read / write */
    path: z.string(),
    kind: z.enum(["file", "dir"]),
    /** 目录 = null */
    size: z.number().nullable(),
});

/** 列目录返回的一项（类型形态；schema 是上面那个 FsEntry） */
export type FsEntryValue = z.infer<typeof FsEntry>;

export const ReadOutput = z.object({
    path: z.string(),
    /** UTF-8 文本；二进制文件不返回内容（`binary: true`） */
    text: z.string(),
    size: z.number(),
    /** 超过上限被截断（只读前 1 MB） */
    truncated: z.boolean(),
    binary: z.boolean(),
});

export const fsApi = RpcSchema.router({
    fs: RpcSchema.group({
        desc: "dev 工具的文件读写（jail 在指定 worktree 内）",
        children: {
            list: RpcSchema.unary({
                desc: "列目录（不递归）；目录在前，按名字排序",
                input: { worktree: Worktree, path: RelPath },
                output: z.array(FsEntry),
            }),
            read: RpcSchema.unary({
                desc: "读一个文本文件（>1 MB 截断，二进制只回 binary 标记）",
                input: { worktree: Worktree, path: RelPath },
                output: ReadOutput,
            }),
            write: RpcSchema.unary({
                desc: "写回文本（整文件覆盖）",
                input: { worktree: Worktree, path: RelPath, text: z.string() },
                output: z.object({ ok: z.boolean(), size: z.number() }),
            }),
        },
    }),
});
