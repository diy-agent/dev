#!/usr/bin/env bash
#
# _diy 开发辅助仓入口（TypeScript / npm workspaces）
#
# ── 编写规则 ────────────────────────────────────
# 1. 定义函数即为子命令：`foo() { ... }` → `./sha.sh foo`
# 2. 用 `run` 执行外部命令（带彩色日志）
# 3. 文件末尾保留 `sha "$@"` 调度入口
#
# ── 执行链 ──────────────────────────────────────
# sha.sh → source ./sha.common.sh → source vendor/sha/sha.bash
#
# 依赖主仓（../diy）的包走 path 依赖；主仓改了先 `cd ../diy && ./sha.sh build-pkgs`。
#

# shellcheck disable=SC2329,SC2317,SC2034
set -o errtrace -o errexit -o functrace -o pipefail
shopt -s globstar extglob

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
source "./sha.common.sh"

####################################################################################
# 必备子命令
####################################################################################

# 每个 workspace（pkgs/* + apps/*）都是一个独立单元：自己带 sha.sh 与 tsconfig
_workspaces() {
  local d
  for d in pkgs/* apps/*; do
    [ -f "$d/package.json" ] || continue
    echo "$d"
  done
}

clean() {
  run rm -rf ./build ./dist
  local d
  while read -r d; do ( cd "$d" && ./sha.sh clean ); done < <(_workspaces)
}

sync() {
  run npm install
  run git submodule update --init --recursive
}

# 在每个 workspace 里跑一条命令（如 `./sha.sh exec npx tsc -p tsconfig.json`）
# 注意：这里覆盖了 bash 内建 `exec` 的名字；本脚本与其 vendor 均不调用内建 exec。
exec() {
  local d
  while read -r d; do
    echo "${info}▸ $d${reset}"
    ( cd "$d" && "$@" ) || return 1
  done < <(_workspaces)
}

check() {
  local d
  while read -r d; do
    echo "${info}▸ $d${reset}"
    ( cd "$d" && ./sha.sh check ) || return 1
  done < <(_workspaces)
}

fix() {
  local d
  while read -r d; do ( cd "$d" && ./sha.sh fix ); done < <(_workspaces)
}

test() {
  run npx vitest run "$@"
}

# dev-core / dev-page 先编 lib（apps/dev 的装配器按包名解析它们）
build() {
  ( cd pkgs/dev-core && ./sha.sh build )
  ( cd pkgs/dev-page && ./sha.sh build )
  ( cd pkgs/dev-ref && ./sha.sh build )
}

# 源码方式跑 dev CLI（cwd 即作用域：请在想操作的目录下调用）
dev() {
  run npx tsx "$SCRIPT_DIR/pkgs/dev-ref/src/cli/index.ts" "$@"
}

sha "$@"
