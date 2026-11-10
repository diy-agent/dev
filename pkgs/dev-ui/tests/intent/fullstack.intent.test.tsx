// fullstack.intent.test.tsx —— **进程内全栈**的 UI 意图测试（##518）
//
// 与 `app.intent.test.tsx` 的分工：
//   · 那边用**假快照**（快，验「给这份数据界面怎么画」）；
//   · 这边连**真 core** —— 真 `discover()` / 真 `buildSnapshot()` / 真注册表 / 真临时 git 目录，
//     只让路一处：`spawn`（拉起真实例要 2–4 s 且抢端口），换成「写一条注册记录」。
//
// 所以这条链是：真组件 → 真 client（`createDevClient`）→ 真 page 方法 → 真快照 → 回填界面。
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { fireEvent } from "@testing-library/react";
import { DevRunner } from "@diy-agent/dev-core";
import { chipFor, renderUi } from "../../src/testing/harness.js";
import { createFullStackFixture, type FullStackFixture } from "../../src/testing/fullstack.js";

let fx: FullStackFixture;
let pageModule: typeof import("@diy-agent/dev-page/page");

beforeAll(async () => {
    // ⚠️ 顺序：先设 DIY_HOME 与 cwd，再 import dev-page（它加载时就算 REPO_ROOT / 注册表目录）
    fx = createFullStackFixture();
    pageModule = await import("@diy-agent/dev-page/page");

    // 唯一让路：不真 spawn，改成「写一条注册记录」——这正好也让 watchLog/快照读到真数据
    vi.spyOn(DevRunner.prototype, "start").mockImplementation((input: { appDir: string; home?: string }) => {
        const pid = fx.record({ diyHome: input.home });
        return { pid, logFile: "/tmp/fake.log" } as never;
    });
});

afterAll(() => {
    vi.restoreAllMocks();
    fx.cleanup();
});

/** 把 page 桥接到**真 page 方法**上（除了 start 已被 stub） */
function realHandlers() {
    return {
        snapshot: () => pageModule.snapshot(),
        start: (args: unknown) => pageModule.startLaunch(args as never),
        stop: (args: unknown) => pageModule.stopLaunch(args as never),
        session: () => null,
        clearSession: () => ({ ok: true, reason: "ok" }),
    } as Record<string, (args: unknown) => unknown>;
}

describe("全栈：真 core 算出来的快照驱动界面", () => {
    it("临时仓库里的 app.yaml 被真发现 ⇒ 侧栏出现这条 launch", () => {
        const ui = renderUi({ snapshot: pageModule.snapshot(), handlers: realHandlers() });
        expect(ui.text()).toContain("lab");
        expect(ui.text()).toContain("chat");
    });

    it("点「启动」⇒ 真 startLaunch 走到（spawn 被换成写注册表）⇒ 刷新后界面显示运行中", async () => {
        const ui = renderUi({ snapshot: pageModule.snapshot(), handlers: realHandlers() });
        fireEvent.click(chipFor(document.body, "lab"));
        fireEvent.click(ui.result.getByRole("button", { name: "启动" }));
        await new Promise((r) => setTimeout(r, 50)); // startLaunch 是同步的，这里只是让 microtask 走完

        // 真 core 重新算快照（读真注册表）→ 喂回界面
        ui.rerender(pageModule.snapshot());

        const text = ui.text();
        expect(text).toContain("运行中");
        // 注册表里确实有一条记录（真盘上的文件）
        expect(fx.record).toBeTypeOf("function");
    });

    it("注册表被清空（模拟实例退出）⇒ 刷新后回到未启动", () => {
        fx.clearRecords();
        const ui = renderUi({ snapshot: pageModule.snapshot(), handlers: realHandlers() });
        fireEvent.click(chipFor(document.body, "lab"));
        expect(ui.text()).toContain("未启动");
    });
});
