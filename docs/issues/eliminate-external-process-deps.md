# 消除外部进程依赖（sha.sh / pkill / pgrep / ps）

## 当前依赖

app 和核心程序依赖 shell 外部命令，脆弱且不可控。

| 文件 | 依赖 | 用途 |
|------|------|------|
| `_forward.py` | `sha.sh` via `subprocess.Popen(["bash", script, "app"])` | 启动 app |
| `_dai_cli.py` | `sha.sh` via `subprocess.Popen` | 启动 app |
| `_dai_cli.py` | `pkill -f diydev.app.main` | shutdown 兜底 |
| `_dai_cli.py` | `ps aux | grep | wc -l` | 检测实例数 |
| `main.py` | `subprocess.Popen([hermes_python, ...])` | spawn agentd |
| `_doctor.py` | `subprocess.run(["ps", ...])` | 多实例检测 |

## 问题

1. `sha.sh` 路径硬编码（`os.path.dirname(__file__) + /../../sha.sh`），不同工作目录、打包后找不到
2. `pkill -f` 匹配进程 cmdline，壳层转义问题，可能误杀无关进程
3. `ps aux` 输出格式跨平台不同（macOS `comm` 截断 15 字节 vs Linux 全路径）
4. `subprocess.Popen` stderr=DEVNULL 吞掉所有错误→不可调试
5. app 启动脚本 `sha.sh app` 包含不必要的 shell 初始化（`set +m` 等）

## 改造方向

| 当前 | 替代 | 原因 |
|------|------|------|
| `sha.sh app` → bash | `psutil.Popen(["uv", "run", "python", "-m", "diydev.app.main"])` | 纯 Python，可控 |
| `pkill -f diydev.app.main` | `psutil.Process(pid).kill()` | 精确杀进程 |
| `ps aux \| grep` | `psutil.process_iter()` + `name()`/`cmdline()` | 跨平台，结构化 |
| `subprocess.Popen` spawn agentd | `runpy.run_module("diydev._agent_daemon")` | 同进程启动，无子进程管理问题 |

`psutil` 已在 `_dai_cli.py` 的 `_local_process_count()` 中使用，无需新增依赖。
`runpy` 是 Python 标准库。

## 范围

- [ ] `_forward.py` — 替换 sha.sh 启动为 `psutil.Popen`
- [ ] `_dai_cli.py` — 替换 shutdown 的 pkill 为 `psutil.Process(pid).kill()`
- [ ] `main.py` — 替换 agentd spawn 为 `runpy.run_module`
- [ ] `_doctor.py` — 替换 `subprocess.run(["ps", ...])` 为 `psutil.process_iter()`
- [ ] 整理后删除 `sha.sh` 中 app 相关代码（如不再被引用）

关联：设计评审中 "Runtime/ControlPlane 可合进主进程" 的结论方向。
