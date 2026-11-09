// CSS 副作用 import 的声明（##518：dev 吃 diy 的 M3 令牌 CSS）。
//
// 为什么要它：`import "./x.css"` 在 esbuild 里是合法的（会产出同名 .css 产物），
// 但 TS 只认 JS/TS 模块 → 报 TS2882。这里只声明「有这种东西」，不做任何类型检查。
declare module "*.css";
