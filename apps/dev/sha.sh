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
# 为什么要有这一层：`run.lab` 在前台占着终端，而「再起一份做 A/B 测试」是日常需求。
# 这一层只管**后台起 / 列 / 停**。
#
# ##518 用户裁：**没有槽位**。多份实例 = 多个数据根 + 各自的名字，都由人显式给
# （`app new --home <新根> --name <名字>`）；缺省根的实例在跑就拒绝，不自动编号。
####################################################################################

_reg_dir() { echo "${DIY_DEV_HOME:-$HOME/.diy/dev}/apps"; }

# 本 worktree 的在跑实例：每行 `name<TAB>pid<TAB>home`（name 取实例自报，没名字就 pid）
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
      out.push([String(rec.name ?? rec.launch ?? ""), String(rec.pid), String(rec.diyHome ?? "")]);
    }
    out.sort((a, b) => a[1].localeCompare(b[1]));
    for (const row of out) console.log(row.join("\t"));
  ' "$reg" "$repo"
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
# 数据根：`build/<variant>/home` —— 变体 = 哪类入口（lab / staging）。
#
# ##518 用户裁：**slot 取消**。一个变体一个缺省根；「再起一份」不再靠编号猜，
# 而是显式给 `--home <新根>`（数据根就是身份的一部分），实例名字自己报（--name）。
_home_dir() {
  local variant="${1:-lab}"
  echo "$(_repo_root)/build/$variant/home"
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

# 界面：**React 19**（##518 试点转正）—— 样式走 tailwind v4 CLI（esbuild 不认 @theme），
# 脚本走 esbuild 的 automatic JSX。产物仍是 build/app/renderer/{index.js,index.css,index.html}。
_build_renderer() {
  local d; d="$(_build_dir)/renderer"
  run mkdir -p "$d"
  run npx @tailwindcss/cli -i src-ui/index.css -o "$d/index.css" --minify
  run npx esbuild src-ui/main.tsx --bundle --platform=browser --format=iife --target=es2022 \
    --jsx=automatic --define:process.env.NODE_ENV='"production"' --minify --outfile="$d/index.js"
  run cp index.html "$d/index.html"
}

# electron 的其余参数（`--` 之后原样透传）
_REST=()

# 起实例：产物固定 build/app，变体决定运行参数与缺省数据根。
#   $1 = 变体（lab / staging）  $2 = 环境（development / production）
#   DIY_DEV_HOME / DIY_DEV_NAME 由 run.* 的 --home / --name 传全局（见下）
_run_variant() {
  local variant="$1" env="$2"
  _ensure_electron
  build
  local d; d="$(_build_dir)"
  # 数据根：--home 显式优先；否则缺省 build/<variant>/home
  local home="${DIY_DEV_HOME:-}"
  home="${home:-$(_home_dir "$variant")}"
  run mkdir -p "$home"
  echo "${info}产物：${d}（与变体无关）${reset}"
  echo "${info}数据根：${home}（变体 ${variant}）${reset}"
  # DIY_LAUNCH = 这条启动命令的 id（注册表里的元数据 + 窗口标题的实例 URI）。
  # ##518：**不再有 `<variant>/<slot>`** —— launch 就是 app.yaml 里的条目名，slot 取消。
  local launch="$variant"
  # DIY_INSTANCE_NAME = 实例自报名字（人认得出的那个）；没给就让 diy-app 退化成 <app>#<pid>。
  run env DIY_HOME="$home" DIY_VARIANT="$variant" DIY_ENV="$env" DIY_LAUNCH="$launch" \
    ${DIY_DEV_NAME:+DIY_INSTANCE_NAME="$DIY_DEV_NAME"} npx electron "$d/main/index.mjs" "${_REST[@]}"
}

#: 跑 lab（试验）实例：development + CDP + 副屏
#: 用法: ./sha.sh run.lab [--home <数据根>] [--name <实例名>]
#: 产物固定 build/app；数据根缺省 build/lab/home。再起一份就显式给 --home（新根）+ --name。
sha.def "run.lab" --opt "--home:string::数据根（缺省 build/lab/home）" --opt "--name:string::实例自报名字" --desc "跑 lab 实例"
run.lab() {
  local home name
  sha.parse "$@" || return $?
  DIY_DEV_HOME="$home" DIY_DEV_NAME="$name" _run_variant lab development
}

#: 跑 staging（预生产）实例：prod 构建 + 隔离数据根
#: 用法: ./sha.sh run.staging [--home <数据根>] [--name <实例名>]
#: `prod` 一词只留给真正的生产（~/.diy）；这里跑的是 prod 产物 + build/staging/home。
sha.def "run.staging" --opt "--home:string::数据根（缺省 build/staging/home）" --opt "--name:string::实例自报名字" --desc "跑 staging 实例"
run.staging() {
  local home name
  sha.parse "$@" || return $?
  DIY_DEV_HOME="$home" DIY_DEV_NAME="$name" _run_variant staging production
}

#: 弃用：等价于 `run lab`
lab() { run.lab "$@"; }
#: 弃用：等价于 `run staging`
staging() { run.staging "$@"; }

#: 只类型检查
typecheck() { run npx tsc -p tsconfig.json; }
lint() { run npx oxlint .; }
lint-fix() { run npx oxlint --fix .; }
fmt() { run npx oxfmt --check .; }
fmt-fix() { run npx oxfmt --write .; }

####################################################################################
# app —— 多实例管理（##518）：new / list / stop
#
# 为什么要有这一层：`run.lab` 在前台占着终端，而「再起一份做 A/B 测试」是日常需求。
# 这一层只管**后台起 / 列 / 停**。
#
# ##518 用户裁：**没有槽位**。多份实例 = 多个数据根 + 各自的名字，都由人显式给
# （`app new --home <新根> --name <名字>`）；缺省根的实例在跑就拒绝，不自动编号。
####################################################################################

_reg_dir() { echo "${DIY_DEV_HOME:-$HOME/.diy/dev}/apps"; }

# 本 worktree 的在跑实例：每行 `name<TAB>pid<TAB>home`（name 取实例自报，没名字就 pid）
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
      out.push([String(rec.name ?? rec.launch ?? ""), String(rec.pid), String(rec.diyHome ?? "")]);
    }
    out.sort((a, b) => a[1].localeCompare(b[1]));
    for (const row of out) console.log(row.join("\t"));
  ' "$reg" "$repo"
}

