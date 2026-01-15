import sys
import sys
import os
import csv
import json
from datetime import datetime
from typing import Optional
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QGridLayout,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QFileDialog,
    QMessageBox,
    QFrame,
    QDialog,
    QCalendarWidget,
    QToolButton,
    QSystemTrayIcon,
    QMenu,
)
from PyQt6.QtCore import Qt, QTimer, QDate, QPoint, QSettings, QMimeData
from PyQt6.QtGui import (
    QFont,
    QDrag,
    QColor,
    QIcon,
    QAction,
    QPixmap,
    QPainter,
    QPen,  # 添加 QPen 导入
)

# --- 1. 自定义日历弹窗 (修复星期显示问题) ---
class CalendarPopup(QDialog):
    def __init__(self, parent=None, current_date=QDate.currentDate()):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.selected_date = current_date
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.cal = QCalendarWidget()
        self.cal.setSelectedDate(current_date)
        # 设置一周的第一天为周一，符合中国习惯
        self.cal.setFirstDayOfWeek(Qt.DayOfWeek.Monday) 
        self.cal.clicked.connect(self.save_date)
        
        # --- 【核心修改 1：替换丑陋的箭头图标】 ---
        # 找到日历控件中默认的上一个月/下一个月按钮
        prev_btn = self.cal.findChild(QToolButton, "qt_calendar_prevmonth")
        next_btn = self.cal.findChild(QToolButton, "qt_calendar_nextmonth")
        
        # 移除默认图标，设置扁平化的文本箭头
        if prev_btn:
            prev_btn.setIcon(QIcon()) # 移除图标需要导入 QIcon，或者干脆不设置，直接设文本
            prev_btn.setText("◀")      # 使用 Unicode 箭头字符
            prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            
        if next_btn:
            next_btn.setIcon(QIcon())
            next_btn.setText("▶")
            next_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        # --- 【核心修改 2 & 3：深度定制样式表】 ---
        self.cal.setStyleSheet("""
            /* --- 整体结构 --- */
            QCalendarWidget {
                background-color: #2c3e50; /* 整体深色背景 */
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 8px;
            }
            
            /* --- 顶部导航栏区域 (修复月份看不清的问题) --- */
            /* 导航栏背景 */
            QWidget#qt_calendar_navigationbar {
                background-color: #2c3e50;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                padding: 5px;
            }
            /* 导航栏里的文字标签（显示月份和年份的文本）强制白色 */
            QWidget#qt_calendar_navigationbar QLabel {
                color: white;
                font-size: 16px;
                font-weight: bold;
            }

            /* --- 修复箭头按钮样式 --- */
            /* 针对我们刚才修改了文本的两个特定按钮 */
            QToolButton#qt_calendar_prevmonth, QToolButton#qt_calendar_nextmonth {
                color: rgba(255,255,255,0.6); /* 平时稍微透明 */
                background-color: transparent;
                border: none;
                font-size: 18px;
                font-weight: bold;
                padding: 5px;
            }
            QToolButton#qt_calendar_prevmonth:hover, QToolButton#qt_calendar_nextmonth:hover {
                color: white; /* 悬停变亮 */
                background-color: rgba(255,255,255,0.1);
                border-radius: 4px;
            }

            /* --- 修复年份下拉框 (修复图4看不清的问题) --- */
            QCalendarWidget QSpinBox {
                color: white;
                background-color: rgba(255,255,255,0.1);
                selection-background-color: #1abc9c;
                selection-color: white;
                border-radius: 4px;
                padding-right: 15px; /* 给下拉箭头留位置 */
            }
            /* 年份输入框的向上向下小按钮 */
            QCalendarWidget QSpinBox::up-button, QCalendarWidget QSpinBox::down-button {
                subcontrol-origin: border;
                width: 15px;
                background: transparent; 
            }
            /* 下拉出来的列表视图 */
            QCalendarWidget QAbstractItemView:enabled {
                background-color: #34495e; /* 下拉列表背景色 */
                color: white;
                selection-background-color: #1abc9c;
            }

            /* --- 日历主体表格区域 (修复红白相间问题) --- */
            QCalendarWidget QTableView {
                background-color: transparent;
                alternate-background-color: transparent;
                selection-background-color: #1abc9c; /* 选中日期为青色 */
                selection-color: white;
                outline: none; /* 去除选中虚线框 */
            }
            
            /* 【关键】强制所有日期格子的文字颜色为白色，覆盖默认的周末红色 */
            QCalendarWidget QAbstractItemView {
                color: white;
                font-size: 14px;
            }
            /* 鼠标悬停在日期上 */
            QCalendarWidget QAbstractItemView:hover {
                background-color: rgba(255,255,255,0.1);
                border-radius: 4px;
            }
            
            /* --- 表头 (周一、周二...) --- */
            QCalendarWidget QHeaderView::section {
                background-color: transparent;
                color: rgba(255,255,255,0.5); /* 表头文字稍微暗一点 */
                border: none;
                font-weight: bold;
                padding: 5px;
            }
        """)
        
        layout.addWidget(self.cal)

    def save_date(self, date):
        self.selected_date = date
        self.accept()

