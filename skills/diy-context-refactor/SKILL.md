---
name: diy-context-refactor
description: >
  定期扫描 diy 生态所有 AGENTS.md，检查是否符合上下文组织规范并自动修复。
  触发词：上下文重构、清理 AGENTS.md、更新生态地图、检查项目上下文、
  agents.md 审计、context cleanup、refactor context。
---

# diy-context-refactor — diy 生态上下文重构

> 详细检查清单和操作步骤见 `references/checklist.md`。
> 本文件定义组织规范和核心原则。

## 核心原则

1. **根文件集中** — `~/git/AGENTS.md` 是生态地图、全局约束、信息架构的唯一真相源
2. **项目文件最小化** — 项目 AGENTS.md 只写**该项目特有**的约束（如 GPG 签名），不重复目录结构
3. **子包深层知识** — 子包 AGENTS.md 保留核心概念、特有命令、commit checklist
4. **归档不干扰** — 不想被 Hermes 加载的 AGENTS.md → 改名 `_AGENTS.md.archived`
5. **禁止敏感路径** — 所有路径引用用 `~/` 或相对路径，不写 `/Users/<name>/`
6. **不跨层引用** — 子文件不引用父文件（渐进发现自动叠加），不冗余指路

## 执行流程

1. **扫描** — 用 `search_files` 找到所有 AGENTS.md，排除 `.git/` `node_modules/` `.venv/`
2. **对照检查** — 按 `references/checklist.md` 逐项审查
3. **自动修复** — 可自动处理的重命名、删除空文件、敏感路径替换直接执行
4. **人工审核** — 需要判断的内容（如是否该归档）提请用户决策
5. **更新地图** — 如有项目结构变更，更新 `~/git/AGENTS.md` 生态地图段
6. **记录** — 将审计报告写入 `_diy/docs/tasks/<日期>_context-refactor/`
