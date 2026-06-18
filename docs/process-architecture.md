# 进程管理架构

app (PySide6) + agentd (Hermes AIAgent) 之间的进程管理约定。

## 进程关系

```
app (主进程)
  ├── socket server (~/.diy/app.sock)
  ├── spawn/kill agentd（子进程）
  └── PySide6 UI

agentd（子进程）
  ├── socket server (~/.diy/agentd.sock)
  ├── SessionPool (AIAgent 线程池)
  └── 写 ~/.diy/agents/<uri>/（GUI bridge）
```

agentd 是 app 的子进程，app 负责 spawn/kill。app 启动时先尝试连接已有 agentd socket（复用），连不上才启动新的。

## 单实例锁

两个进程各自用 socket 锁防止多实例：

```
启动时:
  1. connect(socket_path) → 通 → "已有实例" → exit
  2. OSError → 清理残留 socket 文件 → bind 新的
```

socket 文件（bind）在操作系统层面独占，是最可靠的单实例锁——比 PID 文件可靠（PID 可能被回收重用）。

## 自检与自愈

心跳线程每 5 秒 `os.stat(socket_path)`：

| 检测结果 | 行为 |
|---|---|
| `FileNotFoundError`（socket 被删） | 退出 |
| `(dev, ino)` 不匹配（socket 被替换） | 退出 |

app 和 agentd 都是。app 发现 critical 时 `QApplication.instance().quit()`，不留 lockdown 面板。

## 退出生命周期

```
正常退出（用户关窗口 / Ctrl+C）:
  app → app.exec() 返回 → agentd.terminate()
       → wait(3) → 超时则 kill
       → agentd cleanup（unlink socket, 等 agent 跑完）

app crash / SIGKILL:
  agentd 变成孤儿（ppid=1），socket 仍然有效
  app 重启 → 连接 agentd socket → 复用（agent 状态保留）

app 重启后接孤儿 agentd:
  app 先 socket connect 探测 → 连上则复用
  → 不复用才 spawn 新的
  → 新 agentd 启动时 socket 锁检测已有 agentd → 退出
  → app 日志记录"agentd 已在运行"
```

## 不使用的方案

- **PID 文件**：不必要。socket 锁 + inode 心跳覆盖了全部场景。
- **lockdown 面板**：已删。严重问题直接退出，日志留下记录。
- **agentd 检测父进程死亡**：不需要。孤儿 agentd 仍然可以通过 socket 被新 app 复用。
