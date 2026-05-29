#!/usr/bin/env bash
# git-cleanup 测试
# 在临时 git 仓库中模拟各种异常状态，验证检测和清理行为

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
GIT_CLEANUP="$SCRIPT_DIR/git-cleanup.sh"
TEST_DIR=$(mktemp -d)
PASS=0
FAIL=0

cleanup_test_dir() { rm -rf "$TEST_DIR"; }
trap cleanup_test_dir EXIT

say()  { echo "  $*"; }
pass() { echo "  ✅ PASS: $*"; PASS=$((PASS + 1)); }
fail() { echo "  ❌ FAIL: $*"; FAIL=$((FAIL + 1)); }

assert_contains() {
  local haystack="$1" needle="$2" msg="$3"
  if echo "$haystack" | grep -qF "$needle"; then
    pass "$msg"
  else
    fail "$msg — 期望包含 '$needle'"
    echo "    实际输出: $haystack"
  fi
}

assert_not_contains() {
  local haystack="$1" needle="$2" msg="$3"
  if echo "$haystack" | grep -qF "$needle"; then
    fail "$msg — 不应包含 '$needle'"
  else
    pass "$msg"
  fi
}

# ── 初始化测试仓库 ──────────────────────────────────────────

cd "$TEST_DIR"
git init --quiet
git config user.email "test@test"
git config user.name "test"

mkdir -p src lib
echo "main" > src/main.py
echo "util" > lib/util.py
git add -A
git commit -m "init" --quiet

echo ""
echo "══════════════════════════════════════════════"
echo " git-cleanup 测试"
echo "══════════════════════════════════════════════"
echo ""

# ═══════════════════════════════════════════════════════════
# 1: git rm 提交后磁盘残留（未被 .gitignore）
# ═══════════════════════════════════════════════════════════
echo "── 1: git rm 提交 → 磁盘残留 ──"
echo ""

git rm --cached lib/util.py --quiet
git commit -m "remove util.py" --quiet
# --cached 后磁盘文件还在 → 成为异常残留

out=$(bash "$GIT_CLEANUP")
assert_contains "$out" "❌" "检测到未跟踪残留"
assert_contains "$out" "lib/util.py" "精确指向残留文件"

# 正常跟踪文件不应出现
assert_not_contains "$out" "src/main.py" "不误报正常跟踪文件"

echo ""

# ═══════════════════════════════════════════════════════════
# 2: 重新 git add 回来的文件不应被误报
# ═══════════════════════════════════════════════════════════
echo "── 2: 删除后重新跟踪 → 不误报 ──"
echo ""

# 先把 lib/util.py add 回来，模拟恢复场景
git add lib/util.py
git commit -m "restore util.py" --quiet

# 再次 git rm 并提交
git rm lib/util.py --quiet
git commit -m "remove util.py" --quiet

# 磁盘上重建并重新 git add
mkdir -p lib
echo "restored" > lib/util.py
git add lib/util.py
git commit -m "restore util.py again" --quiet

out=$(bash "$GIT_CLEANUP")
assert_not_contains "$out" "lib/util.py" "重新跟踪的文件不误报"

echo ""

# ═══════════════════════════════════════════════════════════
# 3: 被 .gitignore 忽略的残留
# ═══════════════════════════════════════════════════════════
echo "── 3: .gitignore 后的残留 ──"
echo ""

# 先提交一个 log 文件（此时无 gitignore）
echo "debug log" > debug.log
git add debug.log
git commit -m "add log file" --quiet

# 然后添加 .gitignore，再 git rm 并提交
echo "*.log" > .gitignore
git add .gitignore
git rm debug.log --quiet
git commit -m "gitignore + remove log" --quiet

# 手动重建，现在被 .gitignore 忽略
echo "residual log" > debug.log

out=$(bash "$GIT_CLEANUP")
assert_contains "$out" "⚠️" "标记被 .gitignore 忽略的残留"

echo ""

# ═══════════════════════════════════════════════════════════
# 4: 空目录检测
# ═══════════════════════════════════════════════════════════
echo "── 4: 空目录残留 ──"
echo ""

mkdir -p empty_dir

out=$(bash "$GIT_CLEANUP")
assert_contains "$out" "👻" "检测到空目录"
assert_contains "$out" "empty_dir" "精确指向空目录"

echo ""

# ═══════════════════════════════════════════════════════════
# 5: --rm 实际删除
# ═══════════════════════════════════════════════════════════
echo "── 5: --rm 删除 ──"
echo ""

# 利用测试 1 产生的 lib/util.py 残留 + 测试 3 的 debug.log + 测试 4 的 empty_dir
# 先确认当前有残留
out=$(bash "$GIT_CLEANUP")
# 残留可能是 ❌ 或 ⚠️，不限定具体类型
if echo "$out" | grep -qE '[❌⚠️👻]'; then
  pass "--rm 前检测到残留"
else
  fail "--rm 前检测到残留 — 无任何残留标记"
  echo "    实际输出: $out"
fi

# 执行删除
out=$(bash "$GIT_CLEANUP" --rm)
assert_contains "$out" "🗑️" "--rm 执行了删除"

# 删除后干净
out=$(bash "$GIT_CLEANUP")
# (无异常文件) 走 stderr，stdout 为空
[ -z "$out" ] && pass "--rm 后仓库干净" || fail "--rm 后仓库干净 — stdout 应为空"

echo ""
echo "══════════════════════════════════════════════"
echo " 结果: $PASS 通过, $FAIL 失败"
echo "══════════════════════════════════════════════"

[ "$FAIL" -eq 0 ] && exit 0 || exit 1
