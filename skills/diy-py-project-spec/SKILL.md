---
name: diy-py-project-spec
description: >
  diy 生态 Python 项目规范。pyproject.toml 约定、uv 包管理、
  目录命名、ruff/pyright/pytest 配置模板、项目命名前缀。
  Trigger: 创建 Python 项目、配置 pyproject.toml、uv 问题、项目结构问题。
---

# diy-py-project-spec

diy 生态所有 Python 项目遵循统一的 uv + pyproject.toml 约定。

---

## 项目命名

| 规则 | 示例 |
|------|------|
| 项目名用 `diy-` 前缀 | `diy-cli`、`diyui.py`、`diy-research` |
| 元/工具项目用 `_` 前缀 | `_diy` |
| 包名用 `-` 分隔 | `diy-cli.py`、`diyui.py` |
| GitHub repo 名与项目名一致 | `diy-agent/diy`、`diy-agent/_diy` |

---

## 目录结构

### Mono 项目

```
project/
├── pyproject.toml          # workspace 根配置
├── AGENTS.md
├── sha.sh
├── sha.common.sh
├── packages/               # 子包目录（统一用 packages/）
│   ├── pkg-a/
│   │   ├── pyproject.toml
│   │   ├── src/
│   │   ├── tests/
│   │   └── sha.sh
│   └── pkg-b/
│       └── ...
├── vendor/                 # git submodule
└── docs/
```

### 单项目

```
project/
├── pyproject.toml
├── AGENTS.md
├── sha.sh
├── sha.common.sh
├── src/
│   └── mypkg/
├── tests/
├── vendor/
└── docs/
```

### 目录命名约定

| 目录 | 用途 | 必须 |
|------|------|------|
| `packages/` | mono 项目的子包目录 | mono 项目 ✅ |
| `src/` | 源码（`src` layout） | ✅ |
| `tests/` | 测试 | ✅ |
| `vendor/` | git submodule | 推荐 |
| `docs/` | 稳定文档 | 推荐 |
| `examples/` | 示例 | 可选 |
| `scripts/` | 一次性脚本 | 可选 |

**禁用**：`pkgs/` 已统一为 `packages/`（新项目不用 `pkgs/`）。

---

## pyproject.toml 模板

### Mono 项目根配置

```toml
[project]
name = "diy-xxx"           # diy- 前缀
version = "0.0.0"
requires-python = ">=3.12"
dependencies = []

[tool.uv]
package = false

# 镜像源配置（国内加速）
[tool.uv.workspace]
members = ["packages/*"]

[[tool.uv.index]]
url = "https://mirrors.aliyun.com/pypi/simple/"

# Python 安装镜像
# UV_PYTHON_INSTALL_MIRROR 环境变量或:
# python-install-mirror = "https://registry.npmmirror.com/-/binary/python-build-standalone/"

# ========== Ruff 配置 ==========
[tool.ruff]
target-version = "py312"
line-length = 88

[tool.ruff.lint]
select = [
    "E",      # pycodestyle errors
    "F",      # pyflakes
    "I",      # isort
    "UP",     # pyupgrade
    "B",      # flake8-bugbear
    "C4",     # flake8-comprehensions
    "SIM",    # flake8-simplify
]
ignore = ["E501"]  # line too long（交给 formatter）

[tool.ruff.format]
quote-style = "double"

# ========== Pyright 配置 ==========
[tool.pyright]
typeCheckingMode = "standard"
pythonVersion = "3.12"

# ========== Pytest 配置 ==========
[tool.pytest.ini_options]
testpaths = ["tests"]
```

### 单项目配置

```toml
[project]
name = "diy-xxx"
version = "0.1.0"
description = "项目描述"
requires-python = ">=3.12"
dependencies = []

[project.scripts]
mycli = "mypkg:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/mypkg"]

[dependency-groups]
dev = [
    "ruff>=0.15",
    "pyright>=1.1.409",
    "pytest>=9.0",
]

[[tool.uv.index]]
url = "https://mirrors.aliyun.com/pypi/simple/"

# Ruff/Pyright/Pytest 配置同上
```

---

## uv 命令规范

### 包管理

```bash
# ✅ 正确
uv add <package>           # 添加依赖
uv add --dev <package>     # 添加开发依赖
uv sync                    # 同步环境
uv run <command>           # 在 venv 中运行

# ❌ 禁止
pip install <package>      # 污染全局 Python
pip install -e .           # 用 uv 替代
```

### 新建项目

```bash
# mono 项目
uv init --package false diy-xxx
cd diy-xxx
uv add ruff pyright pytest --dev

# 单项目
uv init --package diy-xxx
cd diy-xxx
uv add ruff pyright pytest --dev
```

### 镜像源

```toml
# 推荐配置（同时设置 PyPI 和 Python 安装镜像）
[[tool.uv.index]]
url = "https://mirrors.aliyun.com/pypi/simple/"

[tool.uv]
python-install-mirror = "https://registry.npmmirror.com/-/binary/python-build-standalone/"
```

---

## 开发依赖

所有项目必须包含以下开发依赖（最新稳定版）：

| 工具 | 用途 | 依赖名 |
|------|------|--------|
| ruff | lint + format | `ruff>=0.15` |
| pyright | type check | `pyright>=1.1.409` |
| pytest | 测试 | `pytest>=9.0` |

---

## Git 忽略

```gitignore
# Python
.venv/
__pycache__/
*.pyc
*.egg-info/
build/
dist/
.pytest_cache/
.ruff_cache/

# IDE
.vscode/
.idea/
```

---

## 反模式

| 不要 | 应该 |
|------|------|
| `pip install` 裸用 | `uv add` 或 `uv run` |
| `pkgs/` 目录名 | `packages/` |
| 项目名不加前缀 | `diy-xxx` |
| 缺少 ruff/pyright/pytest | 三项必备 |
| 在 venv 外运行项目命令 | `uv run` |
