#!/usr/bin/env bash
#
# apps/dev — dev 启动器装配器（##508 从主仓 apps/dev 搬来并拆包）
#
# ── 编写规则 ────────────────────────────────────
# 定义函数即为子命令：`foo() { ... }` → `./sha.sh foo`
#
# ── 执行链 ──────────────────────────────────────
# sha.sh → source ../../sha.common.sh → source vendor/sha/sha.bash → ####################################################################################
# app —— 多实例管理（##518）：new / list / stop
#
# 为什么要有这一层：`lab`/`staging` 一次只起**一份**（前台，占着终端），而
# 「再起一份做 remote A/B 测试」是日常需求。命令层负责**自动分配 slot**并让实例跑在后台，
# 人只需要说「再来一个」。
####################################################################################

_reg_dir() { echo "${DIY_DEV_HOME:-$HOME/.diy/dev}/apps"; }

# 本 worktree 的在跑实例：每行 `slot<TAB>pid<TAB>home`
_running() {
  local reg repo; reg="$(_reg_dir)"; repo="$(_repo_root)"
  [ -d "$reg" ] || return 0
  node -e '
    const { readdirSync, readFileSync } = require("node:fs");
    const [dir, repo] = process.argv.slice(1);
    const out = [];
    for (const name of readdirSync(dir)) {
      if (!name.endsWith(".json")) continue;
      let rec;
      try { rec = JSON.parse(readFileSync(`${dir}/${name}`, "utf-8")); } catch { continue; }
      if (rec.app !== "diy-dev" || rec.worktree !== repo) continue;
      try { process.kill(rec.pid, 0); } catch { continue; } // 死记录不算
      out.push([String(rec.launch ?? ""), String(rec.pid), String(rec.diyHome ?? "")]);
    }
    out.sort((a, b) => a[1].localeCompare(b[1]));
    for (const row of out) console.log(row.join("\t"));
  ' "$reg" "$repo"
}

#: 多实例管理：app list / app new [variant] / app stop <slot|pid|all>
#: 用法: ./sha.sh app list
#: 槽位数据根 build/<变体>/<槽>/home，自动挑最小空闲槽。
app() {
  local action="${1:-list}"; shift || true
  case "$action" in
    list|ls)
      echo "${info}在跑的实例（worktree: $(_repo_root)）${reset}"
      _running | while IFS=$'\t' read -r slot pid home; do
        printf '  %-10s pid %-8s %s\n' "$slot" "$pid" "$home"
      done
      ;;
    new)
      local variant="${1:-lab}"
      # 自动挑最小的空闲整数 slot
      local slot=1 used
      used="$(_running | cut -f1)"
      while printf '%s\n' "$used" | grep -qx "${variant}/${slot}"; do slot=$((slot + 1)); done
      local log="$(_repo_root)/build/${variant}/${slot}.log"
      run mkdir -p "$(_repo_root)/build/${variant}"
      echo "${info}新实例：${variant}/${slot}（日志 ${log}）${reset}"
      # 后台起：脱离终端（disown 效果），立刻回到提示符
      nohup "$SCRIPT_DIR/sha.sh" "$variant" "$slot" > "$log" 2>&1 < /dev/null &
      echo "  已后台启动 ${variant}/${slot}（pid $!）→ ./sha.sh app list 看状态，app stop ${slot} 停它"
      ;;
    stop)
      local target="${1:-}"
      [ -n "$target" ] || { echo "用法：./sha.sh app stop <slot|pid|all>" >&2; return 1; }
      local rows; rows="$(_running)"
      if [ "$target" = "all" ]; then
        printf '%s\n' "$rows" | while IFS=$'\t' read -r slot pid home; do
          [ -n "$pid" ] && { kill -TERM "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null; echo "  已停 ${slot} (pid ${pid})"; }
        done
        return 0
      fi
      local pid
      pid="$(printf '%s\n' "$rows" | awk -F'\t' -v t="$target" '$1==t || $1 ~ "/"t"$" {print $2; exit}')"
      [ -n "$pid" ] || { echo "找不到目标：$target（用 app list 看看有什么）" >&2; return 1; }
      kill -TERM "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null
      echo "  已停 ${target}（pid ${pid}）"
      ;;
    *)
      echo "用法：./sha.sh app <new [variant] | list | stop <slot|pid|all>>" >&2
      return 1
      ;;
  esac
}

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
# 选项/位置参数解析（sha.parse / sha.def）在新版里单独成文件
if ! declare -F sha.parse >/dev/null; then source "$SCRIPT_DIR/../../vendor/sha/sha_opt.bash"; fi

