# diy-dev — dev CLI 操作手册

> 命令列表、交互绕过表、常用流程、故障排查的详细内容。

所有命令通过 `_diy` 项目的 `uv run dev` 执行。

## 命令速查

### `dev new <描述>`

```bash
uv run dev new "优化登录页面性能"
```

自动：创建 issue → 关联 Project → 设置字段 → Status=Backlog

### `dev start <issue> [--priority P] [--size S]`

```bash
uv run dev start 42
uv run dev start 42 --priority P1 --size M
```

自动：Status → In progress → 创建 worktree（`.worktree/<N>-<slug>`）→ 创建分支 → 推送远端

### `dev status [--issue N]`

```bash
uv run dev status             # 所有项目 worktree 概览
uv run dev status --issue 42  # 查询单个 issue
```

### `dev commit <issue> [--type TYPE] [--scope SCOPE] [--message MSG]`

```bash
uv run dev commit 42                                # 自动检测 type/scope+生成 message
uv run dev commit 42 --type fix --scope cli         # 指定 type/scope
uv run dev commit 42 -m "修复路径问题"              # 完全指定
```

执行链：`check` → `test` → git-cleanup 检查 → Conventional Commit → git commit

快捷方式：在 worktree 内用 `./sha.sh commit`。

### `dev doctor`

```bash
uv run dev doctor
```

检查 sha.sh/pyproject 是否符合规范。

### `dev pr <issue>`

```bash
uv run dev pr 42
```

自动：推送 → 创建 PR（关联 issue）→ Status → In review。快捷方式：`./sha.sh pr`。

### `dev merge-pr [--method squash|merge]`

```bash
uv run dev merge-pr                    # 默认 squash
uv run dev merge-pr --method merge     # 普通 merge
```

自动：GitHub squash merge → 拉取 main → 提示可清理

### `dev remove <issue>`

```bash
uv run dev remove 42
```

移除 worktree，**不删除本地分支**。必须指定 issue 编号或 worktree 名称。

### `dev prune`

```bash
uv run dev prune          # 清理远程已合并分支
uv run dev prune --local  # 一并清理本地分支
```

人类操作。

### `dev retro <issue>`

```bash
uv run dev retro 42
```

复盘，引导填写内容写入 Issue body 的 Retro 段落。

### `dev close <issue>`

```bash
uv run dev close 42 -y    # -y 跳过确认
```

---

## 交互命令与绕过方式

以下命令在未提供必要 option 时会进入 stdin 交互模式，可能导致 Agent 卡死。执行前务必先查 `dev <cmd> -h`。

| 命令 | 交互点 | 绕过方式 |
|------|--------|----------|
| `dev merge-pr` | 策略选择器 | `--method squash/merge/rebase` |
| `dev prune` | 确认清理 | `-y` |
| `dev commit` | 编辑器编辑 message | `-m "msg"` 或 `--type TYPE --scope SCOPE --message MSG` |
| `dev close` | 确认关闭 | `-y` |

通用原则：所有交互式 prompt 都有对应的 option 跳过。

---

## 常用流程

```bash
# 新任务
uv run dev new "功能描述"
uv run dev start <N>
# ... 修改代码，设计变更直接改 Issue body

# 当前项目快捷操作
./sha.sh commit              # → dev commit $(current_issue)
./sha.sh pr                  # → dev pr $(current_issue)

# 全局查看
uv run dev status             # 所有项目 worktree 概览
uv run dev list --label bug   # 跨项目 issue 过滤

# 规范检查
uv run dev doctor

# 收尾
uv run dev merge-pr <PR#>     # 合并 PR
uv run dev prune              # 清理
uv run dev retro <N>          # 复盘
uv run dev close <N> -y       # 关闭 issue
```

---

## 故障排查

| 现象 | 原因 | 解决 |
|------|------|------|
| `dev` 命令不存在 | 未激活环境 | `uv sync; source .venv/bin/activate` |
| `dev status` 显示异常 | gh 未登录 | `gh auth status` |
| `dev start` 失败 | 分支或 worktree 冲突 | 检查 `git branch -l` 和 `git worktree list` |
| `dev commit` 跳过测试 | 项目无 test 入口 | 正常，日志打印 `[SKIP]` |
