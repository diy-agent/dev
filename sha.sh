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
# 子模块
####################################################################################

#: 子模块同步：把 vendor/（sha 脚本框架等）对齐到仓库记录的提交
#: 用法: ./sha.sh submodule update [--remote]
#: 缺省只对到「当前记录」的提交；--remote 跟到该 submodule 的上游分支最新。
sha.def "submodule.update" --opt "--remote:bool:跟到上游分支最新" --desc "更新子模块"
submodule.update() {
  local remote
  sha.parse "$@" || return $?
  case "${remote:-}" in
    1 | true | yes) set -- remote ;;
    *) set -- ;;
  esac
  if [ "${1:-}" = "remote" ]; then
    run git submodule update --init --recursive --remote
  else
    run git submodule update --init --recursive
  fi
  run git submodule status
}

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

#: 删本仓各包的产物与依赖缓存
clean() {
  run rm -rf ./build ./dist
  local d
  while read -r d; do ( cd "$d" && ./sha.sh clean ); done < <(_workspaces)
}

#: 同步依赖（npm install）
sync() {
  run npm install
  run git submodule update --init --recursive
}

# 在每个 workspace 里跑一条命令（如 `./sha.sh exec npx tsc -p tsconfig.json`）
# 注意：这里覆盖了 bash 内建 `exec` 的名字；本脚本与其 vendor 均不调用内建 exec。
#: 在各 workspace 里并行执行同一个子命令
exec() {
  local d
  while read -r d; do
    echo "${info}▸ $d${reset}"
    ( cd "$d" && "$@" ) || return 1
  done < <(_workspaces)
}

#: 全仓类型检查 + lint
check() {
  local d
  while read -r d; do
    echo "${info}▸ $d${reset}"
    ( cd "$d" && ./sha.sh check ) || return 1
  done < <(_workspaces)
}

#: 自动修复（lint-fix + fmt-fix）
fix() {
  local d
  while read -r d; do ( cd "$d" && ./sha.sh fix ); done < <(_workspaces)
}

#: 跑全部单测
test() {
  run npx vitest run "$@"
}

# dev-core / dev-page 先编 lib（apps/dev 的装配器按包名解析它们）
#: 构建本仓所有包
build() {
  ( cd pkgs/dev-ref && ./sha.sh build )
  ( cd pkgs/dev-core && ./sha.sh build )
  ( cd pkgs/dev-page && ./sha.sh build )
}

# 源码方式跑 ref CLI（cwd 即作用域：请在想操作的目录下调用；##510 起入口只在开发期用）
#: 源码方式跑 dev-ref CLI（cwd 即作用域）
dev() {
  run npx tsx "$SCRIPT_DIR/pkgs/dev-ref/src/cli/index.ts" "$@"
}

sha "$@"
