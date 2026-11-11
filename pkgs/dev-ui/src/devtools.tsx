/**
 * devtools.tsx —— 把 devtools 插件**嵌进实例详情**（##518 用户裁）
 *
 * 用户口径：不要为观测再造一个入口（独立的「请求」页 + 目标选择器），
 * 实例本来就已经被捕捉到了 —— 在**现有实例体系**里加一个**可观测项**即可。
 *
 * 所以本文件只暴露一个 `TrafficPanel({ ctx, port })`：给它一个实例的 rpc 端口，它就把
 * raw request log 嵌在当前详情页里；谁调用它由页面决定（launch 详情 / 外部实例详情）。
 */
import { useEffect, useMemo, useRef } from "react";
import { trafficPageView } from "@diy-agent/devtools-traffic";
import type { DevtoolsHost } from "@diy-agent/devtools-traffic";
import type { UiContext } from "./app.js";

/** 观测一个实例的请求：插件是命令式 PageView，用 effect 管挂载/销毁 */
export function TrafficPanel(props: { ctx: UiContext; port: number }) {
    const host = useMemo<DevtoolsHost>(
        () => ({
            invoke: <T,>(method: string, args?: unknown): Promise<T> =>
                props.ctx.client.trafficCall<T>({ port: props.port, method, args }),
        }),
        [props.ctx, props.port],
    );

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
