"""
WHITELOTUS V3.2 - Main Window (Full Fixed & Integrated Settings)
"""
import sys
import os
# Tự động thêm thư mục gốc và thư mục ui vào sys.path để Python nhìn thấy mọi thứ
current_dir = os.path.dirname(os.path.abspath(__file__)) # Thư mục chứa file này (ui/)
root_dir = os.path.dirname(current_dir)                  # Thư mục gốc dự án (VeoSuite_V3/)

if current_dir not in sys.path: sys.path.insert(0, current_dir)
if root_dir not in sys.path: sys.path.insert(0, root_dir)

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QStackedWidget, QTextEdit,
    QSplitter, QButtonGroup, QFrame
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont, QIcon

# Bây giờ import sẽ rất mượt
try:
    # Trường hợp 1: Chạy từ main.py (Gốc)
    from ui.styles import DARK_THEME_STYLESHEET
    from ui.widgets.radar_tab import RadarTab
    from ui.widgets.content_tab import ContentTab
    from ui.widgets.media_tab import MediaTab
    from ui.widgets.editor_tab import EditorTab
    from ui.widgets.publisher_tab import PublisherTab
    from ui.widgets.dashboard_tab import DashboardTab
    from ui.admin_tab import AdminTab
except ImportError:
    # Trường hợp 2: Chạy trực tiếp trong folder ui/ hoặc cấu trúc phẳng
    # NB: Mỗi import ở Trường hợp 1 PHẢI có dòng tương ứng ở đây, nếu không
    # khi 1 import bất kỳ ở Trường hợp 1 fail thì fallback chạy nhưng thiếu
    # symbol → NameError ở `_create_content_stack()` thay vì ImportError
    # rõ ràng (ví dụ: thiếu `PublisherTab` từng làm app crash trong
    # bước splash "Preparing User Interface...").
    try:
        from styles import DARK_THEME_STYLESHEET
        from widgets.radar_tab import RadarTab
        from widgets.content_tab import ContentTab
        from widgets.media_tab import MediaTab
        from widgets.editor_tab import EditorTab
        from widgets.publisher_tab import PublisherTab
        from widgets.dashboard_tab import DashboardTab
        from admin_tab import AdminTab
    except ImportError as e:
        # Trường hợp 3: Debug chi tiết lỗi nếu vẫn không tìm thấy
        print(f"❌ LỖI IMPORT NGHIÊM TRỌNG: {e}")
        print(f"📂 Current Dir: {current_dir}")
        print(f"📂 Root Dir: {root_dir}")
        print(f"🐍 Sys Path: {sys.path}")
        raise e

