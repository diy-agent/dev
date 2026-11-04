// index.ts — 页面插件的包入口：工作台按 `pages` 取页面贡献（`packages/workbench/src/loader.ts`）。
//
// ##518：外部仓库并入 dev 页（原来是一页「ref」）—— 一页两区：左侧矩阵 + 底部外部仓库列表，
// 右侧按当前选中的东西画（app / worktree / 仓库）。方法表也在 page.ts 里合并成一张。

import appPage from "./page.js";

export { appPage };
export const pages = [appPage];
export default pages;
