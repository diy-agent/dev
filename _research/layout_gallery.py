#!/usr/bin/env python3
"""
PySide6 布局能力完整图谱 — 每个机制独立展示，用于 IDE 应用设计参考。

运行: uv run --no-group dev python _research/layout_gallery.py
选择编号查看对应布局机制的演示窗口。
"""
import sys

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QColor, QPalette, QShortcut, QKeySequence
from PySide6.QtWidgets import *


# ═══════════════════════════════════════════════════════════════
# 1. QVBoxLayout / QHBoxLayout — 盒式布局（最基本）
# ═══════════════════════════════════════════════════════════════
class Demo_BoxLayout(QWidget):
    """QHBoxLayout / QVBoxLayout — 垂直/水平堆叠。
    用途：面板内的基本排列、工具栏、状态栏。
    能力：stretch 弹性系数、alignment 对齐、spacing 间距。
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("01 — QVBoxLayout / QHBoxLayout")
        layout = QVBoxLayout(self)

        # ── VBox（垂直堆叠）──
        vbox = QVBoxLayout()
        vbox.addWidget(QLabel("QVBoxLayout（垂直堆叠）:"))
        vbox.addWidget(QPushButton("按钮 1"), 1)  # stretch=1
        vbox.addWidget(QPushButton("按钮 2"), 2)  # stretch=2（占比更大）
        vbox.addWidget(QPushButton("按钮 3"), 1)
        layout.addLayout(vbox)

        # ── HBox（水平排列）──
        hbox = QHBoxLayout()
        hbox.addWidget(QLabel("QHBoxLayout（水平排列）:"))
        hbox.addWidget(QPushButton("左"))
        hbox.addWidget(QPushButton("中"), 1)  # stretch 撑开
        hbox.addWidget(QPushButton("右"))
        hbox.addStretch()  # 弹性空白
        hbox.addWidget(QPushButton("贴右"))
        layout.addLayout(hbox)


# ═══════════════════════════════════════════════════════════════
# 2. QGridLayout — 网格布局
# ═══════════════════════════════════════════════════════════════
class Demo_GridLayout(QWidget):
    """QGridLayout — 网格布局（行列跨度）。
    用途：工具栏按钮网格、属性面板、仪表盘。
    能力：addWidget(w, row, col, rowSpan, colSpan, alignment)。
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("02 — QGridLayout")
        layout = QGridLayout(self)

        # 标题跨 4 列
        layout.addWidget(QLabel("QGridLayout — 网格布局（行列跨度）:"), 0, 0, 1, 4)

        # 数字键盘式布局
        for i, (r, c) in enumerate([(1,0),(1,1),(1,2), (2,0),(2,1),(2,2), (3,0),(3,1),(3,2)]):
            layout.addWidget(QPushButton(f"{i+1}"), r, c)

        layout.addWidget(QPushButton("0"), 4, 0, 1, 2)   # 跨 2 列
        layout.addWidget(QPushButton("确定"), 4, 2)       # 单个

        # 右侧跨行面板
        panel = QTextEdit("右侧面板\n跨 4 行")
        layout.addWidget(panel, 1, 3, 4, 1)


# ═══════════════════════════════════════════════════════════════
# 3. QFormLayout — 表单布局
# ═══════════════════════════════════════════════════════════════
class Demo_FormLayout(QWidget):
    """QFormLayout — 表单布局（标签-字段对）。
    用途：设置面板、属性编辑器。
    能力：addRow(label, widget)、行换行策略、标签对齐。
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("03 — QFormLayout")
        form = QFormLayout(self)

        form.addRow("项目名称:", QLineEdit("untitled"))
        form.addRow("作者:", QLineEdit("user"))
        form.addRow("描述:", QTextEdit("项目描述"))
        form.addRow("版本:", QSpinBox())
        form.addRow("语言:", QComboBox())
        form.addRow("", QPushButton("保存"))

        # QFormLayout 自动处理标签对齐和字段换行
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)


# ═══════════════════════════════════════════════════════════════
# 4. QStackedLayout / QStackedWidget — 堆叠页面
# ═══════════════════════════════════════════════════════════════
class Demo_StackedLayout(QWidget):
    """QStackedLayout / QStackedWidget — 堆叠页面切换。
    用途：配置向导、多步骤流程、侧边栏不同模式。
    能力：setCurrentIndex()、setCurrentWidget()、count()。
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("04 — QStackedWidget")
        self.resize(400, 250)
        layout = QVBoxLayout(self)

        # 按钮导航
        btn_row = QHBoxLayout()
        for name in ["👤 用户", "⚙ 设置", "📊 统计"]:
            btn = QPushButton(name)
            btn.clicked.connect(lambda checked, n=name: self._switch(n))
            btn_row.addWidget(btn)
        layout.addLayout(btn_row)

        # 堆叠页面
        self._stack = QStackedWidget()
        self._stack.addWidget(QLabel("这是用户管理页面\n可以在这里管理用户信息"))
        self._stack.addWidget(QLabel("这是设置页面\n可以在这里修改配置"))
        self._stack.addWidget(QLabel("这是统计页面\n显示各种统计数据"))
        layout.addWidget(self._stack)

    def _switch(self, name):
        idx = ["👤 用户", "⚙ 设置", "📊 统计"].index(name)
        self._stack.setCurrentIndex(idx)


