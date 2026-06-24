# diy 开发规范：事件驱动优先，时间退避兜底

## 核心原则

> **时间 timeout 只能是最后兜底，不是主要协调手段。**  
> **所有 I/O retry 本质是异步操作，在 Qt UI 线程用 time.sleep 阻塞 = 界面冻结。**

## 决策层次

判断一个等待/重试场景应该如何实现，按以下优先级：

```
有事件/信号可监听？
  ├─ ✅ 是 → 监听事件（Qt signal、asyncio.Event、threading.Event、
  │             changeEvent、QFileSystemWatcher、select/poll/kqueue）
  │
  └─ ❌ 否 → 有同步原语可用？
       ├─ ✅ 是 → threading.Event、asyncio.Event、QSemaphore、
       │            QWaitCondition、Future
       │
       └─ ❌ 否 → 只能轮询 → 用 diydev._backoff.Backoff
            ├─ CLI/线程 → Backoff（time.sleep）
            ├─ asyncio  → AsyncBackoff（await asyncio.sleep）
            └─ Qt UI 线程 → QtBackoff（QTimer 事件驱动）
```

## 具体禁令

### ❌ 禁止：在 Qt UI 线程使用 time.sleep 或同步 Backoff

```python
# ✗ 坏：阻塞 UI 线程
def on_click(self):
    time.sleep(0.5)          # UI 冻结 0.5s
    result = poll_something() # 又一段阻塞

# ✗ 坏：同步 Backoff 在 UI 线程用
for tick in Backoff(timeout=5):  # → time.sleep → 冻结
    ...
```

```python
# ✓ 好：QtBackoff 事件驱动
def check(tick):
    result = poll_something()
    if result: label.setText(result); return True
    return False

QtBackoff(check, timeout=5).start()
```

### ❌ 禁止：手写 `deadline + while + sleep + backoff = min(...)`

```python
# ✗ 坏：手写轮询
deadline = time.time() + 5
backoff = 0.05
while time.time() < deadline:
    try:
        do_something()
        break
    except OSError:
        time.sleep(backoff)
        backoff = min(backoff * 1.5, 0.5)
```

```python
# ✓ 好：Backoff.until
ok, _ = Backoff.until(do_something, timeout=5, exceptions=(OSError,))
```

### ❌ 禁止：纯 `time.sleep(X)` 作为协调手段

```python
# ✗ 坏：猜时间
time.sleep(3.0)  # 等旧进程退出？等 MachPort 清理？
                # 快了不行，慢了浪费
```

等待必须关联到一个**可观测的条件**（锁释放、socket 就绪、进程退出码、flag 变化）。
如果该条件真的没有事件通知机制（如 `flock`），在轮询代码旁注释：

```python
# 注意：flock 不提供事件通知机制（非 selectable），
# 只能轮询。timeout 是最后兜底，不是预期耗时。
```

### ✅ 允许：周期性 UI 刷新（QTimer.start）

```python
self._timer = QTimer(self)
self._timer.timeout.connect(self._refresh)
self._timer.start(5000)  # 5s 刷新一次 agent 状态
```

这是 UI 定帧刷新，不是协调手段，允许。

### ✅ 允许：defer 到下一帧（QTimer.singleShot(0)）

```python
QTimer.singleShot(0, self._do_scroll_to_bottom)
```

这是「当前帧工作做完后再执行」的标准 Qt 模式，不是轮询。

### ✅ 允许：subprocess / asyncio / socket 超时参数

```python
subprocess.run(..., timeout=30)
await asyncio.wait_for(coro, timeout=30)
sock.settimeout(5.0)
```

这些都是标准 API 的最后兜底，不是主要协调手段。

## 常见场景对照表

| 场景 | 正确做法 | 兜底 timeout |
|------|---------|-------------|
| 等旧进程退出 | `os.waitpid()` / `Process.wait()` | 合理上限 |
| 等旧进程释放 flock | `Backoff.until(try_lock, ...)` | 5-8s |
| 等新进程 socket 就绪 | `Backoff.until(connect, ...)` | 10-15s |
| 等 QWebEngineView 可创建 | `changeEvent(ActivationChange)` → flag | 无（事件驱动） |
| 等 agent 完成 | `asyncio.Event` / `threading.Event` | 30-120s |
| 等跨线程结果 | `MainThread.invoke(timeout=20)` | 20s |
| 等子进程输出 | `asyncio.wait_for(readline, timeout=...)` | 按场景 |

## 历史教训

见 `docs/crash-investigation-20260624.md` 的具体案例：

- **`--single-process`** 导致 V8 SIGSEGV — 错误 flag 导致的 crash
- **`QTimer.singleShot(0, setFocus)`** 导致过早创建 QWebEngineView → SIGSEGV — 时间假设错误
- **`self.windowHandle()` 在子控件返回 None** 导致无限 defer — API 误用

三个问题都是"用时间/假设替代事件/检测"导致的。

## 引用

- 退避工具：`src/diydev/_backoff.py`
- 事件驱动范例：`MainWindow.changeEvent` 在 `main.py`
- 文件锁（flock 无法事件化）：`src/diydev/_lock.py`
