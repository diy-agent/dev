// index.ts — 页面插件的包入口：工作台按 `default` 取页面贡献（`packages/workbench/src/loader.ts`）。
//
// 主进程装配器只 `import * as devPage from "@diy-agent/dev-page"` 然后塞进插件清单；
// renderer 单独走 `@diy-agent/dev-page/renderer`（esbuild 打包时读 exports）。

export { default } from "./page.js";
