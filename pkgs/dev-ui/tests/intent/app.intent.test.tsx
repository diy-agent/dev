// app.intent.test.tsx —— dev 界面的**意图测试**（##518 新口径的第一个样板）
//
// 测什么：用户点得到什么、点了以后发出哪个 rpc、界面变成什么样。
// 不测什么：Electron、真进程、真 fs —— 那些交给 core 的进程内全栈与 e2e。
//
// 断言口径（docs/test-ownership.md）：
//   · 找元素按**可访问名/文本**（用户视角），不按 class / data-testid；
//   · 交互后断言两件事：① 发出去的 rpc（`calls`）；② 用户看得见的文本。
import { describe, expect, it } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import { chipFor, renderUi } from "../../src/testing/harness.js";
import { external, launch, runningLaunch, snapshot } from "../../src/testing/fixtures.js";

describe("应用页：launch 的启停", () => {
    it("点「启动」⇒ 发出 start（带对的工作区/app/launch），界面出现操作结果", async () => {
        const ui = renderUi({ snapshot: snapshot(), handlers: { start: () => ({ ok: true }) } });
        // 先选中那条 launch（chip 只选中，不启停）
        fireEvent.click(chipFor(document.body, "lab"));
        // 详情里出现「启动」按钮
        fireEvent.click(screen.getByRole("button", { name: "启动" }));

        expect(ui.calls).toEqual([
            {
                method: "start",
                args: { worktree: "/repo", app: "chat", launch: "lab" },
            },
        ]);
    });

    it("运行中的 launch ⇒ 详情显示 PID 与端口（数据来自快照，不是硬编码）", async () => {
        const ui = renderUi({
            snapshot: snapshot({ launches: [runningLaunch()], worktreeCount: 1, runningCount: 1 }),
        });
        fireEvent.click(chipFor(document.body, "lab"));

        expect(ui.text()).toContain("4242");
        expect(ui.text()).toContain("18888");
    });

    it("运行中时给的是「停止」而不是「启动」（破坏性动作有明确入口）", () => {
        renderUi({ snapshot: snapshot({ launches: [runningLaunch()], runningCount: 1 }), handlers: { stop: () => ({ ok: true }) } });
        fireEvent.click(chipFor(document.body, "lab"));
        expect(screen.queryByRole("button", { name: "启动" })).toBeNull();
        expect(screen.getByRole("button", { name: "停止" })).toBeTruthy();
    });
});

describe("应用页：外部实例只读", () => {
    it("点开外部实例 ⇒ 标明真生产、且**没有**启动/停止入口", () => {
        const ui = renderUi({
            snapshot: snapshot({ launches: [], externals: [external()], worktreeInstances: {} }),
        });
        // 外部实例在侧栏以 pid 开头的一行出现
        const row = [...document.querySelectorAll("button")].find((el) => (el.textContent ?? "").includes("999"));
        expect(row).toBeTruthy();
        fireEvent.click(row!);

        expect(ui.text()).toContain("真生产");
        expect(ui.text()).toContain("只读");
        // 注意：按**角色**找，不按文本 —— 外部实例详情里有一个叫「启动」的字段标签（启动时刻），
        // 用 queryByText 会误判成按钮。这条也是「断言要贴着用户语义」的实例。
        expect(screen.queryByRole("button", { name: "启动" })).toBeNull();
        expect(screen.queryByRole("button", { name: "停止" })).toBeNull();
    });
});

describe("应用页：过滤与空态", () => {
    it("「只显示运行中」开启后，未启动的 launch 从表里消失", () => {
        const running = runningLaunch({ app: "diy-app", launch: "lab" });
        renderUi({
            snapshot: snapshot({
                launches: [launch({ app: "chat", launch: "staging" }), running],
                runningCount: 1,
            }),
        });
        const before = document.body.textContent ?? "";
        expect(before).toContain("staging");

        fireEvent.click(screen.getByText("只显示运行中"));
        const after = document.body.textContent ?? "";
        expect(after).not.toContain("staging");
        expect(after).toContain("lab");
    });
});
