/**
 * devtools.tsx —— 「请求」页：把 devtools 插件挂进 dev（##518 第一个插件接入）
 *
 * 两个职责分得很清：
 *   · **选目标实例**：从快照里取「有 rpc 端口的实例」（launches 带 runtime.port、以及 externals）；
 *   · **把宿主能力喂给插件**：插件的 `DevtoolsHost.invoke` → dev 的 `trafficCall` 代理 →
 *     目标实例的 h2c rpc。插件本身不知道 dev 存在。
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { trafficPageView } from "@diy-agent/devtools-traffic";
import type { DevtoolsHost } from "@diy-agent/devtools-traffic";
import { selectSnapshot, useSlice, type UiContext } from "./app.js";

interface Target {
    readonly port: number;
    readonly label: string;
}

/** 从快照里挑出「可以被观测的实例」：有 rpc 端口的 launch 与外部实例 */
function useTargets(ctx: UiContext): readonly Target[] {
    const snapshot = useSlice(ctx, selectSnapshot);
    return useMemo(() => {
        if (snapshot === null) return [];
        const out: Target[] = [];
        for (const launch of snapshot.launches) {
            const port = launch.runtime?.port;
            if (typeof port === "number" && port > 0) {
                out.push({ port, label: `${launch.app}.${launch.launch} :${String(port)}` });
            }
        }
        for (const item of snapshot.externals) {
            if (typeof item.port === "number" && item.port > 0) {
                const who = item.production ? "生产" : "外部";
                out.push({ port: item.port, label: `${String(item.app ?? "?")} ${who} :${String(item.port)}` });
            }
        }
        return out;
    }, [snapshot]);
}

function PluginHost(props: { ctx: UiContext; port: number }) {
    const host = useMemo<DevtoolsHost>(
        () => ({
            // 插件的唯一能力面：把方法名透传给 dev 的代理（代理再打目标实例的 h2c rpc）
            invoke: <T,>(method: string, args?: unknown): Promise<T> =>
                props.ctx.client.trafficCall<T>({ port: props.port, method, args }),
        }),
        [props.ctx, props.port],
    );

    // 插件是**命令式** PageView：render(container) 返回 dispose。用 effect 管生命周期，
    // 端口变化时先 dispose 再重挂（否则旧会话的查询会继续往界面上写）。
    const holder = useRef<HTMLDivElement | null>(null);
    useEffect(() => {
        const node = holder.current;
        if (node === null) return undefined;
        node.replaceChildren();
        const div = document.createElement("div");
        div.className = "h-full";
        node.append(div);
        const dispose = trafficPageView.render(div, {
            invoke: (m: string, a?: unknown) => host.invoke(m, a),
        } as never);
        return () => {
            dispose?.();
            node.replaceChildren();
        };
    }, [host]);
    return <div ref={holder} className="h-full" />;
}

export function TrafficPage(props: { ctx: UiContext }) {
    const targets = useTargets(props.ctx);
    const [picked, setPicked] = useState<number | null>(null);
    const active = picked !== null && targets.some((t) => t.port === picked) ? picked : (targets[0]?.port ?? null);

    if (targets.length === 0) {
        return (
            <div className="p-3 text-[11px] text-on-surface-variant">
                还没有带 rpc 端口的实例（应用起来之后这里会出现可观测目标）
            </div>
        );
    }
    return (
        <div className="flex h-full flex-col">
            <header className="flex items-center gap-2 border-b border-outline px-2 py-1 text-[11px]">
                <span className="text-on-surface-variant">观测目标</span>
                <select
                    className="rounded border border-outline bg-transparent px-1 py-[1px]"
                    value={active ?? ""}
                    onChange={(e) => setPicked(Number(e.target.value))}
                >
                    {targets.map((t) => (
                        <option key={t.port} value={t.port}>
                            {t.label}
                        </option>
                    ))}
                </select>
                <span className="ml-auto text-[10px] text-on-surface-variant">数据来自目标实例的 traffic 域（h2c rpc）</span>
            </header>
            <div className="min-h-0 flex-1">
                {active === null ? null : <PluginHost ctx={props.ctx} port={active} />}
            </div>
        </div>
    );
}
