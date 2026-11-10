/**
 * fs.ts —— dev-fs 的**唯一入口**（##518）。
 *
 * 为什么单独成文件：文件视图（`files.tsx`）与「文件」页（`worktrees.tsx`）都要用它，
 * 而 transport 是 preload 递进来的单例 —— 两处各建一次 binding 也「能用」，
 * 但一旦将来要加缓存 / 重试 / 超时，就必须只有一处可改。
 */
import { ChannelClientBinding, type EnvelopeTransport } from "@diy-agent/rpc";
import { devFsService } from "@diy-agent/dev-fs/api";

export interface FsEntry {
    name: string;
    path: string;
    kind: "file" | "dir";
    size: number | null;
}

type FsClient = ReturnType<typeof devFsService.use>["fs"];

let cached: FsClient | null = null;

export function fsClient(): FsClient {
    if (cached !== null) return cached;
    const transport = (window as unknown as { transport?: EnvelopeTransport }).transport;
    if (transport === undefined) throw new Error("preload 没递出 window.transport（rpc 通道缺失）");
    cached = devFsService.use(new ChannelClientBinding(transport)).fs;
    return cached;
}
