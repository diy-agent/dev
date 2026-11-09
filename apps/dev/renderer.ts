// renderer.ts — 装配器侧的 renderer 入口（##508）。
//
// 界面实现在 @diy-agent/dev-page/renderer（裸 DOM，无框架）；本文件只是给 esbuild 的打包入口，
// 产物 `<build>/<variant>/renderer/index.js` 由 index.html 的 `<script src="./index.js">` 加载。

// Material Web（##518 用户裁：**全面接受 @material/web**，控件一律用它）。
// 只按需 import 用到的 —— 整包 all.js 会打进来 ~1 MB。
import "@material/web/button/text-button.js";
import "@material/web/button/filled-button.js";
import "@material/web/button/filled-tonal-button.js";
import "@material/web/button/outlined-button.js";
import "@material/web/button/elevated-button.js";
import "@material/web/iconbutton/icon-button.js";
import "@material/web/chips/assist-chip.js";
import "@material/web/chips/filter-chip.js";
import "@material/web/progress/circular-progress.js";
import "@material/web/divider/divider.js";

// M3 设计令牌（diy 自家 `pkgs.ts/ui/design`，尚未发 npm）：@material/web 全靠 `--md-sys-color-*` 取色。
// 那个包的令牌现在是**生成物**（scripts/gen.mts 从 seed 算），入口只 import 一个 index.css；
// 等 @diy-agent/ui-design 发到 npm，这行换成 `import "@diy-agent/ui-design"` 即可。
import "../../../diy/pkgs.ts/ui/design/src/index.css";

import "@diy-agent/dev-page/renderer";
