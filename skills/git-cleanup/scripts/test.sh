#!/usr/bin/env bash
# git-cleanup test suite
#
# Design:
#   1. Declare test file tree in directory-tree style
#   2. Assert git file status in git-status style
#   3. Assert disk files in directory-tree style
#   4. Each case gets its own tmpdir, auto setup/teardown

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
GIT_CLEANUP="$SCRIPT_DIR/git-cleanup.sh"
PASS=0; FAIL=0

# ── Helpers ─────────────────────────────────────────────────

# ensure_repo — create a temp git repo from a tree description
# Usage: ensure_repo "name" "tree"
#   tree is a directory-tree description, e.g.:
#     ensure_repo "basic" "
#       src/
#       src/x.py
#       a.py
#     "
#   Lines ending with / are directories, others are files.
ensure_repo() {
  local name="$1" tree="$2"
  local tmp; tmp=$(mktemp -d)

  echo "-- $name --" >&2
  echo "" >&2

  cd "$tmp"
  git init --quiet
  git config user.email "t@t"
  git config user.name "t"

  while IFS= read -r line; do
    local path="${line#"${line%%[![:space:]]*}"}"  # strip indent
    [ -z "$path" ] && continue
    case "$path" in
      */) mkdir -p "$path" ;;
      *)  mkdir -p "$(dirname "$path")"; touch "$path" ;;
    esac
  done <<< "$tree"

  echo "$tmp"  # return path on stdout
}

# assert_git_status — assert file status like `git status --short`
# Usage: assert_git_status "$tmp" "tree"
#   tree format (matches git status --short):
#      M  a.py    — modified
#      A  b.py    — staged new
#      D  c.py    — deleted from index (disk may still exist)
#     ??  d.py    — untracked
#   Files not in tree = expected no change
assert_git_status() {
  local tmp="$1" tree="$2"

  cd "$tmp"

  local actual; actual=$(git status --short 2>/dev/null || true)

  # build expected (preserve leading spaces for git-status format)
  local expected=""
  while IFS= read -r line; do
    [[ "$line" =~ ^[[:space:]]*$ ]] && continue
    expected+="$line"$'\n'
  done <<< "$tree"

  actual=$(echo "$actual" | grep -v '^$' | sort)
  expected=$(echo "$expected" | grep -v '^$' | sort)

  if [ "$expected" = "$actual" ]; then
    printf "  [OK] git_status\n"
    PASS=$((PASS + 1))
  else
    printf "  [FAIL] git_status\n"
    printf "    expected:\n"
    echo "$expected" | sed 's/^/      /'
    printf "    actual:\n"
    echo "$actual" | sed 's/^/      /'
    FAIL=$((FAIL + 1))
  fi
}

# assert_files — assert files on disk (relative to repo root)
# Usage: assert_files "$tmp" "tree"
#   tree format is same as ensure_repo's directory-tree style
assert_files() {
  local tmp="$1" tree="$2"

  cd "$tmp"

  local actual; actual=$(find . -not -path './.git/*' -not -name '.git' -not -name '.' | sort | sed 's|^\./||')

  local expected=""
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    expected+="${line#"${line%%[![:space:]]*}"}"$'\n'
  done <<< "$tree"

  actual=$(echo "$actual" | sort)
  expected=$(echo "$expected" | sort)

  if [ "$expected" = "$actual" ]; then
    printf "  [OK] files\n"
    PASS=$((PASS + 1))
  else
    printf "  [FAIL] files\n"
    printf "    expected:\n"
    echo "$expected" | sed 's/^/      /'
    printf "    actual:\n"
    echo "$actual" | sed 's/^/      /'
    FAIL=$((FAIL + 1))
  fi
}

# assert_output — assert script stdout
assert_output() {
  local expected="$1" actual="$2"
  if [ "$expected" = "$actual" ]; then
    printf "  [OK] output\n"
    PASS=$((PASS + 1))
  else
    printf "  [FAIL] output\n"
    printf "    expected: %s\n" "$expected"
    printf "    actual:   %s\n" "$actual"
    FAIL=$((FAIL + 1))
  fi
}

# run_cleanup — run git-cleanup.sh in the given repo
run_cleanup() {
  local tmp="$1"; shift
  cd "$tmp"
  bash "$GIT_CLEANUP" "$@" 2>/dev/null || true
}