# --- 2. 任务项逻辑 ---
class TaskItem(QListWidgetItem):
    def __init__(
        self,
        text: str,
        created_at: Optional[str] = None,
        finished_at: str = "未完成",
        is_done: bool = False,
    ):
        super().__init__(text)
        # 真实内容单独保存，方便显示时加前缀符号（✓ 等）
        self.content = text
        # 如果是从历史记录恢复，则使用传入时间；否则使用当前时间
        self.created_at = created_at or datetime.now().strftime("%Y-%m-%d %H:%M")
        self.finished_at = finished_at
        self.is_done = is_done
        self.update_appearance()

    def toggle_status(self):
        self.is_done = not self.is_done
        self.finished_at = datetime.now().strftime("%Y-%m-%d %H:%M") if self.is_done else "未完成"
        self.update_appearance()

    def update_appearance(self):
        """根据完成状态更新显示样式"""
        # 文本（显示时为内容前加符号，真实内容保存在 self.content）
        display_text = self.content
        if self.is_done:
            display_text = f"✓ {self.content}"
        self.setText(display_text)

        # 字体样式：完成后加删除线、稍微变细一点
        font = self.font()
        font.setStrikeOut(self.is_done)
        self.setFont(font)

        # 颜色与背景：完成后显著变灰并加半透明底色
        if self.is_done:
            self.setForeground(QColor(200, 200, 200, 130))
            self.setBackground(QColor(0, 0, 0, 80))
        else:
            self.setForeground(QColor(255, 255, 255))
            self.setBackground(QColor(0, 0, 0, 0))

        # 悬停提示：显示任务状态和时间信息
        status_text = "已完成" if self.is_done else "未完成"
        tooltip = f"内容：{self.content}\n状态：{status_text}\n创建时间：{self.created_at}"
        if self.is_done and self.finished_at:
            tooltip += f"\n完成时间：{self.finished_at}"
        self.setToolTip(tooltip)

