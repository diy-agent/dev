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

clean() {
  run rm -rf ./build ./dist
  run rm -rf ./pkgs/dev/build ./pkgs/dev/dist
}

sync() {
  run npm install
  run git submodule update --init --recursive
}

check() {
  run npx tsc --noEmit
  run npx oxlint pkgs/
}

fix() {
  run npx oxfmt --write pkgs/
  run npx oxlint --fix pkgs/
}

test() {
  run npx vitest run "$@"
}

build() {
  ( cd pkgs/dev && run npx vite build --config vite.cli.config.ts )
}

# 源码方式跑 dev CLI（cwd 即作用域：请在想操作的目录下调用）
dev() {
  run npx tsx "$SCRIPT_DIR/pkgs/dev/src/cli/index.ts" "$@"
}

sha "$@"