# ── 产物 vs 变体：两件事，别绑一起 ─────────────────────────
# 产物（tsc + esbuild）只跟**源码**有关：一份，落在 `build/app/`，与变体无关。
# 变体只决定**运行空间**：数据根 `build/<variant>/home`、`DIY_ENV`、CDP / 副屏行为。
#   lab  = 试验（development、CDP、副屏、watch 重启会打断轮次）
#   prod = 生产（production、真数据根；改 src 不重启）
_build_dir() { echo "build/app"; }
# 数据根：`build/<variant>/<slot>/home` —— 变体 = 哪类入口，slot = 第几份实例。
# 不兼容旧路径 `build/<variant>/home`：都是开发环境数据，重来即可（用户裁：简单一致）。
_home_dir() {
  local variant="${1:-lab}" slot="${2:-1}"
  echo "$(_repo_root)/build/$variant/$slot/home"
}
_repo_root() { ( cd "$SCRIPT_DIR/../.." && pwd ); }
_main_repo() { ( cd "$SCRIPT_DIR/../../../diy" && pwd ); }

clean() { run rm -rf ./build ./dist ./lib; }
#: 同步依赖（本包无依赖，空实现）
sync() { :; }
#: 类型 + lint
check() { typecheck; lint; }
fix() { fmt-fix; lint-fix; }
#: 跑测试（本包无单测，空实现）
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
_build_deps() {
  ( cd "$SCRIPT_DIR/../../pkgs/dev-ref" && ./sha.sh build )
  ( cd "$SCRIPT_DIR/../../pkgs/dev-core" && ./sha.sh build )
  ( cd "$SCRIPT_DIR/../../pkgs/dev-fs" && ./sha.sh build )
  ( cd "$SCRIPT_DIR/../../pkgs/dev-page" && ./sha.sh build )
  ( cd "$(_main_repo)/pkgs.ts/ui/workbench" && ./sha.sh build )
  ( cd "$(_main_repo)/pkgs.ts/ui/workbench-ui" && ./sha.sh build )
}

#: 构建全部产物（tsc + 依赖包 lib + main/preload/renderer）
#: 用法: ./sha.sh build
#: 产物固定 build/app，与变体无关。
build() {
  run npx tsc -p tsconfig.build.json
  _build_deps
  _build_main
  _build_preload
  _build_renderer
}

_build_main() {
  local d; d="$(_build_dir)"
  # @diy-agent/* 保持外部：运行时按包名解析（真插件边界）
  run npx esbuild main.ts --bundle --platform=node --format=esm --target=node22 \
    --external:electron "--external:@diy-agent/*" --outfile="$d/main/index.mjs"
}

_build_preload() {
  local d; d="$(_build_dir)"
  # sandbox 下的 preload 只能是 CJS；只外置 electron
  run npx esbuild preload.ts --bundle --platform=node --format=cjs --target=node22 \
    --external:electron --outfile="$d/preload/index.cjs"
}

_build_renderer() {
  local d; d="$(_build_dir)"
  run mkdir -p "$d/renderer"
  run npx esbuild renderer.ts --bundle --platform=browser --format=iife --target=es2022 \
    --outfile="$d/renderer/index.js"
  run cp index.html "$d/renderer/index.html"
}

