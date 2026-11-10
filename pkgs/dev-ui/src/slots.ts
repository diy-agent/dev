/**
 * slots.ts —— **React-free** 的扩展点注册表（##518 dev 试点，照 dsh 的 `ui-slots` 抄思路）。
 *
 * 要解决的原问题：现在 `renderer.ts` 里到处是 `if (panel === "app") … else …` 和一堆
 * `Map<worktree, Pane>` —— 「谁能画这一块」散落在 switch 里，加一个视图就要改主文件。
 *
 * 这里的模型（与 dsh 同一套）：
 *   · **Slot** = 一个具名的挂载点（`sidebar`、`detail`、`statusbar`），由**宿主**声明；
 *   · 每个 Slot 挂若干 **Contribution**，带 `id` / `order` / `props`；
 *   · 注册表本身不认识 React：它只存「怎么把 props 变成某物的函数」——
 *     渲染层（renderer.tsx）把它绑成组件，别的层（测试 / 终端）可以绑成别的东西。
 */

export interface SlotContribution<P> {
    /** 全局唯一（`<slot>/<id>`）；重复注册直接抛错，不静默覆盖 */
    readonly id: string;
    /** 同一 slot 内的排序，小的在前 */
    readonly order?: number;
    /** 宿主会把 Slot 自己的上下文一起递进来 */
    readonly render: (props: P) => unknown;
}

export class SlotRegistry {
    private readonly slots = new Map<string, Map<string, SlotContribution<never>>>();

    /** 声明一个挂载点（宿主启动时调；重复声明等价于取已存在的那个） */
    declare(slot: string): void {
        if (!this.slots.has(slot)) this.slots.set(slot, new Map());
    }

    /** 注册一个贡献；同一 slot 下 id 重复 = 编程错误，直接抛 */
    register<P>(slot: string, contribution: SlotContribution<P>): () => void {
        this.declare(slot);
        const bucket = this.slots.get(slot)!;
        if (bucket.has(contribution.id)) {
            throw new Error(`slot ${slot} 里已有同 id 的贡献：${contribution.id}（注册表不静默覆盖）`);
        }
        bucket.set(contribution.id, contribution as SlotContribution<never>);
        return () => {
            bucket.delete(contribution.id);
        };
    }

    /** 取某 slot 当前的贡献（按 order 排序；order 相同按 id 稳定排序） */
    contributions<P>(slot: string): readonly SlotContribution<P>[] {
        const bucket = this.slots.get(slot);
        if (bucket === undefined) return [];
        return [...bucket.values()]
            .sort((a, b) => (a.order ?? 100) - (b.order ?? 100) || a.id.localeCompare(b.id))
            .map((item) => item as unknown as SlotContribution<P>);
    }

    /** 已声明的 slot 名（调试/单测） */
    names(): string[] {
        return [...this.slots.keys()].sort();
    }
}
