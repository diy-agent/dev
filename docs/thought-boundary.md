# 思想边界文档 — diy 管控台

> 此文档记录设计讨论中确认的概念边界与取舍，作为思想模型参考。
> **不作为实现依据**。实现从最基本的操作开始，逐步审视。
>
> 日期：2026-06-08

---

## 〇、底层模型：Space → Subject → Task

### Space（空间）

**定义**：信息的载体。是一个信息容器。

```
电脑硬盘           → 一个空间
GitHub 账号        → 一个空间（含其下所有 repo）
GitHub Project V2  → 一个空间
Gmail 邮箱         → 一个空间
某网盘             → 一个空间
```

- 空间通过**连接（Connection）**访问。同一个空间可能通过不同连接进入（如多个 GitHub token），不同连接决定不同身份和权限
- 文件系统只是空间的一种，不是全部

### Subject（关注点 / 主题）

**定义**：空间中我们**选择关注**的一个子空间。是人类维护持久信息资产的边界。

```
整个硬盘中，我们只关注 ~/git/diy/_diy 这个子空间 → Subject
整个 GitHub 账号中，我们只关注 diy-agent/_diy 这个 repo → Subject
diy-agent/_diy 中，我们进一步关注 pkgs/diy-ui → 子 Subject
```

- Subject 可以嵌套（含子 Subject）
- Subject ≠ git repo。git repo 只是恰巧在编程场景下重合的边界。医疗文件目录也可以是 Subject——只要人类选择关注它
- Subject 是稳定的——不因 worktree 创建而增生
- 锁定发生在 subject 上

### 信息资产与价值

Subject 内承载**信息资产**。增长这些资产的价值（代码更整洁、文档更完备）→ 增长物理世界的价值。增长价值的手段是**任务（Task）**。

```
Space → Subject（关注的信息资产）→ Task（增长价值的手段）
```

git、Python monorepo、dai/dev 工具链——都是我们**当下场景的实现细节**，不是模型的基础定义。模型基础是：**空间 → 关注点 → 任务 → 价值增长**。

---

## 一、核心概念

### Subject（coding: 当前实现边界）

在当前编程场景下，Subject 恰好重合为一个 git repo：

```
~/git/diy/_diy  → subject: diy-agent/_diy
~/git/diy/diy   → subject: diy-agent/diy
```

- Subject 和 git repo 当前一对一（巧合，不是必然）
- Subject 是稳定的——不因 worktree 创建而增生
- 锁定发生在 subject 上

### Connection（连接）

**定义**：访问空间的通道，决定身份和权限。

- 同一个空间（如 GitHub）可通过多个连接访问（不同 token → 不同身份）
- 连接信息包括：type（github/gmail/filesystem/...）、credential、endpoint
- 当前编程场景：`gh` CLI 使用 `/Users/ccc/.config/gh/hosts.yml` 中的 token
- 在通用模型中，连接不属于 task——它是访问 subject 的前提条件

### Worktree

**定义**：`dai start` 创建的临时工作目录，**不是新 subject**。

```
/tmp/worktree/diy-1-67-devflow  → 属于 subject diy-agent/_diy
~/git/diy/_diy-67-devflow       → 同上，只是位置不同
```

- worktree 只是锁的工作台，不污染 subject 树
- 可以放在 /tmp 或任何位置，甚至可以考虑不持久化
- 核心资产始终是原 repo

### Task（任务）

**定义**：一个工作单元，挂在 subject 上。

| 属性 | 说明 |
|------|------|
| id | 内部稳定标识（不变） |
| title | 人类可读名称 |
| type | epic / issue / local / tracking |
| status | pending / started / done / abandoned |
| repo | 归属的 subject（一个 task 只属一个 subject） |
| branch | 可选，仅在叶子 task 上存在 |
| plan | 可选，子步骤列表 |

### Lock（锁）

**定义**：subject 级互斥锁。当前 subject = git repo，当前锁即 repo + branch 级。

```
锁 = (subject, task_id) 一对一
锁的状态 = branch / in_pr / merging / released
```

- 一个 subject 同一时间只有一条活跃工作流
- 锁的锚点是 `(subject, task_id)`，目录（worktree）只是附带属性
- dai start → 申请锁，dai close → 释放锁

### Files（文件声明）

**定义**：叶子 task 对计划修改的文件列表，**不是锁，是声明**。

- 声明了 = "我知道这些文件会被改"
- 未声明 = "没有冲突检测"
- 文件声明范围天然约束在 task 的 subject 内

---

## 二、边界决策

### 1. Task 不跨 Subject

一个 task 只属于一个 subject（当前：一个 repo/目录）。

跨 subject 变更 = 在父级拆成多个独立 task，通过执行顺序表达依赖。

**原因**：
- 跨 subject 锁无法原子化
- 一个 task 一个 subject 的锁一个 merge 才是工作流支持的最小单元
- 编排在父级完成，叶子保持简单

### 2. 分支只在叶子 task

Epic、编排组、tracking 类型不持有 branch。

```
#67（无 branch — 容器）
  └── 67/1（branch: feat/start-cmd — 叶子）
```