# ═══════════════════════════════════════════════════════════════
# 5. QSplitter — 可拖动分隔条
# ═══════════════════════════════════════════════════════════════
class Demo_Splitter(QWidget):
    """QSplitter — 可拖动的分隔条。
    用途：编辑器分屏、面板分区。
    能力：setOrientation() 方向、setStretchFactor() 弹性比例、
          setSizes() 初始大小、setChildrenCollapsible() 可折叠。
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("05 — QSplitter（嵌套分屏）")
        self.resize(700, 400)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("QSplitter — 拖拽分隔条调整大小（可嵌套）:"))

        # 水平分屏
        h = QSplitter(Qt.Orientation.Horizontal)

        # 左侧垂直分屏
        left = QSplitter(Qt.Orientation.Vertical)
        left.addWidget(QTextEdit("编辑区 A"))
        left.addWidget(QTextEdit("编辑区 B"))
        h.addWidget(left)

        # 右侧
        right = QSplitter(Qt.Orientation.Vertical)
        right.addWidget(QTextEdit("大纲"))
        right.addWidget(QTextEdit("终端"))
        h.addWidget(right)

        h.setStretchFactor(0, 3)  # 左:右 = 3:1
        h.setStretchFactor(1, 1)
        h.setSizes([500, 200])

        layout.addWidget(h)


# ═══════════════════════════════════════════════════════════════
# 6. QTabWidget — 标签页
# ═══════════════════════════════════════════════════════════════
class Demo_TabWidget(QWidget):
    """QTabWidget — 标签页容器。
    用途：文档标签（IDE 编辑器顶部）、面板标签。
    能力：tabPosition(North/South/East/West)、tabsClosable、
          movable、documentMode、setTabBarAutoHide。
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("06 — QTabWidget")
        self.resize(600, 300)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("QTabWidget — 标签页容器，支持拖拽/关闭/位置切换:"))

        tabs = QTabWidget()
        tabs.setTabPosition(QTabWidget.TabPosition.North)
        tabs.setTabsClosable(True)
        tabs.setMovable(True)
        tabs.setDocumentMode(True)  # 边框更紧凑

        tabs.addTab(QTextEdit("文档内容 1"), "main.py")
        tabs.addTab(QTextEdit("文档内容 2"), "utils.py")
        tabs.addTab(QTextEdit("文档内容 3"), "config.json")

        # 标签位置切换
        pos_row = QHBoxLayout()
        for pos, name in [(QTabWidget.TabPosition.North, "上"),
                          (QTabWidget.TabPosition.South, "下"),
                          (QTabWidget.TabPosition.West, "左"),
                          (QTabWidget.TabPosition.East, "右")]:
            btn = QPushButton(name)
            btn.clicked.connect(lambda checked, p=pos: tabs.setTabPosition(p))
            pos_row.addWidget(btn)
        layout.addLayout(pos_row)
        layout.addWidget(tabs)