class MainWindow(QMainWindow):
    def __init__(self, db=None, plugin_manager=None):
        super().__init__()
        self.current_department = None
        # PR-6 wiring — both are optional so smoke tests / older callers
        # constructing ``MainWindow()`` with no args keep working.
        self.db = db
        self.plugin_manager = plugin_manager

        self._setup_window()
        self._create_ui()
        self.setStyleSheet(DARK_THEME_STYLESHEET)
        self.switch_to_department(0) # Mặc định vào Radar
        self.log_message("✓ VEO SUITE V3.2 đã khởi động thành công!")
    
    def _setup_window(self):
        self.setWindowTitle("VEO SUITE V3.2 Enterprise")
        self.setMinimumSize(1280, 850)
        self.showMaximized()
    
    def _create_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Phần trên: Container (Sidebar + Content)
        content_container = self._create_content_container()
        splitter.addWidget(content_container)
        
        # Phần dưới: Console
        console_widget = self._create_console_area()
        splitter.addWidget(console_widget)
        
        splitter.setStretchFactor(0, 9) # Content lớn
        splitter.setStretchFactor(1, 1) # Console nhỏ
        main_layout.addWidget(splitter)
    
    def _create_content_container(self):
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Sidebar (Menu Trái)
        self.sidebar = self._create_sidebar()
        layout.addWidget(self.sidebar)
        
        # Content (Nội dung Phải)
        self.content_stack = self._create_content_stack()
        layout.addWidget(self.content_stack, stretch=1)
        
        return container
    
    def _create_sidebar(self):
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(200) # Chiều rộng mặc định
        
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 1. Header Sidebar (Có nút Hamburger)
        header = self._create_sidebar_header()
        layout.addWidget(header)
        
        # 2. Danh sách Menu
        self.button_group = QButtonGroup()
        self.button_group.setExclusive(True)
        
        departments = [
            {'name': 'Tình Báo', 'icon': '🎯', 'tooltip': 'Quét Trend & Spy'},
            {'name': 'Biên Tập', 'icon': '✍️', 'tooltip': 'Sáng tạo Kịch bản'},
            {'name': 'Xưởng Media', 'icon': '🏭', 'tooltip': 'Sản xuất Voice/Ảnh/Nhạc'},
            {'name': 'Dựng Phim', 'icon': '🎬', 'tooltip': 'Render Video & Editor'},
            {'name': 'Phát Hành', 'icon': '📡', 'tooltip': 'Upload đa kênh'},
            {'name': 'Quản Trị', 'icon': '⚙️', 'tooltip': 'Cấu hình hệ thống'},
            {'name': 'Tổng Quan', 'icon': '📊', 'tooltip': 'Dashboard tổng hợp (PR-6)'},
        ]
        
        self.department_buttons = []
        for idx, dept in enumerate(departments):
            btn = QPushButton(f"{dept['icon']}  {dept['name']}")
            btn.setObjectName("sidebar")
            btn.setCheckable(True)
            btn.setToolTip(dept['tooltip'])
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(50)
            btn.clicked.connect(lambda checked, i=idx: self.switch_to_department(i))
            
            self.button_group.addButton(btn, idx)
            self.department_buttons.append(btn)
            layout.addWidget(btn)
        
        layout.addStretch()
        
        # Footer
        self.lbl_version = QLabel("Copyright © 2025 by Whitelotus")
        self.lbl_version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_version.setStyleSheet("color: #666; font-size: 11px; padding: 10px;")
        layout.addWidget(self.lbl_version)
        
        return sidebar
    
    def _create_sidebar_header(self):
        header = QFrame()
        header.setFixedHeight(60)
        header.setStyleSheet("background: #1e1e1e; border-bottom: 1px solid #333;")
        
        layout = QHBoxLayout(header)
        layout.setContentsMargins(10, 0, 10, 0)
        
        # Nút Hamburger (Thu gọn menu)
        self.btn_menu = QPushButton("☰")
        self.btn_menu.setFixedSize(30, 30)
        self.btn_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_menu.setStyleSheet("QPushButton {background: transparent; color: #666; font-size: 18px; border: none;} QPushButton:hover {color: #666;}")
        self.btn_menu.clicked.connect(self.toggle_sidebar)
        
        # Logo Text
        self.lbl_logo = QLabel("WHITELOTUS")
        self.lbl_logo.setStyleSheet("font-weight: bold; font-size: 14px; color: #fff;")
        
        layout.addWidget(self.btn_menu)
        layout.addWidget(self.lbl_logo)
        layout.addStretch()
        
        return header

    # Department labels kept in module-level constants so toggle_sidebar()
    # / switch_to_department() / the dashboard log line all share one source
    # of truth — adding/removing a tab in _create_sidebar() now only requires
    # updating these two tuples.
    _DEPT_NAMES = ('Tình Báo', 'Biên Tập', 'Xưởng Media', 'Dựng Phim', 'Phát Hành', 'Quản Trị', 'Tổng Quan')
    _DEPT_ICONS = ('🎯', '✍️', '🏭', '🎬', '📡', '⚙️', '📊')

    def toggle_sidebar(self):
        """Hàm đóng/mở sidebar"""
        width = self.sidebar.width()
        if width > 100:
            # Đang to -> Thu nhỏ
            self.sidebar.setFixedWidth(60)
            self.lbl_logo.hide()
            self.lbl_version.hide()
            # Ẩn text nút, chỉ hiện icon
            for btn in self.department_buttons:
                text = btn.text()
                icon = text.split("  ")[0] if "  " in text else text
                btn.setText(icon)
        else:
            # Đang nhỏ -> Mở to
            self.sidebar.setFixedWidth(200)
            self.lbl_logo.show()
            self.lbl_version.show()
            # Hiện lại text đầy đủ
            for i, btn in enumerate(self.department_buttons):
                if i < len(self._DEPT_NAMES):
                    btn.setText(f"{self._DEPT_ICONS[i]}  {self._DEPT_NAMES[i]}")

    def _create_content_stack(self):
        stack = QStackedWidget()
        
        # --- TAB 0: RADAR ---
        self.tab_radar = RadarTab(self)
        stack.addWidget(self.tab_radar)
        
        # --- TAB 1: CONTENT ---
        self.content_tab = ContentTab()
        stack.addWidget(self.content_tab)


        # --- TAB 2: MEDIA ---
        self.tab_media = MediaTab()
        stack.addWidget(self.tab_media)

        # --- TAB 3: EDITOR (DỰNG PHIM) ---
        self.editor_tab = EditorTab()
        stack.addWidget(self.editor_tab)

        # --- TAB 4: PHÁT HÀNH ---
        self.publisher_tab = PublisherTab()
        stack.addWidget(self.publisher_tab)
        
        # --- [TÍCH HỢP] TAB 5: QUẢN TRỊ (SETTINGS) ---
        self.tab_admin = AdminTab() 
        stack.addWidget(self.tab_admin)
        # ---------------------------------------------

        # --- [PR-6] TAB 6: DASHBOARD (TỔNG QUAN) ---
        # Constructed last so the plugin_manager / db dependencies (which
        # may have been seeded by main.py) are visible. If neither is
        # supplied (e.g. headless smoke test) the dashboard still renders
        # with zeroed KPIs — see DashboardTab.refresh().
        self.tab_dashboard = DashboardTab(
            db=self.db,
            plugin_manager=self.plugin_manager,
        )
        stack.addWidget(self.tab_dashboard)
        # -------------------------------------------

        # --- [MỚI] ĐẤU NỐI DÂY THẦN KINH LOGGING TOÀN DIỆN ---
        # Nối dây từ TẤT CẢ các Tab về Main để hiện Nhật ký hệ thống
        # [QUAN TRỌNG]: Phải nối sau khi đã tạo hết các Tab ở trên!
        tabs_with_logs = [
            (self.tab_radar, "Tình Báo"),
            (self.content_tab, "Biên Tập"),
            (self.tab_media, "Xưởng Media"),
            (self.editor_tab, "Dựng Phim"),
            (self.publisher_tab, "Phát Hành"),
            (self.tab_admin, "Quản Trị"),
            (self.tab_dashboard, "Tổng Quan"),
        ]
        
        for tab_obj, tab_name in tabs_with_logs:
            if hasattr(tab_obj, 'log_signal'):
                tab_obj.log_signal.connect(self.log_message)
            else:
                print(f"⚠️ Cảnh báo: {tab_name} chưa có log_signal")
        # -------------------------------------------
        
        # Kết nối Radar
        try:
             for i in range(min(3, self.tab_radar.tabs.count())):
                widget = self.tab_radar.tabs.widget(i)
                if hasattr(widget, 'data_sent'):
                    widget.data_sent.connect(self.on_radar_data_received)
        except: pass

        return stack
    
    def _create_placeholder(self, text):
        w = QWidget(); l = QVBoxLayout(w); l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(QLabel(text, styleSheet="font-size: 24px; color: #555; font-weight: bold;"))
        return w
    
    def _create_console_area(self):
        console = QWidget(); console.setObjectName("consoleWidget")
        l = QVBoxLayout(console); l.setContentsMargins(0, 0, 0, 0); l.setSpacing(0)
        l.addWidget(QLabel("📋 NHẬT KÝ HỆ THỐNG", objectName="consoleLabel"))
        self.console_text = QTextEdit(readOnly=True, objectName="consoleTextEdit", maximumHeight=150)
        l.addWidget(self.console_text)
        return console
    
    def switch_to_department(self, index):
        if 0 <= index < len(self.department_buttons):
            self.content_stack.setCurrentIndex(index)
            self.department_buttons[index].setChecked(True)

            # Ghi log khi chuyển tab (dùng chung _DEPT_NAMES với toggle_sidebar)
            if index < len(self._DEPT_NAMES):
                self.log_message(f"📂 Đã chuyển sang bộ phận: {self._DEPT_NAMES[index]}")

            # Xử lý riêng cho Media Tab
            if index == 2: # Media
                if hasattr(self.tab_media, 'refresh_ready_list'):
                    self.tab_media.refresh_ready_list()
            elif index == 3: # Editor (Dựng Phim)
                if hasattr(self.editor_tab, 'refresh_project_list'):
                    self.editor_tab.refresh_project_list()
            elif index == 6: # Tổng Quan (Dashboard) — PR-6
                if hasattr(self.tab_dashboard, 'refresh'):
                    self.tab_dashboard.refresh()
    
    def log_message(self, message):
        # Kiểm tra: Nếu tin nhắn chưa có timestamp (từ Main), thì thêm vào
        # Nếu tin nhắn từ Tab gửi về (đã có [..:..]), thì giữ nguyên
        if not message.startswith("["):
            from datetime import datetime
            ts = datetime.now().strftime("%H:%M:%S")
            message = f"[{ts}] {message}"
        
        self.console_text.append(message)
        
        # [MỚI] Tự động cuộn xuống dòng cuối cùng để luôn thấy tin mới nhất
        scrollbar = self.console_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def on_radar_data_received(self, data):
        self.switch_to_department(1) # Sang Content
        self.content_tab.receive_data_from_radar(data)

    def closeEvent(self, event):
        """Hàm dọn dẹp các tiến trình ngầm (Graceful Shutdown).

        Lifecycle order (each step swallows its own exception so a single
        failure cannot block the rest):
          1. Publisher scheduler stop (legacy).
          2. ``plugin_manager.shutdown()`` — dispatches ``on_app_shutdown``
             to every loaded plugin in reverse load order.
          3. ``telemetry.record('session_ended')`` — best-effort, only
             runs when the sink is enabled (opt-in default stays opt-out).
        """
        import logging
        logger = logging.getLogger("VeoSuite")
        try:
            self.log_message("🔴 Đang dọn dẹp các tiến trình ngầm trước khi thoát...")
        except Exception:
            pass

        # 1. Legacy scheduler (kept from PR-4).
        try:
            if hasattr(self, "publisher_tab") and hasattr(self.publisher_tab, "scheduler"):
                self.publisher_tab.scheduler.stop()
        except Exception:
            logger.exception("Publisher scheduler stop failed (non-fatal)")

        # 2. Plugin shutdown — PR-7. Wire here (not in main.py) because by
        # the time main.py's app.exec() returns Qt has already torn down
        # widgets; closeEvent is the last hook where plugins still see a
        # live host.
        try:
            if self.plugin_manager is not None:
                ok, errs = self.plugin_manager.shutdown({"app": None, "db": self.db})
                logger.info("Plugins shutdown: %d ok, %d errors", ok, len(errs))
        except Exception:
            logger.exception("Plugin shutdown raised (non-fatal)")

        # 3. Telemetry session marker — only writes when sink is enabled.
        try:
            from services import telemetry
            telemetry.record("session_ended")
        except Exception:
            logger.exception("Telemetry session_ended record failed (non-fatal)")

        import time
        time.sleep(0.2)
        event.accept()
