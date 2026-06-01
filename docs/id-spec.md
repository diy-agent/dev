---
title: ID 规范
tags: [diy, 规范, id]
category: 规范
description: 项目中各类实体的 ID 生成规范
---

# ID 规范

## Goal ID

使用 **XID**（12 字符，URL 安全，全球唯一，可逆解创建时间）。

```python
from xid import Xid

# 生成
gid = Xid().string()           # "cvn65t2g23hq"

# 还原时间
Xid.from_string(gid).time()    # datetime(2026, 5, 31, 12, 30, 45)
```

- **长度**：12 字符
- **唯一性**：全球唯一，多人使用不冲突
- **可排序**：前 4 字符编码时间，肉眼可辨先后
- **依赖**：`pip install xid`

## 使用场景

| 实体 | ID 类型 | 说明 |
|------|---------|------|
| Goal | XID | AGENTS.md frontmatter 中 `goal.id` |
| Session | 时间戳格式 `YYYYMMDD-HHMMSS-NNN` | 关联 Goal XID 作为目录名 |
| Task | Session 内自增序号 | 临时，不跨 Session 引用 |

## Session 目录结构

```
~/.diy-research/sessions/<goal-xid>/
├── 20260530-194059-001.json
├── 20260531-201530-002.json
└── active_state.json
```