# ── Test Cases ──────────────────────────────────────────────

echo ""
echo "=================================================="
echo " git-cleanup test suite"
echo "=================================================="

# ── Case 1: residual after git rm ──
{
  tmp=$(ensure_repo "residual after git rm" "
    src.py
    lib.py
  ")
  cd "$tmp"
  git add src.py lib.py
  git commit -m "init" --quiet
  git rm --cached lib.py --quiet
  git commit -m "rm lib.py" --quiet

  # lib.py still on disk, no longer tracked
  output=$(run_cleanup "$tmp")
  assert_output "❌ lib.py" "$output"
  rm -rf "$tmp"
}

# ── Case 2: no false positive on re-tracked file ──
{
  tmp=$(ensure_repo "no false positive on re-track" "
    src.py
  ")
  cd "$tmp"
  git add src.py
  git commit -m "init" --quiet
  git rm src.py --quiet
  git commit -m "remove" --quiet
  echo "restored" > src.py
  git add src.py
  git commit -m "restore" --quiet
  git rm src.py --quiet
  git commit -m "remove again" --quiet
  echo "restored again" > src.py
  git add src.py
  git commit -m "restore again" --quiet

  output=$(run_cleanup "$tmp")
  assert_output "" "$output"
  rm -rf "$tmp"
}

# ── Case 3: residual hidden by .gitignore ──
{
  tmp=$(ensure_repo "residual hidden by .gitignore" "
    app.log
    .gitignore
  ")
  cd "$tmp"
  echo "log data" > app.log
  git add app.log .gitignore
  git commit -m "add log" --quiet
  echo "*.log" > .gitignore
  git rm app.log --quiet
  git commit -m "gitignore + rm" --quiet
  echo "residual" > app.log

  output=$(run_cleanup "$tmp")
  assert_output "⚠️ app.log" "$output"
  rm -rf "$tmp"
}

# ── Case 4: --rm deletes residual files ──
{
  tmp=$(ensure_repo "--rm deletes residual" "
    data.txt
  ")
  cd "$tmp"
  echo "data" > data.txt
  git add data.txt
  git commit -m "init" --quiet
  git rm --cached data.txt --quiet
  git commit -m "remove" --quiet

  # detect residual
  output=$(run_cleanup "$tmp")
  assert_output "❌ data.txt" "$output"

  # --rm cleanup
  run_cleanup "$tmp" --rm > /dev/null

  # data.txt should be gone from disk
  assert_files "$tmp" ""
  rm -rf "$tmp"
}

# ── Case 5: clean repo, no anomalies ──
{
  tmp=$(ensure_repo "clean repo" "
    ok.txt
  ")
  cd "$tmp"
  echo "ok" > ok.txt
  git add ok.txt
  git commit -m "init" --quiet

  output=$(run_cleanup "$tmp")
  assert_output "" "$output"
  rm -rf "$tmp"
}

# ── Case 6: mixed residuals (both types) ──
{
  tmp=$(ensure_repo "mixed residuals" "
    A.txt
    B.log
    .gitignore
  ")
  cd "$tmp"
  echo "a" > A.txt
  echo "b" > B.log
  git add A.txt B.log .gitignore
  git commit -m "init" --quiet
  echo "*.log" > .gitignore
  git rm A.txt B.log --quiet
  git commit -m "remove all" --quiet
  echo "residual A" > A.txt
  echo "residual B" > B.log

  output=$(run_cleanup "$tmp")
  assert_output "❌ A.txt
⚠️ B.log" "$output"
  rm -rf "$tmp"
}

# ── Case 7: git_status assertion smoke test ──
{
  tmp=$(ensure_repo "git_status smoke test" "
    src/
    src/x.py
    a.py
    b.py
  ")
  cd "$tmp"
  git add .
  git commit -m "init" --quiet

  # modify a.py
  echo "changed" > a.py

  # delete b.py
  git rm b.py --quiet

  # new untracked c.py
  echo "new" > c.py

  assert_git_status "$tmp" "
 M a.py
D  b.py
?? c.py
"
  rm -rf "$tmp"
}

echo ""
echo "=================================================="
echo " Result: $PASS passed, $FAIL failed"
echo "=================================================="

[ "$FAIL" -eq 0 ] && exit 0 || exit 1
