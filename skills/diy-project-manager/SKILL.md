---
name: diy-project-manager
description: >
  AI-Native Issue-Centric 项目管理方法论。
  触发: 项目命名/结构讨论、重构/改名、包结构调整、代码组织方式讨论、
  任务拆分与追踪、Issue 创建与编辑、设计评审、复盘讨论、
  任何涉及"怎么组织代码""包名合不合理""要不要拆文件""项目结构设计"的问题。
---

# diy-project-manager

详见方法论文档：[docs/diy-project-manager.md](../docs/diy-project-manager.md)

核心要点：

1. **Issue body 是任务 SSOT**，设计变更直接改 body，不散落 comments
2. **文档分层**：过程中变→Issue body，稳定结论→docs/
3. **命名规范**：项目名 `-` 分隔，`_` 前缀为元项目，`/ref` 为外部引用
4. **Agent-Human 边界**：Agent 不裸用 `gh`、不删分支、关闭/合并须人类确认
5. **可验证 > 可运行观察 > 静态文档**
