/**
 * store.ts —— **React-free** 的 observable 快照仓库（##518 dev 试点第一刀）。
 *
 * 为什么先有它（照 dsh 的 `packages/client/store` 抄思路）：
 *   业务状态（这里 = 主进程给的 snapshot）不该住在 React 里。React 只是**投影**：
 *   组件订阅「某个切片」，store 负责在数据变化时把**稳定快照**推给订阅者。
 *   换渲染层（React → 别的）时这一层不用动；测试也不需要 React（jsdom 都不开）。
 *
 * 三条规矩：
 *   1. 快照不可变：`get()` 返回同一个对象，直到真的换了新数据（`Object.is` 可做浅比较）；
 *   2. 通知按**切片选择器**去重：选择器结果浅相等就不通知（避免每次轮询都重渲染整棵树）；
 *   3. 通知合批到微任务：同一 tick 里多次 `set()` 只通知一次。
 */

export type Selector<T, S> = (state: T) => S;

export interface Subscription {
    /** 退订 */
    (): void;
}

/** 浅相等：数组比长度+元素，对象比键集+值；其余用 Object.is */
export function shallowEqual(a: unknown, b: unknown): boolean {
    if (Object.is(a, b)) return true;
    if (typeof a !== "object" || typeof b !== "object" || a === null || b === null) return false;
    if (Array.isArray(a) !== Array.isArray(b)) return false;
    const ka = Object.keys(a as Record<string, unknown>);
    const kb = Object.keys(b as Record<string, unknown>);
    if (ka.length !== kb.length) return false;
    for (const k of ka) {
        if (!Object.prototype.hasOwnProperty.call(b, k)) return false;
        if (!Object.is((a as Record<string, unknown>)[k], (b as Record<string, unknown>)[k])) return false;
    }
    return true;
}

interface Entry<T, S> {
    readonly selector: Selector<T, S>;
    readonly listener: (value: S) => void;
    last: S;
}

export class SnapshotStore<T> {
    private state: T;
    private entries = new Set<Entry<T, unknown>>();
    private pending = false;

    constructor(initial: T) {
        this.state = initial;
    }

    get(): T {
        return this.state;
    }

    /**
     * 换一整个快照。**没变就不通知**（用 `equal` 判，缺省浅相等）——
     * 轮询每秒推一次同样的数据时，这能把「整棵树重画」压成 0。
     */
    set(next: T, equal: (a: T, b: T) => boolean = shallowEqual): void {
        if (equal(this.state, next)) return;
        this.state = next;
        this.schedule();
    }

    /** 订阅一个切片：切片结果浅相等就不回调 */
    subscribe<S>(selector: Selector<T, S>, listener: (value: S) => void): Subscription {
        const entry: Entry<T, S> = { selector, listener, last: selector(this.state) };
        const tracked = entry as unknown as Entry<T, unknown>;
        this.entries.add(tracked);
        // 首次立即给当前值（React 的 useSyncExternalStore 要求快照可同步取，这里不回调，
        // 由调用方 get() 取；保留这个分支是为了非 React 消费者方便）
        return () => {
            this.entries.delete(tracked);
        };
    }

    /** 手动取某切片当前值（React 的 getSnapshot 用它） */
    read<S>(selector: Selector<T, S>): S {
        return selector(this.state);
    }

    /** 已订阅数（调试/单测用） */
    get size(): number {
        return this.entries.size;
    }

    private schedule(): void {
        if (this.pending) return;
        this.pending = true;
        queueMicrotask(() => {
            this.pending = false;
            for (const entry of this.entries) {
                const next = entry.selector(this.state);
                if (shallowEqual(entry.last, next)) continue;
                entry.last = next;
                entry.listener(next);
            }
        });
    }
}
