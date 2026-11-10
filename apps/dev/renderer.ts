// renderer.ts —— 装配器侧的 renderer 入口（##518）。
//
// 界面实现在 `@diy-agent/dev-ui`（独立包）：本文件只把它的渲染入口与样式引进来，
// 打包交给 esbuild。装配器（apps/*）只负责「拼装」，不承载 UI —— 这样 UI 与 core
// 之间只剩 rpc（`dev-ui/src/client.ts` 里那层领域封装）。

import "@diy-agent/dev-ui/renderer";
