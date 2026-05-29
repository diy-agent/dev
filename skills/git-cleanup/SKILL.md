---
name: git-cleanup
description: Git 异常文件清理。当 git rm 提交后磁盘仍有残留、或被 .gitignore 忽略的残留文件需要清理时使用。默认仅列出异常文件，加 --rm 才删除。
---

# Git 异常文件清理

## 用法

```bash
bash scripts/git-cleanup.sh [--rm] [路径]
```

默认列出异常文件，加 `--rm` 才删除。

## 检测的异常状态

```
❌ 未跟踪残留    git rm 提交删除后磁盘仍有（未被 .gitignore 忽略）
⚠️ 忽略残留     git rm 提交删除后磁盘仍有（被 .gitignore 忽略）
👻 空目录        git 不跟踪的空目录残留
```

## 不会误报

- 重新 `git add` 恢复的文件 → 视为正常跟踪，不报
- 从未被 git 跟踪过的新文件 → 不在此工具范围，用 `git clean`
