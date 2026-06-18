# PySide6 provider: diy-ui 设计评审 + 改造路线图

## 背景

diy-ui 即将新增 PySide6 provider。在动手之前，对当前 diy-ui 核心（Signal / ScopeProxy / ContextVar / async cell）做了系统性评审，识别出 8 个 Panel 硬编码耦合点和 3 个架构级缺陷。

---

## 一、必须在做 PySide6 之前修掉的 3 个 Bug

| # | 问题 | 位置 | 影响 |
|---|------|------|------|
| 1 | `Signal._set_context` 在模块导入时执行（全局副作用） | `_scope.py:63-64` | 双 provider 时 context 互相覆盖 |
| 2 | `_debug_cache` 用 `id()` 做 key 永不清除 | `_debug.py:48-56` | PySide6 QWidget 生命周期下更严重（Qt 销毁对象后 id 复用返回 stale 数据） |
| 3 | async cell 执行失败后 `_flush_deps_and_reset` 传入空 deps，清空所有依赖 | `_scope.py:322` | cell 失败一次后永不再响应 signal 变化 |

**修复量**：3 处共约 15 行。

---

## 二、发现的 8 处 Panel 硬编码耦合

| 耦合点 | 文件 | 假定 |
|--------|------|------|
| Signal ContextVar | `_signal.py:32-33` | 单线程 asyncio |
| ScopeProxy cell 执行 | `_scope.py:255-416` | asyncio `create_task` |
| `ImmediateScheduler.enqueue_async` | `_scheduler.py:34-52` | `asyncio.get_running_loop()` |
| `_WidgetsFactoryBase._add` | `_widgets_factory.py:63-84` | `param.watch` / `param.Event` |
| `_HasValue` mixin | `_base.py:65-86` | `self.param['value']` |
| `DiyInitSub` metaclass | `_meta.py:178-211` | `hasattr(base, "param")` |
| `ScopeProxy._add_child` | `_scope.py:138-139` | `self._host.append(child._host)` |
| `_PanelContainerMixin` | `_base.py:44-62` | `self[:] = [...]` / `self.remove()` |

---

## 三、6 个几乎相同的 cell 执行路径

`_execute_cell`, `_execute_cell_async`, `_execute_cell_generator`, `_drive_generator_sync`, `_drive_generator_async`, `on_signal_changed`

代码重复率 ~70%。设计文档（reactive-design-patterns.md）已自省 "yield 在 async cell 中没有独立价值"，但代码未执行。

---

## 四、PySide6 独立 provider 的影响矩阵

### 需要新增的

| 新增项 | 说明 |
|--------|------|
| `PySide6App(BaseApp)` | 管理 QApplication |
| `QtScheduler` | `QTimer.singleShot(0, ...)` 实现调度 |
| `PySide6Component` | QWidget 包装，继承 ScopeNode |
| Qt signals -> diy Signal 桥接 | `widget.valueChanged.connect(lambda v: ...)` |
| PySide6 widget wrapper 工厂 | 读 QWidget 属性签名生成 init |

### 需要重构的

| 重构项 | 说明 |
|--------|------|
| cell 执行从 ScopeProxy 拆到独立 `_cell.py` | 目前 cell 执行逻辑嵌在 ScopeProxy 的方法里 |
| Scheduler 从"全局 ImmediateScheduler"改为 injectable provider scheduler | 每个 provider 用自己的 scheduler |
| `ScopeProxy._add_child` 拆离 Panel 原生同步逻辑 | 保留树结构操作，UI 同步委托给 provider mixin |
| `UIComponent` 拆为 provider-agnostic 基类 + Panel/PySide6 子类 | 当前 UIComponent 继承链混乱 |

### 不要动的

- `Signal[T]` 类本身 — 独立于 provider
- ScopeProxy 树结构（parent/children/ancestor_ids）
- ContextVar 做依赖追踪的原理
- `cell()` 装饰器概念

---

## 五、PySide6 + Panel WebView 共存场景

（暂不处理，但设计层预留）

1. **双事件循环**：Qt `QApplication.exec()` + asyncio（Panel/Tornado）
2. **跨线程 Signal 通知**：PySide6 widget 在 Qt 主线程修改 Signal -> `_trigger_observers` 同步触发 Panel cell 的 `on_signal_changed` -> 跨线程修改 Panel Document 可能不一致
3. **Signal setter 同步递归**：Qt slot -> Signal.value setter -> `_notify` + `_trigger_observers` 全在 Qt 线程同步执行

---

## 六、改造路线图

### Phase 0：修 Bug（不可跳过）

- [ ] 删除 `_scope.py:63-64` 的模块级 `Signal._set_context(_runtime)`
- [ ] `_debug_cache` 改为 `weakref.WeakKeyDictionary`
- [ ] async cell 失败时不清空依赖：异常路径里 `deps = self._dependencies`

### Phase 1：拆离 cell 执行

- [ ] 新建 `_cell.py`，提取 `_execute_cell/_execute_cell_async` 等 6 个方法到 `CellRunner` 类
- [ ] ScopeProxy 保留树结构，cell 执行委托给 `CellRunner`
- [ ] 消除 generator 的冗余路径（yield -> 直接 `app.xxx()`）

### Phase 2：Scheduler 抽象

- [ ] `SchedulerProtocol` 增加 `is_async` / `run_cell_sync` / `run_cell_async`
- [ ] `ImmediateScheduler` -> `PanelScheduler`（移入 `providers/panel/`）
- [ ] `on_signal_changed` 不自己判断 `iscoroutinefunction`，改问 scheduler

### Phase 3：UIComponent 拆分

- [ ] `UIComponent` -> `BaseComponent(ScopeNode)` + `PanelComponent(BaseComponent, DiyInitSub)`
- [ ] `_HasValue` mixin -> provider-agnostic 版本 + `PanelHasValue`
- [ ] `ScopeProxy._add_child` 里的 `self._host.append()` 移到 `PanelContainerMixin`

### Phase 4：PySide6 provider

- [ ] `PySide6App(BaseApp)` + `QtScheduler`
- [ ] `PySide6Component(BaseComponent, QWidget)` + Qt signals -> Signal 桥接
- [ ] widget wrapper 工厂
- [ ] 意图测试

---

## 七、设计原则

1. **Signal 是 provider-agnostic 的状态原语** — 不引入 provider 依赖
2. **ContextVar 隔离 per-provider** — PySide6 和 Panel 各自持有自己的 ContextVar 栈
3. **Scheduler injectable** — 不允许模块级 `ImmediateScheduler()` 硬编码
4. **cell 执行逻辑不要在 ScopeProxy 里** — 树结构和响应式执行是不同的关注点
5. **失败路径保留现有依赖** — cell 执行失败是暂时的，不应永久丢失依赖关系