# 第一个非 `-` 开头的位置参数 = slot（第几份实例），其余原样透传给 electron
_REST=()
SLOT=1
# ⚠️ 不能用 `$(...)` 取返回值：命令替换跑在子 shell 里，`_REST` 会丢。
# 一律写全局：SLOT = 第几份实例，_REST = 透传给 electron 的其余参数。
_take_slot() {
  local first="${1:-}"
  if [ -n "$first" ] && [ "${first#-}" = "$first" ]; then
    SLOT="$first"
    _REST=("${@:2}")
  else
    SLOT=1
    _REST=("$@")
  fi
}

# 起实例：产物固定 build/app，变体只换运行参数，slot 决定数据根
_run_variant() {
  local variant="$1" env="$2" slot="${3:-}"
  slot="${slot:-${DIY_DEV_LAUNCH_SLOT:-1}}"
  _ensure_electron
  build
  local d; d="$(_build_dir)"
  # 数据根：**只有 dev 启动器拉起时**才认注入的 DIY_HOME（它带了 DIY_LAUNCH）；
  # 手工跑时 shell 里残留的 DIY_HOME（如生产 ~/.diy）绝不能把人带进生产数据根
  local home; home="${DIY_LAUNCH:+${DIY_HOME:-}}"; home="${home:-$(_home_dir "$variant" "$slot")}"
  run mkdir -p "$home"
  echo "${info}产物：${d}（与变体无关）${reset}"
  echo "${info}数据根：${home}（变体 ${variant}，slot ${slot}）${reset}"
  # DIY_LAUNCH = 这条 launch 的身份：注册表匹配键 + 窗口标题里的实例 URI（diy://<node>/…）
  # 一律注入 ⇒ 手工跑与 dev 面板拉起在注册表里长得一模一样，没有「另一个 lance」这回事
  local launch="${variant}/${slot}"
  # DIY_DEV_LAUNCH_SLOT：让 app 自己也能知道是第几份（注册表 / 标题 / URI 用）
  run env DIY_HOME="$home" DIY_VARIANT="$variant" DIY_ENV="$env" DIY_LAUNCH="$launch" \
    DIY_DEV_LAUNCH_SLOT="$slot" npx electron "$d/main/index.mjs" "${_REST[@]}"
}

#: 跑 lab（试验）实例：development + CDP + 副屏
#: 用法: ./sha.sh run.lab [--slot N]
#: 产物固定 build/app；数据根 build/lab/<slot>/home；slot 缺省 1，也可由 DIY_DEV_LAUNCH_SLOT 给。
#: 槽位 = 第几份实例：再起一份做 remote A/B 测试时用它，两份数据互不干扰。
sha.def "run.lab" --opt "--slot:string=1:实例槽位（第几份）" --desc "跑 lab 实例"
run.lab() {
  local slot
  sha.parse "$@" || return $?
  _run_variant lab development "$slot"
}

#: 跑 staging（预生产）实例：prod 构建 + 隔离数据根
#: 用法: ./sha.sh run.staging [--slot N]
#: `prod` 一词只留给真正的生产（~/.diy）；这里跑的是 prod 产物 + build/staging/<slot>/home。
sha.def "run.staging" --opt "--slot:string=1:实例槽位（第几份）" --desc "跑 staging 实例"
run.staging() {
  local slot
  sha.parse "$@" || return $?
  _run_variant staging production "$slot"
}

#: 弃用：等价于 `run lab`，请改用 ./sha.sh run lab [--slot N]
lab() { _take_slot "$@"; _run_variant lab development "$SLOT"; }
#: 弃用：等价于 `run staging`，请改用 ./sha.sh run staging [--slot N]
staging() { _take_slot "$@"; _run_variant staging production "$SLOT"; }

#: 只类型检查
typecheck() { run npx tsc -p tsconfig.json; }
lint() { run npx oxlint .; }
lint-fix() { run npx oxlint --fix .; }
fmt() { run npx oxfmt --check .; }
fmt-fix() { run npx oxfmt --write .; }