# ═══════════════════════════════════════════════════════════════
# 7. QGroupBox — 分组框
# ═══════════════════════════════════════════════════════════════
class Demo_GroupBox(QWidget):
    """QGroupBox — 带标题和边框的分组容器。
    用途：设置面板分区、逻辑分组。
    能力：setCheckable(True) 可勾选折叠、setFlat() 扁平样式、
          setAlignment 标题对齐。
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("07 — QGroupBox")
        self.resize(400, 250)
        layout = QHBoxLayout(self)

        # 普通分组
        g1 = QGroupBox("常规设置")
        g1_layout = QVBoxLayout(g1)
        g1_layout.addWidget(QCheckBox("自动保存"))
        g1_layout.addWidget(QCheckBox("显示行号"))
        g1_layout.addWidget(QCheckBox("换行"))
        layout.addWidget(g1)

        # 可勾选分组（可以折叠）
        g2 = QGroupBox("高级设置 (可勾选)")
        g2.setCheckable(True)
        g2.setChecked(False)
        g2_layout = QVBoxLayout(g2)
        g2_layout.addWidget(QCheckBox("实验功能 A"))
        g2_layout.addWidget(QCheckBox("实验功能 B"))
        layout.addWidget(g2)


# ═══════════════════════════════════════════════════════════════
# 8. QScrollArea — 滚动区域
# ═══════════════════════════════════════════════════════════════
class Demo_ScrollArea(QWidget):
    """QScrollArea — 可滚动的视口。
    用途：内容超长/超宽时的滚动容器、代码编辑器、属性面板。
    能力：setWidgetResizable(True) 内容自适应、
          scrollBarPolicy 滚动条策略、
          ensureVisible() 滚动到指定位置。
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("08 — QScrollArea")
        self.resize(350, 250)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("QScrollArea — 滚动查看超出窗口的内容:"))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        content = QWidget()
        cl = QVBoxLayout(content)
        for i in range(30):
            cl.addWidget(QLabel(f"  第 {i+1} 行: Lorem ipsum dolor sit amet..."))
        scroll.setWidget(content)

        layout.addWidget(scroll)


# ═══════════════════════════════════════════════════════════════
# 9. QSplitter + QTabWidget 嵌套（IDE 编辑器经典结构）
# ═══════════════════════════════════════════════════════════════
class Demo_IdeEditorLayout(QWidget):
    """QSplitter + QTabWidget 组合 — IDE 编辑器经典结构。
    四个编辑器组，每组有标签，通过 QSplitter 分屏。
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("09 — Splitter + TabWidget（编辑器分屏）")
        self.resize(800, 500)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        h = QSplitter(Qt.Orientation.Horizontal)
        # 左列
        v_left = QSplitter(Qt.Orientation.Vertical)
        v_left.addWidget(self._make_editor(["main.py", "utils.py"]))
        v_left.addWidget(self._make_editor(["output.log"]))
        h.addWidget(v_left)
        # 右列
        v_right = QSplitter(Qt.Orientation.Vertical)
        v_right.addWidget(self._make_editor(["styles.css", "index.html"]))
        v_right.addWidget(self._make_editor(["README.md"]))
        h.addWidget(v_right)
        h.setSizes([400, 400])
        layout.addWidget(h)

    def _make_editor(self, tabs):
        t = QTabWidget()
        t.setTabsClosable(True)
        t.setMovable(True)
        for name in tabs:
            t.addWidget(QTextEdit(f"// {name}"), name)
        return t


# ═══════════════════════════════════════════════════════════════
# 10. QDockWidget — 停靠面板
# ═══════════════════════════════════════════════════════════════
class Demo_DockWidget(QMainWindow):
    """QDockWidget — 可拖拽/浮动/关闭的停靠面板。
    用途：IDE 侧边栏、底部终端、工具面板。
    能力：setAllowedAreas() 停靠区域、
          setFeatures() 行为控制（浮动/关闭/移动）、
          setFloating() 独立窗口、
          tabifyDockWidgets() 标签化堆叠。
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("10 — QDockWidget（停靠面板）")
        self.resize(800, 500)
        self.setCentralWidget(QTextEdit("中央编辑器"))

        panels = [
            ("📁 文件", Qt.DockWidgetArea.LeftDockWidgetArea, True, True, True),
            ("🔍 搜索", Qt.DockWidgetArea.LeftDockWidgetArea, True, True, True),
            ("📋 大纲", Qt.DockWidgetArea.RightDockWidgetArea, True, True, True),
            ("⬡ 终端", Qt.DockWidgetArea.BottomDockWidgetArea, True, True, False),
        ]

        docks = []
        for title, area, closable, movable, floatable in panels:
            dock = QDockWidget(title, self)
            dock.setObjectName(title.replace(" ", "_"))
            dock.setWidget(QListWidget())
            dock.widget().addItems([f"{title} — 项目 {i}" for i in range(5)])

            features = QDockWidget.DockWidgetFeature(0)
            if closable:
                features |= QDockWidget.DockWidgetFeature.DockWidgetClosable
            if movable:
                features |= QDockWidget.DockWidgetFeature.DockWidgetMovable
            if floatable:
                features |= QDockWidget.DockWidgetFeature.DockWidgetFloatable
            dock.setFeatures(features)
            self.addDockWidget(area, dock)
            docks.append(dock)

        # 文件 + 搜索 标签化堆叠
        self.tabifyDockWidget(docks[0], docks[1])
        docks[0].raise_()

        # 视图菜单
        mb = self.menuBar()
        view_menu = mb.addMenu("面板")
        for dock in docks:
            act = dock.toggleViewAction()
            view_menu.addAction(act)