从任一节点向上找到第一个有 branch 的祖先 = 当前工作分支。找不到 = 不涉及代码。

### 3. Task 启动后不可变

`status: started` 后冻结：ID、目录、plan 步骤全部不可变。

想改 → 复制新 task，原 task 标记 `abandoned`。

**原因**：
- 消除目录迁移风险
- 运行中的 Worker 不受影响
- 状态机简单、可审计

### 4. plan 只保留串行步骤

plan 的职责是声明**做什么、什么顺序**。不包含并行、超时、重试。

```yaml
plan:
  steps:
    - {id: "67/1", files: [...]}
    - {id: "67/2", files: [...]}
    - {id: "67/3", files: [...]}
```

核心任务状态只追踪：**这一步 done 了吗？下一步是谁？**

并行、批量、超时、重试 → 这些是**运行时调度**，交给独立批处理工具（如 `dai batch`），不渗入任务规划层。

**原因**：
- 批处理维度（max、timeout、retry）和任务规划维度（dependency、order）是正交的
- 如果批处理参数渗入规划层，会出现 5 万步并行的状态维护——不可控
- 分离后：规划层只管"步骤 done 了吗"，执行层管"怎么跑得快"

### 5. Group by，不硬编码视图

同一张 task 表，按不同字段聚合产生不同视图：

| 聚合成 | 看到 |
|--------|------|
|| `group_by: subject` | Subject Tree（哪些 subject 活跃、锁状态） |
| `group_by: parent_id` | Issue 层级树（Epic → 子任务依赖） |
| `group_by: status` | 看板（pending / running / done） |

数据模型不支持任何特定视图——视图是查询的结果。

### 6. 内部 ID 与展示标签分离

```
内部 ID（不变）    目录名（不变）        UI 展示
─────────────────────────────────────────────
task-67             tasks/67/           [#67] devflow
task-67-1           tasks/67/1/         [#67/t-1] start命令
task-local-fix      tasks/local-fix/    [@fix] CI修复
```

- 内部 ID = 稳定标识，决定目录名
- UI label = `#` `@` `t-` 前缀由 type 字段决定
- local 任务升级为 issue → 只改 type 字段和 display label，不迁目录

---

## 三、Task 数据结构（思想模型）

```yaml
# 任务表 — 纯数据，不决定视图
task:
  id: "67"                    # 内部稳定 ID
  title: "devflow 实现"
  type: issue                 # epic | issue | local | tracking
  source: gh                  # gh | local
  status: pending             # pending | started | done | abandoned
  subject: ~/git/diy/_diy     # 归属的关注点（一个 task 一个 subject）
  branch: feat/67-devflow     # 可选，叶子可持有
  worktree: null              # 可选，dai start 后写入
  parent: "58"                # 父 task ID（形成层级树）
  plan:                       # 可选，子步骤
    steps:
      - id: "67/1"
        files: [src/diydev/_start_cmd.py, tests/test_start*.py]
      - id: "67/2"
        files: [src/diydev/_close_cmd.py, tests/test_close*.py]
      - id: "67/3"
        files: [tests/conftest.py]
```

---

## 四、显式排除

以下概念**不在**任务规划层建模：

| 排除项 | 属于哪里 |
|--------|----------|
| 并行执行、max workers | 批处理工具 |
| 超时、重试 | 批处理工具 |
| 文件冲突检测 | 可选工具，非模型层 |
| Worker 会话信息 | 独立会话层（tmux pane / hermes 进程） |
| 目录迁移 | 不存在（task 冻结） |
| 跨 subject task | 不存在（每个 task 一个 subject） |

---

## 五、技术选型变更

> **2026-06-08：放弃 PySide6，改用 Panel + diy.ui 套壳程序**

原计划用 PySide6 构建桌面管控台。改为：

- **Panel** 作为渲染层（基于 Bokeh）
- **diy.ui** 提供的 Panel provider 封装（`app.signal` / `app.cell` / `app.servable`）
- **套壳程序** = `panel serve` + `webview` / Tauri / Electron 之类最小壳子

理由：
1. diy.ui 已对 Panel 做极简封装，异步隔离、Signal 状态管理是开箱即用
2. Panel 异步能力（`async_cell_demo.pn.py` 已验证并发隔离）
3. 同一份代码既能在浏览器跑，也能套壳成桌面 app
4. Agent 和 GUI 可以共用 Python 进程（`from run_agent import AIAgent` 同进程）
5. 部署层级少：lib → pn.py 视图 → serve → 浏览器/壳子

参考实现：
- `~/git/diy/diy/pkgs/diy-ui/examples/features/async_cell_demo.pn.py`
- `~/git/diy/diy/pkgs/diy-ui/examples/serve_all.py`（PEP 723 元数据 + 分类索引模板）

---

## 六、下一步：从最基本开始

> 以下是明确不在此文档中但作为实现起点的参考方向。**不作为设计依据。**

模型的实现不从此文档直接翻译。从最基本操作开始：

1. 看看当前状态（`dai status` 的风味）
2. 创建一个 task
3. 标记一个 task done
4. 显示 task 树

确认这四个操作的手感后，再审视是否需要锁、worktree、GUI。
