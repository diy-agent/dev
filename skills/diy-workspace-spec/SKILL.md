---
name: diy-workspace-spec
description: >
  diy 生态项目工作空间管理规范。sha.sh 脚本引擎的编写与使用标准，
  包括命名约定、模板结构、必需子命令、mono/单项目模式。
  Trigger: 创建新项目、写 sha.sh、修改构建脚本、项目结构问题。
---

# diy-workspace-spec

diy 生态所有项目使用统一的 sha.sh 脚本引擎管理开发工作空间（构建、检查、测试、同步、清理）。

---

## 文件命名

| 文件 | 用途 | 注意 |
|------|------|------|
| `sha.sh` | 项目级入口脚本，定义项目特有命令 | 项目根目录 |
| `sha.common.sh` | 公共基础设施（颜色、`run()`、vendor/sha 加载） | **`.` 分隔，不用 `_`** |
| `vendor/sha/` | sha.bash 调度引擎（git submodule） | 由 `sha.common.sh` source |

**唯一正确命名**：`sha.common.sh`。历史遗留的 `sha_common.sh` 已废弃。

---

## 模板结构

### sha.common.sh（权威模板在 `_diy/sha.common.sh`）

```bash
#!/usr/bin/env bash
# shellcheck disable=SC2329,SC2034
shopt -s globstar

__SHA_COMMON_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/" && pwd)

# --- M3 颜色变量 ---
# 必须提供: $primary $secondary $success $error $warning $info $reset
primary="\033[38;5;255;48;5;55;1m"
secondary="\033[38;5;255;48;5;66;1m"
success="\033[38;5;255;48;5;28;1m"
error="\033[38;5;255;48;5;124;1m"
warning="\033[38;5;16;48;5;214;1m"
info="\033[38;5;255;48;5;31;1m"
reset=$(printf '\033[0m')

# --- run() 函数 ---
# 彩色日志执行器。name 固定为 `run`，无 `_` 前缀。
run() {
  local caller_script=$(caller 0 | awk '{print $3}')
  local caller_script=$(echo "$caller_script" | sed "s@^$HOME@~@")
  local caller_line=$(caller 0 | awk '{print $1}')
  local current_pwd=$(echo "$PWD" | sed "s@^$HOME@~@")
  local color_caller="${secondary}${caller_script}:${caller_line} ${FUNCNAME[1]}() ${reset}"
  local color_pwd="${info}${current_pwd} ${reset}"

  local quoted_cmd=""
  for arg in "$@"; do
    if [[ "$arg" == *" "* ]]; then
      quoted_cmd+="\"$arg\" "
    else
      quoted_cmd+="$arg "
    fi
  done
  quoted_cmd="${quoted_cmd% }"

  local color_cmd="${primary}${quoted_cmd}${reset}"
  echo "$color_caller$color_pwd$color_cmd" >&2
  "$@"
}

# --- vendor/sha 加载 ---
if [ ! -d "$__SHA_COMMON_DIR/vendor/sha" ] || [ -z "$(ls -A "$__SHA_COMMON_DIR/vendor/sha" 2>/dev/null)" ]; then
  echo "${info} vendor/sha 初始化中... ${reset}"
  run git submodule update --init --recursive
fi
source "$__SHA_COMMON_DIR/vendor/sha/sha.bash"
shopt -s expand_aliases
```

### sha.sh 入口模板

**单项目模式**（如 `diyq`、简单的子包）：

```bash
#!/usr/bin/env bash

set -o errtrace -o errexit -o functrace -o pipefail
shopt -s globstar extglob

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"
source "sha.common.sh"

# --- 必需子命令 ---
check() {
  run uv run ruff check src/ tests/
  run uv run ruff format --check src/ tests/
  run uv run pyright src/ tests/
}

test() {
  run uv run pytest
}

sync() {
  run uv sync
  run git submodule update --init --recursive
}

clean() {
  run rm -rf .venv .ruff_cache .pytest_cache build/ dist/ ./*.egg-info
}

fix() {
  run uv run ruff check --fix src/ tests/
  run uv run ruff format src/ tests/
}

# === 项目特有命令在此之下 ===

sha "$@"
```

**Mono 项目模式**（如 `diy`、`diy-research`）：

sha.sh 定义 `_workspaces` 数组遍历所有子包：