# ═══════════════════════════════════════════════════════════════
# 11. SizePolicy & Stretch — 弹性大小控制
# ═══════════════════════════════════════════════════════════════
class Demo_SizePolicy(QWidget):
    """SizePolicy — 控件在布局中的伸缩行为。
         Fixed:      固定大小，不伸缩
         Preferred:  按 sizeHint，可伸缩
         Expanding:  尽可能占据空间
         Minimum:    不低于 minimumSize，按需伸缩
         Maximum:    不高于 maximumSize
         MinimumExpanding: 不低于 minimumSize，尽量撑开
         Ignored:    忽略 sizeHint，完全按 stretch 分配
    用途：控制面板中各个区域谁撑开、谁固定。
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("11 — SizePolicy（控件伸缩策略）")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("SizePolicy — 每个控件的伸缩行为:"))

        examples = [
            (QSizePolicy.Policy.Fixed, "Fixed — 固定，不伸缩", "#e74c3c"),
            (QSizePolicy.Policy.Preferred, "Preferred — 按建议，可伸缩", "#e67e22"),
            (QSizePolicy.Policy.Expanding, "Expanding — 尽可能撑开", "#27ae60"),
            (QSizePolicy.Policy.MinimumExpanding, "MinExpanding — 最小+撑开", "#2980b9"),
            (QSizePolicy.Policy.Minimum, "Minimum — 按最小，可收缩", "#8e44ad"),
            (QSizePolicy.Policy.Maximum, "Maximum — 按最大，不缩小", "#f39c12"),
            (QSizePolicy.Policy.Ignored, "Ignored — 忽略 hint，全由 stretch 决定", "#c0392b"),
        ]

        h = QHBoxLayout()
        for policy, label, color in examples:
            btn = QPushButton(label.split("—")[0].strip())
            btn.setStyleSheet(f"background:{color}; color:white; font-size:10px; padding:8px;")
            btn.setSizePolicy(policy, QSizePolicy.Policy.Expanding)
            btn.setMinimumWidth(60)
            btn.setToolTip(label)
            h.addWidget(btn)
        layout.addLayout(h)
        layout.addWidget(QLabel(
            "提示: 调整窗口宽度，观察各按钮不同的伸缩行为"))


# ═══════════════════════════════════════════════════════════════
# 12. QToolBar — 工具栏
# ═══════════════════════════════════════════════════════════════
class Demo_ToolBar(QMainWindow):
    """QToolBar — 可移动/浮动的工具栏。
    用途：IDE 菜单栏下方的快速操作区。
    能力：setMovable(True) 可拖拽移动、
          setFloatable(True) 可浮动为独立窗口、
          ToolBarArea 上下左右停靠、
          addSeparator() 分隔线。
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("12 — QToolBar（工具栏）")
        self.resize(600, 300)
        self.setCentralWidget(QTextEdit("拖拽工具栏试试"))

        tb = QToolBar("主工具栏")
        tb.setMovable(True)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        tb.addAction("📂 打开")
        tb.addAction("💾 保存")
        tb.addSeparator()
        tb.addAction("↩ 撤销")
        tb.addAction("↪ 重做")
        tb.addSeparator()
        tb.addAction("▶ 运行")

        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)

        # 新增工具栏（可以拖拽到不同区域）
        tb2 = QToolBar("调试")
        tb2.addAction("🐛 调试")
        tb2.addAction("⬆ 单步")
        tb2.addAction("⬇ 步入")
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, tb2)


