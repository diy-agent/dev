#!/usr/bin/env bash
#
# pkgs/dev-fs — dev 工具的文件能力（##518）：声明式 rpc API + worktree 内路径 jail
#
# ── 编写规则 ────────────────────────────────────
# 1. 定义函数即为子命令：`foo() { ... }` → `./sha.sh foo`
# 2. 用 `run` 执行外部命令（带彩色日志）
# 3. 文件末尾保留 `sha "$@"` 调度入口
#
# ── 执行链 ──────────────────────────────────────
# sha.sh → source ../../sha.common.sh → source vendor/sha/sha.bash
#

# shellcheck disable=SC2329,SC2317,SC2034
set -o errtrace -o errexit -o functrace -o pipefail
shopt -s globstar extglob

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
source "../../sha.common.sh"

clean() { run rm -rf ./lib ./build ./dist; }
sync() { :; }
check() { typecheck; lint; }
fix() { fmt-fix; lint-fix; }

# 产物 lib/*.js + *.d.ts：装配器与 renderer 都按包名（exports）解析
build() { run npx tsc -p tsconfig.build.json; }

test() { run npx vitest run "$@"; }
test-unit() { run npx vitest run "$@"; }
test-watch() { run npx vitest "$@"; }

typecheck() { run npx tsc -p tsconfig.json; }
lint() { run npx oxlint src/ tests/; }
lint-fix() { run npx oxlint --fix src/ tests/; }
fmt() { run npx oxfmt --check src/ tests/; }
fmt-fix() { run npx oxfmt --write src/ tests/; }

sha "$@"
