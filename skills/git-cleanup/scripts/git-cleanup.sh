#!/usr/bin/env bash
# git-cleanup — 找出 git 仓库中处于异常状态的文件并清理
# 用法: git-cleanup [--rm] [路径]
#
# 异常状态:
#   ⚠️ 忽略残留   已被 git rm 提交删除，但 .gitignore 忽略导致磁盘仍有
#   ❌ 未跟踪残留   已被 git rm 提交删除，磁盘仍有（未被 .gitignore 忽略）
#   👻 空目录      git 不跟踪目录，但磁盘存在空目录
#
# 默认仅列出，加 --rm 才真正删除。

set -euo pipefail

DO_RM=false
TARGET="."

while [[ $# -gt 0 ]]; do
  case "$1" in
    --rm) DO_RM=true; shift ;;
    -h|--help) sed -n '2,10p' "$0" | sed 's/^# //'; exit 0 ;;
    *) TARGET="$1"; shift ;;
  esac
done

# ── 找出已从 git 删除但磁盘仍在的文件 ──────────────────────
# 方法：遍历 git 历史中曾删除的文件，过滤出磁盘仍存在的
find_deleted_on_disk() {
  git log --diff-filter=D --format="" --name-only -- "$TARGET" 2>/dev/null \
    | sort -u \
    | while read -r f; do
        [ -e "$f" ] || continue
        # 避免误杀：检查当前 git 是否仍在跟踪（可能是重新 add 的）
        if git ls-files --error-unmatch "$f" &>/dev/null 2>&1; then
          continue
        fi
        if git check-ignore -q "$f" 2>/dev/null; then
          echo "⚠️ $f"
        else
          echo "❌ $f"
        fi
      done
}

# ── 找出空目录 ──────────────────────────────────────────────
find_empty_dirs() {
  find "$TARGET" -type d -empty 2>/dev/null \
    | while read -r d; do
        # 跳过 git 跟踪的目录、.git
        [[ "$d" == */.git/* || "$d" == */.git ]] && continue
        if git ls-files --error-unmatch "$d" &>/dev/null 2>&1; then
          continue
        fi
        echo "👻 $d"
      done
}

# ── 主流程 ──────────────────────────────────────────────────

found=false

while IFS= read -r line; do
  [ -z "$line" ] && continue
  found=true
  icon="${line:0:1}"   # ⚠️ ❌ 👻 等多字节字符取首字节不准确，改用前缀判断
  path="${line#* }"

  if $DO_RM; then
    rm -rf "$path"
    echo "🗑️  $line"
  else
    echo "$line"
  fi
done < <(
  find_deleted_on_disk
  find_empty_dirs
)

if ! $found; then
  echo "(无异常文件)" >&2
fi
