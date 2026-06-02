---
name: diy-ref-lookup
description: >
  查找 diy 生态依赖包的源码镜像。diy sync 将依赖源码 clone 到 ~/.diy/ref/，
  并在项目 .diy/ref.lock.json 中建立索引。
  触发: 查依赖源码、看 xxx 包怎么实现、第三方库内部逻辑、
  依赖实现细节、read dependency internals、查一下源码。
---

# diy-ref-lookup

## 查找流程（严格按此顺序）

### 1. 读 `.diy/ref.lock.json`

这是依赖镜像索引，记录哪些依赖已 clone 到本地。结构：

```json
{
  "mirrorRoot": "~",
  "workspaces": [{
    "dependencies": [{
      "name": "rich",
      "mirrorPath": ".diy/ref/github.com/Textualize/rich/15.0.0"
    }]
  }]
}
```

`mirrorPath` 相对于 `mirrorRoot`（`~`），所以完整路径是 `~/.diy/ref/github.com/Textualize/rich/15.0.0`。

### 2. 去 `~/.diy/ref/` 读源码

按 lock 文件中的 `mirrorPath` 拼接出完整路径，直接 `read` 或 `grep`。

```bash
# 搜索 rich 包的源码
grep -r "关键词" ~/.diy/ref/github.com/Textualize/rich/15.0.0/

# 查看文件
ls ~/.diy/ref/github.com/Textualize/rich/15.0.0/src/
```

### 3. 兜底（lock 文件中找不到时）

| 生态 | 路径 | 注意 |
|------|------|------|
| Python | `.venv/lib/` | 可能被编译或压缩 |
| Node.js | `node_modules/` | 可能被打包或压缩 |

仅当 `.diy/ref.lock.json` 中找不到该依赖、或 mirrorPath 对应的目录不存在时才用兜底路径。

## 原则

- **永远先读 `.diy/ref.lock.json`**，不要直接翻 `.venv/lib/`
- lock 文件在项目根目录的 `.diy/` 下
