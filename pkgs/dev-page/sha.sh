#!/usr/bin/env bash
#
# pkgs/dev-page — dev 启动器的页面插件（主进程方法表 + renderer，##508）
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

# 依赖 @diy-agent/dev-core 的 lib：先编它（装配器与 renderer 都按包名解析）
build-core() { ( cd ../dev-core && ./sha.sh build ); }
build() { build-core; run npx tsc -p tsconfig.build.json; }

test() { run npx vitest run "$@"; }
test-unit() { run npx vitest run "$@"; }

typecheck() { run npx tsc -p tsconfig.json; }
lint() { run npx oxlint src/; }
lint-fix() { run npx oxlint --fix src/; }
fmt() { run npx oxfmt --check src/; }
fmt-fix() { run npx oxfmt --write src/; }

sha "$@"