# ═══════════════════════════════════════════════════════════════
# 13. QToolBox — 折叠工具箱
# ═══════════════════════════════════════════════════════════════
class Demo_ToolBox(QWidget):
    """QToolBox — 可折叠的多层工具箱。
    用途：属性编辑器分组、工具面板。
    能力：addItem(widget, icon, label) 添加折叠层、
          setCurrentIndex() 切换、
          removeItem() 移除。
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("13 — QToolBox（折叠工具箱）")
        self.resize(300, 350)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("QToolBox — 折叠/展开各面板:"))

        tb = QToolBox()
        tb.addItem(self._page("通用设置", ["语言", "主题", "字号"]), "⚙ 通用")
        tb.addItem(self._page("编辑器", ["字体", "缩进", "补全"]), "✏ 编辑器")
        tb.addItem(self._page("快捷键", ["导航", "编辑", "调试"]), "⌨ 快捷键")
        layout.addWidget(tb)

    def _page(self, title, items):
        w = QWidget()
        l = QVBoxLayout(w)
        l.addWidget(QLabel(f"<b>{title}</b>"))
        for name in items:
            l.addWidget(QCheckBox(name))
        return w


# ═══════════════════════════════════════════════════════════════
# 14. QMdiArea — 多文档界面
# ═══════════════════════════════════════════════════════════════
class Demo_MdiArea(QMainWindow):
    """QMdiArea — 多文档界面（子窗口管理）。
    用途：类似旧版 IDE（Visual Studio 6/Matlab）的浮动子窗口。
    能力：addSubWindow()、cascade()/tile() 排列、
          setActiveSubWindow()、subWindowList()。
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("14 — QMdiArea（多文档界面）")
        self.resize(700, 400)

        mdi = QMdiArea()
        for i in range(3):
            sub = mdi.addSubWindow(QTextEdit(f"文档 {i+1} 内容"))
            sub.setWindowTitle(f"文档 {i+1}")
            sub.show()
        self.setCentralWidget(mdi)

        mb = self.menuBar()
        win = mb.addMenu("窗口")
        win.addAction("层叠", mdi.cascadeSubWindows)
        win.addAction("平铺", mdi.tileSubWindows)


# ═══════════════════════════════════════════════════════════════
# 15. QSS (Qt Style Sheets) — 样式表驱动布局
# ═══════════════════════════════════════════════════════════════
class Demo_QSS(QWidget):
    """QSS — Qt 样式表控制布局间距/边框/背景。
    不像 CSS flexbox 那么强，但可以精细控制视觉布局。
    能力：padding、margin、border、border-radius、min-width、max-width。
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("15 — QSS（样式表布局控制）")
        layout = QVBoxLayout(self)

        # 用 QSS 做卡片布局
        cards = QHBoxLayout()
        for i, color in enumerate(["#e74c3c", "#2ecc71", "#3498db", "#f39c12"]):
            card = QFrame()
            card.setStyleSheet(f"""
                QFrame {{
                    background: {color};
                    border-radius: 8px;
                    padding: 16px;
                    margin: 4px;
                }}
                QFrame:hover {{
                    margin: 0px;
                    border: 3px solid white;
                }}
            """)
            cl = QVBoxLayout(card)
            cl.addWidget(QLabel(f"卡片 {i+1}"))
            cl.addWidget(QLabel(f"#{color}"))
            cards.addWidget(card)
        layout.addLayout(cards)

        layout.addWidget(QLabel(
            "提示: QSS 可以控制 padding/margin/border-radius，\n"
            "实现间距、圆角、悬停效果等视觉布局"))


# ═══════════════════════════════════════════════════════════════
# 16. QLayout Spacer — 弹性空白
# ═══════════════════════════════════════════════════════════════
class Demo_Spacer(QWidget):
    """QSpacerItem — 用弹性空白控制元素位置。
    addStretch() = 添加 QSpacerItem(0, 0, Expanding, Minimum)。
    用途：让按钮"贴"到右侧/底部、居中。
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("16 — Layout Spacer（弹性空白）")
        layout = QVBoxLayout(self)

        # 贴右
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("贴右:     "))
        h1.addStretch()
        h1.addWidget(QPushButton("确定"))
        h1.addWidget(QPushButton("取消"))
        layout.addLayout(h1)

        # 居中
        h2 = QHBoxLayout()
        h2.addStretch()
        h2.addWidget(QPushButton("◀"))
        h2.addWidget(QPushButton("▶ "))
        h2.addStretch()
        layout.addLayout(h2)

        # 贴左+贴右
        h3 = QHBoxLayout()
        h3.addWidget(QPushButton("左对齐"))
        h3.addStretch()
        h3.addWidget(QPushButton("右对齐"))
        layout.addLayout(h3)

        # 自定义 SpacerItem
        h4 = QHBoxLayout()
        h4.addWidget(QPushButton("A"))
        h4.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Policy.Fixed))  # 固定40px空白
        h4.addWidget(QPushButton("B"))
        h4.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Policy.Expanding))  # 弹性撑开
        h4.addWidget(QPushButton("C"))
        layout.addLayout(h4)

        layout.addStretch()


