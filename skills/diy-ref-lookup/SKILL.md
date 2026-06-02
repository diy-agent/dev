---
name: diy-ref-lookup
description: >
  查找 diy 生态依赖包的参考源码镜像。
  触发: 查依赖源码、看 xxx 包怎么实现、第三方库内部逻辑、
  依赖实现细节、read dependency internals、ref 参考代码、查一下源码。
---

# diy-ref-lookup

diy 生态通过 `diy sync` 将关键依赖的源码镜像到本地。

## 查找顺序（严格按此顺序）

### 1. `~/.diy/ref` — 依赖源码镜像

`diy sync` 维护的源代码镜像目录。代码完整、可全文搜索。

```bash
# 列出已镜像的依赖
ls ~/.diy/ref/

# 搜索特定包的源码
grep -r "关键词" ~/.diy/ref/包名/
```

### 2. `.diy/ref.lock.json` — 镜像索引

记录了哪些依赖已镜像、版本号。不确定某个依赖是否有镜像时，先读这个文件确认。

### 3. `.venv/lib/` — 兜底

仅当 `~/.diy/ref` 和 `.diy/ref.lock.json` 都找不到时才使用。注意这里的代码可能被编译或压缩过。

## 原则

- **永远先查 `~/.diy/ref`**，不要直接翻 `.venv/lib/`
- 遇到 `~/.diy/ref` 中没有的依赖，正常用 `.venv/lib/` 即可
