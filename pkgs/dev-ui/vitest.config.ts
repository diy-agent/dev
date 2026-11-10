// vitest.config.ts —— dev-ui 的**UI 意图测试**（##518）
//
// 环境用 happy-dom：组件是真组件，DOM 是模拟的，**不起 Electron**。
// 数据面用真 store + 真 client（`createDevClient`）+ 脚本化的 page 桥 ——
// 只有「真窗口 / 真进程」才需要 Electron，意图测试要的是「用户看到什么」。
import { defineConfig } from "vitest/config";

export default defineConfig({
    esbuild: { jsx: "automatic", jsxImportSource: "react" },
    test: {
        environment: "happy-dom",
        // ⚠️ 必须开 globals：@testing-library/react 的**自动清理**靠 afterEach 全局钩子，
        // 关着的话上一个用例的 DOM 会留在 document.body 里 —— 症状是「找到多个元素」
        // 或断言读到上一个用例的界面（本轮真踩了）。
        globals: true,
        include: ["tests/**/*.test.tsx", "tests/**/*.test.ts"],
        // 意图测试要的是快：单文件 < 2s 是验收线（docs/research/ui-testing-strategy.md）
        testTimeout: 10_000,
    },
});