#: 列出本 worktree 在跑的实例（名字 / pid / 数据根）
#: 用法: ./sha.sh app list
app.list() {
  echo "${info}在跑的实例（worktree: $(_repo_root)）${reset}"
  _running | while IFS=$'\t' read -r name pid home; do
    printf '  %-16s pid %-8s %s\n' "${name:-pid $pid}" "$pid" "$home"
  done
}

#: 起一份新实例：后台跑（立刻回到提示符）
#: 用法: ./sha.sh app new [--launch lab] [--home <数据根>] [--name <实例名>]
#: 缺省数据根上已有实例在跑 ⇒ 拒绝（不自动编号）：再起一份请显式给 --home + --name。
sha.def "app.new" --opt "--launch:string=lab:入口（lab / staging）" --opt "--home:string::数据根（缺省 build/<launch>/home）" --opt "--name:string::实例自报名字" --desc "起一份新实例"
app.new() {
  local launch home name
  sha.parse "$@" || return $?
  local root; root="$(_repo_root)"
  local target; target="${home:-$(_home_dir "$launch")}"
  if _running | cut -f3 | grep -qxF "$target"; then
    echo "该数据根已有实例在跑：$target" >&2
    echo "  再起一份请显式给不同数据根：./sha.sh app new --launch $launch --home $root/build/$launch/alt/home --name <名字>" >&2
    return 1
  fi
  local slug; slug="$(basename "$target")"
  local log="$root/build/${launch}/${slug}.log"
  run mkdir -p "$root/build/${launch}" "$target"
  echo "${info}新实例：${launch} @ ${target}（日志 ${log}）${reset}"
  local args=(run "$launch" --home "$target")
  [ -n "$name" ] && args+=(--name "$name")
  nohup "$SCRIPT_DIR/sha.sh" "${args[@]}" > "$log" 2>&1 < /dev/null &
  echo "  已后台启动（pid $!）→ ./sha.sh app list 看状态，app stop <名字|pid> 停它"
}

#: 停一份实例：实例名 / pid / all
#: 用法: ./sha.sh app stop <TARGET>
sha.def "app.stop" --arg "TARGET!:槽位名 / pid / all" --desc "停实例"
app.stop() {
  local TARGET
  sha.parse "$@" || return $?
  local rows; rows="$(_running)"
  if [ "$TARGET" = "all" ]; then
    printf '%s\n' "$rows" | while IFS=$'\t' read -r name pid home; do
      [ -n "$pid" ] && { kill -TERM "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null; echo "  已停 ${name:-pid $pid} (pid ${pid})"; }
    done
    return 0
  fi
  local pid
  pid="$(printf '%s\n' "$rows" | awk -F'\t' -v t="$TARGET" '$1==t || $2==t {print $2; exit}')"
  [ -n "$pid" ] || { echo "找不到目标：$TARGET（用 app list 看看有什么）" >&2; return 1; }
  kill -TERM "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null
  echo "  已停 ${TARGET}（pid ${pid}）"
}

sha "$@"
