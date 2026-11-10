/**
 * traffic-page.ts —— 「网络请求」页的主进程侧（##518 第一个 devtools 插件接入）
 *
 * dev 是**独立进程**：要看别的实例发出去的请求，只能连它的 rpc 端口。
 * 这里给插件做一层**通用代理**：`{ port, method, args }` → 用 `HttpClientBinding` 打过去。
 *
 * 为什么是泛型代理而不是逐方法包装：
 *   · 插件的方法名（query / recent / logFiles …）属于 diy-app 的 traffic 域，
 *     在这里再抄一遍等于把协议复制两处；
 *   · 代理只看「方法名 + 参数」，加新方法（比如 cleanLogs）不用改 dev。
 *
 * 安全边界：只连 **127.0.0.1**，端口来自调用方（UI 从实例列表里选）；不碰数据根、不落盘。
 */
import { HttpClientBinding } from "@diy-agent/rpc/http";

export interface TrafficCallArgs {
    readonly port: number;
    readonly method: string;
    readonly args?: unknown;
}

/** 允许代理的方法白名单（防止 UI 借这条通道调任意 rpc） */
const ALLOWED = new Set(["query", "recent", "logFiles", "snapshot"]);
/**
 * 目标实例上的**方法全名** = `<service 名>.<域内路径>`（见 diy-app 的 `trafficService`）。
 * 少了这层前缀只会得到一句 `No handler for "query"` —— 实测踩过。
 */
const SERVICE = "diy.traffic";
/** 连接缓存：同一个端口复用一条 h2c 会话（每次新建会很慢且泄漏会话） */
const clients = new Map<number, HttpClientBinding>();

function clientFor(port: number): HttpClientBinding {
    const hit = clients.get(port);
    if (hit !== undefined) return hit;
    const client = new HttpClientBinding(`http://127.0.0.1:${String(port)}`);
    clients.set(port, client);
    return client;
}

export async function trafficCall(input: TrafficCallArgs): Promise<unknown> {
    if (!Number.isInteger(input.port) || input.port <= 0 || input.port > 65535) {
        throw new Error(`端口不合法：${String(input.port)}`);
    }
    if (!ALLOWED.has(input.method)) {
        throw new Error(`不允许代理的方法：${input.method}（白名单：${[...ALLOWED].join(" / ")}）`);
    }
    return clientFor(input.port).invoke(`${SERVICE}.${input.method}`, input.args ?? {});
}

/** 断开缓存的会话（实例退出 / 用户切目标时调） */
export function trafficDispose(port?: number): void {
    if (port === undefined) {
        for (const client of clients.values()) client.dispose?.();
        clients.clear();
        return;
    }
    clients.get(port)?.dispose?.();
    clients.delete(port);
}
