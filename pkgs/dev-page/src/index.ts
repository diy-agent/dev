// index.ts — 页面插件的包入口：工作台按 `pages` 取页面贡献（`packages/workbench/src/loader.ts`）。
//
// 主进程装配器只 `import * as devPage from "@diy-agent/dev-page"` 然后塞进插件清单；
// renderer 单独走 `@diy-agent/dev-page/renderer`（esbuild 打包时读 exports）。
//
// ##510：一个插件出两页 —— 「dev」（启动本仓 app）与「ref」（diy.yaml 里的外部仓库）。
// loader 的归一顺序是 pages → default → apply，`pages` 存在即按数组取。

import appPage from "./page.js";
import refPage from "./ref-page.js";

export { appPage, refPage };
export const pages = [appPage, refPage];
export default pages;