# ═══════════════════════════════════════════════════════════════
# 17. QMainWindow 完整结构 — 所有区域一览
# ═══════════════════════════════════════════════════════════════
class Demo_MainWindowFull(QMainWindow):
    """QMainWindow 完整结构（菜单栏/工具栏/停靠面板/状态栏）。
    这是 IDE 应用的主干框架。
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("17 — QMainWindow 完整结构")
        self.resize(900, 600)

        # ── 中央 ──
        self.setCentralWidget(QTextEdit("中央编辑器区域"))

        # ── 菜单 ──
        mb = self.menuBar()
        mb.addMenu("文件").addAction("退出")
        mb.addMenu("编辑")
        mb.addMenu("视图")

        # ── 工具栏 ──
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, QToolBar("主工具栏"))

        # ── 停靠面板 ──
        for title, area in [("文件", Qt.DockWidgetArea.LeftDockWidgetArea),
                            ("终端", Qt.DockWidgetArea.BottomDockWidgetArea),
                            ("大纲", Qt.DockWidgetArea.RightDockWidgetArea)]:
            dock = QDockWidget(title, self)
            dock.setWidget(QListWidget())
            dock.widget().addItems([f"{title} 项目 {i}" for i in range(5)])
            self.addDockWidget(area, dock)

        # ── 状态栏 ──
        sb = self.statusBar()
        sb.showMessage("就绪")
        sb.addPermanentWidget(QLabel("行: 1  列: 1"))


def _add_close_shortcut(widget):
    """为窗口添加 Ctrl+W 关闭、Ctrl+Q 退出"""
    QShortcut(QKeySequence("Ctrl+W"), widget).activated.connect(widget.close)
    app = QApplication.instance()
    QShortcut(QKeySequence("Ctrl+Q"), widget).activated.connect(app.quit)


# ═══════════════════════════════════════════════════════════════
# 选单 — 运行全部
# ═══════════════════════════════════════════════════════════════
ALL_DEMOS = [
    ("盒式布局",          Demo_BoxLayout),
    ("网格布局",          Demo_GridLayout),
    ("表单布局",          Demo_FormLayout),
    ("堆叠页面",          Demo_StackedLayout),
    ("分隔条",            Demo_Splitter),
    ("标签页",            Demo_TabWidget),
    ("分组框",            Demo_GroupBox),
    ("滚动区域",          Demo_ScrollArea),
    ("编辑器分屏",        Demo_IdeEditorLayout),
    ("停靠面板",          Demo_DockWidget),
    ("伸缩策略",          Demo_SizePolicy),
    ("工具栏",            Demo_ToolBar),
    ("折叠工具箱",        Demo_ToolBox),
    ("多文档界面",        Demo_MdiArea),
    ("样式表布局",        Demo_QSS),
    ("弹性空白",          Demo_Spacer),
    ("完整窗口结构",      Demo_MainWindowFull),
]


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    print("=" * 60)
    print("  PySide6 布局能力图谱 — 17 种独立机制")
    print("=" * 60)
    for i, (name, cls) in enumerate(ALL_DEMOS, 1):
        print(f"  {i:2d}. {name:<12s}  ({cls.__doc__.split(chr(10))[0]})")
    print()
    idx = int(input("  选择编号运行 (0=全部, 1-17): ").strip())

    if idx == 0:
        for name, cls in ALL_DEMOS:
            w = cls()
            _add_close_shortcut(w)
            w.show()
        app.exec()
    elif 1 <= idx <= len(ALL_DEMOS):
        name, cls = ALL_DEMOS[idx - 1]
        w = cls()
        _add_close_shortcut(w)
        w.show()
        sys.exit(app.exec())
    else:
        print("invalid")


if __name__ == "__main__":
    main()