```bash
_workspaces=(packages/*/)

_ws_run() {
  for ws in "${_workspaces[@]}"; do
    [ -f "$ws/sha.sh" ] || continue
    (
      cd "$ws"
      echo "${info}workspace: $ws${reset}"
      run "$@"
    )
  done
}

check() { _ws_run command ./sha.sh check; }
test()  { _ws_run command ./sha.sh test; }
fix()   { _ws_run command ./sha.sh fix; }

sync() {
  run uv sync --all-packages
  run git submodule update --init --recursive
  _ws_run command ./sha.sh sync
}

clean() {
  run rm -rf .venv .ruff_cache .pytest_cache
  _ws_run command ./sha.sh clean
}
```

---

## 必需子命令

每个项目应实现以下命令。未定义的命令打印 `[SKIP]`，不阻塞流程。

| 命令 | 用途 | 必须 |
|------|------|------|
| `check` | lint + format check + type check（ruff + pyright） | ✅ |
| `test` | 单元测试（pytest） | ✅ |
| `sync` | 环境同步（uv sync + submodule + 全局工具安装） | ✅ |
| `clean` | 清理构建产物和缓存 | ✅ |
| `fix` | 自动修复（ruff fix + format） | 推荐 |

### check 实现建议

```bash
check() {
  run uv run ruff check src/ tests/        # lint
  run uv run ruff format --check src/ tests/  # format
  run uv run pyright src/ tests/           # type check
}
```

### 跳过未定义命令

在 sha.common.sh 的 vendor/sha 加载前设置默认：

```bash
check() { echo "${info}[SKIP] check${reset}"; }
test()  { echo "${info}[SKIP] test${reset}"; }
```

---

## run() 使用规范

- **永远使用 `run` 包装外部命令**，不使用裸命令
- `run` 自动打印彩色日志：调用位置 + 工作目录 + 执行命令
- 不要在 `run` 后面加 `2>/dev/null`，错误必须可见

```bash
# ✅ 正确
run uv run pytest tests/
run git push origin main

# ❌ 错误
uv run pytest tests/          # 缺少彩色日志
run uv run pytest 2>/dev/null # 隐藏错误
```

---

## 编写规则

1. **定义函数即为子命令**：`foo() { ... }` → `./sha.sh foo`
2. **命令可嵌套**：函数内再定义函数 → `./sha.sh foo bar`
3. **用 `run` 执行外部命令**
4. **可用颜色变量**：`$primary` `$secondary` `$error` `$info` `$success` `$warning` `$reset`
5. **文件末尾保留 `sha "$@"` 调度入口**
6. **`set -o errtrace -o errexit -o functrace -o pipefail`** 四件套

---

## 子包 sha.sh

Mono 项目的子包也有自己的 `sha.sh`，通过子包的 `sha.common.sh`（或相对路径 source 父级）加载基础设施：

```
project/
├── sha.sh              # 根入口，遍历 workspace
├── sha.common.sh       # 公共基础设施（权威模板）
└── packages/
    └── mypkg/
        ├── sha.sh      # 子包入口（check/test/sync 等）
        └── pyproject.toml
```

子包 sha.sh 格式：

```bash
#!/usr/bin/env bash
set -o errtrace -o errexit -o functrace -o pipefail
shopt -s globstar extglob

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
source "../../sha.common.sh"  # 引用父级公共脚本

check() {
  run uv run ruff check src/ tests/
  run uv run ruff format --check src/ tests/
  run uv run pyright src/ tests/
}

test() { run uv run pytest; }
sync() { run uv sync; }
clean() {
  run rm -rf .venv .ruff_cache .pytest_cache build/ dist/
}
fix() {
  run uv run ruff check --fix src/ tests/
  run uv run ruff format src/ tests/
}

sha "$@"
```

---

## 新项目初始化清单

创建新 diy 项目时，按以下清单初始化 sha.sh 基础设施：

1. [ ] 从 `_diy/sha.common.sh` 复制权威模板
2. [ ] 编写 `sha.sh`（单项目或 mono 模式）
3. [ ] 确保 `check`、`test`、`sync`、`clean` 四个必需命令可执行
4. [ ] 添加 `vendor/sha` 为 git submodule
5. [ ] `chmod +x sha.sh`
6. [ ] 将 `.venv/`、`__pycache__/`、`build/`、`dist/` 加入 `.gitignore`
7. [ ] 运行 `./sha.sh sync` 验证环境正常
