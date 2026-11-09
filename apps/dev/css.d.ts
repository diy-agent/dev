// CSS 副作用 import 的声明（##518：dev 吃 diy 的 M3 令牌 CSS）。
// esbuild 认识 `import "./x.css"` 并产出同名 .css；TS 不认，故在这里声明一次。
declare module "*.css";