# --- 3. 列表控件 ---
class QuadrantList(QListWidget):
    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSpacing(4)
        
        # 启用自定义右键菜单策略
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        self.setStyleSheet("""
            QListWidget { background: transparent; border: none; outline: none; }
            QListWidget::item { color: white; padding: 8px; background: transparent; }
            QListWidget::item:selected { background: transparent; border: none; }
        """)

    def show_context_menu(self, pos):
        """显示右键删除菜单"""
        item = self.itemAt(pos)
        if not item:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #34495e; color: white; border: 1px solid #555; border-radius: 5px; }
            QMenu::item { padding: 5px 20px; }
            QMenu::item:selected { background-color: #e74c3c; }
        """)
        
        delete_action = QAction("🗑️ 删除任务", self)
        delete_action.triggered.connect(lambda: self.delete_task(item))
        menu.addAction(delete_action)
        
        menu.exec(self.mapToGlobal(pos))

    def delete_task(self, item):
        """删除操作并保存"""
        row = self.row(item)
        if row >= 0:
            self.takeItem(row)
            if hasattr(self.window(), "save_state"):
                self.window().save_state()




def create_tray_icon():
    """创建托盘图标"""
    # 创建一个64x64的透明位图
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    # 绘制蓝色圆形背景
    painter.setBrush(QColor(66, 135, 245, 220))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(8, 8, 48, 48)
    
    # 绘制白色"E"字母
    painter.setPen(QPen(Qt.GlobalColor.white, 4))
    painter.setFont(QFont("Arial", 30, QFont.Weight.Bold))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "E")
    
    painter.end()
    
    return QIcon(pixmap)


class EisenhowerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.target_date = QDate(2026, 2, 6)
        self._is_locked = False  # 锁定状态标记
        self._drag_pos = QPoint()  # 用于处理无边框拖动
        # JSON 数据文件，用于保存除位置以外的所有内容
        self.data_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tasks_data.json")
        # 字体大小设置（可通过设置面板调整）
        self.title_font_size = 28
        self.event_font_size = 16
        self.task_font_size = 12
        # 开机自启设置
        self.auto_start_enabled = False
        # 窗口大小设置（初始值与默认 resize 一致）
        self.window_width = 850
        self.window_height = 750
        
        # 先初始化托盘
        self.init_tray()
        
        # 再初始化窗口
        self.init_window_style()
        self.initUI()

        # 加载上一次的完整状态（标题、事件名、任务列表等）
        self.load_state()

        self.set_auto_start(False) # 默认开启开机不自启
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_countdown_display)
        self.timer.start(60000)
        self.update_countdown_display()

    def init_window_style(self):
        """设置桌面挂件特有的窗口属性"""
        # FramelessWindowHint: 无边框
        # WindowStaysOnBottomHint: 贴在桌面（如果想总在最前，改为 WindowStaysOnTopHint）
        # Tool: 不在任务栏显示主图标
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | 
                            Qt.WindowType.WindowStaysOnBottomHint | 
                            Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground) # 背景透明
        
        # 加载上次保存的位置（其余状态在 load_state 中加载）
        self.settings = QSettings("MyStudio", "EisenhowerDesktop")
        last_pos = self.settings.value("pos", QPoint(100, 100))
        if isinstance(last_pos, QPoint):
            self.move(last_pos)

    def initUI(self):
        self.setWindowTitle("桌面任务挂件")
        # 使用可配置的窗口大小
        self.resize(self.window_width, self.window_height)
        
        # 主外壳，用于设置带圆角的半透明背景
        self.main_frame = QFrame(self)
        self.main_frame.setObjectName("MainFrame")
        self.main_frame.setStyleSheet("""
            QFrame#MainFrame {
                background-color: rgba(37, 52, 57, 230); /* 85% 不透明度 */
                border-radius: 10px;
                border: 1px solid rgba(255, 255, 255, 10);
            }
        """)
        
        # 全局布局包装在 main_frame 中
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0,0,0,0)
        outer_layout.addWidget(self.main_frame)

        main_layout = QVBoxLayout(self.main_frame)
        main_layout.setContentsMargins(15, 5, 15, 10)
        main_layout.setSpacing(5)

        # --- 顶部交互区域 ---
        header_layout = QHBoxLayout()

        # 新增：设置按钮
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setFixedSize(20, 20)
        self.settings_btn.setToolTip("打开设置")
        self.settings_btn.clicked.connect(self.open_settings_dialog)
        self.settings_btn.setStyleSheet(
            """
            QPushButton { background: transparent; color: white; font-size: 18px; border: none; }
            QPushButton:hover { background: rgba(255,255,255,0.1); border-radius: 5px; }
        """
        )

        # 锁定按钮
        self.lock_btn = QPushButton("🔓")
        self.lock_btn.setFixedSize(20, 20)
        self.lock_btn.setCheckable(True)
        self.lock_btn.setToolTip("锁定/解锁位置")
        self.lock_btn.clicked.connect(self.toggle_lock)
        self.lock_btn.setStyleSheet("""
            QPushButton { background: transparent; color: white; font-size: 18px; border: none; }
            QPushButton:checked { color: #ff7675; }
            QPushButton:hover { background: rgba(255,255,255,0.1); border-radius: 5px; }
        """)
        
        self.main_title = QLineEdit("计划")
        self.main_title.setStyleSheet("color: white; font-weight: bold; background: transparent; border: none;")
        
        # [此处保留你原有的倒计时逻辑代码...]
        self.event_name_input = QLineEdit("截止日期")
        self.event_name_input.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.event_name_input.setStyleSheet("color: rgba(255,255,255,0.9); font-weight: bold; background: transparent; border: none;")
        
        self.date_btn = QPushButton(f"  {self.target_date.toString('yyyy-MM-dd')}")
        self.date_btn.clicked.connect(self.open_calendar_popup)
        self.date_btn.setStyleSheet("color: rgba(255,255,255,0.4); font-size: 12px; background: transparent; border: none; text-align: right;")
        
        right_info_vbox = QVBoxLayout()
        right_info_vbox.addWidget(self.event_name_input)
        right_info_vbox.addWidget(self.date_btn)
        
        self.cd_days_label = QLabel("0 天")
        self.cd_days_label.setStyleSheet("color: white; font-size: 30px; font-weight: bold; margin-left: 5px;")

        # 标题和事件名改动时自动保存
        self.main_title.textChanged.connect(self.save_state)
        self.event_name_input.textChanged.connect(self.save_state)

        header_layout.addWidget(self.settings_btn)
        header_layout.addWidget(self.lock_btn)
        header_layout.addWidget(self.main_title)
        header_layout.addStretch()
        header_layout.addLayout(right_info_vbox)
        header_layout.addWidget(self.cd_days_label)
        main_layout.addLayout(header_layout)

        # --- 输入与导出 ---
        input_bar = QHBoxLayout()
        self.task_input = QLineEdit()
        self.task_input.setPlaceholderText("新增任务...")
        self.task_input.setFixedHeight(35)
        self.task_input.setStyleSheet("background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.1); color: white; padding: 0 10px; border-radius: 8px;")
        self.task_input.returnPressed.connect(self.add_task)
        
        self.export_btn = QPushButton("导出")
        self.export_btn.setFixedSize(60, 35)
        self.export_btn.setStyleSheet("background: rgba(255,255,255,0.12); color: white; border-radius: 8px;")
        self.export_btn.clicked.connect(self.export_tasks)
        
        input_bar.addWidget(self.task_input)
        input_bar.addWidget(self.export_btn)
        main_layout.addLayout(input_bar)

        # 四象限 Grid 部分
        grid = QGridLayout()
        grid.setSpacing(15)
        self.quadrants = {}
        configs = [
            ("不紧急重要", "rgba(125, 107, 66, 0.45)", 0, 0),
            ("紧急重要", "rgba(139, 61, 72, 0.45)", 0, 1),
            ("不紧急不重要", "rgba(42, 111, 118, 0.45)", 1, 0),
            ("紧急不重要", "rgba(109, 61, 109, 0.45)", 1, 1)
        ]
        for title, color, r, c in configs:
            card = QFrame()
            card.setStyleSheet(f"background-color: {color}; border-radius: 15px;")
            vbox = QVBoxLayout(card)
            lbl = QLabel(title)
            lbl.setStyleSheet("color: rgba(255,255,255,0.5); font-size: 12px; font-weight: bold;")
            list_w = QuadrantList()
            list_w.itemClicked.connect(self.on_item_clicked)
            vbox.addWidget(lbl)
            vbox.addWidget(list_w)
            grid.addWidget(card, r, c)
            self.quadrants[title] = list_w
        main_layout.addLayout(grid)

        # 初始时根据当前字体设置应用一次字体
        self.apply_font_settings()

    # ====== 状态保存/恢复 ======
    def save_state(self):
        """
        保存当前界面状态到 JSON 文件：标题、事件名、日期、任务和锁定状态。
        位置 pos 仍然使用 QSettings 单独保存。
        """
        # 先保存位置
        if hasattr(self, "settings"):
            self.settings.setValue("pos", self.pos())

        # 保存当前窗口大小
        self.window_width = self.width()
        self.window_height = self.height()

        # 组织要写入 JSON 的数据
        data = {
            "main_title": self.main_title.text(),
            "event_name": self.event_name_input.text(),
            "target_date": self.target_date.toString("yyyy-MM-dd"),
            "is_locked": self._is_locked,
            "auto_start": self.auto_start_enabled,
            "window_size": {
                "width": self.window_width,
                "height": self.window_height,
            },
            "font_sizes": {
                "title": self.title_font_size,
                "event": self.event_font_size,
                "task": self.task_font_size,
            },
            "tasks": [],
        }

        for q_name, list_widget in self.quadrants.items():
            task_count = list_widget.count()
            print(f"保存象限: {q_name}, 任务数量: {task_count}")
            for i in range(task_count):
                item = list_widget.item(i)
                if isinstance(item, TaskItem):
                    data["tasks"].append(
                        {
                            "content": item.content,
                            "quadrant": q_name,
                            "created_at": item.created_at,
                            "finished_at": item.finished_at,
                            "is_done": item.is_done,
                        }
                    )

        # 写入 JSON 文件
        try:
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            # 即使保存失败，也不要影响程序运行
            pass

    def load_state(self):
        """从 JSON 文件恢复上一次保存的状态（标题、事件、日期、任务、锁定状态）"""
        if not os.path.exists(self.data_file):
            # 没有保存过数据，使用默认值即可
            self.update_countdown_display()
            return

        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            # 文件损坏等情况，忽略错误，保持默认状态
            self.update_countdown_display()
            return

        # 标题、事件名
        main_title = data.get("main_title") or ""
        if main_title:
            self.main_title.setText(main_title)

        event_name = data.get("event_name") or ""
        if event_name:
            self.event_name_input.setText(event_name)

        # 截止日期
        date_str = data.get("target_date") or ""
        if date_str:
            d = QDate.fromString(date_str, "yyyy-MM-dd")
            if d.isValid():
                self.target_date = d
                self.date_btn.setText(f"{self.target_date.toString('yyyy-MM-dd')}")

        # 锁定状态
        is_locked = bool(data.get("is_locked", False))
        self._is_locked = is_locked
        self.lock_btn.setChecked(is_locked)
        self.lock_btn.setText("🔒" if is_locked else "🔓")

        # 开机自启
        self.auto_start_enabled = bool(data.get("auto_start", False))
        # 根据保存的设置应用一次开机自启逻辑
        self.set_auto_start(self.auto_start_enabled)

        # 窗口大小
        size_cfg = data.get("window_size") or {}
        w = int(size_cfg.get("width", self.window_width))
        h = int(size_cfg.get("height", self.window_height))
        if w > 0 and h > 0:
            self.window_width, self.window_height = w, h
            self.resize(self.window_width, self.window_height)

        # 字体大小设置
        font_cfg = data.get("font_sizes") or {}
        self.title_font_size = int(font_cfg.get("title", self.title_font_size))
        self.event_font_size = int(font_cfg.get("event", self.event_font_size))
        self.task_font_size = int(font_cfg.get("task", self.task_font_size))

        # 任务列表
        tasks_data = data.get("tasks") or []
        # 先清空现有的任务
        for list_widget in self.quadrants.values():
            list_widget.clear()

        for t in tasks_data:
            quadrant = t.get("quadrant", "紧急重要")
            content = t.get("content", "")
            created_at = t.get("created_at")
            finished_at = t.get("finished_at", "未完成")
            is_done = t.get("is_done", False)
            if content and quadrant in self.quadrants:
                item = TaskItem(
                    content,
                    created_at=created_at,
                    finished_at=finished_at,
                    is_done=is_done,
                )
                self.quadrants[quadrant].addItem(item)

        # 根据字体设置刷新一次字体样式
        self.apply_font_settings()
        # 更新倒计时显示
        self.update_countdown_display()

    def init_tray(self):
        """初始化托盘图标"""
        # 检查系统是否支持托盘
        if not QSystemTrayIcon.isSystemTrayAvailable():
            print("系统不支持托盘图标")
            return
            
        # 创建托盘图标
        self.tray_icon = QSystemTrayIcon(self)
        # 使用自定义绘制的图标
        self.tray_icon.setIcon(create_tray_icon())
        
        # 创建托盘菜单
        menu = QMenu()
        
        show_action = QAction("显示主界面", self)
        show_action.triggered.connect(self.show_normal)
        
        hide_action = QAction("隐藏主界面", self)
        hide_action.triggered.connect(self.hide)
        
        quit_action = QAction("退出程序", self)
        quit_action.triggered.connect(self.quit_application)
        
        menu.addAction(show_action)
        menu.addAction(hide_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(menu)
        
        # 设置托盘图标点击事件
        self.tray_icon.activated.connect(self.on_tray_activated)
        
        # 显示托盘图标
        self.tray_icon.show()

    def show_normal(self):
        """正常显示窗口"""
        self.show()
        self.raise_()  # 置于顶层
        self.activateWindow()  # 激活窗口

    def on_tray_activated(self, reason):
        """托盘图标激活事件处理"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            if self.isVisible():
                self.hide()
            else:
                self.show_normal()

    def quit_application(self):
        """退出应用程序"""
        self.save_state()
        self.tray_icon.hide()  # 隐藏托盘图标
        QApplication.quit()  # 退出应用

    def closeEvent(self, event):
        """重写关闭事件，隐藏窗口而不是退出"""
        # 关闭前保存当前状态
        self.save_state()
        event.ignore()  # 忽略关闭事件
        self.hide()     # 隐藏窗口
        # 显示通知
        self.tray_icon.showMessage(
            "桌面任务挂件",
            "程序已最小化到系统托盘",
            QSystemTrayIcon.MessageIcon.Information,
            2000
        )

    def toggle_lock(self):
        self._is_locked = self.lock_btn.isChecked()
        self.lock_btn.setText("🔒" if self._is_locked else "🔓")
        # 锁定状态改变时也保存一次
        self.save_state()

    def apply_font_settings(self):
        """根据当前字体大小设置，统一调整界面字体"""
        # 标题
        title_font = self.main_title.font()
        title_font.setPointSize(self.title_font_size)
        self.main_title.setFont(title_font)

        # 事件名
        event_font = self.event_name_input.font()
        event_font.setPointSize(self.event_font_size)
        self.event_name_input.setFont(event_font)

        # 各象限任务项
        for list_widget in getattr(self, "quadrants", {}).values():
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                if isinstance(item, TaskItem):
                    font = item.font()
                    font.setPointSize(self.task_font_size)
                    item.setFont(font)
                    # 重新应用一次外观（确保删除线/颜色仍然正确）
                    item.update_appearance()

    def open_settings_dialog(self):
        """打开字体大小设置对话框"""
        dlg = QDialog(self)
        dlg.setWindowTitle("设置")
        layout = QVBoxLayout(dlg)

        # 标题字体
        title_row = QHBoxLayout()
        title_label = QLabel("标题字体大小：")
        from PyQt6.QtWidgets import QSpinBox

        title_spin = QSpinBox()
        title_spin.setRange(12, 60)
        title_spin.setValue(self.title_font_size)
        title_row.addWidget(title_label)
        title_row.addWidget(title_spin)
        layout.addLayout(title_row)

        # 事件名字体
        event_row = QHBoxLayout()
        event_label = QLabel("事件字体大小：")
        event_spin = QSpinBox()
        event_spin.setRange(10, 40)
        event_spin.setValue(self.event_font_size)
        event_row.addWidget(event_label)
        event_row.addWidget(event_spin)
        layout.addLayout(event_row)

        # 任务文字字体
        task_row = QHBoxLayout()
        task_label = QLabel("任务字体大小：")
        task_spin = QSpinBox()
        task_spin.setRange(8, 30)
        task_spin.setValue(self.task_font_size)
        task_row.addWidget(task_label)
        task_row.addWidget(task_spin)
        layout.addLayout(task_row)

        # 开机自启
        auto_row = QHBoxLayout()
        from PyQt6.QtWidgets import QCheckBox

        auto_chk = QCheckBox("开机自启动")
        auto_chk.setChecked(self.auto_start_enabled)
        auto_row.addWidget(auto_chk)
        layout.addLayout(auto_row)

        # 应用窗口大小设置
        size_row = QHBoxLayout()
        size_label = QLabel("应用大小（宽 x 高）：")
        from PyQt6.QtWidgets import QSpinBox as QSpinBox2

        width_spin = QSpinBox2()
        width_spin.setRange(400, 3000)
        width_spin.setValue(self.window_width)
        height_spin = QSpinBox2()
        height_spin.setRange(300, 2000)
        height_spin.setValue(self.window_height)
        size_row.addWidget(size_label)
        size_row.addWidget(width_spin)
        size_row.addWidget(height_spin)
        layout.addLayout(size_row)

        # 确认/取消按钮
        btn_row = QHBoxLayout()
        ok_btn = QPushButton("确定")
        cancel_btn = QPushButton("取消")
        ok_btn.clicked.connect(dlg.accept)
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addStretch()
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        if dlg.exec():
            # 保存新的字体设置
            self.title_font_size = title_spin.value()
            self.event_font_size = event_spin.value()
            self.task_font_size = task_spin.value()
            # 保存开机自启设置
            self.auto_start_enabled = auto_chk.isChecked()
            self.set_auto_start(self.auto_start_enabled)
            # 保存窗口大小设置
            self.window_width = width_spin.value()
            self.window_height = height_spin.value()
            self.resize(self.window_width, self.window_height)
            # 应用到界面
            self.apply_font_settings()
            # 持久化到 JSON
            self.save_state()

    # --- 拖动逻辑 ---
    def mousePressEvent(self, event):
        if not self._is_locked and event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if not self._is_locked and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def moveEvent(self, event):
        """窗口移动时，实时保存位置"""
        super().moveEvent(event)
        if hasattr(self, "settings"):
            self.settings.setValue("pos", self.pos())

    def set_auto_start(self, enable=True):
        """开机自启逻辑 (Windows 注册表)"""
        if sys.platform == 'win32':
            reg_path = "HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run"
            settings = QSettings(reg_path, QSettings.Format.NativeFormat)
            app_path = os.path.abspath(sys.argv[0])
            if enable:
                settings.setValue("EisenhowerDesktopTask", f'"{app_path}"')
            else:
                settings.remove("EisenhowerDesktopTask")

    def open_calendar_popup(self):
        dialog = CalendarPopup(self, self.target_date)
        # 获取按钮在屏幕上的全局位置
        pos = self.date_btn.mapToGlobal(QPoint(0, self.date_btn.height()))
        dialog.move(pos.x() - 100, pos.y())
        if dialog.exec():
            self.target_date = dialog.selected_date
            self.date_btn.setText(f"截止日期：{self.target_date.toString('yyyy-MM-dd')}")
            self.update_countdown_display()
            self.save_state()

    def update_countdown_display(self):
        today = QDate.currentDate()
        days = today.daysTo(self.target_date)
        self.cd_days_label.setText(f"{max(0, days)} 天")
        self.cd_days_label.setStyleSheet(f"color: {'#ff7675' if days < 0 else 'white'}; font-size: 50px; font-weight: bold;")

    def add_task(self):
        text = self.task_input.text().strip()
        if text:
            item = TaskItem(text)
            self.quadrants["紧急重要"].addItem(item)
            self.task_input.clear()
            # 为新任务应用当前任务字体大小
            font = item.font()
            font.setPointSize(self.task_font_size)
            item.setFont(font)
            item.update_appearance()
            self.save_state()

    def on_item_clicked(self, item):
        """处理项目点击事件"""
        print(f"Item clicked: {item.text()}, Type: {type(item)}")
        
        if isinstance(item, TaskItem):
            item.toggle_status()
            item.listWidget().clearSelection()
            self.save_state()

    def export_tasks(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出任务", "已完成事项.csv", "CSV (*.csv)")
        if not path: return
        data = []
        for q_name, list_widget in self.quadrants.items():
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                if isinstance(item, TaskItem) and item.is_done:
                    data.append([item.content, q_name, item.created_at, item.finished_at])
        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(["内容", "象限", "创建时间", "完成时间"])
            writer.writerows(data)
        QMessageBox.information(self, "完成", "数据已成功导出")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 关闭窗口时不退出程序（在托盘运行）
    app.setFont(QFont("Microsoft YaHei UI", 10))
    
    # 确保只有一个实例运行
    app.setApplicationName("EisenhowerDesktopTask")
    
    window = EisenhowerApp()
    window.show()
    sys.exit(app.exec())