# 方案 A 修正：异常由公共层捕获，前端壳只处理正常流

## 原则

前端壳（CLI 命令、Gateway handler、GUI 按钮事件）**只负责正常流**。
异常处理由公共中间件统一拦截，按前端类型分发展示。

```
create_task(title, subject, ...)
  ⇣
┌──────────────────────────────┐
│  Core 内部校验 → 抛异常       │
│  正常 → return dict           │
└──────────────────────────────┘
  ⇣                        ⇣
ValidationError          dict(正常)
  ⇣                        ⇣
公共中间件捕获            前端壳收到 → 展示
  ⇣
按前端类型分发:
  CLI:    遍历打印 + sys.exit(1)
  Gateway: JSON 序列化返回
  GUI:    字段级 showError() / 弹窗
```

---

## 具体实现

### 公共中间件

```python
# core/middleware.py

def cli_call(fn, args, kwargs):
    """CLI 命令的公共包装器。"""
    try:
        result = fn(*args, **kwargs)
        yaml.dump(result, sys.stdout)
    except ValidationError as e:
        for err in e.errors:
            print(f"  {err.field}: {err.code} — {err.msg}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


def gateway_call(fn, args, kwargs):
    """Gateway handler 的公共包装器。"""
    try:
        result = fn(*args, **kwargs)
        import yaml, io; buf = io.StringIO()
        yaml.dump({"status": "ok", "data": result}, buf)
        return buf.getvalue()
    except ValidationError as e:
        return json.dumps({"status": "error", "errors": [
            {"field": e.field, "code": e.code, "msg": e.msg}
            for e in e.errors
        ]})
    except ValueError as e:
        return json.dumps({"status": "error", "msg": str(e)})
```

### CLI：零捕获

```python
# _dai_cli.py
from diydev.core.middleware import cli_call

@task_app.command(name="create")
def task_create(title: str, subject: str, ...):
    """创建任务。"""
    from diydev.core.task import create_task
    cli_call(create_task, (title, subject), {"parent": parent, ...})
```

### Gateway：零捕获

```python
# app/main.py GatewayCLI
from diydev.core.middleware import gateway_call

@task_app.command(name="create")
def task_create(title: str, subject: str, ...):
    """创建任务。"""
    from diydev.core.task import create_task
    return gateway_call(create_task, (title, subject), {"parent": parent, ...})
```

### GUI：表单组件统收

GUI 的场景跟 CLI/Gateway 不同——**错误需要展示到具体字段旁边**，所以是表单基类负责捕获：

```python
# app/_create_task_dialog.py
class TaskFormMixin:
    """表单基类：统一捕获 ValidationError 并映射到字段级显示。"""

    _field_labels: dict[str, QLabel] = {}

    def execute(self, fn, *args, **kwargs):
        """执行 Core 函数，异常自动展示到字段。"""
        self._clear_errors()
        try:
            return fn(*args, **kwargs)
        except ValidationError as e:
            for err in e.errors:
                label = self._field_labels.get(err.field)
                if label:
                    label.setText(f"⚠ {err.msg}")
                    label.show()
                else:
                    # 没有对应字段的 fallback
                    QMessageBox.warning(self, "输入有误", err.msg)
            return None


class CreateTaskDialog(QDialog, TaskFormMixin):
    def __init__(self, ...):
        super().__init__()
        self._field_labels = {
            "title": self._title_error,   # QLabel 初始化时已创建
            "subject": self._subject_error,
        }

    def _on_create(self):
        uri = self.execute(create_task, title=self._title.text(), ...)
        if uri is None:
            return  # 错误已由表单基类展示，不需要额外处理
        self._result_uri = uri
        self.accept()
```

按钮（`_on_create`）里 **只有正常流**：成功 → accept()，失败 → execute 返回 None。

### 更激进：decorator 风格

```python
# core/middleware.py
import functools

def cli_handler(fn):
    """标记一个 CLI 命令 handler，自动包装异常。"""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            result = fn(*args, **kwargs)
            yaml.dump(result, sys.stdout)
        except ValidationError as e:
            for err in e.errors:
                print(f"  {err.field}: {err.code} — {err.msg}", file=sys.stderr)
            sys.exit(1)
        except ValueError as e:
            print(f"错误: {e}", file=sys.stderr)
            sys.exit(1)
    return wrapper
```

---

## 最终效果

| 层级 | 代码行数 | 错误处理 |
|------|---------|---------|
| CLI 命令函数 | 1 行（调 cli_call） | 零 |
| Gateway handler | 1 行（调 gateway_call） | 零 |
| GUI 按钮事件 | 2 行（execute + accept） | 零 |
| Core 函数 | 正常行数 | 内部抛 ValidationError/ValueError |
| middleware.py | ~20 行 | 全部错误处理逻辑 |

**前端壳的所有 if 全部消失，错误处理不再是每个 handler 的责任。**
