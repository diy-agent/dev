#!/usr/bin/env bash
#
# apps/dev — dev 启动器装配器（##508 从主仓 apps/dev 搬来并拆包）
#
# ── 编写规则 ────────────────────────────────────
# 定义函数即为子命令：`foo() { ... }` → `./sha.sh foo`
#
# ── 执行链 ──────────────────────────────────────
# sha.sh → source ../../sha.common.sh → source vendor/sha/sha.bash → sha "$@"
#
# 产物按变体分根：build/<variant>/{main,preload,renderer}
# 数据根在**仓库根** build/<variant>/home（与主仓 pkgs.ts 各包同一约定）
#
# 依赖方向：本仓 → 主仓（../diy）。主仓改了先 `cd ../diy && ./sha.sh build-pkgs`。
#

# shellcheck disable=SC2329,SC2317,SC2034
set -o errtrace -o errexit -o functrace -o pipefail
shopt -s globstar extglob

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
source "../../sha.common.sh"

# ── 产物 vs 变体：两件事，别绑一起 ─────────────────────────
# 产物（tsc + esbuild）只跟**源码**有关：一份，落在 `build/app/`，与变体无关。
# 变体只决定**运行空间**：数据根 `build/<variant>/home`、`DIY_ENV`、CDP / 副屏行为。
#   lab  = 试验（development、CDP、副屏、watch 重启会打断轮次）
#   prod = 生产（production、真数据根；改 src 不重启）
_build_dir() { echo "build/app"; }
_home_dir() { echo "$(_repo_root)/build/${1:-lab}/home"; }
_repo_root() { ( cd "$SCRIPT_DIR/../.." && pwd ); }
_main_repo() { ( cd "$SCRIPT_DIR/../../../diy" && pwd ); }

clean() { run rm -rf ./build ./dist ./lib; }
sync() { :; }
check() { typecheck; lint; }
fix() { fmt-fix; lint-fix; }
test() { :; }
test-unit() { :; }

# electron 二进制就绪：复用主仓的 ensure-electron（全机 store + 本仓 node_modules 软链；
# npm workspaces 把 electron 提升到仓根，所以 ROOT 传仓根而不是 app 目录），
# 缺 dist 时 electron 会「惰性下载且无超时」把 lab 静默卡死（主仓 2026-10 实测）。
_ensure_electron() {
  run env DIY_ENSURE_ELECTRON_ROOT="$(_repo_root)" node "$(_main_repo)/scripts/ensure-electron.mjs" --quiet
}

# 依赖包先编 lib：主进程按包名 import、renderer 打包读 exports，都指向 lib/*.js
# 顺序 = 依赖顺序：dev-page → dev-core；主仓的 workbench / ui-workbench 由主仓自己编。
build-deps() {
  ( cd "$SCRIPT_DIR/../../pkgs/dev-ref" && ./sha.sh build )
  ( cd "$SCRIPT_DIR/../../pkgs/dev-core" && ./sha.sh build )
  ( cd "$SCRIPT_DIR/../../pkgs/dev-fs" && ./sha.sh build )
  ( cd "$SCRIPT_DIR/../../pkgs/dev-page" && ./sha.sh build )
  ( cd "$(_main_repo)/pkgs.ts/ui/workbench" && ./sha.sh build )
  ( cd "$(_main_repo)/pkgs.ts/ui/workbench-ui" && ./sha.sh build )
}

build() {
  run npx tsc -p tsconfig.build.json
  build-deps
  build-main
  build-preload
  build-renderer
}

build-main() {
  local d; d="$(_build_dir)"
  # @diy-agent/* 保持外部：运行时按包名解析（真插件边界）
  run npx esbuild main.ts --bundle --platform=node --format=esm --target=node22 \
    --external:electron "--external:@diy-agent/*" --outfile="$d/main/index.mjs"
}

build-preload() {
  local d; d="$(_build_dir)"
  # sandbox 下的 preload 只能是 CJS；只外置 electron
  run npx esbuild preload.ts --bundle --platform=node --format=cjs --target=node22 \
    --external:electron --outfile="$d/preload/index.cjs"
}

build-renderer() {
  local d; d="$(_build_dir)"
  run mkdir -p "$d/renderer"
  run npx esbuild renderer.ts --bundle --platform=browser --format=iife --target=es2022 \
    --outfile="$d/renderer/index.js"
  run cp index.html "$d/renderer/index.html"
}

# 开发实例：构建后直接起（lab 变体自带 CDP 9223）
# 起实例：产物固定 build/app，变体只换运行参数
_run_app() {
  local variant="$1" env="$2"; shift 2
  _ensure_electron
  build
  local d; d="$(_build_dir)"
  # 数据根：**只有 dev 启动器拉起时**才认注入的 DIY_HOME（它带了 DIY_LAUNCH）；
  # 手工跑时 shell 里残留的 DIY_HOME（如生产 ~/.diy）绝不能把人带进生产数据根
  local home; home="${DIY_LAUNCH:+${DIY_HOME:-}}"; home="${home:-$(_home_dir "$variant")}"
  run mkdir -p "$home"
  echo "${info}产物：$d（与变体无关）${reset}"
  echo "${info}数据根：$home（变体 $variant）${reset}"
  # DIY_LAUNCH = 这条 launch 的身份：注册表匹配键 + 窗口标题里的实例 URI（diy://<node>/…）
  # 一律注入 ⇒ 手工跑与 dev 面板拉起在注册表里长得一模一样，没有「另一个 lance」这回事
  run env DIY_HOME="$home" DIY_VARIANT="$variant" DIY_ENV="$env" DIY_LAUNCH="$variant" npx electron "$d/main/index.mjs" "$@"
}

# 试验变体：开发环境 + CDP + 副屏
lab() { _run_app "${DIY_VARIANT:-lab}" development "$@"; }

# 预生产变体（staging）：prod 构建 + 隔离数据根 `build/staging/home`。
# `prod` 这个词只留给真正的生产（~/.diy），worktree 里不再有叫 prod 的 launch。
staging() { _run_app "${DIY_VARIANT:-staging}" production "$@"; }

typecheck() { run npx tsc -p tsconfig.json; }
lint() { run npx oxlint .; }
lint-fix() { run npx oxlint --fix .; }
fmt() { run npx oxfmt --check .; }
fmt-fix() { run npx oxfmt --write .; }

sha "$@"
