import { defineConfig } from "vite";
import { resolve } from "node:path";

/**
 * 库构建配置（##510）：把 src/index.ts 编成 lib/index.js，供 dev app 的 Electron 主进程按包名 import。
 *
 * why 不用 tsc：`src/ref/**` 的内部 import 是无扩展名的（`from "../runtime"`，走 bundler 解析），
 * tsc 原样 emit 会被 Node ESM 拒绝。vite（rollup）在构建期解析，产物是可直接跑的 ESM。
 * 判据：ref/ 六个文件一行不改（##510）。
 *
 * SSR 模式（node 环境）：vite 自动外部化 node 内建 + node_modules 依赖，只打包本包源码；
 * @diy-agent/rpc 同为 TS 源码依赖，由 Node 类型剥离 / 其自身产物解析（与 CLI 构建同机制）。
 */
export default defineConfig({
    build: {
        outDir: "lib",
        emptyOutDir: true,
        ssr: true,
        lib: {
            entry: resolve(__dirname, "src/index.ts"),
            formats: ["es"],
            fileName: "index",
        },
        // @diy-agent/* 保持外部：宿主（dev app）也用同一份 rpc 实例，别打进本包
        rollupOptions: { external: [/^@diy-agent\//, "zod", "js-yaml"] },
        minify: false,
        sourcemap: false,
    },
});
