// renderer.ts — 装配器侧的 renderer 入口（##508）。
//
// 界面实现在 @diy-agent/dev-page/renderer（裸 DOM，无框架）；本文件只是给 esbuild 的打包入口，
// 产物 `<build>/<variant>/renderer/index.js` 由 index.html 的 `<script src="./index.js">` 加载。

import "@diy-agent/dev-page/renderer";
