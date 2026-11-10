/**
 * harness.tsx —— UI 意图测试的**装配器**（##518）
 *
 * 装配的是**真的那部分**：
 *   · 真 `SnapshotStore` / 真 `SlotRegistry` / 真 `createDevClient`（组件里的 client.ts 那层封装被测到）；
 *   · 真 React 组件（`App`），真点击。
 * 只替身一处：page 桥（`bridge.invoke`）—— 它背后是 Electron IPC，测试里换成脚本化 handler，
 * 顺手把「调了哪个方法、带什么参数」记下来（`calls`），这就是 UI 层最该断言的契约。
 */
import { useState } from "react";
import { render, type RenderResult } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { CommandSession, DevSnapshot, LaunchStatus } from "@diy-agent/dev-core/shared";
import { App, type Selection } from "../app.js";
import { createDevClient, type PageBridge } from "../client.js";
import { SlotRegistry } from "../slots.js";
import { SnapshotStore } from "../store.js";

export interface Call {
    readonly method: string;
    readonly args: unknown;
}

export interface RenderUiOptions {
    readonly snapshot: DevSnapshot;
    readonly session?: CommandSession | null;
    /** 方法名 → 返回值（没写的直接抛：**没实现的动作一调就红**，不静默） */
    readonly handlers?: Partial<Record<string, (args: unknown) => unknown>>;
}

export interface Ui {
    /** 所有经 page 桥发出的调用（顺序保留） */
    readonly calls: readonly Call[];
    /** 换一份快照并重画（模拟轮询拿到新数据） */
    rerender(next: DevSnapshot): void;
    /** 查看当前界面文本（用户看得到的东西） */
    text(): string;
    readonly user: ReturnType<typeof userEvent.setup>;
    readonly result: RenderResult;
    unmount(): void;
}

export function renderUi(options: RenderUiOptions): Ui {
    const calls: Call[] = [];
    const handlers = options.handlers ?? {};
    const bridge: PageBridge = {
        async invoke(_pageId: string, method: string, args?: unknown): Promise<unknown> {
            calls.push({ method, args });
            const handler = handlers[method];
            if (handler === undefined) throw new Error(`测试没给 handler：${method}（不该被调用）`);
            return handler(args);
        },
    };
    const client = createDevClient(bridge, "dev");
    const store = new SnapshotStore<DevSnapshot | null>(options.snapshot);
    const session = new SnapshotStore<CommandSession | null>(options.session ?? null);
    const slots = new SlotRegistry();
    const ctx = { store, session, slots, client };

    // 选中态是 UI 态（与生产一致：由 Shell 持有），这里用一个极薄的容器承接
    function Host() {
        const [selection, setSelection] = useState<Selection>(null);
        return <App ctx={ctx} selection={selection} onSelect={setSelection} notify={() => undefined} />;
    }

    const user = userEvent.setup();
    const result = render(<Host />);
    return {
        calls,
        user,
        result,
        text: () => document.body.textContent ?? "",
        rerender: (next: DevSnapshot) => {
            store.set(next);
        },
        unmount: () => result.unmount(),
    };
}

/** 找一条 launch 的按钮（按可访问名；找不到 = 用户也找不到，这就是失败） */
export function chipFor(scope: HTMLElement, name: string): HTMLElement {
    const all = [...scope.querySelectorAll<HTMLElement>("button")];
    const hit = all.find((el) => (el.textContent ?? "").trim().startsWith(name));
    if (hit === undefined) throw new Error(`界面上找不到「${name}」按钮（现有：${all.map((e) => e.textContent).join(" | ")}）`);
    return hit;
}

export { type LaunchStatus };
