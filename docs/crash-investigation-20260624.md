# SIGSEGV 崩溃调查记录（2026-06-24）

## 症状

```
$ uv run dai restart
[INFO ] 正在关闭管控台...
[INFO ] 等待旧管控台退出...
[INFO ] 正在启动管控台...
...
[main] window.show() 完成
EXIT: 139   # ← SIGSEGV
```

管控台进程启动后瞬间退出（exit code 139 = 128 + SIGSEGV），UI 窗口不出现。
`agentd`（`diydev._agent_daemon`）正常存活。

---

## 崩溃一：`--single-process` + V8 Proxy Resolver SIGSEGV

### 现象

stderr 出现：

```
Cannot use V8 Proxy resolver in single process mode.
```

随后 SIGSEGV。

### 根因

代码在 `main()` 中主动向 `QTWEBENGINE_CHROMIUM_FLAGS` 添加了 `--single-process`：

```python
# main.py 原代码
if "--single-process" not in existing and "--disable-gpu" not in existing:
    flags = (existing + " --single-process").strip()
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = flags
```

该 flag 的本意是"单进程模式，从根本上避免 GPU 子进程的 MachPort 冲突"，但在 **PySide6 6.8.3 + macOS 12** 组合下，`--single-process` 导致 Chromium 的 V8 Proxy Resolver 无法在单进程模式下初始化，触发 NetworkContextManager 内部 SIGSEGV。

### 可否复现

**稳定复现**。任何运行 `python -m diydev.app.main` 且不带 `QTWEBENGINE_CHROMIUM_FLAGS` 环境变量的场景，都会因为 main.py 自动添加 `--single-process` 而崩溃。

### 修复

将默认 flag 改为 `--disable-gpu`，避免 GPU 子进程的同时保持 multi-process 模式，V8 Proxy Resolver 正常工作。

```python
# 修复后（模块级，在 import QtWebEngineWidgets 之前设置）
if "--single-process" not in flags and "--disable-gpu" not in flags:
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu"
```

---

## 崩溃二：过早创建 QWebEngineView → NSApplication 冲突 SIGSEGV

### 现象

即使改用 `--disable-gpu`，app.exe() 仍在首次 event loop 迭代时 SIGSEGV。
但用 `processEvents()` 代替 `app.exec()` 则不崩溃（hang 住而非 crash）。

### 根因

MainWindow.__init__ 末尾有：

```python
QTimer.singleShot(0, self._tree.setFocus)
```

执行时序：

1. `window.show()` 将窗口提交给 macOS 窗口服务器，但 **`NSApplicationDidBecomeActiveNotification` 尚未送达**
2. `app.exec()` 进入 event loop
3. `singleShot(0)` 立即触发 → `self._tree.setFocus()`
4. setFocus 导致 `QTreeView.selectionModel().currentChanged` 信号触发
5. → `MainWindow._on_select(index_of_first_item)`
6. → `DetailView.show_placeholder(html)`
7. → `DetailView._ensure_view()`
8. → **创建 `QWebEngineView`**

macOS 上，QWebEngineView 的创建会触发 Chromium 子进程初始化，而该初始化需要 `NSApplicationDidBecomeActiveNotification` 已完成。窗口 active 通知尚未到达时创建 WebEngineView，导致 use-after-free → SIGSEGV。

这恰好是代码注释早有预见的场景：

```python
# view 页 — body 区（QWebEngineView 延迟创建，避免 macOS 启动时 Chromium
# 初始化与 NSApplicationDidBecomeActiveNotification 冲突 → SIGSEGV）
```

但原"延迟创建"只在用户点击任务时才会触发——`singleShot(0, setFocus)` 绕过了这一保护。

### 触发条件

- macOS 平台
- `QTimer.singleShot(0, ...)` 在窗口 active 前触发 `_on_select`
- `_on_select` 调用 `_ensure_view()` 创建 QWebEngineView

### 可否复现

**稳定复现**。只要 `QTimer.singleShot(0, self._tree.setFocus)` 存在、且 DetailView 的占位 HTML 通过 `_ensure_view()` 触发 QWebEngineView 创建，每次启动都会触发。

### 修复

```python
# 延迟 300ms 设置焦点，给窗口激活留出时间
QTimer.singleShot(300, self._tree.setFocus)
```

并在 `_ensure_view()` 增加安全检测：

```python
def _ensure_view(self):
    if self.view is not None:
        return
    top = self.window()
    if not top or not top.isVisible() or not top.windowHandle():
        QTimer.singleShot(200, self._ensure_view)
        return
    # ... 创建 QWebEngineView
```

注意：`DetailView` 是 QWidget 子控件（非 native window），`self.windowHandle()` 永远为 None。**必须用 `self.window().windowHandle()` 检测顶层窗口。**

---

## 衍生 bug：修复后任务详情不显示

### 现象

修复崩溃后，app 正常启动且 UI 可见，但点击任务树节点时详情面板无内容。

### 根因

`_ensure_view` 中的安全检测使用 `self.windowHandle()`，但 `DetailView` 是 `QWidget` 子控件，不是 native window，`self.windowHandle()` 永远返回 `None`。

导致 `_ensure_view` **无限 defer**（每 200ms 重试一次，每次都判定窗口没有 native handle），QWebEngineView 永不创建，`show_task()` / `show_placeholder()` 也永远延迟重试，最终详情面板始终空白。

```python
# 错误写法（DetailView 是子控件，windowHandle() 永远 None）
if not self.windowHandle():
    QTimer.singleShot(200, self._ensure_view)
    return

# 正确写法：用 self.window() 拿到顶层 QMainWindow
top = self.window()
if not top or not top.isVisible() or not top.windowHandle():
    QTimer.singleShot(200, self._ensure_view)
    return
```

### 可否复现

**稳定复现**。只要用 `self.windowHandle()` 检查子控件，就永远无法创建 QWebEngineView。

---

## 最终状态

| 问题 | 修复 | 稳定？ |
|------|------|--------|
| `--single-process` V8 crash | → `--disable-gpu` | ✅ 不崩溃 |
| 过早 setFocus 创建 WebEngineView | `singleShot(0)` → `singleShot(300)` | ✅ 不崩溃 |
| `_ensure_view` 用 `self.windowHandle()` 检查子控件 | → `self.window().windowHandle()` | ✅ 详情可见 |

`dai restart` + `dai ui status` + `dai ui task detail` 全部正常。

---

## 调试要点（供下次参考）

- **exit code 139** = SIGSEGV（128 + 11），Qt/C++ 级崩溃，Python try/except 捕获不到
- 用 `os.environ['QTWEBENGINE_CHROMIUM_FLAGS']` 必须在 `import` QtWebEngineWidgets **之前**设置，否则不生效
- 非 native QWidget 的 `windowHandle()` 永远为 None，需走 `self.window().windowHandle()`
- `processEvents()` 不会触发全部事件（挂起而崩溃），但 `app.exec()` 会
