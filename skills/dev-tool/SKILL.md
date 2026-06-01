---
name: dev-tool
description: >
  AI Agent 使用 dev CLI 工具的操作指南。
  触发词：创建 issue、开始工作、提交代码、创建 PR、合并 PR、查看状态、清理 worktree、
  关闭 issue、复盘、dev 命令用法咨询。
  任何涉及"dev start""dev commit""dev status""dev pr""dev merge""dev prune"等操作都触发此 skill。
---

# dev-tool — dev CLI 工具指南

## 执行规则

- **始终使用 `uv run dev <command>`** 而非全局 `dev`，避免版本不一致
- dev 命令默认在**当前 worktree 下**执行，涉及 git 操作会自动识别 worktree 上下文
- 不要直接使用 `gh` 裸命令操作 issue/PR，通过 `dev` 封装命令

---

## Agent 须知：交互命令与绕过方式

以下命令在**未提供必要 option 时会进入 stdin 交互模式**，可能导致 Agent 卡死。执行前务必先查 `dev <cmd> -h`。

| 命令 | 交互点 | 绕过方式 |
|------|--------|----------|
| `dev merge-pr` | 策略选择器 | `--method squash/merge/rebase` |
| `dev prune` | 确认清理 | `-y` |
| `dev commit` | 编辑器编辑 message | `-m "msg"` 或 `-t TYPE -s SCOPE` |
| `dev close` | 确认关闭 | `-y` |

**通用原则**：所有交互式 prompt 都有对应的 option 跳过。执行前先用 `-h` 查看，找不到再查 skill。

---

## 命令速查

### `dev new <描述>`

创建新 issue。参数 `<描述>` 为自然语言标题。

```bash
uv run dev new "优化登录页面性能"
```

自动：创建 issue → 关联 Project → 设置字段 → Status=Backlog

### `dev start <issue> [--priority P] [--size S]`

开始工作。

```bash
uv run dev start 42
uv run dev start 42 --priority P1 --size M
```

自动：Status → In progress → 创建 worktree → 创建分支 → 推送远端

### `dev status [--all/-a] [--issue N]`

查看 worktree 状态。

```bash
uv run dev status        # 树状概览所有 worktree
uv run dev status -a     # 展开详情（URL、拓扑图）
uv run dev status --issue 42  # 查询单个 issue
```

### `dev commit [-t TYPE] [-s SCOPE] [-m MSG]`

提交代码。

```bash
uv run dev commit                    # 自动检测 type/scope+生成 message
uv run dev commit -t fix -s cli -m "修复路径问题"
```

执行链：`check` → `test` → git-cleanup 检查 → Conventional Commit → git commit

### `dev doctor`

规范检查。

```bash
uv run dev doctor
```

检查 sha.sh/pyproject 是否符合规范。

### `dev pr`

创建 PR。

```bash
uv run dev pr
```

自动：推送 → 创建 PR（关联 issue）→ Status → In review

### `dev merge-pr [--method squash|merge]`

合并 PR。

```bash
uv run dev merge-pr          # 默认 squash
uv run dev merge-pr --method merge  # 普通 merge
```

自动：GitHub squash merge → 拉取 main → 提示可清理

### `dev remove`

移除 worktree，**不删除本地分支**。

```bash
uv run dev remove
```

### `dev prune`

清理已合并分支。

```bash
uv run dev prune          # 清理远程已合并分支
uv run dev prune --local  # 一并清理本地分支
```

### `dev retro <issue>`

复盘。

```bash
uv run dev retro 42
```

引导填写复盘内容，写入 Issue body 的 Retro 段落。

---

## 常用流程

### 新任务
```bash
uv run dev new "功能描述"
uv run dev start <N>
# ... 修改代码
uv run dev commit
uv run dev pr
```

### 日常
```bash
uv run dev status -a      # 查看所有 worktree 状态
uv run dev doctor          # 检查规范
```

### 收尾
```bash
uv run dev merge-pr        # 合并 PR
uv run dev prune           # 清理
uv run dev retro <N>       # 复盘
```

---

## 故障排查

| 现象 | 原因 | 解决 |
|------|------|------|
| `dev` 命令不存在 | 未激活环境 | `uv sync; source .venv/bin/activate` |
| `dev status` 显示异常 | gh 未登录 | `gh auth status` |
| `dev start` 失败 | 分支或 worktree 冲突 | 检查 `git branch -l` 和 `git worktree list` |
| `dev commit` 跳过测试 | 项目无 test 入口 | 正常，日志打印 `[SKIP]` |