####################################################################################
# app —— 多实例管理（##518）：new / list / stop
#
# 为什么要有这一层：`lab`/`staging` 一次只起**一份**（前台，占着终端），而
# 「再起一份做 remote A/B 测试」是日常需求。命令层负责**自动分配 slot**并让实例跑在后台，
# 人只需要说「再来一个」。
####################################################################################

_reg_dir() { echo "${DIY_DEV_HOME:-$HOME/.diy/dev}/apps"; }

# 本 worktree 的在跑实例：每行 `slot<TAB>pid<TAB>home`
_running() {
  local reg repo; reg="$(_reg_dir)"; repo="$(_repo_root)"
  [ -d "$reg" ] || return 0
  node -e '
    const { readdirSync, readFileSync } = require("node:fs");
    const [dir, repo] = process.argv.slice(1);
    const out = [];
    for (const name of readdirSync(dir)) {
      if (!name.endsWith(".json")) continue;
      let rec;
      try { rec = JSON.parse(readFileSync(`${dir}/${name}`, "utf-8")); } catch { continue; }
      if (rec.app !== "diy-dev" || rec.worktree !== repo) continue;
      try { process.kill(rec.pid, 0); } catch { continue; } // 死记录不算
      out.push([String(rec.launch ?? ""), String(rec.pid), String(rec.diyHome ?? "")]);
    }
    out.sort((a, b) => a[1].localeCompare(b[1]));
    for (const row of out) console.log(row.join("\t"));
  ' "$reg" "$repo"
}

#: 多实例管理：app list / app new [variant] / app stop <slot|pid|all>
#: 用法: ./sha.sh app list
#: 槽位数据根 build/<变体>/<槽>/home，自动挑最小空闲槽。
app() {
  local action="${1:-list}"; shift || true
  case "$action" in
    list|ls)
      echo "${info}在跑的实例（worktree: $(_repo_root)）${reset}"
      _running | while IFS=$'\t' read -r slot pid home; do
        printf '  %-10s pid %-8s %s\n' "$slot" "$pid" "$home"
      done
      ;;
    new)
      local variant="${1:-lab}"
      # 自动挑最小的空闲整数 slot
      local slot=1 used
      used="$(_running | cut -f1)"
      while printf '%s\n' "$used" | grep -qx "${variant}/${slot}"; do slot=$((slot + 1)); done
      local log="$(_repo_root)/build/${variant}/${slot}.log"
      run mkdir -p "$(_repo_root)/build/${variant}"
      echo "${info}新实例：${variant}/${slot}（日志 ${log}）${reset}"
      # 后台起：脱离终端（disown 效果），立刻回到提示符
      nohup "$SCRIPT_DIR/sha.sh" "$variant" "$slot" > "$log" 2>&1 < /dev/null &
      echo "  已后台启动 ${variant}/${slot}（pid $!）→ ./sha.sh app list 看状态，app stop ${slot} 停它"
      ;;
    stop)
      local target="${1:-}"
      [ -n "$target" ] || { echo "用法：./sha.sh app stop <slot|pid|all>" >&2; return 1; }
      local rows; rows="$(_running)"
      if [ "$target" = "all" ]; then
        printf '%s\n' "$rows" | while IFS=$'\t' read -r slot pid home; do
          [ -n "$pid" ] && { kill -TERM "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null; echo "  已停 ${slot} (pid ${pid})"; }
        done
        return 0
      fi
      local pid
      pid="$(printf '%s\n' "$rows" | awk -F'\t' -v t="$target" '$1==t || $1 ~ "/"t"$" {print $2; exit}')"
      [ -n "$pid" ] || { echo "找不到目标：$target（用 app list 看看有什么）" >&2; return 1; }
      kill -TERM "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null
      echo "  已停 ${target}（pid ${pid}）"
      ;;
    *)
      echo "用法：./sha.sh app <new [variant] | list | stop <slot|pid|all>>" >&2
      return 1
      ;;
  esac
}

sha "$@"
