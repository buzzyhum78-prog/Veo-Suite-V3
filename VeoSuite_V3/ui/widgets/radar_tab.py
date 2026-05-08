import sys
import json
import csv
import os
import re
import random
import requests
import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QStyleOptionButton,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QStyle,
    QTabWidget, QLineEdit, QTextEdit, QProgressBar, QMessageBox,
    QFrame, QAbstractItemView, QMenu, QDialog, QFileDialog, 
    QInputDialog, QGroupBox, QApplication, QSpinBox, 
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer, QRect, QUrl, QMetaObject, Q_ARG
from PyQt6.QtGui import QColor, QBrush, QIcon, QFont, QAction, QPixmap, QStandardItemModel, QStandardItem, QCursor, QDesktopServices

# --- IMPORT AI FACTORY ---
try:
    from services.ai_factory import AIFactory
except ImportError:
    # Mockup nếu chạy độc lập
    class AIFactory:
        def __init__(self):
            # Thêm registry giả để không bị crash
            self.registry = {
                "providers": {
                    "youtube": {"api_key": "YOUR_API_KEY_HERE_1, YOUR_API_KEY_HERE_2"}
                }
            }
        def get_api_key(self, pid): return "YOUR_YOUTUBE_KEY"
        def get_gemini_response(self, prompt): return "Keyword 1, Keyword 2, Keyword 3"
        def get_worker_config(self, name): return {"provider": "google", "model": "gemini-pro"}
        def execute_custom_ai(self, provider, prompt, model): return True, "MOCK AI RESPONSE"


from modules.radar.constants import *
from modules.radar.ui_components import *
from modules.radar.ai_worker import RadarAIWorker
from modules.radar.youtube_worker import RealYouTubeWorker
from modules.radar.planner_worker import QuickPlannerWorker
from modules.radar.spy_worker import SpyMetadataWorker

class RadarTab(QWidget):
    # --- [BƯỚC 1] KHAI BÁO SIGNAL TẠI ĐÂY ---
    log_signal = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # [FIX LAG] TẠO BỘ ĐỆM (Debounce Timer)
        # Giúp việc click chọn mượt mà, không bị khựng do phải load prompt liên tục
        self.debounce_timer = QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.setInterval(150) # Độ trễ chỉ 0.15 giây (Mắt thường ko thấy, nhưng CPU được nghỉ)
        
        # Khi hết giờ đệm thì mới chạy hàm cập nhật Prompt nặng nề
        self.debounce_timer.timeout.connect(self._real_update_prompt)
        # Tabs Container
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #3e3e42; }
            QTabBar::tab { background: #2d2d30; color: #999; padding: 10px 20px; font-weight: bold; }
            QTabBar::tab:selected { background: #1e1e1e; color: #fff; border-bottom: 2px solid #007acc; }
        """)
        
        self.tab_niche = QWidget()
        self.tab_hunter = QWidget()
        self.tab_spy = QWidget()
        
        self.tabs.addTab(self.tab_niche, "🔍 1. KHO Ý TƯỞNG (Niche Finder)")
        self.tabs.addTab(self.tab_hunter, "🏹 2. ĐÀO SÂU (Opportunity Hunter)")
        self.tabs.addTab(self.tab_spy, "🔬 3. GIẢI PHẪU (Spy & Clone)")
        
        self.layout.addWidget(self.tabs)
        
        self._setup_tab_niche()
        self.setup_tab_hunter()
        self.setup_tab_spy()
        
        # Load history if exists
        self.load_history()

        # [FIX CRASH] Khởi tạo biến backup rỗng để tránh lỗi AttributeError
        self.backup_data_list = []
        
        # [AUTO LOAD] Tự động đọc lại file lịch sử lần trước (nếu có)
        self.load_keyword_history_from_disk()
        if self.backup_data_list: # Nếu có dữ liệu cũ
            self.on_keywords_generated(self.backup_data_list, 'keywords') # -> Hiển thị lên bảng ngay

        # [THÊM DÒNG NÀY]
        self.load_hunter_history_from_disk() # Của Tab 2

        # --- [CHÈN VÀO ĐÂY] ---
        self.load_staging_table() # <--- Dòng lệnh kích hoạt Load Bảng Nhân Bản
    
    # [HÀM MỚI] TÔ MÀU DÒNG ĐƯỢC CHỌN (Highlight)
    def tint_row_color(self, table, row, is_checked):
        # Màu khi chọn: Xanh rêu đậm (dễ nhìn chữ trắng)
        # Màu khi bỏ chọn: Trong suốt (hoặc màu nền mặc định của bảng)
        color = QColor("#1f4037") if is_checked else QColor("#1e1e1e") # Hoặc transparent
        
        for col in range(table.columnCount()):
            item = table.item(row, col)
            if item:
                item.setBackground(color)

    # --- TAB 1: NICHE FINDER ---
    def _setup_tab_niche(self):
        l = QVBoxLayout(self.tab_niche)
        
        # 1. INPUT GROUP
        grp_in = QGroupBox("BỘ LỌC ĐẦU VÀO & CẤU HÌNH AI")
        grp_in.setStyleSheet("QGroupBox {font-weight: bold; color: #ddd; border: 1px solid #444; margin-top: 10px;}")
        l_in = QVBoxLayout(grp_in)
        
        # Hàng 1: Các ComboBox (Đã dùng class mới dễ bấm)
        grid = QHBoxLayout()
        self.cb_country = CheckableComboBox(); self.cb_country.addItems(COUNTRIES_FULL)
        self.cb_topic = CheckableComboBox(); self.cb_topic.addItems(TOPICS_FULL)
        self.cb_platform = CheckableComboBox(); self.cb_platform.addItems(PLATFORMS)
        # self.cb_time = QComboBox(); self.cb_time.addItems(THOI_GIAN_QUET) # Hoặc QComboBox thường
        
        # [FIX LAG] Thay vì gọi thẳng hàm update, ta gọi qua bộ đệm
        # Khi CEO bấm liên tục, bộ đệm sẽ reset lại, chỉ chạy cái cuối cùng
        self.cb_country.selectionChanged.connect(self.trigger_update_smooth)
        self.cb_topic.selectionChanged.connect(self.trigger_update_smooth)
        self.cb_platform.selectionChanged.connect(self.trigger_update_smooth)

        for lbl, w in [("Quốc gia:", self.cb_country), ("Chủ đề:", self.cb_topic), ("Nền tảng:", self.cb_platform)]:
            v = QVBoxLayout(); v.addWidget(QLabel(lbl)); v.addWidget(w)
            grid.addLayout(v)
        l_in.addLayout(grid)

        # Hàng 2: Prompt Target + Show Công nghệ
        h_prompt = QHBoxLayout()
        
        # [MỚI] Ô PROMPT TARGET
        v_p = QVBoxLayout()
        v_p.addWidget(QLabel("🎯 Prompt Target (Câu lệnh điều khiển AI):"))
        self.txt_prompt_target = QTextEdit()
        self.txt_prompt_target.setFixedHeight(150)
        self.txt_prompt_target.setPlaceholderText("AI sẽ nhận lệnh này để sinh từ khóa...")
        self.txt_prompt_target.setStyleSheet("background: #222; color: #00ff00; font-family: Consolas;")
        v_p.addWidget(self.txt_prompt_target)
        h_prompt.addLayout(v_p, 4)

        # [MỚI] Ô SHOW CÔNG NGHỆ & NÚT BẤM
        v_btn = QVBoxLayout()
        
        # Label hiển thị AI đang dùng (Lấy từ config)
        self.lbl_ai_tech = QLabel("🤖 AI: Đang tải...")
        self.lbl_ai_tech.setStyleSheet("color: #f1c40f; font-weight: bold; font-size: 11px;")
        self.update_ai_tech_label() # Hàm cập nhật label (xem bên dưới)
        
        self.btn_scan_niche = QPushButton("🧠 AI SINH Ý TƯỞNG")
        self.btn_scan_niche.setMinimumHeight(40)
        self.btn_scan_niche.setStyleSheet("background: #0d7377; color: white; font-weight: bold;")
        self.btn_scan_niche.clicked.connect(self.run_niche_generator) # Kết nối hàm chạy
        self.log_signal.emit("🔍 Đã khởi tạo Tab Tình Báo (Radar).")
        
        # [MỚI] Nút Làm Mới (Reset)
        btn_reset = QPushButton("🧹 Làm mới")
        btn_reset.setMinimumHeight(40)
        btn_reset.setStyleSheet("background: #555; color: white; border: 1px solid #777;")
        btn_reset.clicked.connect(self.reset_tab1_inputs) # Kết nối hàm mới

        v_btn.addWidget(self.lbl_ai_tech)
        v_btn.addWidget(self.btn_scan_niche)
        v_btn.addWidget(btn_reset) # Thêm nút vào layout
        h_prompt.addLayout(v_btn, 1)
        
        l_in.addLayout(h_prompt)
        l.addWidget(grp_in)
        
        # 2. TABLE KẾT QUẢ
        headers = [" ", "STT", "📱 Nền Tảng", "🌍 Quốc Gia", "📂 Chủ Đề (Niche)", "🔑 TỪ KHÓA (SEO)", "🇻🇳 Dịch Key", "🔥 TIÊU ĐỀ (Viral)", "📝 Dịch Title"]
        self.tbl_keywords = BaseResultTable(headers) # <-- Dùng đúng tên này
        
        # [MỚI] GẮN HEADER CÓ CHECKBOX
        self.header_checkbox = CheckBoxHeader()
        self.tbl_keywords.setHorizontalHeader(self.header_checkbox)
        self.header_checkbox.checkBoxClicked.connect(self.toggle_all_checkboxes)

        # [QUAN TRỌNG] Bật tính năng tự xuống dòng (Word Wrap)
        self.tbl_keywords.setWordWrap(True)
        self.tbl_keywords.setTextElideMode(Qt.TextElideMode.ElideNone) # Không hiện dấu "..."
        self.tbl_keywords.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents) # Tự dãn chiều cao dòng theo nội dung

        # Tắt thanh cuộn ngang (Ép bảng phải nằm gọn trong view)
        self.tbl_keywords.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # --- CẤU HÌNH ĐỘ RỘNG (CHIẾN THUẬT CHIA BÁNH) ---
        header = self.tbl_keywords.horizontalHeader()
        
        # 1. [QUAN TRỌNG] Tắt tự giãn cột cuối
        header.setStretchLastSection(False) 
        
        # 2. [MẤU CHỐT] Cho phép co nhỏ về 0 (Phá bỏ giới hạn mặc định)
        header.setMinimumSectionSize(0) 
        
        # Reset mode
        for i in range(9): # Reset hết về Interactive trước
             header.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
        
        # --- NHÓM CỘT BÉ (FIXED CỨNG) ---
        # Cột 0: Checkbox (cho co theo text)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        
        # Cột 1: STT (cho co theo text)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        
        # Cột 2: Nền tảng
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.tbl_keywords.setColumnWidth(2, 100)
        
        # Cột 3: Quốc gia
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.tbl_keywords.setColumnWidth(3, 80) # Đủ rộng để hiện "🇻🇳 Việt Nam"
        
        # Cột 4: Chủ đề
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch) # Cho phép kéo tay
        #self.tbl_keywords.setColumnWidth(4, 120)

        # Nhóm 2: Các cột Nội dung (Tự co giãn chia nhau phần còn lại)
        # ResizeMode.Stretch: Tự động co giãn theo tỷ lệ màn hình -> KHÔNG BAO GIỜ CÓ THANH CUỘN
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch) # Từ khóa
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch) # Ý nghĩa Key
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch) # Tiêu đề (Quan trọng)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch) # Ý nghĩa Title
        
        # Tinh chỉnh tỷ lệ (Tiêu đề cần rộng hơn các cột khác một chút)
        # Note: Stretch chia đều, nhưng ta có thể ăn gian bằng cách setWidth khởi tạo (ít tác dụng với Stretch)
        # Cách tốt nhất là để Stretch tự xử lý, nội dung dài sẽ tự xuống dòng.

        l.addWidget(self.tbl_keywords)
        # [MỚI] Dòng này sẽ biến cả cái ô (bao gồm phần trống) thành nút bấm
        self.tbl_keywords.cellClicked.connect(self.on_niche_cell_clicked)

        # 3. [MỚI] THANH CÔNG CỤ (TÌM KIẾM, FULLSCREEN, XÓA)
        h_tools = QHBoxLayout()
        
        btn_search = QPushButton("🔍 Tìm kiếm"); btn_search.clicked.connect(lambda: self.search_table(self.tbl_keywords))
        btn_search.setStyleSheet("background: #333; color: #ccc; border: 1px solid #555; padding: 6px;")
        
        self.btn_fullscreen_idea = QPushButton("⛶ Full Screen"); self.btn_fullscreen_idea.setCheckable(True)
        self.btn_fullscreen_idea.setStyleSheet("background: #333; color: #ccc; border: 1px solid #555; padding: 6px;")
        self.btn_fullscreen_idea.toggled.connect(lambda c: self.toggle_fullscreen(self.tbl_keywords, self.btn_fullscreen_idea))
        
        btn_clear = QPushButton("🗑️ Xóa List"); btn_clear.clicked.connect(lambda: self.tbl_keywords.setRowCount(0))
        btn_clear.setStyleSheet("background: #c0392b; color: white; padding: 6px;")

        btn_restore = QPushButton("♻️ Khôi phục"); btn_restore.clicked.connect(self.restore_table)
        btn_restore.setStyleSheet("background: #27ae60; color: white; padding: 6px;")

        h_tools.addWidget(btn_search)
        h_tools.addWidget(self.btn_fullscreen_idea)
        h_tools.addWidget(btn_clear)
        h_tools.addWidget(btn_restore)
        h_tools.addStretch()
        l.addLayout(h_tools)

        # 4. ACTION NEXT STEP
        self.stage_idea = self._create_staging_area("DANH SÁCH CHUYỂN QUA BƯỚC 2")
        l.addWidget(self.stage_idea['group'])
        
        # --- [THÊM DÒNG NÀY VÀO ĐÂY] ---
        # Ánh xạ cái ô Text bên trong group ra biến self.lbl_step2_status để hàm update gọi được
        self.lbl_step2_status = self.stage_idea['text']

        self.btn_next_step = QPushButton("🚀 CHUYỂN SANG BƯỚC 2 (ĐÀO SÂU)") # Gán vào self
        self.btn_next_step.setStyleSheet("background: #d35400; color: white; font-weight: bold; padding: 12px;")
        self.btn_next_step.clicked.connect(self.transfer_to_deep)
        l.addWidget(self.btn_next_step)

        self.setup_context_menu()

        

     
    
    # --- HELPER: TẠO KHU VỰC STAGING (Ô CHUẨN BỊ) ---
    def _create_staging_area(self, title):
        grp = QGroupBox(title)
        # Style cho khung: Viền nét đứt, nền tối
        grp.setStyleSheet("QGroupBox {font-weight: bold; border: 1px dashed #777; margin-top: 10px; background: #2b2b2b; color: #f1c40f;}")
        
        v = QVBoxLayout(grp)
        
        # Ô hiển thị text tóm tắt
        txt = QTextEdit()
        txt.setReadOnly(True) # Chỉ đọc, ko cho sửa
        txt.setFixedHeight(200) # Chiều cao cố định
        txt.setPlaceholderText("Chưa chọn mục nào...")
        txt.setStyleSheet("background: transparent; border: none; color: #aaa; font-size: 12px;")
        
        v.addWidget(txt)
        
        # Trả về cả Group (để add vào layout) và Text (để code update nội dung)
        return {'group': grp, 'text': txt}

    # --- TAB 2: OPPORTUNITY HUNTER (ĐÃ FIX LỖI LAYOUT) ---
    def setup_tab_hunter(self):
        # Đảm bảo layout cũ bị xóa (nếu có) để tránh lỗi "already has a parent"
        if self.tab_hunter.layout():
            QWidget().setLayout(self.tab_hunter.layout()) # Trick để xóa layout cũ

        layout = QVBoxLayout(self.tab_hunter)
        
        # 1. INPUT AREA
        input_layout = QHBoxLayout() # Đây là LAYOUT

        self.txt_input_keywords = QLineEdit()
        self.txt_input_keywords.setPlaceholderText("Danh sách từ khóa (cách nhau dấu chấm phẩy)...")
        self.txt_input_keywords.setStyleSheet("background: #252526; color: #fff; padding: 8px; border: 1px solid #444;")

        self.cb_time_filter = QComboBox()
        self.cb_time_filter.addItems([
            "📅 Mọi lúc (All Time)",
            "🔥 7 ngày qua (Hot Trend)", 
            "📅 30 ngày qua (Tháng này)", 
            "📅 90 ngày qua (Quý này)", 
            "📅 1 năm qua (Năm nay)"
        ])
        self.cb_time_filter.setStyleSheet("background: #333; color: white; padding: 8px;")
        self.cb_time_filter.setFixedWidth(180)

        # [MỚI] CHỈNH MẶC ĐỊNH LÀ 7 NGÀY (Index 1)
        self.cb_time_filter.setCurrentIndex(1)

        self.btn_scan_hunter = QPushButton("🎯 QUÉT & TÍNH V/S")
        self.btn_scan_hunter.setStyleSheet("background: #d83b01; color: white; font-weight: bold; padding: 8px;")
        self.btn_scan_hunter.clicked.connect(self.run_opportunity_hunter)
        
        # Nút Hủy
        self.btn_stop_scan = QPushButton("🛑 HỦY")
        self.btn_stop_scan.setStyleSheet("background: #555; color: white; font-weight: bold; padding: 8px;")
        self.btn_stop_scan.setEnabled(False)
        self.btn_stop_scan.clicked.connect(self.stop_hunter_scan)

        # Thêm các WIDGET vào input_layout
        input_layout.addWidget(self.txt_input_keywords, 4)
        input_layout.addWidget(self.cb_time_filter, 0)
        input_layout.addWidget(self.btn_scan_hunter, 1)
        input_layout.addWidget(self.btn_stop_scan, 0)
        
        # [QUAN TRỌNG] Thêm input_layout vào layout chính bằng addLayout (KHÔNG PHẢI addWidget)
        layout.addLayout(input_layout) 
        
        # 2. PROGRESS AREA
        v_progress = QVBoxLayout() # Đây là LAYOUT
        self.lbl_scan_status = QLabel("Sẵn sàng.")
        self.lbl_scan_status.setStyleSheet("color: #aaa; font-style: italic; margin-left: 5px;")
        
        self.pbar = QProgressBar()
        self.pbar.setStyleSheet("QProgressBar {height: 5px; background: #333;} QProgressBar::chunk {background: #d83b01;}")
        
        v_progress.addWidget(self.lbl_scan_status)
        v_progress.addWidget(self.pbar)
        
        # [QUAN TRỌNG] Thêm v_progress vào layout chính bằng addLayout
        layout.addLayout(v_progress)
        
        # 3. TOOLBAR AREA
        toolbar = QHBoxLayout() # Đây là LAYOUT
        btn_search = QPushButton("🔍 Tìm kiếm")
        btn_search.setStyleSheet("background: #333; color: #ccc; border: 1px solid #555; padding: 6px;")
        btn_search.clicked.connect(lambda: self.search_table(self.tbl_videos))
        
        self.btn_fullscreen_hunter = QPushButton("⛶ Full Screen"); self.btn_fullscreen_hunter.setCheckable(True)
        self.btn_fullscreen_hunter.setStyleSheet("background: #333; color: #ccc; border: 1px solid #555; padding: 6px;")
        self.btn_fullscreen_hunter.toggled.connect(lambda c: self.toggle_fullscreen(self.tbl_videos, self.btn_fullscreen_hunter))

        btn_export = QPushButton("💾 Xuất Excel")
        btn_export.setStyleSheet("background: #2980b9; color: white; padding: 6px;")
        btn_export.clicked.connect(lambda: self.export_table(self.tbl_videos))
        
        btn_clear = QPushButton("🗑️ Xóa List")
        btn_clear.setStyleSheet("background: #c0392b; color: white; padding: 6px;")
        btn_clear.clicked.connect(self.clear_hunter_safe)

        btn_restore = QPushButton("♻️ Khôi phục")
        btn_restore.setStyleSheet("background: #27ae60; color: white; padding: 6px;")
        btn_restore.clicked.connect(self.load_hunter_history_from_disk)

        toolbar.addWidget(btn_search)
        toolbar.addWidget(self.btn_fullscreen_hunter)
        toolbar.addWidget(btn_export)
        toolbar.addWidget(btn_clear)
        toolbar.addWidget(btn_restore)
        toolbar.addStretch() 

        # [QUAN TRỌNG] Thêm toolbar vào layout chính bằng addLayout
        layout.addLayout(toolbar)

        # 4. TABLE STRUCTURE
        cols = [" ", "STT", "🖼️ Thumb", "🎬 Video Title", "📂 Chủ đề", "🌍 Quốc Gia", "⏳ Thời lượng", "📅 Ngày Đăng", "🚀 Tốc độ/Ngày", 
                "👀 Views", "👥 Subs", "⚡ V/S", "🔥 Outlier", "💰 Doanh Thu", "📊 Đánh Giá", 
                "🔑 Keyword", "🇻🇳 Nghĩa", "🔗 Link", "▶ Xem"]
        self.tbl_videos = BaseResultTable(cols)
        
        # [MỚI] Bật tính năng Click để sắp xếp
        self.tbl_videos.setSortingEnabled(True)

        self.tbl_videos.verticalHeader().setDefaultSectionSize(90)
        self.tbl_videos.setWordWrap(True)

        # Header Checkbox
        self.header_chk_hunter = CheckBoxHeader()
        self.tbl_videos.setHorizontalHeader(self.header_chk_hunter)
        self.header_chk_hunter.checkBoxClicked.connect(self.toggle_all_hunter)

        # [FIX] CẤU HÌNH CỘT
        h = self.tbl_videos.horizontalHeader()
              
        # Tắt tính năng tự giãn cột cuối (để cột Link không bị kéo dài thượt)
        h.setStretchLastSection(False)
        
        # 1. Ép cứng các cột nhỏ (FIXED) -> Không cho phép giãn -> Bé lại ngay
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        # h.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed); self.tbl_videos.setColumnWidth(0, 30) # Checkbox
        
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        #h.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed); self.tbl_videos.setColumnWidth(1, 40) # STT
        
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed); self.tbl_videos.setColumnWidth(2, 200) # Thumb (Rộng ra để ko che chữ)

        # 2. Ép cột Tiêu đề (STRETCH) -> Tự phình to lấp đầy màn hình
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        # h.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive); self.tbl_videos.setColumnWidth(3, 400)

        # Cột Mới
        self.tbl_videos.setColumnWidth(4, 100) # Chủ đề
        self.tbl_videos.setColumnWidth(5, 60)  # QG
        self.tbl_videos.setColumnWidth(6, 70)  # Thời lượng

        # 3. Các cột còn lại (INTERACTIVE) -> Cho phép kéo thả
        for col in range(7, 18):
            h.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)

        # Các cột còn lại
        self.tbl_videos.setColumnWidth(7, 100) # Ngày
        h.setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)
        #self.tbl_videos.setColumnWidth(5, 90)  # Tốc độ
        self.tbl_videos.setColumnWidth(9, 90)  # Views
        self.tbl_videos.setColumnWidth(10, 80)  # Subs
        self.tbl_videos.setColumnWidth(11, 60)  # V/S
        self.tbl_videos.setColumnWidth(12, 70)  # Outlier (Mới)
        self.tbl_videos.setColumnWidth(13, 100) # Doanh thu
        self.tbl_videos.setColumnWidth(14, 110)# Rate
        h.setSectionResizeMode(15, QHeaderView.ResizeMode.Stretch)
        #self.tbl_videos.setColumnWidth(14, 120)# Key
        h.setSectionResizeMode(16, QHeaderView.ResizeMode.Stretch)
        #self.tbl_videos.setColumnWidth(15, 120)# Nghĩa
        self.tbl_videos.setColumnWidth(17, 0)  # Link
        self.tbl_videos.setColumnWidth(18, 60) # Xem
        
        # Ẩn cột Link (Cột 17)
        self.tbl_videos.setColumnHidden(17, True)

        # [QUAN TRỌNG] Bảng là Widget nên dùng addWidget
        layout.addWidget(self.tbl_videos)

        # 5. ACTION BUTTON
        btn_spy = QPushButton("🕵️ CHUYỂN SANG BƯỚC 3 (GIẢI PHẪU VIDEO)")
        btn_spy.setStyleSheet("background: #6a1b9a; color: white; font-weight: bold; padding: 10px;")
        btn_spy.clicked.connect(self.transfer_to_spy)
        
        # [QUAN TRỌNG] Nút là Widget nên dùng addWidget
        layout.addWidget(btn_spy)
        
        self.tbl_videos.cellClicked.connect(self.on_hunter_cell_clicked)
        # Sự kiện double click mở link
        self.tbl_videos.cellDoubleClicked.connect(self.open_video_on_double_click)

    # --- TAB 3: SPY & CLONE (GIAO DIỆN NHÀ MÁY) ---
    def setup_tab_spy(self):
        layout = QVBoxLayout(self.tab_spy)
        # Giảm lề cho gọn
        layout.setContentsMargins(5, 5, 5, 5) 
        layout.setSpacing(5)

        # 1. INPUT AREA
        h_layout = QHBoxLayout()
        self.txt_video_url = QLineEdit()
        self.txt_video_url.setPlaceholderText("Link video GEM sẽ hiện ở đây (sang Đào sâu mà lấy)...")
        self.txt_video_url.setStyleSheet("background: #252526; color: #fff; padding: 10px; border: 1px solid #444;")
        
        btn_analyze = QPushButton("🧬 1. GIẢI MÃ DNA & DỊCH THUẬT")
        btn_analyze.setMinimumHeight(35)
        btn_analyze.setStyleSheet("background: #c2185b; color: white; font-weight: bold; font-size: 12px;")
        btn_analyze.clicked.connect(self.run_spy_analysis)
        
        # [MỚI] THÊM CỤM NÚT QUẢN LÝ
        btn_restore_spy = QPushButton("♻️ Khôi phục")
        btn_restore_spy.setToolTip("Khôi phục phiên làm việc trước")
        btn_restore_spy.setFixedSize(130, 35)
        btn_restore_spy.setStyleSheet("background: #27ae60; color: white; border-radius: 4px;")
        btn_restore_spy.clicked.connect(self.load_spy_history_from_disk) # Gọi hàm load

        btn_clear_spy = QPushButton("🗑️ Xóa trống")
        btn_clear_spy.setToolTip("Xóa trắng màn hình")
        btn_clear_spy.setFixedSize(130, 35)
        btn_clear_spy.setStyleSheet("background: #c0392b; color: white; border-radius: 4px;")
        btn_clear_spy.clicked.connect(self.clear_spy_tab) # Hàm mới bên dưới

        h_layout.addWidget(self.txt_video_url, 4)
        h_layout.addWidget(btn_analyze, 1)
        h_layout.addWidget(btn_restore_spy) # Thêm nút
        h_layout.addWidget(btn_clear_spy)   # Thêm nút
        layout.addLayout(h_layout)

        # 2. ANALYSIS REPORT AREA (CHIA ĐÔI MÀN HÌNH)
        # Sử dụng QSplitter để có thể kéo qua kéo lại kích thước 2 ô
        from PyQt6.QtWidgets import QSplitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        # Style chung cho TextEdit gọn
        txt_style = "border: none; font-family: Consolas; font-size: 11px; padding: 5px;"

        # Ô Trái: DNA Gốc (English - Dùng để chạy Tool)
        grp_en = QGroupBox("🧬 DNA GỐC (SKELETON - INPUT)")
        grp_en.setStyleSheet("color: #00ffea; font-weight: bold; margin-top: 8px;") 
        l_en = QVBoxLayout(grp_en); l_en.setContentsMargins(0,10,0,0), l_en.setSpacing(0)
        self.txt_report_en = QTextEdit()
        self.txt_report_en.setPlaceholderText("Mã gene của video sẽ hiện ở đây (Tiếng Anh)...")
        self.txt_report_en.setStyleSheet("font-family: Consolas; color: #aaffaa; background: #111; border: none;")
        l_en.addWidget(self.txt_report_en)
        
        # Ô Phải: Bản Dịch (Vietnamese - Dùng để CEO đọc)
        grp_vi = QGroupBox("🇻🇳 BẢN DỊCH CHIẾN THUẬT (ĐỂ HIỂU)")
        grp_vi.setStyleSheet("color: #ff5252; font-weight: bold; margin-top: 8px;")
        l_vi = QVBoxLayout(grp_vi); l_vi.setContentsMargins(0,10,0,0); l_vi.setSpacing(0)
        self.txt_report_vi = QTextEdit()
        self.txt_report_vi.setPlaceholderText("Giải thích tiếng Việt sẽ hiện ở đây...")
        self.txt_report_vi.setStyleSheet("font-family: Segoe UI; color: #fff; background: #2b2b2b; border: none;")
        l_vi.addWidget(self.txt_report_vi)

        # [MỚI] Cột 3: JSON Thô (Metadata)
        grp_json = QGroupBox("⚙️ JSON THÔ (METADATA)")
        grp_json.setStyleSheet("color: #ff5252; font-weight: bold;")
        l_json = QVBoxLayout(grp_json); l_json.setContentsMargins(0,10,0,0)
        self.txt_report_json = QTextEdit()
        self.txt_report_json.setPlaceholderText("Waiting for JSON Data...")
        self.txt_report_json.setStyleSheet("font-family: Consolas; color: #ff9999; background: #1a1a1a; border: none;")
        l_json.addWidget(self.txt_report_json)


        splitter.addWidget(grp_en)
        splitter.addWidget(grp_vi)
        splitter.addWidget(grp_json)

        splitter.setSizes([500, 500, 500]) # Chia đều 3 cột
        splitter.setFixedHeight(250) # Chiều cao khu vực báo cáo
        
        layout.addWidget(splitter)

        # --- [GIAO DIỆN MỚI] 🕵️ HỒ SƠ MỤC TIÊU (TARGET PROFILE) ---
        self.grp_target_profile = QGroupBox("🕵️ HỒ SƠ MỤC TIÊU (TARGET PROFILE)")
        # Style kiểu "Thẻ bài" (Card), bo góc, nền tối sang trọng
        self.grp_target_profile.setStyleSheet("""
            QGroupBox {
                font-weight: bold; color: #00e6e6; 
                border: 1px solid #444; border-radius: 8px;
                margin-top: 10px; background-color: #151515;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
        """)
        
        # Chia layout làm 2 phần: Trái (Ảnh) - Phải (Thông tin)
        l_target = QHBoxLayout(self.grp_target_profile)
        l_target.setContentsMargins(15, 20, 15, 15)
        l_target.setSpacing(20)
        
        # --- CỘT TRÁI: ẢNH THUMBNAIL (HERO IMAGE) ---
        # Làm khung ảnh to, bo góc
        self.lbl_spy_thumb = QLabel()
        self.lbl_spy_thumb.setFixedSize(240, 135) # Chuẩn 16:9 to rõ
        self.lbl_spy_thumb.setStyleSheet("""
            QLabel {
                background-color: #000; 
                border: 2px solid #333; border-radius: 6px;
            }
        """)
        self.lbl_spy_thumb.setScaledContents(True)
        self.lbl_spy_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_spy_thumb.setText("Waiting for Thumbnail...") 
        l_target.addWidget(self.lbl_spy_thumb)
        
        # --- CỘT PHẢI: THÔNG TIN CHI TIẾT ---
        v_info = QVBoxLayout()
        v_info.setSpacing(5)
        
        # 1. Tên Video (Tiêu đề to)
        self.lbl_spy_video_title = QLabel("--- Video Title ---")
        self.lbl_spy_video_title.setWordWrap(True)
        self.lbl_spy_video_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #fff;")
        v_info.addWidget(self.lbl_spy_video_title)
        
        # 2. Tên Kênh & Chỉ số (Hàng ngang)
        h_stats = QHBoxLayout()
        self.lbl_spy_channel_name = QLabel("👤 Channel Name")
        self.lbl_spy_channel_name.setStyleSheet("font-size: 13px; font-weight: bold; color: #f1c40f;")
        
        self.lbl_spy_stats = QLabel("👁️ --- views • ❤️ --- likes")
        self.lbl_spy_stats.setStyleSheet("color: #aaa; font-size: 12px;")

        # [MỚI] Nút Xem Video Gốc
        self.btn_watch_original = QPushButton("▶ Xem Video Gốc")
        self.btn_watch_original.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_watch_original.setStyleSheet("""
            QPushButton { background: #c0392b; color: white; border-radius: 4px; padding: 4px 10px; font-weight: bold; font-size: 11px; }
            QPushButton:hover { background: #e74c3c; }
        """)
        self.btn_watch_original.clicked.connect(self.open_current_spy_video)
        self.btn_watch_original.hide() # Ẩn đi khi chưa có link
        
        h_stats.addWidget(self.lbl_spy_channel_name)
        h_stats.addWidget(QLabel(" | "))
        h_stats.addWidget(self.lbl_spy_stats)
        h_stats.addWidget(self.btn_watch_original)
        h_stats.addStretch()
        v_info.addLayout(h_stats)
        
        # 3. Tab Mô tả (Gốc / Dịch Việt) - GIẢI PHÁP ĐỌC MÔ TẢ
        self.tab_desc = QTabWidget()
        self.tab_desc.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #333; background: #222; border-radius: 4px; }
            QTabBar::tab { background: #333; color: #888; padding: 5px 10px; }
            QTabBar::tab:selected { background: #444; color: #fff; font-weight: bold; }
        """)
        self.tab_desc.setFixedHeight(100) # Cao lên để dễ đọc
        
        # Tab Tiếng Gốc
        self.txt_spy_desc_raw = QTextEdit()
        self.txt_spy_desc_raw.setReadOnly(True)
        self.txt_spy_desc_raw.setStyleSheet("border:none; background:transparent; color:#ccc; font-size:11px;")
        self.tab_desc.addTab(self.txt_spy_desc_raw, "📝 Mô tả Gốc")
        
        # Tab Tiếng Việt (Mới)
        self.txt_spy_desc_vi = QTextEdit()
        self.txt_spy_desc_vi.setReadOnly(True)
        self.txt_spy_desc_vi.setStyleSheet("border:none; background:transparent; color:#aaffaa; font-size:11px;")
        self.txt_spy_desc_vi.setPlaceholderText("Đang dịch mô tả sang tiếng Việt...")
        self.tab_desc.addTab(self.txt_spy_desc_vi, "🇻🇳 Dịch Việt (Tham khảo)")
        
        v_info.addWidget(self.tab_desc)
        
        l_target.addLayout(v_info)
        layout.addWidget(self.grp_target_profile) # Thêm vào layout chính

        # 3. STAGING AREA (KHU VỰC ĐÓNG GÓI - COMPACT VERSION)
        grp_clone = QGroupBox("🏭 DÂY CHUYỀN ĐÓNG GÓI (STAGING)")
        grp_clone.setStyleSheet("QGroupBox {font-weight: bold; color: #00ffea; border: 1px dashed #444; margin-top: 10px;}")
        
        # [QUAN TRỌNG] Set spacing cực nhỏ (2px) để các thành phần dính sát vào nhau
        l_clone = QVBoxLayout(grp_clone)
        l_clone.setSpacing(5) 
        l_clone.setContentsMargins(5, 15, 5, 5)

        # --- HÀNG 1: CÁC Ô CHỌN (OPTIONS) ---
        h_options = QHBoxLayout()
        h_options.setSpacing(10) # Khoảng cách giữa các cột ngang

        # Cột 1: Chủ đề (Chiếm 40% diện tích)
        v1 = QVBoxLayout(); v1.setSpacing(2)
        
        # Label + Nút Reset nằm chung 1 hàng để tiết kiệm chiều cao
        h_lbl_1 = QHBoxLayout(); h_lbl_1.setContentsMargins(0,0,0,0)
        h_lbl_1.addWidget(QLabel("🎯 Chủ Đề Gốc (Niche):"))
        
        btn_refresh = QPushButton()
        btn_refresh.setToolTip("Khôi phục lựa chọn gốc")
        btn_refresh.setFixedSize(22, 22)
        # Lấy icon "Refresh" chuẩn của hệ thống
        btn_refresh.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        btn_refresh.setStyleSheet("background: #444; color: white; border: 1px solid #555; border-radius: 3px;")
        btn_refresh.clicked.connect(self.restore_original_choices)
        h_lbl_1.addWidget(btn_refresh)
        h_lbl_1.addStretch() # Đẩy sang trái
        
        v1.addLayout(h_lbl_1)
        
        self.cb_batch_niche = CheckableComboBox()
        self.cb_batch_niche.addItems(BATCH_NICHE_IDEAS)
        self.cb_batch_niche.setFixedHeight(30) # Chiều cao chuẩn
        v1.addWidget(self.cb_batch_niche)
        
        h_options.addLayout(v1, 4) # Stretch Factor = 4

        # Cột 2: Quốc gia (Chiếm 40% diện tích)
        v2 = QVBoxLayout(); v2.setSpacing(2)
        v2.addWidget(QLabel("🌍 Quốc gia (Đã chọn):"))
        
        self.cb_batch_lang = CheckableComboBox()
        self.cb_batch_lang.addItems(BATCH_LANGUAGES)
        self.cb_batch_lang.setFixedHeight(30)
        v2.addWidget(self.cb_batch_lang)
        
        h_options.addLayout(v2, 4) # Stretch Factor = 4

        # Cột 3: Số lượng (Chiếm 20% diện tích - Bé thôi)
        v3 = QVBoxLayout(); v3.setSpacing(2)
        v3.addWidget(QLabel("🔢 Biến thể:"))
        
        self.spin_quantity = QSpinBox()
        self.spin_quantity.setRange(1, 20); self.spin_quantity.setValue(3)
        self.spin_quantity.setStyleSheet("background: #333; color: white;")
        self.spin_quantity.setFixedHeight(30)
        v3.addWidget(self.spin_quantity)
        
        h_options.addLayout(v3, 2) # Stretch Factor = 2

        l_clone.addLayout(h_options)

        # --- HÀNG 2: NÚT LÊN KẾ HOẠCH ---
        # [SỬA] Đổi tên biến thành self.btn_plan và KHÓA ngay từ đầu
        self.btn_plan = QPushButton("✨ BƯỚC 1: LÊN KẾ HOẠCH NHÂN BẢN & ĐẶT TÊN KÊNH (AI AUTO)")
        self.btn_plan.setFixedHeight(35)
        # Style xám (Disabled)
        self.btn_plan.setStyleSheet("background: #444; color: #888; font-weight: bold; border: 1px solid #555;")
        self.btn_plan.setEnabled(False) # <--- KHÓA CỨNG
        self.btn_plan.setToolTip("⚠️ Hãy chạy 'GIẢI MÃ DNA' ở trên trước để có dữ liệu!")
        self.btn_plan.clicked.connect(self.run_channel_planning)
        l_clone.addWidget(self.btn_plan)

        # --- HÀNG 3: BẢNG (TABLE) ---
        # Cấu trúc cột: [0:Check, 1:STT, 2:QG, 3:Tên, 4:Handle, 5:Style, 6:Trạng thái]
        self.tbl_staging = QTableWidget()
        self.tbl_staging.setColumnCount(10)
        self.tbl_staging.setHorizontalHeaderLabels([" ", "STT", "🌍 Quốc Gia", "🏷️ Niche Gốc", "🔑 Key Vua", "📺 Tên Kênh (AI)", "🔗 Handle", "🎬 Số Lượng", "🎨 Style", "Trạng thái"])

        # [NÂNG CẤP] Header Checkbox (Select All)
        self.header_chk_staging = CheckBoxHeader()
        self.tbl_staging.setHorizontalHeader(self.header_chk_staging)
        self.header_chk_staging.checkBoxClicked.connect(self.toggle_all_staging) # Hàm mới bên dưới

        # [CẤU HÌNH CỘT CHI TIẾT]
        header = self.tbl_staging.horizontalHeader()
        
        # Reset chế độ cũ
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive) # Cho phép kéo thả tay
        
        # 0. Cột Checkbox (Cố định nhỏ)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents) #; self.tbl_staging.setColumnWidth(0, 30) # Check

        # 1. Cột Checkbox (Cố định nhỏ)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents) #; self.tbl_staging.setColumnWidth(1, 40) # STT
        
        # 2. Cột Quốc gia (Vừa đủ chữ)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        # 3. Niche gốc
        self.tbl_staging.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        # 4. Cột Key Vua: Rộng vừa phải
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

        # 5. Cột Tên Kênh (QUAN TRỌNG NHẤT -> Giãn hết cỡ)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        
        # 6. Cột Handle (Vừa phải)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)

        # 7. SL Video
        self.tbl_staging.setColumnWidth(7, 50)  # SL Video [MỚI]

        # 8. Cột Style (Vừa phải)
        # self.tbl_staging.setColumnWidth(6, 300)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)

        # 9. Cột Trạng thái (Vừa đủ chữ)
        header.setSectionResizeMode(9, QHeaderView.ResizeMode.ResizeToContents)
        
        self.tbl_staging.verticalHeader().setVisible(False) # Ẩn cột số thứ tự dọc cho đẹp
        self.tbl_staging.setStyleSheet("background: #1e1e1e; border: 1px solid #333;")
        # [QUAN TRỌNG] Set chiều cao tối thiểu để nó không bị bóp méo
        self.tbl_staging.setMinimumHeight(150) 

        # [MỚI] Bấm vào dòng là tự tích chọn
        self.tbl_staging.cellClicked.connect(self.on_staging_cell_clicked)
        l_clone.addWidget(self.tbl_staging)

        # --- HÀNG 4: NÚT CHUYỂN (FINAL) ---
        btn_transfer_final = QPushButton("🚀 BƯỚC 2: DUYỆT & CHUYỂN SANG NHÀ MÁY (TAB 4)")
        btn_transfer_final.setFixedHeight(45) # To hơn chút để nhấn mạnh
        btn_transfer_final.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_transfer_final.setStyleSheet("""
            QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #27ae60, stop:1 #2ecc71); color: white; font-weight: bold; font-size: 13px; border-radius: 4px; }
            QPushButton:hover { background: #2ecc71; }
        """)
        btn_transfer_final.clicked.connect(self.transfer_staging_to_factory)
        l_clone.addWidget(btn_transfer_final)

        layout.addWidget(grp_clone)
        # [AUTO LOAD] Tự động tải lại lịch sử Spy
        self.load_spy_history_from_disk()

    # =========================================================================
    # LOGIC: NICHE FINDER (TAB 1)
    # =========================================================================
    def run_niche_generator(self):
        # Gather inputs
        countries = self.cb_country.get_checked_items()
        topics = self.cb_topic.get_checked_items()
        
        if not countries or not topics:
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng chọn ít nhất 1 Quốc gia và 1 Chủ đề!")
            return
            
        # [MỚI] Lấy Prompt từ ô nhập liệu
        prompt_target = self.txt_prompt_target.toPlainText()

        # Combine inputs for AI prompt
        data = {
            "country": ", ".join(countries),
            "topic": ", ".join(topics),
            "platform": self.cb_platform.currentText(),
            "prompt_target": prompt_target # <--- QUAN TRỌNG: Gửi kèm cái này
        }

        # [LOG] Báo cáo bắt đầu
        self.handle_log_message(f"🚀 [Tab 1] Đang tìm ý tưởng Ngách cho: {data['topic']} tại {data['country']}...")

        # [HIỆU ỨNG] KHÓA NÚT BẤM
        # Chuyển nút sang trạng thái "Đang chạy" để user không bấm liên tục
        if hasattr(self, 'btn_scan_niche'):
            self.btn_scan_niche.setEnabled(False) # Khóa nút
            self.btn_scan_niche.setText("⏳ AI ĐANG TẠO Ý TƯỞNG...") # Đổi chữ
            self.btn_scan_niche.setStyleSheet("background: #555; color: #aaa;") # Đổi màu xám
        
        self.tbl_keywords.setRowCount(0) # Clear table
        
        # Call AI Worker
        self.ai_worker = RadarAIWorker('keywords', data)
        self.ai_worker.finished.connect(self.on_keywords_generated)

        # [QUAN TRỌNG] Khi chạy xong hoặc Lỗi -> Gọi hàm mở khóa nút
        self.ai_worker.finished.connect(self.reset_scan_button) 
        self.ai_worker.error.connect(self.reset_scan_button)

        self.ai_worker.error.connect(lambda e: QMessageBox.critical(self, "Lỗi AI", e)) # Thêm báo lỗi
        # Kết nối signal của Worker vào hàm xử lý chúng ta vừa tạo ở Bước 2
        self.ai_worker.log_signal.connect(self.handle_log_message)
        self.ai_worker.start()
    
    # --- HÀM MỞ KHÓA NÚT (Thêm ngay bên dưới hàm trên) ---
    def reset_scan_button(self):
        """Trả lại trạng thái ban đầu cho nút Quét"""
        if hasattr(self, 'btn_scan_niche'):
            self.btn_scan_niche.setEnabled(True) # Mở khóa
            self.btn_scan_niche.setText("✨ GỢI Ý TỪ KHÓA NGÁCH") # Trả lại chữ cũ
            self.btn_scan_niche.setStyleSheet("background: #0d7377; color: white; font-weight: bold;") # Trả lại màu xanh

    def on_keywords_generated(self, data_list, type):
        # Lưu backup trước khi hiển thị
        self.backup_data_list = data_list

        # 2. [MỚI] Lưu ngay xuống ổ cứng
        self.save_keyword_history_to_disk(data_list)

        self.tbl_keywords.setRowCount(len(data_list))
        # --- [SỬA ĐOẠN NÀY] ---
        
        # 1. Lấy chủ đề (Giữ nguyên)
        current_topic = self.cb_topic.get_checked_items()[0] if self.cb_topic.get_checked_items() else "General"
        
        # 2. Lấy nền tảng (FIX LỖI HIỂN THỊ "---Chọn nhiều mục---")
        # Logic: Kiểm tra xem có mục nào được tích không?
        checked_platforms = self.cb_platform.get_checked_items()
        
        if checked_platforms:
            # Nếu có chọn -> Nối chúng lại (VD: Youtube Long, TikTok)
            current_platform = ", ".join(checked_platforms)
        else:
            # Nếu không chọn gì -> Mặc định là Youtube Long
            current_platform = "Youtube Long"

        # ----------------------

        # --- [MỚI] TỪ ĐIỂN PHIÊN DỊCH MÃ QUỐC GIA ---
        CODE_TO_NAME = {
            "GLOBAL": "🌍 Global",
            # Tier 1
            "US": "🇺🇸 Hoa Kỳ", "AU": "🇦🇺 Úc", "CH": "🇨🇭 Thụy Sĩ", "GB": "🇬🇧 Anh", "UK": "🇬🇧 Anh",
            "CA": "🇨🇦 Canada", "NO": "🇳🇴 Na Uy", "NZ": "🇳🇿 New Zealand",
            # Tier 2
            "DE": "🇩🇪 Đức", "NL": "🇳🇱 Hà Lan", "SE": "🇸🇪 Thụy Điển", "DK": "🇩🇰 Đan Mạch",
            "FI": "🇫🇮 Phần Lan", "FR": "🇫🇷 Pháp", "IE": "🇮🇪 Ireland", "AT": "🇦🇹 Áo", "BE": "🇧🇪 Bỉ",
            # Tier 3
            "QA": "🇶🇦 Qatar", "AE": "🇦🇪 UAE", "SG": "🇸🇬 Singapore", "JP": "🇯🇵 Nhật Bản",
            "KR": "🇰🇷 Hàn Quốc", "IL": "🇮🇱 Israel", "SA": "🇸🇦 Ả Rập", "HK": "🇭🇰 Hồng Kông",
            "TW": "🇹🇼 Đài Loan", "KW": "🇰🇼 Kuwait",
            # Tier 4
            "ES": "🇪🇸 T.Ban Nha", "IT": "🇮🇹 Ý", "PT": "🇵🇹 Bồ Đào Nha", "PL": "🇵🇱 Ba Lan",
            "CZ": "🇨🇿 Séc", "GR": "🇬🇷 Hy Lạp", "HU": "🇭🇺 Hungary", "RU": "🇷🇺 Nga", "TR": "🇹🇷 Thổ Nhĩ Kỳ",
            # Tier 5
            "BR": "🇧🇷 Brazil", "MX": "🇲🇽 Mexico", "AR": "🇦🇷 Argentina", "CL": "🇨🇱 Chile",
            "IN": "🇮🇳 Ấn Độ", "ZA": "🇿🇦 Nam Phi",
            # Tier 6
            "VN": "🇻🇳 Việt Nam", "ID": "🇮🇩 Indo", "PH": "🇵🇭 Phil", "TH": "🇹🇭 Thái Lan",
            "MY": "🇲🇾 Malay", "PK": "🇵🇰 Pakistan", "BD": "🇧🇩 Bangladesh", "LA": "🇱🇦 Lào", "KH": "🇰🇭 Campuchia",
            # Tier 7
            "IR": "🇮🇷 Iran", "IQ": "🇮🇶 Iraq", "EG": "🇪🇬 Ai Cập", "NG": "🇳🇬 Nigeria", "UA": "🇺🇦 Ukraine"
        }
        # -----------------------------------------------
        
        # [FIX] Tạm thời ngắt kết nối để điền dữ liệu cho nhanh, tránh giật
        self.tbl_keywords.blockSignals(True)

        for i, item in enumerate(data_list):
            # 0. Checkbox
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Unchecked)  # <--- SỬA THÀNH UNCHECKED
            chk.setTextAlignment(Qt.AlignmentFlag.AlignCenter) # [CĂN GIỮA CHECKBOX]
            self.tbl_keywords.setItem(i, 0, chk)                      

            # 1. STT
            stt_item = QTableWidgetItem(str(i + 1))
            stt_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter) # [CĂN GIỮA TEXT]
            self.tbl_keywords.setItem(i, 1, stt_item)

            # 2. Nền Tảng
            plat_item = QTableWidgetItem(current_platform)
            plat_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter) # [CĂN GIỮA TEXT]
            self.tbl_keywords.setItem(i, 2, plat_item)     
            
            # 3. Quốc gia (Căn giữa) - Lấy từ item['country'] đã tách sạch
            raw_code = item.get('country', 'Global').upper().strip()
            # Tra từ điển: Nếu có thì lấy tên đẹp, ko có thì giữ nguyên mã
            display_name = CODE_TO_NAME.get(raw_code, raw_code)
            
            country_item = QTableWidgetItem(display_name)
            country_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            
            # Tô màu mã nước cho nổi (VD: TW màu vàng, US màu xanh)
            if raw_code != "GLOBAL":
                country_item.setForeground(QBrush(QColor("#00ffea"))) # Xanh Neon
                country_item.setFont(QFont("Segoe UI Emoji", 9, QFont.Weight.Bold)) # Font Emoji để hiện cờ
                
            self.tbl_keywords.setItem(i, 3, country_item)
            
            # 4. Chủ Đề Gốc
            topic_str = item.get('topic', current_topic) # Ưu tiên lấy từ item, nếu ko có thì lấy chung
            topic_item = QTableWidgetItem(topic_str)
            topic_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter) # [CĂN GIỮA CHECKBOX]
            self.tbl_keywords.setItem(i, 4, topic_item)

            # 5. Từ Khóa Ngách (Key Vua) - In đậm
            kw_item = QTableWidgetItem(item.get('keyword', ''))
            kw_item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            self.tbl_keywords.setItem(i, 5, kw_item)
            
            # 6. Ý Nghĩa Tiếng Việt - Màu xanh Neon
            mean_item = QTableWidgetItem(item.get('meaning', ''))
            mean_item.setForeground(QBrush(QColor("#cccccc")))
            self.tbl_keywords.setItem(i, 6, mean_item)
            
            # 7. Gợi ý Tiêu Đề
            title_item = QTableWidgetItem(item.get('title', ''))
            title_item.setForeground(QBrush(QColor("#ff9f43"))) # Màu cam nhạt
            self.tbl_keywords.setItem(i, 7, title_item)

            # --- [MỚI] 8. Ý Nghĩa Tiêu Đề (Vi) ---
            # Lấy dữ liệu từ worker, nếu ko có thì để trống
            t_mean = item.get('title_meaning', '') 
            t_mean_item = QTableWidgetItem(t_mean)
            t_mean_item.setForeground(QBrush(QColor("#f1c40f"))) # Màu vàng cho khác biệt
            self.tbl_keywords.setItem(i, 8, t_mean_item)
        
        # [QUAN TRỌNG MỚI THÊM] 
        # Lệnh này bắt bảng tự động dãn chiều cao dòng để chứa hết nội dung xuống dòng
        self.tbl_keywords.resizeRowsToContents()
        # Bật lại tín hiệu
        self.tbl_keywords.blockSignals(False)
        
        # [QUAN TRỌNG] Kết nối sự kiện: Khi bấm checkbox -> Gọi hàm update
        # Ngắt kết nối cũ nếu có để tránh trùng lặp
        try: self.tbl_keywords.itemChanged.disconnect()
        except: pass
        self.tbl_keywords.itemChanged.connect(self.update_transfer_info)
        
        # [MỚI] Bấm vào cell bất kỳ cũng toggle checkbox (UX xịn)
        try: self.tbl_keywords.cellClicked.disconnect()
        except: pass
        self.tbl_keywords.cellClicked.connect(self.on_cell_clicked_toggle)

        # [QUAN TRỌNG] Gọi thủ công 1 lần ngay lập tức để nó đếm số lượng mặc định
        self.update_transfer_info()

        # [MỚI] Lệnh bắt buộc bảng tính toán lại chiều cao dòng để hiện hết chữ (xuống dòng)
        self.tbl_keywords.resizeRowsToContents()
        self.handle_log_message(f"✅ [Tab 1] Hoàn tất! Đã tìm thấy {len(data_list)} ý tưởng tiềm năng.")

    
    # =========================================================================
    # LOGIC: OPPORTUNITY HUNTER (TAB 2)
    # =========================================================================
    def run_opportunity_hunter(self):
        # 1. KIỂM TRA ĐẦU VÀO
        raw_text = self.txt_input_keywords.text()

        # LOGIC ƯU TIÊN: Nếu có hàng từ Tab 1 (hunter_payload) thì dùng nó
        target_data = []
        rpm_val = 1.0    # Giá trị mặc định

        # --- TRƯỜNG HỢP A: CÓ GÓI HÀNG TỪ TAB 1 (Ưu tiên số 1 - CHUẨN NHẤT) ---
        # Kiểm tra xem text trong ô có khớp với payload không (tránh user xóa text nhập bậy)
        if hasattr(self, 'hunter_payload') and self.hunter_payload and raw_text:
             print("🚀 Chạy chế độ: PAYLOAD (Dữ liệu chuẩn từ Tab 1)")
             target_data = self.hunter_payload
             # RPM sẽ để Worker tự tính lại theo từng quốc gia trong gói hàng
             # rpm_val = 1.0   

        # --- TRƯỜNG HỢP B: NHẬP TAY THỦ CÔNG (FALLBACK - LOGIC CŨ CỦA BẠN) ---
        else:
            if not raw_text: 
                QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng nhập từ khóa hoặc chuyển từ Tab 1 sang!")
                return
            
            print("🖐️ Chạy chế độ: MANUAL (Nhập tay - Mượn Context từ Tab 1)")

            # 3. TÁCH TỪ KHÓA
            if ";" in raw_text: keywords = [k.strip() for k in raw_text.split(';')]
            else: keywords = [k.strip() for k in raw_text.split(',')]

            # [LẤY CONTEXT TỪ UI TAB 1 ĐỂ GÁN CHO TAB 2]
            # Đây là đoạn fix lỗi hiển thị "us Hoa Kỳ..." dài ngoằng
            
            # [LẤY CONTEXT TỪ UI TAB 1]
            topic_lbl = "General"
            country_lbl = "Global"
            
            try:
                # Lấy Topic
                if hasattr(self, 'cached_niche_context') and self.cached_niche_context:
                    topic_lbl = self.cached_niche_context
                else:
                    checked_t = self.cb_topic.get_checked_items()
                    if checked_t: topic_lbl = checked_t[0]

                # Lấy Country
                if hasattr(self, 'cached_country_context') and self.cached_country_context:
                    country_lbl = self.cached_country_context
                else:
                    checked_c = self.cb_country.get_checked_items()
                    if checked_c:
                        # Làm sạch chuỗi: "🇺🇸 Hoa Kỳ (En) ~$15..." -> "Hoa Kỳ"
                        country_lbl = checked_c[0].split('(')[0].split('~')[0].strip()
            except: pass

        # [FIX CHỐT CHẶN] Nếu lỡ dính chữ "Chọn nhiều mục", ép về mặc định
            if "Chọn nhiều mục" in country_lbl.upper(): country_lbl = "Global"
            if "Chọn nhiều mục" in topic_lbl.upper(): topic_lbl = "General"

            print(f"🎯 Context Scan: Topic='{topic_lbl}' | Country='{country_lbl}'")
        
            # 5. TÍNH TOÁN RPM (Dựa trên tên quốc gia)
            rpm_val = 1.0 # Mặc định
            country_str = country_lbl.upper()

            # Định nghĩa các Tier và mức giá trung bình (Lấy cận dưới của CEO để an toàn)
            # Tier 1: Kho báu ($15.0)
            t1_keys = ["Hoa Kỳ", "Úc", "Thụy Sĩ", "Anh", "Canada", "Na Uy", "New Zealand"]
            
            # Tier 2: Châu Âu Thịnh Vượng ($8.0)
            t2_keys = ["Đức", "Hà Lan", "Thụy Điển", "Đan Mạch", "Phần Lan", "Pháp", "Ireland", "Áo", "Bỉ"]
            
            # Tier 3: Châu Á Rồng Hổ ($5.0)
            t3_keys = ["Qatar", "UAE", "Singapore", "Nhật", "Hàn Quốc", "Israel", "Ả Rập", "Hồng Kông", "Đài Loan", "Kuwait"]
            
            # Tier 4: Nam & Đông Âu ($3.0)
            t4_keys = ["Tây Ban Nha", "Ý", "Bồ Đào Nha", "Ba Lan", "Séc", "Hy Lạp", "Hungary", "Nga", "Thổ Nhĩ Kỳ"]
            
            # Tier 5: Mỹ Latin & Nam Á ($1.5)
            t5_keys = ["Brazil", "Mexico", "Argentina", "Chile", "Ấn Độ", "Nam Phi"]
            
            # Tier 6: Đông Nam Á ($0.8 - Cao hơn mặc định xíu vì volume lớn)
            t6_keys = ["Việt Nam", "Indonesia", "Philippines", "Thái Lan", "Malaysia", "Pakistan", "Bangladesh", "Lào", "Campuchia"]
            
            # Tier 7: Các nước khác ($1.2 - Trung bình)
            t7_keys = ["Iran", "Iraq", "Ai Cập", "Nigeria", "Ukraine"]

            # LOGIC QUÉT: Kiểm tra xem tên nước có nằm trong chuỗi CEO chọn không
            # Ưu tiên từ Tier 1 xuống dần
            if any(k in country_str for k in t1_keys): rpm_val = 15.0
            elif any(k in country_str for k in t2_keys): rpm_val = 8.0
            elif any(k in country_str for k in t3_keys): rpm_val = 5.0
            elif any(k in country_str for k in t4_keys): rpm_val = 3.0
            elif any(k in country_str for k in t5_keys): rpm_val = 1.5
            elif any(k in country_str for k in t7_keys): rpm_val = 1.2 # Tier 7 (Ngang ngửa Tier 5)
            elif any(k in country_str for k in t6_keys): rpm_val = 0.5 # Tier 6 (Thấp nhất)
            
            target_region_code = "GLOBAL" # Mặc định là Mỹ nếu không tìm thấy
            
            # TỪ ĐIỂN ÁNH XẠ TÊN -> MÃ (ISO 3166-1 alpha-2)
            # Khớp với danh sách COUNTRIES_FULL của CEO
            ISO_CODE_MAP = {
                # --- CHÂU Á ---
                "VIETNAM": "VN", "VIỆT NAM": "VN", "VIỆT": "VN", "VN": "VN",
                "JAPAN": "JP", "NHẬT BẢN": "JP", "NHẬT": "JP", "JA": "JP", "JP": "JP",
                "CHINA": "CN", "TRUNG QUỐC": "CN", "TRUNG": "CN", "ZH": "CN", "CN": "CN",
                "TAIWAN": "TW", "ĐÀI LOAN": "TW", "TW": "TW",
                "HONG KONG": "HK", "HỒNG KÔNG": "HK", "HK": "HK",
                "KOREA": "KR", "HÀN QUỐC": "KR", "HÀN": "KR", "NAM HÀN": "KR", "KO": "KR", "KR": "KR",
                "THAILAND": "TH", "THÁI LAN": "TH", "THÁI": "TH", "TH": "TH",
                "INDONESIA": "ID", "INDO": "ID", "ID": "ID",
                "INDIA": "IN", "ẤN ĐỘ": "IN", "ẤN": "IN", "HINDI": "IN", "IN": "IN",
                "PHILIPPINES": "PH", "PHILIPPIN": "PH", "PHI": "PH", "PH": "PH",
                "SINGAPORE": "SG", "SING": "SG", "SG": "SG",
                "MALAYSIA": "MY", "MÃ LAI": "MY", "MY": "MY",
                "LAOS": "LA", "LÀO": "LA", "LA": "LA",
                "CAMBODIA": "KH", "CAMPUCHIA": "KH", "CAM": "KH", "KHMER": "KH", "KH": "KH",

                # --- CHÂU ÂU ---
                "GERMANY": "DE", "DEUTSCHLAND": "DE", "ĐỨC": "DE", "DE": "DE",
                "FRANCE": "FR", "PHÁP": "FR", "FR": "FR",
                "UNITED KINGDOM": "GB", "UK": "GB", "ANH QUỐC": "GB", "ANH": "GB", "BRITAIN": "GB", "GB": "GB",
                "IRELAND": "IE", "AI LEN": "IE", "IE": "IE",
                "SPAIN": "ES", "ESPAÑA": "ES", "TÂY BAN NHA": "ES", "TÂY": "ES", "ES": "ES",
                "ITALY": "IT", "ITALIA": "IT", "Ý": "IT", "IT": "IT",
                "RUSSIA": "RU", "NGA": "RU", "RU": "RU",
                "PORTUGAL": "PT", "BỒ ĐÀO NHA": "PT", "PT": "PT",
                "POLAND": "PL", "BA LAN": "PL", "PL": "PL",
                "NETHERLANDS": "NL", "HÀ LAN": "NL", "DUTCH": "NL", "NL": "NL",
                "SWEDEN": "SE", "THỤY ĐIỂN": "SE", "SE": "SE",
                "NORWAY": "NO", "NA UY": "NO", "NO": "NO",
                "DENMARK": "DK", "ĐAN MẠCH": "DK", "DK": "DK",
                "FINLAND": "FI", "PHẦN LAN": "FI", "FI": "FI",
                "SWITZERLAND": "CH", "THỤY SĨ": "CH", "CH": "CH",
                "AUSTRIA": "AT", "ÁO": "AT", "AT": "AT",
                "BELGIUM": "BE", "BỈ": "BE", "BE": "BE",
                "GREECE": "GR", "HY LẠP": "GR", "GR": "GR",
                "HUNGARY": "HU", "HUNG": "HU", "HU": "HU",
                "CZECH": "CZ", "CZECHIA": "CZ", "CZ": "CZ", "SEC": "CZ", "CS": "CZ", "SZ": "CZ", "TIỆP": "CZ", "TIỆP KHẮC": "CZ", "SÉC": "CZ",
                "UKRAINE": "UA", "UCRAINA": "UA", "UA": "UA",

                # --- CHÂU MỸ ---
                "UNITED STATES": "US", "USA": "US", "HOA KỲ": "US", "MỸ": "US", "AMERICA": "US", "US": "US",
                "CANADA": "CA", "CA": "CA",
                "BRAZIL": "BR", "BRAZIN": "BR", "BR": "BR",
                "MEXICO": "MX", "MÊ HI CÔ": "MX", "MX": "MX",
                "ARGENTINA": "AR", "AR": "AR",

                # --- CHÂU ÚC ---
                "AUSTRALIA": "AU", "ÚC": "AU", "AU": "AU",
                "NEW ZEALAND": "NZ", "NIU DI LÂN": "NZ", "NZ": "NZ",

                # --- TRUNG ĐÔNG & KHÁC ---
                "SAUDI ARABIA": "SA", "ARAB": "SA", "SAUDI": "SA", "Ả RẬP": "SA", "SA": "SA",
                "UAE": "AE", "TIỂU VƯƠNG QUỐC": "AE", "AE": "AE",
                "EGYPT": "EG", "AI CẬP": "EG", "EG": "EG",
                "TURKEY": "TR", "THỔ NHĨ KỲ": "TR", "THỔ": "TR", "TR": "TR",
                "ISRAEL": "IL", "DO THÁI": "IL", "IL": "IL",
                "IRAN": "IR", "BA TƯ": "IR", "IR": "IR",
                "IRAQ": "IQ", "IQ": "IQ",
                "QATAR": "QA", "QA": "QA",
                "KUWAIT": "KW", "KW": "KW",
                "SOUTH AFRICA": "ZA", "NAM PHI": "ZA", "ZA": "ZA"
            }

            country_str_upper = country_str.upper()
            for name, code in ISO_CODE_MAP.items():
                if name in country_str_upper:
                    target_region_code = code
                    break
            
            # Chốt chặn cuối
            if target_region_code == "GLOBAL" and "CHỌN" not in country_str:
                    # Nếu không map được nhưng có chữ (VD: Đức), cứ để Global tìm cho rộng
                    pass
                
            print(f"🌍 Config Manual Scan: Region={target_region_code} | RPM=${rpm_val} | Topic={topic_lbl}")

            # ĐÓNG GÓI DỮ LIỆU NHẬP TAY -> ĐỂ WORKER XỬ LÝ NHƯ PAYLOAD
            for k in keywords:
                parts = k.split('|')
                kw_text = parts[0].strip()
                mean_text = parts[1].strip() if len(parts) > 1 else ""
                
                target_data.append({
                    "keyword": kw_text,
                    "meaning": mean_text,
                    "country_code": target_region_code, # Lấy mã vừa tìm được (VD: VN)
                    "country_name": country_lbl,        # Tên hiển thị (VD: Việt Nam)
                    "topic": topic_lbl
                })

        # =========================================================
        # 2. KHỞI TẠO UI & WORKER (PHẦN NÀY DÙNG CHUNG CHO CẢ 2 TRƯỜNG HỢP)
        # =========================================================
        
        # [LOG] Báo cáo bắt đầu
        self.handle_log_message(f"🚀 [Tab 2] Bắt đầu chiến dịch Hunter cho {len(target_data)} từ khóa...")

        # [QUAN TRỌNG: RESET GIAO DIỆN]
        self.pbar.setValue(0)
        self.tbl_videos.setSortingEnabled(False)
        self.tbl_videos.setRowCount(0)
        
        # [QUAN TRỌNG: KHÓA NÚT BẤM CỦA BẠN ĐÂY]
        if hasattr(self, 'btn_scan_hunter'):
            self.btn_scan_hunter.setEnabled(False)
            self.btn_scan_hunter.setText("⏳ ĐANG QUÉT...")
            self.btn_scan_hunter.setStyleSheet("background: #555; color: #aaa;")

        time_mode = self.cb_time_filter.currentText()

        # [GỌI WORKER] - Gửi list dict (target_data) đã được chuẩn hóa ở trên
        self.yt_worker = RealYouTubeWorker(
            target_data, 
            rpm_val, 
            time_mode
        )

        self.yt_worker.progress.connect(self.pbar.setValue)

        # [MỚI] KẾT NỐI TÍN HIỆU TỪNG VIDEO
        self.yt_worker.video_found.connect(self.add_single_video_row)
        self.yt_worker.finished_signal.connect(self.on_scan_finished)
        self.yt_worker.status_signal.connect(self.lbl_scan_status.setText)
        self.yt_worker.status_signal.connect(self.log_signal.emit) # <--- ĐÃ SỬA: Nối vào log hệ thống
        
        # [MỚI] Reset nút Hủy
        self.btn_stop_scan.setEnabled(True)
        
        # [QUAN TRỌNG] Kết nối để mở khóa nút khi xong
        self.yt_worker.error.connect(lambda e: QMessageBox.critical(self, "Lỗi API", e))
        self.yt_worker.error.connect(self.reset_hunter_button)
        self.yt_worker.start()

    # 3. [HÀM MỚI] THÊM 1 DÒNG VÀO BẢNG (Logic điền dữ liệu & Fix sắp xếp số)
    def add_single_video_row(self, vid):
        row_idx = self.tbl_videos.rowCount()
        self.tbl_videos.insertRow(row_idx)

        # Helper tạo item
        def make_item(value, center=True, color=None, bold=False, sort_value=None):
            # Luôn chuyển value thành string để tránh lỗi hiển thị None
            display_text = str(value) if value is not None else ""
            item = SortableItem(display_text)
            
            if sort_value is not None:
                item.setData(Qt.ItemDataRole.UserRole, sort_value)
            else:
                # Nếu không có sort_value riêng, thử dùng chính text làm sort_value (nếu là số)
                try: item.setData(Qt.ItemDataRole.UserRole, float(value))
                except: pass

            if center: item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if color: item.setForeground(QBrush(QColor(color)))
            if bold: item.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            return item

        # 0. Checkbox
        chk = QTableWidgetItem()
        if "GEM" in vid['rating'] or "HOT" in vid['rating']:
            chk.setCheckState(Qt.CheckState.Checked)
            chk.setBackground(QColor("#1e3a3a"))
        else:
            chk.setCheckState(Qt.CheckState.Unchecked)
        chk.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tbl_videos.setItem(row_idx, 0, chk)

        # 1. STT
        self.tbl_videos.setItem(row_idx, 1, make_item(row_idx + 1, sort_value=row_idx+1))

        # 2. Thumb (Giữ nguyên logic widget)
        lbl_thumb = ZoomableLabel(vid['thumb'])
        lbl_thumb.setFixedSize(160, 90)
        if vid.get('thumb_bytes'):
            pix = QPixmap(); pix.loadFromData(vid['thumb_bytes'])
            lbl_thumb.set_high_res_pixmap(pix)
            lbl_thumb.setPixmap(pix.scaled(160, 90, Qt.AspectRatioMode.KeepAspectRatioByExpanding))
        container = QWidget()
        lo = QHBoxLayout(container); lo.setContentsMargins(5,0,5,0); lo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lo.addWidget(lbl_thumb)
        self.tbl_videos.setCellWidget(row_idx, 2, container)

        # 3. Title
        t_item = QTableWidgetItem(vid['title'])
        t_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.tbl_videos.setItem(row_idx, 3, t_item)

        # 4, 5, 6 (Text thường)
        self.tbl_videos.setItem(row_idx, 4, make_item(vid.get('topic_label', '')))
        self.tbl_videos.setItem(row_idx, 5, make_item(vid.get('country_label', '')))
        
        dur = vid.get('duration', 'N/A')
        item_dur = make_item(dur)
        if dur == "Shorts": item_dur.setForeground(QBrush(QColor("#ff5252")))
        self.tbl_videos.setItem(row_idx, 6, item_dur)

        # 7. Ngày đăng (Hiển thị Ngày - Sort theo Số ngày tuổi)
        # SỬA LỖI: Hiện ngày tháng (pub_date) chứ không hiện số 1974 nữa
        pub_date = vid.get('published_at', '')
        recency = str(vid.get('recency', '')).strip() 
        date_display = f"{pub_date}\n{recency}" if (recency and recency != "0") else pub_date
        
        # Mẹo: sort_value là days_old (số), nhưng hiển thị là date_display (chữ)
        self.tbl_videos.setItem(row_idx, 7, make_item(date_display, sort_value=vid.get('days_old', 999)))

        # 8. Tốc độ (Sort theo số)
        vpd = int(vid.get('views_per_day', 0))
        vpd_color = "#ff5252" if vpd > 1000 else None
        vpd_bold = vpd > 1000
        self.tbl_videos.setItem(row_idx, 8, make_item(f"{vpd:,}/ngày", color=vpd_color, bold=vpd_bold, sort_value=vpd))

        # 9. Views (Sort theo số)
        self.tbl_videos.setItem(row_idx, 9, make_item(f"{vid['views']:,}", sort_value=vid['views']))

        # 10. Subs (Sort theo số)
        self.tbl_videos.setItem(row_idx, 10, make_item(f"{vid['subs']:,}", sort_value=vid['subs']))

        # 11. V/S Ratio (Sort theo float)
        vs_val = float(vid['vs_ratio'])
        vs_color = "#00ffea" if vs_val >= 10 else "#f1c40f" if vs_val >= 3 else "#ffffff"
        self.tbl_videos.setItem(row_idx, 11, make_item(f"{vs_val:.2f}", color=vs_color, bold=True, sort_value=vs_val))

        # --- [MỚI] 12. Outlier Score ---
        out_val = vid.get('outlier_score', 0)
        out_text = f"{out_val}x"
        out_color = "#ffffff"

        # Logic tô màu: Đột phá > 5 lần trung bình là màu Đỏ, > 2 lần là vàng
        if out_val >= 5.0: out_color = "#ff5252" # Đỏ (Siêu đột phá)
        elif out_val >= 2.0: out_color = "#f1c40f" # Vàng (Tốt)
        
        # In đậm nếu > 2x
        self.tbl_videos.setItem(row_idx, 12, make_item(out_text, color=out_color, bold=(out_val>=2.0)))

        # 13. Revenue (Sort theo float)
        self.tbl_videos.setItem(row_idx, 13, make_item(f"${vid['revenue']:,.2f}", sort_value=vid['revenue']))

        # 14. Đánh Giá (QUAN TRỌNG NHẤT)
        # SỬA LỖI: Hiển thị chữ rating (GEM/HOT...) - Sort theo điểm số money_score
        item_rating = make_item(vid['rating'], color=vid['color'], bold=True, sort_value=vid['money_score'])
        item_rating.setToolTip(f"Money Score: {vid['money_score']}")
        self.tbl_videos.setItem(row_idx, 14, item_rating)

        # ... (Các cột Keyword, Meaning, Link giữ nguyên) ...
        self.tbl_videos.setItem(row_idx, 15, QTableWidgetItem(vid['keyword']))
        self.tbl_videos.setItem(row_idx, 16, QTableWidgetItem(vid['meaning_vi']))
        
        # Nút Xem
        link_url = vid['link']
        self.tbl_videos.setItem(row_idx, 17, QTableWidgetItem(str(link_url)))
        btn_watch = QPushButton("▶ Xem")
        btn_watch.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_watch.setStyleSheet("background: #333; color: #4da6ff; border: 1px solid #555;")
        btn_watch.clicked.connect(lambda checked, u=link_url: QDesktopServices.openUrl(QUrl(u)))
        self.tbl_videos.setCellWidget(row_idx, 18, btn_watch)
        
        # Auto scroll xuống dưới cùng để user thấy tool đang chạy
        self.tbl_videos.scrollToBottom()

    # 4. [HÀM MỚI] XỬ LÝ KHI QUÉT XONG (Tự động sắp xếp)
    def on_scan_finished(self):
        self.btn_stop_scan.setEnabled(False)
        self.reset_hunter_button()
        
        # Bật lại tính năng click header
        self.tbl_videos.setSortingEnabled(True)
        
        # TỰ ĐỘNG SẮP XẾP NGON NHẤT LÊN ĐẦU
        # Cột 13 là Rating (chứa Money Score ẩn), 11 là V/S.
        # Ở đây mình sort theo cột 13 (Money Score) giảm dần
        self.tbl_videos.sortItems(13, Qt.SortOrder.DescendingOrder)
        
        # 3. [SỬA LỖI] Lưu file ngay lập tức
        self.save_hunter_history_to_disk()

        QMessageBox.information(self, "Hoàn tất", "Đã quét xong! Danh sách đã được sắp xếp theo độ ngon (Money Score).")

    # --- HÀM MỞ KHÓA NÚT TAB 2 ---
    def reset_hunter_button(self):
        if hasattr(self, 'btn_scan_hunter'):
            self.btn_scan_hunter.setEnabled(True)
            self.btn_scan_hunter.setText("🎯 QUÉT & TÍNH V/S RATIO")
            self.btn_scan_hunter.setStyleSheet("background: #d83b01; color: white; font-weight: bold; padding: 8px;")
            
    def on_scan_results(self, results):
        # [CẬP NHẬT] LOGIC HIỂN THỊ: NHẬN GÌ HIỆN NẤY (KHÔNG LỌC NỮA)
        # Vì Worker đã lọc sơ bộ (Score > 5) rồi, nên ra đây ta cứ hiện hết để CEO đánh giá.
        
        # 1. Kiểm tra nếu không có kết quả
        if not results:
            QMessageBox.information(self, "Thông báo", "Đã quét hết các Key nhưng không tìm thấy video nào phù hợp tiêu chí (>3 phút, Score >5).")
            return

        # 2. Bắt đầu thêm vào bảng (nối tiếp đuôi)
        start_row = self.tbl_videos.rowCount()
        self.tbl_videos.setRowCount(start_row + len(results))
        
        for i, vid in enumerate(results):
            row_idx = start_row + i

             # --- HÀM HELPER: TẠO ITEM CĂN GIỮA ---
            def make_center_item(text, color=None, bold=False):
                item = QTableWidgetItem(str(text))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter) # Căn giữa
                if color: item.setForeground(QBrush(QColor(color)))
                if bold: item.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                return item
            
            # 0. Checkbox (Tự động TÍCH CHỌN luôn hàng ngon)
            chk = QTableWidgetItem()
            # [TỐI ƯU] Nếu rating xịn thì tích luôn
            if "GEM" in vid['rating'] or "HOT" in vid['rating']:
                chk.setCheckState(Qt.CheckState.Checked)
                # Cho nền màu xanh nhẹ để dễ nhìn dòng được chọn
                chk.setBackground(QColor("#1e3a3a")) 
            else:
                chk.setCheckState(Qt.CheckState.Unchecked)
            chk.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tbl_videos.setItem(row_idx, 0, chk)
            

            # 1. STT (Số thứ tự)
            stt_item = QTableWidgetItem(str(row_idx + 1))
            stt_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tbl_videos.setItem(row_idx, 1, make_center_item(str(row_idx + 1)))
            #self.tbl_videos.setItem(row_idx, 1, stt_item)
            
            # 2. Thumb (FIX ẢNH MỜ -> Dùng MAXRES)
            # Trong Worker CEO nhớ sửa url thành: 
            # url = snippet['thumbnails'].get('maxres', snippet['thumbnails'].get('high', snippet['thumbnails']['medium']))['url']
            lbl_thumb = ZoomableLabel(vid['thumb'])
            # Set lại kích thước hiển thị của ZoomableLabel cho khớp với chiều cao dòng mới (90px)
            lbl_thumb.setFixedSize(160, 90)
            if vid.get('thumb_bytes'):
                pix = QPixmap(); pix.loadFromData(vid['thumb_bytes'])
                # Gọi hàm mới để lưu ảnh gốc
                lbl_thumb.set_high_res_pixmap(pix)
                # Hiển thị ảnh vừa khung
                lbl_thumb.setPixmap(pix.scaled(160, 90, Qt.AspectRatioMode.KeepAspectRatioByExpanding))
            # Tạo một Widget con để căn giữa ảnh trong ô (Thẩm mỹ hơn)
            container = QWidget()
            lo = QHBoxLayout(container); lo.setContentsMargins(5,0,5,0); lo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lo.addWidget(lbl_thumb)
            self.tbl_videos.setCellWidget(row_idx, 2, container)
            
            # 3. Title
            title_item = QTableWidgetItem(vid['title'])
            title_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.tbl_videos.setItem(row_idx, 3, title_item)

            # 4. Chủ đề (MỚI)
            self.tbl_videos.setItem(row_idx, 4, make_center_item(vid.get('topic_label', '')))

            # 5. Quốc gia (MỚI)
            self.tbl_videos.setItem(row_idx, 5, make_center_item(vid.get('country_label', '')))

            # 6. Thời lượng (MỚI)
            dur = vid.get('duration', 'N/A')
            item_dur = make_center_item(dur)
            if dur == "Shorts": 
                item_dur.setForeground(QBrush(QColor("#ff5252"))) # Màu đỏ cho Shorts
            self.tbl_videos.setItem(row_idx, 6, item_dur)

            # 7. Ngày Đăng
            # [FIX 2] NGÀY ĐĂNG (Cột 7) - Xử lý số "0"
            pub_date = vid.get('published_at', '')
            recency = str(vid.get('recency', '')).strip() 
            
            # Logic: Nếu recency khác rỗng VÀ khác chuỗi "0" thì mới hiện dòng 2
            if recency and recency != "0": 
                date_display = f"{pub_date}\n{recency}"
            else:
                date_display = pub_date 
            
            self.tbl_videos.setItem(row_idx, 7, make_center_item(date_display))

            # 8. Tốc độ (Center)
            vpd = int(vid.get('views_per_day', 0))
            vpd_item = make_center_item(f"{vpd:,}/ngày")
            if vpd > 1000: 
                vpd_item.setForeground(QBrush(QColor("#ff5252")))
                vpd_item.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            self.tbl_videos.setItem(row_idx, 8, vpd_item)
            
            # 9. Views (Center)
            self.tbl_videos.setItem(row_idx, 9, make_center_item(f"{vid['views']:,}"))
            
            # 10. Subs (Center)
            self.tbl_videos.setItem(row_idx, 10, make_center_item(f"{vid['subs']:,}"))

            # 11. V/S Ratio (Center + Color)
            vs_val = float(vid['vs_ratio'])
            vs_color = "#00ffea" if vs_val >= 10 else "#f1c40f" if vs_val >= 3 else "#ffffff"
            self.tbl_videos.setItem(row_idx, 11, make_center_item(f"{vs_val:.2f}", vs_color, True))
            
            # 12. Revenue (Center)
            self.tbl_videos.setItem(row_idx, 12, make_center_item(f"${vid['revenue']:,.2f}"))
            
            # 13. Rating (Center + Color)
            item_rating = make_center_item(vid['rating'], vid['color'], True)
            # Tạo nội dung Tooltip dựa trên loại Rating
            tooltip_text = ""
            if "GEM" in vid['rating']:
                tooltip_text = (
                    "💎 GEM (KHO BÁU - MUST CLONE):\n"
                    "---------------------------\n"
                    "• Đặc điểm: Kênh BÉ TÍ (<10k sub) nhưng View KHỔNG LỒ.\n"
                    "• Ý nghĩa: Nội dung quá hay, thuật toán tự đề xuất bất chấp kênh nhỏ.\n"
                    "👉 CHIẾN LƯỢC: COPY NGAY! Tỷ lệ thắng cực cao cho kênh mới."
                )
            elif "HOT" in vid['rating']:
                tooltip_text = (
                    "🔥 HOT (XU HƯỚNG - NÊN LÀM):\n"
                    "---------------------------\n"
                    "• Đặc điểm: Tốc độ tăng trưởng view rất nhanh.\n"
                    "• Ý nghĩa: Chủ đề đang trend, nhiều người quan tâm.\n"
                    "👉 CHIẾN LƯỢC: Làm để ăn theo trend, kéo traffic tốt."
                )
            elif "OK" in vid['rating']:
                tooltip_text = (
                    "✅ OK (TIỀM NĂNG - THAM KHẢO):\n"
                    "---------------------------\n"
                    "• Đặc điểm: View ổn định, có thị trường ngách.\n"
                    "• Ý nghĩa: Chủ đề an toàn, 'cần câu cơm' lâu dài.\n"
                    "👉 CHIẾN LƯỢC: Làm để duy trì kênh hoặc khi bí ý tưởng GEM."
                )
            else:
                tooltip_text = (
                    "⚪ THƯỜNG (RỦI RO CAO):\n"
                    "---------------------------\n"
                    "• Đặc điểm: View thấp hoặc Kênh quá lớn (Triệu sub).\n"
                    "👉 CHIẾN LƯỢC: Hạn chế làm theo, khó cạnh tranh."
                )
            
            item_rating.setToolTip(tooltip_text) # <--- Gán Tooltip vào đây
            self.tbl_videos.setItem(row_idx, 13, item_rating)
            
            # 14. Keyword (Wrap)
            self.tbl_videos.setItem(row_idx, 14, QTableWidgetItem(vid['keyword']))
            
            # 15. Nghĩa (Wrap)
            self.tbl_videos.setItem(row_idx, 15, QTableWidgetItem(vid['meaning_vi']))
            
            # 16. Widget Xem Video (Button nhỏ)
            link_url = vid['link']
            self.tbl_videos.setItem(row_idx, 16, QTableWidgetItem(str(link_url))) # Cột 16 Ẩn
            
            btn_watch = QPushButton("▶ Xem")
            btn_watch.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_watch.setStyleSheet("background: #333; color: #4da6ff; border: 1px solid #555;")
            btn_watch.clicked.connect(lambda checked, u=link_url: QDesktopServices.openUrl(QUrl(u)))
            self.tbl_videos.setCellWidget(row_idx, 17, btn_watch) # Cột 17 Hiện
        
        # [QUAN TRỌNG] Tự động giãn chiều cao dòng để chứa hết chữ (xuống dòng)
        self.tbl_videos.resizeRowsToContents()

        # Nhưng đảm bảo chiều cao tối thiểu là 90px (cho ảnh thumb)
        for r in range(start_row, self.tbl_videos.rowCount()):
            if self.tbl_videos.rowHeight(r) < 95:
                self.tbl_videos.setRowHeight(r, 95)

        else:
            self.save_hunter_history_to_disk()
        # Reset nút Hủy
        if hasattr(self, 'btn_stop_scan'): self.btn_stop_scan.setEnabled(False)
    # =========================================================================
    # HÀM CHUYỂN ĐỔI GIỮA CÁC TAB (NAVIGATION)
    # =========================================================================
    def transfer_to_deep(self):
        """Chuyển Keyword sang Tab 2 (ĐÓNG GÓI CHI TIẾT KÈM QUỐC GIA/CHỦ ĐỀ RIÊNG)"""
        # 1. Khởi tạo danh sách chứa các gói dữ liệu chuẩn
        self.hunter_payload = [] 
        display_list = [] # Chỉ để hiển thị ra ô text cho vui mắt

        table = getattr(self, 'tbl_keywords', None)
        
        # Bộ từ điển map ngược từ Tên hiển thị (Tab 1) -> Mã Code (Để gửi API)
        # Tab 1 hiện "🇺🇸 Hoa Kỳ", ta cần đổi về "US"
        NAME_TO_CODE = {
            "HOA KỲ": "US", "MỸ": "US", "UNITED STATES": "US",
            "VIỆT NAM": "VN", "VIETNAM": "VN",
            "NHẬT BẢN": "JP", "JAPAN": "JP",
            "HÀN QUỐC": "KR", "KOREA": "KR",
            "TRUNG QUỐC": "CN", "CHINA": "CN",
            "ĐÀI LOAN": "TW", "TAIWAN": "TW",
            "THÁI LAN": "TH", "THAILAND": "TH",
            "ANH": "GB", "UK": "GB", "UNITED KINGDOM": "GB",
            "PHÁP": "FR", "FRANCE": "FR",
            "ĐỨC": "DE", "GERMANY": "DE",
            "NGA": "RU", "RUSSIA": "RU",
            "THỤY SĨ": "CH", "SWITZERLAND": "CH",
            "NA UY": "NO", "NORWAY": "NO",
            "THỤY ĐIỂN": "SE", "SWEDEN": "SE",
            "ÚC": "AU", "AUSTRALIA": "AU",
            "CANADA": "CA",
            "GLOBAL": "GLOBAL"
        }
        
        if table:
            for i in range(table.rowCount()):
                item_chk = table.item(i, 0)
                # Chỉ lấy những dòng ĐƯỢC TÍCH
                if item_chk and item_chk.checkState() == Qt.CheckState.Checked:
                    # Lấy thông tin từng cột
                    country_display = table.item(i, 3).text() # VD: 🇺🇸 Hoa Kỳ
                    topic_display = table.item(i, 4).text()   # VD: True Crime
                    kw = table.item(i, 5).text()      # Cột 5: Từ khóa
                    meaning = table.item(i, 6).text() # Cột 6: Nghĩa                    
                                
                    # Xử lý tìm Mã Quốc Gia từ tên hiển thị
                    c_upper = country_display.upper()
                    code = "GLOBAL" # Mặc định
                    for name, c_code in NAME_TO_CODE.items():
                        if name in c_upper:
                            code = c_code
                            break
                    
                    # Đóng gói kiện hàng
                    data_package = {
                        "keyword": kw,
                        "meaning": meaning,
                        "country_code": code,           # Mã để tìm kiếm (quan trọng nhất)
                        "country_name": country_display, # Để hiển thị lại bên Tab 2
                        "topic": topic_display
                    }
                    self.hunter_payload.append(data_package)
                    
                    # Tạo chuỗi hiển thị
                    display_list.append(f"{kw}|{meaning}")

        if not self.hunter_payload:
            QMessageBox.warning(self, "Chưa chọn", "Vui lòng chọn ít nhất 1 từ khóa ngách để đào sâu!")
            return
        
        # 2. LƯU VÀO BỘ NHỚ ĐỆM (CACHE)
        # Nối các giá trị tìm được lại (VD: "True Crime" hoặc "True Crime, Horror")
        #self.cached_niche_context = ", ".join(topic_display) if topic_display else "General"
        #self.cached_country_context = ", ".join(country_display) if country_display else "Global"

        print(f"🔄 Đã đồng bộ Context từ bảng: Topic='{self.cached_niche_context}' | QG='{self.cached_country_context}'")

        # 3. GỬI DỮ LIỆU SANG TAB 2
        inp = getattr(self, 'txt_input_keywords', None)
        if inp:
            inp.setText("; ".join(display_list))
        
        # 4. CHUYỂN TAB & RESET TRẠNG THÁI
        self.tabs.setCurrentIndex(1) # Chuyển sang Tab 2
        
        # Reset thanh tiến trình bên Tab 2
        self.pbar.setValue(0)
        self.lbl_scan_status.setText("Sẵn sàng quét.")
        
        # Disable nút Stop nếu cần
        if hasattr(self, 'btn_stop_scan'): 
            self.btn_stop_scan.setEnabled(False)
            
        # Ghi log
        try: self.log_message.emit(f"🚀 Đã chuyển {len(self.hunter_payload)} từ khóa sang Tab Đào Sâu.")
        except: pass

    def transfer_to_spy(self):
        """Chuyển từ Tab 2 sang Tab 3: Lấy Link, giữ nguyên Context từ Tab 1"""
        
        # 1. Xác định bảng dữ liệu (Tab 2)
        table = getattr(self, 'tbl_videos', getattr(self, 'tb_deep', None))
        if not table: return
        
        target_link = ""
        target_niche = ""   # Biến chứa Chủ đề của dòng được chọn
        target_country = "" # Biến chứa Quốc gia của dòng được chọn
        selected_rows = 0
        
        # 2. Quét dòng được chọn
        for i in range(table.rowCount()):
            item_chk = table.item(i, 0)
            # 2. Quét dòng được chọn
        print("\n🕵️ [DEBUG] Bắt đầu quét các dòng đã chọn...")
        for i in range(table.rowCount()):
            item_chk = table.item(i, 0)
            
            # Kiểm tra xem dòng có được tích không
            if item_chk and item_chk.checkState() == Qt.CheckState.Checked:
                selected_rows += 1
                print(f"   -> Đã tìm thấy dòng {i+1} được chọn.")
                
                # --- CHIẾN THUẬT LẤY LINK V2.0 ---
                # 1. Ưu tiên lấy trực tiếp từ Cột 17 (Cột Link ẩn)
                item_link_def = table.item(i, 17)
                if item_link_def and item_link_def.text().strip():
                    target_link = item_link_def.text().strip()
                    print(f"      + Lấy được Link từ Cột 17: {target_link}")
                
                # 2. Nếu Cột 17 rỗng, quét toàn bộ dòng tìm chuỗi "youtube.com" hoặc "youtu.be"
                if not target_link:
                    for c in range(table.columnCount()):
                        item = table.item(i, c)
                        if item and ("youtube.com" in item.text() or "youtu.be" in item.text()):
                            target_link = item.text().strip()
                            print(f"      + Quét thấy Link ở Cột {c}: {target_link}")
                            break
                
                # --- LẤY CONTEXT (Để điền vào Tab 3) ---
                if table.item(i, 4): target_niche = table.item(i, 4).text()
                if table.item(i, 5): target_country = table.item(i, 5).text()
                
                # Chỉ xử lý 1 dòng đầu tiên tìm thấy, sau đó thoát vòng lặp
                break 
        
        # 3. KIỂM TRA LỖI CHI TIẾT
        if selected_rows == 0:
            QMessageBox.warning(self, "Chưa chọn", "Ngài chưa tích chọn video nào cả!\nHãy bấm vào ô vuông đầu dòng.")
            return

        if not target_link:
            QMessageBox.warning(self, "Lỗi Dữ Liệu", f"Đã chọn dòng nhưng không tìm thấy Link video.\n(Có thể do lúc quét bị lỗi mạng nên thiếu Link).")
            return

        # 3. [FIX LỖI] CẬP NHẬT BIẾN NHỚ (CACHE) NGAY LẬP TỨC
        # Ghi đè biến nhớ bằng thông tin thực tế của video vừa chọn
        if target_niche: self.cached_niche_context = target_niche
        if target_country: self.cached_country_context = target_country

        print(f"🔄 Đồng bộ sang Spy: Niche='{target_niche}' | Country='{target_country}'")
        
        # Lưu ngay xuống ổ cứng để nút "Khôi phục gốc" dùng được sau này
        self.save_spy_history_to_disk()

        # 4. Điền Link và Chuyển Tab
        self.tabs.setCurrentWidget(self.tab_spy)
        self.txt_video_url.setText(target_link)
        
        # 5. GỌI LOGIC ĐỒNG BỘ (Nó sẽ dùng cached_niche_context chuẩn từ Tab 1)
        self.apply_smart_sync()

        # --- 6. CHẠY THUẬT TOÁN ĐỒNG BỘ THÔNG MINH (SCORE-BASED) ---
        import re

        # A. Đồng bộ Chủ đề (Niche)
        if hasattr(self, 'cached_niche_context') and self.cached_niche_context:
            raw_niche = self.cached_niche_context.lower()
            keywords = [w for w in re.sub(r'[^\w\s]', '', raw_niche).split() if len(w) >= 2]
            
            # [FIX 2] Nếu lọc xong mà rỗng (ví dụ toàn icon) -> Lấy luôn từ gốc
            if not keywords: keywords = raw_niche.split()

            model = self.cb_batch_niche.model
            best_match_item = None
            max_score = 0
            
            # Reset
            for i in range(model.rowCount()): model.item(i).setCheckState(Qt.CheckState.Unchecked)
            
            if keywords: # [FIX 3] Chỉ chạy nếu có từ khóa
                for i in range(model.rowCount()):
                    item = model.item(i)
                    item_text = item.text().lower()
                    if "---" in item_text: continue
                    
                    score = 0
                    for k in keywords:
                        if k in item_text: score += 1
                    
                    # [FIX 4] Kiểm tra an toàn trước khi gọi index [0]
                    if len(keywords) > 0 and item_text.startswith(keywords[0]): 
                        score += 0.5
                    
                    if score > max_score:
                        max_score = score
                        best_match_item = item
                
            if best_match_item and max_score > 0:
                best_match_item.setCheckState(Qt.CheckState.Checked)
                self.cb_batch_niche._update_text()

        # B. Đồng bộ Quốc gia (Language)
        if hasattr(self, 'cached_country_context') and self.cached_country_context:
            target_country = self.cached_country_context.split('(')[0].strip()
            target_country_clean = re.sub(r'[^\w\s]', '', target_country).strip()
            
            model = self.cb_batch_lang.model
            # Reset
            for i in range(model.rowCount()): model.item(i).setCheckState(Qt.CheckState.Unchecked)
            
            found = False
            for i in range(model.rowCount()):
                item = model.item(i)
                item_text = item.text()
                if "---" in item_text: continue

                if target_country_clean and target_country_clean in item_text:
                    item.setCheckState(Qt.CheckState.Checked)
                    self.cb_batch_lang._update_text()
                    found = True
                    break # Tìm thấy 1 cái là dừng ngay (Quốc gia là duy nhất)
            
            if found:
                self.cb_batch_lang._update_text()
                print(f"🔄 Auto-Country: {target_country_clean}")

        # 4. Chuyển Tab
        self.tabs.setCurrentIndex(2)

    # [HÀM MỚI] LOGIC ĐỒNG BỘ CHUNG (DÙNG CHO CẢ TRANSFER VÀ RESTORE)
    def apply_smart_sync(self):
        """Thuật toán tìm và chọn Niche/Country dựa trên biến nhớ"""
        import re
        # --- 1. TỪ ĐIỂN ĐỒNG NGHĨA (TOPIC MAPPING) ---
        # Map từ khóa lạ (Tab 1) -> Chủ đề chuẩn (Tab 3)
        # CEO có thể thêm thoải mái vào đây
        TOPIC_MAP = {
            # Nhóm Động vật
            "RODENT": "Hamsters", "MOUSE": "Hamsters", "RAT": "Hamsters",
            "CAPYBARA": "Hamsters", "HAMSTER": "Hamsters", "GUINEA": "Hamsters",
            "CAT": "Cute Cats", "KITTEN": "Cute Cats", "KITTY": "Cute Cats", "MEOW": "Cute Cats",
            "DOG": "Funny Dogs", "PUPPY": "Funny Dogs", "BARK": "Funny Dogs",
            "ANIMAL": "Wild Life", "WILD": "Wild Life", "TIGER": "Wild Life", "LION": "Wild Life",
            
            # Nhóm Kinh dị / Bí ẩn
            "GHOST": "Scary Stories", "HORROR": "Scary Stories", "CREEPY": "Scary Stories",
            "CRIME": "True Crime", "MURDER": "True Crime", "KILLER": "True Crime", "POLICE": "True Crime",
            "MYSTERY": "Unsolved Mysteries", "CASE": "Unsolved Mysteries",
            
            # Nhóm Khoa học / Tech
            "SPACE": "Space", "UNIVERSE": "Space", "ALIEN": "Space", "PLANET": "Space",
            "TECH": "Future Tech", "ROBOT": "Future Tech", "AI": "Future Tech", "GADGET": "Future Tech",
            "CODE": "Coding", "PROGRAMMING": "Coding",
            
            # Nhóm Thư giãn
            "LOFI": "Lofi", "MUSIC": "Lofi", "CHILL": "Lofi", "STUDY": "Lofi",
            "RAIN": "Rain", "THUNDER": "Rain", "STORM": "Rain", "WATER": "Rain",
            "ASMR": "ASMR", "SLEEP": "ASMR",
            
            # Nhóm Khác
            "FACT": "Facts", "TRUTH": "Facts", "KNOWLEDGE": "Facts", "TOP": "Facts",
            "HISTORY": "History", "WAR": "History", "ANCIENT": "History",
            "MONEY": "Finance", "CRYPTO": "Finance", "INVEST": "Finance",
            "STORY": "Reddit Confessions", "CONFESSION": "Reddit Confessions"
        }
        # --- XỬ LÝ ĐỒNG BỘ CHỦ ĐỀ (NICHE) ---
        if hasattr(self, 'cached_niche_context') and self.cached_niche_context:
            raw_niche = self.cached_niche_context.upper() # VD: "GIANT RODENT FACTS"
            
            # Bước 1: Tìm "Long mạch" trong từ điển
            target_keyword = ""
            for key, val in TOPIC_MAP.items():
                if key in raw_niche: # VD: "RODENT" có trong "GIANT RODENT FACTS"
                    target_keyword = val.upper() # -> Lấy đích đến là "HAMSTERS"
                    break
            
            # Bước 2: Quét Combobox để chọn
            model = self.cb_batch_niche.model
            best_match_item = None
            max_score = 0
            
            # Reset (Bỏ chọn hết)
            for i in range(model.rowCount()): model.item(i).setCheckState(Qt.CheckState.Unchecked)
            
            for i in range(model.rowCount()):
                item = model.item(i)
                item_text = item.text().upper() # VD: "HAMSTERS/CAPYBARA"
                if "---" in item_text: continue
                
                score = 0
                
                # A. Nếu tìm thấy trong Map -> Điểm tuyệt đối
                if target_keyword and target_keyword in item_text: 
                    score += 100 
                
                # B. Nếu không, so khớp từng từ (Fallback)
                # Tách từ khóa gốc ra: ["GIANT", "RODENT", "FACTS"]
                raw_words = re.sub(r'[^\w\s]', '', raw_niche).split()
                for w in raw_words:
                    if len(w) > 2 and w in item_text: # VD: "FACTS" khớp "FACTS/KNOWLEDGE"
                        score += 10
                
                if score > max_score:
                    max_score = score
                    best_match_item = item
            
            # Chốt đơn
            if best_match_item and max_score > 0:
                best_match_item.setCheckState(Qt.CheckState.Checked)
                self.cb_batch_niche._update_text()
                print(f"🔄 Auto-Niche V2: '{self.cached_niche_context}' -> Map: '{best_match_item.text()}'")

        # 2. ĐỒNG BỘ QUỐC GIA (COUNTRY)
        if hasattr(self, 'cached_country_context') and self.cached_country_context:
            raw_country = self.cached_country_context
            target_country = raw_country.split('(')[0].strip() # Lấy tên trước dấu ngoặc
            target_country_clean = re.sub(r'[^\w\s]', '', target_country).strip()
            
            model = self.cb_batch_lang.model
            # Reset
            for i in range(model.rowCount()): model.item(i).setCheckState(Qt.CheckState.Unchecked)
            
            found = False
            for i in range(model.rowCount()):
                item = model.item(i)
                item_text = item.text()
                if "---" in item_text: continue

                # So sánh tên nước
                if target_country_clean and target_country_clean in item_text:
                    item.setCheckState(Qt.CheckState.Checked)
                    found = True
                    break
            
            if found:
                self.cb_batch_lang._update_text()
                print(f"🔄 Auto-Country: {target_country_clean}")

    # =========================================================================
    # LOGIC: SPY (TAB 3) - QUY TRÌNH CHUẨN: LẤY META -> SHOW HÀNG -> PHÂN TÍCH AI
    # =========================================================================
    def run_spy_analysis(self):
        url = self.txt_video_url.text().strip()
        if not url: 
            QMessageBox.warning(self, "Thiếu Link", "Vui lòng nhập Link Video cần Spy!")
            return

        # [LOG] Báo cáo
        self.handle_log_message(f"🚀 [Tab 3] Đang kết nối vệ tinh Spy đến: {url}...")

        # 1. Dọn dẹp màn hình & Reset trạng thái
        self.txt_report_en.clear()
        self.txt_report_vi.clear()
        # [MỚI] Reset ô JSON để chờ dữ liệu mới
        if hasattr(self, 'txt_report_json'):
            self.txt_report_json.setText("⏳ Waiting for AI analysis...")
        # [FIX LỖI THIẾU f] Thêm chữ f vào trước chuỗi để in ra link
        self.txt_report_en.setText(f"⏳ ĐANG KẾT NỐI VỆ TINH ĐẾN VIDEO:\n{url}\n\nĐang gọi yt-dlp lấy dữ liệu gốc...")
        self.txt_report_vi.setText("⏳ Đang chờ dữ liệu gốc...")        

        # Reset khung Profile tạm thời
        self.lbl_spy_channel_name.setText("Đang tải dữ liệu...")
        self.lbl_spy_stats.setText("Waiting for response...")
        self.lbl_spy_thumb.clear()
        self.lbl_spy_thumb.setStyleSheet("background: #000;") # Màu đen chờ ảnh

        # Reset dữ liệu đệm
        self.current_spy_data = {}

        # 2. GỌI WORKER LẤY DỮ LIỆU THẬT (METADATA)
        # Lưu ý: Chỉ gọi MetaWorker ở đây, KHÔNG gọi AI ngay lập tức
        self.meta_worker = SpyMetadataWorker(url)
        self.meta_worker.finished.connect(self.on_metadata_loaded)
        self.meta_worker.start()

    # [HÀM XỬ LÝ KHI CÓ DỮ LIỆU THẬT TRẢ VỀ]
    def on_metadata_loaded(self, data):
        # 1. Kiểm tra lỗi
        if not data.get("success"):
            self.txt_report_en.setText(f"❌ LỖI LẤY DỮ LIỆU: {data.get('error')}\n(Kiểm tra lại Link hoặc Mạng)")
            return

        self.handle_log_message(f"✅ [Tab 3] Đã lấy được Metadata: {data.get('title')[:30]}...")

        # --- [NÂNG CẤP 1] TÍNH TOÁN SỨC MẠNH VIDEO (AGE vs VIEWS) ---
        views = data.get("views", 0)
        upload_date_str = data.get("upload_date", "") # YYYYMMDD
        velocity_text = "N/A"
        
        # Tính tuổi đời video
        days_old = 1
        import datetime
        try:
            # yt-dlp trả về format YYYYMMDD
            if len(upload_date_str) == 8:
                up_date = datetime.datetime.strptime(upload_date_str, "%Y%m%d")
                delta = datetime.datetime.now() - up_date
                days_old = max(1, delta.days) # Tối thiểu 1 ngày
                
                # Tính Velocity (Views/Ngày)
                velocity = views / days_old
                velocity_text = f"{int(velocity):,} views/ngày"
                
                # Đánh giá nhanh
                if velocity > 10000: velocity_text += " (🔥 BREAKOUT)"
                elif velocity > 1000: velocity_text += " (✅ TỐT)"
                else: velocity_text += " (⚪ BÌNH THƯỜNG)"
        except: pass

        # 1. ĐỔ DỮ LIỆU VÀO GIAO DIỆN MỚI
        self.lbl_spy_video_title.setText(data.get("title", "Unknown Title")) # Tên Video
        self.lbl_spy_channel_name.setText(f"👤 {data.get('channel_name')}") # Tên Kênh
        self.lbl_spy_stats.setText(data.get("stats_text")) # View/Like
        
        # [MỚI] Hiển thị chỉ số View thật + Tốc độ tăng trưởng
        stats_display = f"👁️ {data.get('stats_text')} | ⏳ {days_old} ngày tuổi | 🚀 {velocity_text}"
        self.lbl_spy_stats.setText(stats_display)

        # Điền mô tả gốc
        raw_desc = data.get("description", "")
        transcript = data.get("transcript", "")
        
        display_text = f"--- 📝 DESCRIPTION ---\n{raw_desc}\n\n--- 🗣️ TRANSCRIPT (LỜI THOẠI) ---\n{transcript}"
        self.txt_spy_desc_raw.setText(display_text) # Hiện cả 2 cho CEO soi

        video_url = data.get("webpage_url")
        if video_url:
            self.txt_video_url.setText(video_url) # Điền link vào ô nhập luôn cho chắc
            if hasattr(self, 'btn_watch_original'):
                self.btn_watch_original.show() # <--- LỆNH HIỆN NÚT QUAN TRỌNG
                self.btn_watch_original.setToolTip(f"Mở link: {video_url}")

        # --- [FIX LỖI] DỊCH MÔ TẢ (CÁCH ĐƠN GIẢN, KHÔNG CẦN Q_ARG) ---
        if raw_desc:
            self.txt_spy_desc_vi.setText("⏳ Đang dịch mô tả...")
            
            # Chạy thread ngầm để không đơ máy
            import threading
            from deep_translator import GoogleTranslator
            
            def run_translate():
                try:
                    # Cắt ngắn 1000 ký tự đầu để dịch cho nhanh
                    text_short = raw_desc[:1000]
                    translated = GoogleTranslator(source='auto', target='vi').translate(text_short)
                    final_text = translated + "\n\n...(Đã lược bớt)..."
                    # [QUAN TRỌNG] Dùng QMetaObject để nhờ Main Thread cập nhật UI
                    # Không được gọi self.txt_spy_desc_vi.setText() trực tiếp ở đây!
                    QMetaObject.invokeMethod(self.txt_spy_desc_vi, "setText", 
                                             Qt.ConnectionType.QueuedConnection, 
                                             Q_ARG(str, final_text))
                except Exception as e:
                    print(f"Lỗi dịch: {e}")
                    error_msg = "(Lỗi kết nối Google Dịch)"
                    QMetaObject.invokeMethod(self.txt_spy_desc_vi, "setText", 
                                             Qt.ConnectionType.QueuedConnection, 
                                             Q_ARG(str, error_msg))

            # Khởi chạy thread
            t = threading.Thread(target=run_translate)
            t.daemon = True
            t.start()
        else:
            self.txt_spy_desc_vi.setText("(Video không có mô tả)")

        # 2. HIỂN THỊ THUMBNAIL (NÉT CĂNG)
        if data.get("pixmap_thumb"):
            self.lbl_spy_thumb.setPixmap(data["pixmap_thumb"])
            self.lbl_spy_thumb.setText("")
        
        # --- [NÂNG CẤP 2] LẤY CLEAN TITLE LÀM RAW INTENT (KEY TẠM) ---
        # Thay vì lấy Tags rác, ta lấy Title và lọc bỏ các ký tự câu view
        raw_title = data.get("title", "")
        import re
        # Bỏ phần trong ngoặc [], (), bỏ emoji, bỏ ký tự lạ
        clean_intent = re.sub(r"[\(\[].*?[\)\]]", "", raw_title) # Bỏ ngoặc
        clean_intent = re.sub(r"[^\w\s]", "", clean_intent) # Bỏ ký tự đặc biệt
        clean_intent = " ".join(clean_intent.split()) # Xóa khoảng trắng thừa
        
        print(f"🎯 Raw Intent (Clean Title): {clean_intent}")

        # Lưu dữ liệu Spy vào biến nhớ (Để dùng cho các bước sau)
        self.current_spy_data = {
            "root_keyword": clean_intent, # Key tạm, AI sẽ sửa lại sau
            "url": data.get("webpage_url"), # Link video gốc
            "thumbnail_url": data.get("thumbnail_url"),
            "skeleton": "", # Sẽ có sau khi AI phân tích
            "full_meta": data # Lưu full để dành
        }
        # =========================================================
        # 🕵️ SHERLOCK MODE: TỰ ĐỘNG SUY LUẬN CONTEXT TỪ VIDEO SPY
        # =========================================================
        detected_country = "Global"
        detected_topic = "Global"
        
        raw_title = data.get("title", "").upper()
        raw_desc = data.get("description", "").upper()
        full_text = raw_title + " " + raw_desc

        # [MỚI] KIỂM TRA TỶ LỆ TIẾNG ANH / LATIN TRƯỚC
        # Nếu > 80% là ký tự ASCII (Tiếng Anh) -> Chốt luôn là US hoặc Global
        # Để tránh việc video News nói về Iran bị nhận nhầm là nước Iran
        ascii_chars = len([c for c in full_text if ord(c) < 128])
        total_chars = len(full_text) if len(full_text) > 0 else 1
        is_mostly_english = (ascii_chars / total_chars) > 0.8

        if re.search(r'[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]', full_text.lower()):
            detected_country = "Việt Nam (Vn)"
        else:
            # 1. SUY LUẬN QUỐC GIA (Dựa trên ký tự đặc trưng)
            import re
            DETECTION_MAP = [
                # 1. Nhóm Ký Tự Đặc Biệt (Độ chính xác 100%)
                (r'[\u3040-\u30ff\u31f0-\u31ff]', "Nhật Bản (Jp)"), # Hiragana/Katakana
                (r'[\uac00-\ud7af]', "Hàn Quốc (Kr)"), # Hangul
                (r'[\u0e00-\u0e7f]', "Thái Lan (Th)"), # Thai
                (r'[\u1780-\u17ff]', "Campuchia (Kh)"), # Khmer
                (r'[\u0e80-\u0eff]', "Lào (La)"), # Lao
                (r'[\u0600-\u06ff]', "Ả Rập (Sa)"), # Arabic (Saudi/UAE)
                (r'[\u0400-\u04ff]', "Nga (Ru)"), # Cyrillic (Nga/Ukraine)
                
                # 2. Nhóm Latin nhưng có Keyword Tiếng Bản Địa
                (r'\bVIETNAM\b|\bVIỆT\b|\bVLOG\b|\bCHÀO\b', "Việt Nam (Vn)"),
                (r'\bGERMAN\b|\bDEUTSCH\b', "Đức (De)"),
                (r'\bFRANCE\b|\bFRENCH\b|\bFRANÇAIS\b', "Pháp (Fr)"),
                (r'\bSPAIN\b|\bSPANISH\b|\bESPAÑOL\b', "Tây Ban Nha (Es)"),
                (r'\bITALY\b|\bITALIAN\b|\bITALIANO\b', "Ý (It)"),
                (r'\bBRAZIL\b|\bPORTUGUESE\b', "Brazil (Br)"),
                (r'\bINDONESIA\b|\bINDO\b', "Indonesia (Id)"),
                (r'\bINDIA\b|\bHINDI\b', "Ấn Độ (In)"),
                
                # 3. Nhóm Phồn Thể/Giản Thể
                (r'[\u4e00-\u9fff]', "Đài Loan (Tw)") # Gán tạm TW (hoặc CN)
            ]
            
            # Chạy vòng lặp check
            for pattern, c_name in DETECTION_MAP:
                if re.search(pattern, full_text):
                    detected_country = c_name
                    break
            
            ascii_chars = len([c for c in full_text if ord(c) < 128])
            total_chars = len(full_text) if len(full_text) > 0 else 1
            if (ascii_chars / total_chars) > 0.8 and detected_country == "Global":
                detected_country = "Hoa Kỳ (Us)"

        # 2. SUY LUẬN CHỦ ĐỀ (Keyword Matching)
        # Quét danh sách BATCH_NICHE_IDEAS xem có từ nào khớp không
        from ui.widgets.radar_tab import BATCH_NICHE_IDEAS # Import list nếu cần, hoặc dùng self.cb_batch_niche
        
        max_score = 0
        
        # Duyệt qua các item trong combobox Tab 3
        model = self.cb_batch_niche.model
        for i in range(model.rowCount()):
            item_text = model.item(i).text()
            if "---" in item_text: continue
            
            # Tách từ khóa từ Niche (VD: "Rain & Thunder" -> ["Rain", "Thunder"])
            keywords = [w.upper() for w in re.sub(r'[^\w\s]', '', item_text).split() if len(w) > 2]
            
            score = 0
            for k in keywords:
                if k in raw_title: score += 3 # Khớp Title điểm cao
                elif k in raw_desc: score += 1
            
            if score > max_score:
                max_score = score
                detected_topic = item_text

        # 3. CẬP NHẬT GIAO DIỆN (AUTO FILL)
        print(f"🕵️ Sherlock Detected: Country={detected_country} | Topic={detected_topic}")

        # [QUAN TRỌNG] Cập nhật vào biến nhớ
        if detected_country != "Global":
            self.cached_country_context = detected_country
        
        if detected_topic != "Global":
            self.cached_niche_context = detected_topic
            
        # Gọi hàm đồng bộ để nó tự tick vào checkbox
        self.apply_smart_sync()

        # [MỚI - CỰC QUAN TRỌNG] LƯU NGAY LẬP TỨC XUỐNG Ổ CỨNG
        # Để tắt đi bật lại nó vẫn nhớ là "Hamster" chứ không phải "Mèo"
        self.save_spy_history_to_disk()
        
        # 3. GỌI AI PHÂN TÍCH CHIẾN LƯỢC (SAU KHI CÓ DỮ LIỆU THẬT)
        self.txt_report_en.setText("✅ Đã lấy được Metadata. Đang gửi cho AI trích xuất KEY VUA thực sự...")
        self.txt_report_vi.setText("⏳ Đang dịch chiến thuật (Tiếng Việt)...")

        # [NÂNG CẤP PROMPT AI]
        # Gửi Transcript cho AI (Cắt bớt nếu quá dài để tránh lỗi Token, tầm 10k ký tự là đẹp)
        transcript_snippet = transcript[:8000]

        # Chuẩn bị thông tin "Sâu sắc" gửi cho AI
        ai_input_info = (
            f"--- VIDEO METADATA ---\n"
            f"TITLE: {data.get('title')}\n"
            f"CHANNEL: {data.get('channel_name')}\n"
            f"VIEWS: {views} (Velocity: {velocity_text})\n"
            f"PUBLISHED: {days_old} days ago\n"
            f"DURATION: {data.get('duration', 'Unknown')}\n"
            f"DESCRIPTION:\n{raw_desc[:2000]}\n"
            f"--- TRANSCRIPT / SCRIPT (CORE CONTENT) ---\n"
            f"{transcript_snippet}\n"
        )
        
        self.handle_log_message(f"🧠 [Tab 3] Đang gửi DNA cho AI phân tích chiến lược...")

        # Gọi Worker AI (Chỉ gọi 1 lần duy nhất ở đây)
        self.ai_analyzer = RadarAIWorker('analysis', data)
        self.ai_analyzer.finished.connect(self.handle_analysis_result) # Gọi hàm xử lý kết quả riêng

        # [MỚI] Bắt lỗi để hiển thị ra màn hình thay vì treo
        self.ai_analyzer.error.connect(lambda e: self.txt_report_en.setText(f"❌ LỖI AI PHÂN TÍCH: {e}"))
        
        self.ai_analyzer.start()


    # [HÀM XỬ LÝ KẾT QUẢ AI TRẢ VỀ]
    def handle_analysis_result(self, data, type_unused=None):
        # type_unused là tham số thừa do signal cũ, có thể bỏ qua
        
        if isinstance(data, dict):
            self.txt_report_en.setText(data.get('en', ''))
            self.txt_report_vi.setText(data.get('vi', ''))

            # 2. [MỚI] Điền JSON vào ô thứ 3
            import json
            meta = data.get('meta', {})
            # Format JSON cho đẹp (indent=2)
            pretty_json = json.dumps(meta, indent=2, ensure_ascii=False)
            self.txt_report_json.setText(pretty_json)

            # Cập nhật Skeleton vào gói tin
            if hasattr(self, 'current_spy_data'):
                self.current_spy_data['skeleton'] = data.get('en', '')
                
                # Merge thêm meta từ AI phân tích được (nếu có)
                ai_meta = data.get('meta', {})
                if ai_meta: self.current_spy_data.update(ai_meta)

            print(f"✅ Đã phân tích xong: {self.current_spy_data.get('root_keyword')}")
            
            # [QUAN TRỌNG] Lưu lịch sử ngay lập tức
            self.save_spy_history_to_disk()

            # --- [MỚI] MỞ KHÓA NÚT "LÊN KẾ HOẠCH" ---
            if hasattr(self, 'btn_plan'):
                self.btn_plan.setEnabled(True)
                self.btn_plan.setStyleSheet("background: #d35400; color: white; font-weight: bold;") # Màu cam Sáng
                self.btn_plan.setToolTip("✅ Dữ liệu đã sẵn sàng. Bấm để nhân bản!")
                
                # Hiệu ứng báo hiệu (Optional): Focus vào nút
                self.btn_plan.setFocus()

        else:
            self.txt_report_en.setText(str(data))

    # =========================================================================
    # UTILS: SAVE/LOAD & EXPORT
    # =========================================================================
    def export_table(self, table_widget):
        path, _ = QFileDialog.getSaveFileName(self, "Lưu file CSV", "", "CSV Files (*.csv)")
        if path:
            with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                headers = [table_widget.horizontalHeaderItem(i).text() for i in range(table_widget.columnCount())]
                writer.writerow(headers)
                for row in range(table_widget.rowCount()):
                    row_data = []
                    for col in range(table_widget.columnCount()):
                        item = table_widget.item(row, col)
                        row_data.append(item.text() if item else "")
                    writer.writerow(row_data)
            QMessageBox.information(self, "Thành công", "Đã xuất file Excel!")

    def save_history(self):
        # Lưu dữ liệu cơ bản của Tab 2 vào JSON để mở lại không mất
        data = []
        for i in range(self.tbl_videos.rowCount()):
            row = {
                "title": self.tbl_videos.item(i, 2).text(),
                "link": self.tbl_videos.item(i, 9).text(),
                "rating": self.tbl_videos.item(i, 7).text()
            }
            data.append(row)
        
        if not os.path.exists("VEO_DB"): os.makedirs("VEO_DB")
        with open("VEO_DB/radar_history.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def load_history(self):
        # Chỉ demo load lại nếu file tồn tại
        if os.path.exists("VEO_DB/radar_history.json"):
            # Logic load lại dữ liệu vào bảng (Simplified)
            pass
    
    # [MỚI] Tự động điền Prompt mẫu khi chọn QG/Chủ đề
    #def update_prompt_target_template(self):
        #QTimer.singleShot(200, self._real_update_prompt) # Delay xíu để combo cập nhật xong

    def _real_update_prompt(self):
        # Hàm làm sạch: Bỏ emoji, bỏ ngoặc đơn, chỉ lấy tên tiếng Anh gốc
        def clean_input_string(text):
            # Tách theo dấu ( hoặc dấu - để lấy phần đầu (VD: "Ocean & Water" từ "🌊 Ocean & Water (Sóng nước)")
            if "(" in text: text = text.split("(")[0]
            if "---" in text: return "" # Bỏ qua các dòng tiêu đề format
            # Xóa emoji và ký tự lạ
            text = re.sub(r'[^\w\s&,]', '', text) 
            return text.strip()
        
        # 1. Lấy list và LÀM SẠCH DATA ngay lập tức
        raw_countries = self.cb_country.get_checked_items()
        clean_countries = [c.split("~")[0].strip() for c in raw_countries] # Cắt bỏ phần tiền
        clean_codes = []
        for c in raw_countries:
            # Giả sử format là "us Hoa Kỳ (En)", ta chỉ cần lấy mã hoặc tên chuẩn
            # Cách an toàn nhất cho Prompt là lấy tên tiếng Anh hoặc Mã
            # Ở đây mình lấy phần đầu tiên: "us"
            code = c.split()[0].upper() 
            clean_codes.append(f"[{code}]")
            
        c_str = ", ".join(clean_countries) if clean_countries else "[US]"

        # Xử lý Topic
        raw_topics = self.cb_topic.get_checked_items()
        clean_topics_list = []
        for t in raw_topics:
            cleaned = clean_input_string(t)
            if cleaned: clean_topics_list.append(cleaned)
            
        t_str = ", ".join(clean_topics_list) if clean_topics_list else "General"
        
        # 3. [MỚI] Xử lý Nền Tảng
        # Lấy items đã chọn, nếu không chọn gì thì mặc định Youtube
        raw_platforms = self.cb_platform.get_checked_items()
        p_str = ", ".join(raw_platforms) if raw_platforms else "Youtube Long"

        # --- 3. MA TRẬN INTENT & CHIẾN THUẬT FACELESS (FULL OPTIMIZED) ---
        # Map này định hướng AI viết nội dung chuẩn Faceless cho từng ngách
        intent_hint = "Focus on: High Retention, Clickable Viral concepts."
        
        # Kiểm tra từng từ khóa trong t_str để gán Intent
        ts = t_str.lower()
        if "rain" in ts or "ocean" in ts or "healing" in ts or "meditation" in ts:
            intent_hint = "🎯 STRATEGY: Sleep Aid, Insomnia Relief, Focus Study, Stress Reduction (ASMR/Ambience)."
        elif "space" in ts or "universe" in ts or "geography" in ts:
            intent_hint = "🎯 STRATEGY: Cosmic Horror, Scale Comparisons, Future Paradoxes, 'Mind-blowing Facts'."
        elif "history" in ts or "ancient" in ts:
            intent_hint = "🎯 STRATEGY: Forgotten Empires, Dark Secrets, 'What they didn't teach you in school', Timeline breakdowns."
        elif "animal" in ts or "cat" in ts or "dog" in ts:
            intent_hint = "🎯 STRATEGY: Cute Aggression, Survival Instincts, Rare Behaviors, 'Try not to laugh', Heartwarming rescues."
        elif "scary" in ts or "crime" in ts or "mystery" in ts:
            intent_hint = "🎯 STRATEGY: High Curiosity Gap, Urban Legends, Unsolved Mysteries, Psychological Thriller vibes."
        elif "tech" in ts or "ai" in ts or "coding" in ts or "inventions" in ts:
            intent_hint = "🎯 STRATEGY: Productivity Hacks, 'Replace your job', Future Predictions, Tools You Need."
        elif "finance" in ts or "crypto" in ts:
            intent_hint = "🎯 STRATEGY: Wealth Mindset, Passive Income Realities, Market Crash Predictions, 'How rich people think'."
        elif "quote" in ts or "stoic" in ts:
            intent_hint = "🎯 STRATEGY: Life Lessons, Sigma Grindset, Mental Toughness, Philosophy for Modern Life."

        # 4. XÁC ĐỊNH LUẬT CHO TỪNG NHÓM CHỦ ĐỀ
        extra_rule = ""
        
        # NHÓM 1: BẮT BUỘC PHẢI THẬT (Tin tức, Lịch sử, Tài chính, Sức khỏe...)
        strict_topics = ["News", "Tin tức", "History", "Lịch sử", "Finance", "Tài chính", "Health", "Sức khỏe", "Facts", "Sự thật", "Tech", "Công nghệ", "Real Estate", "Bất động sản", "Science", "Khoa học", "Crime", "Vụ án"]
        
        # NHÓM 2: CẦN THẬT NHƯNG ĐƯỢC CẢM XÚC (Sách, Podcast, Vlog)
        semi_topics = ["Book", "Sách", "Podcast", "Tâm sự", "Cooking", "Nấu ăn", "Vlog", "Du lịch"]
        
        # Kiểm tra xem chủ đề hiện tại thuộc nhóm nào
        is_strict = any(k in t_str for k in strict_topics)
        is_semi = any(k in t_str for k in semi_topics)
        
        if is_strict:
            extra_rule = (
                "🚨 STRICT TRUTH POLICY: The content MUST be based on REAL EVENTS, HISTORICAL FACTS, or VERIFIED DATA.\n"
                "- DO NOT invent fake news or fake historical events.\n"
                "- For 'Crime/Vụ án': Must be a TRUE CRIME case.\n"
                "- For 'Science/Finance': Must be scientifically/financially accurate.\n"
            )
        elif is_semi:
            extra_rule = (
                "🌟 AUTHENTICITY POLICY: Content should be based on real experiences or books, but you can focus on EMOTIONAL VALUE and PERSONAL PERSPECTIVE.\n"
                "- Titles should trigger curiosity but remain honest to the source material.\n"
            )
        else:
            # NHÓM 3: GIẢI TRÍ (Ma, Hài, Kids...) -> Thoải mái sáng tạo
            extra_rule = (
                "✨ CREATIVE FREEDOM: Focus purely on ENTERTAINMENT VALUE, VIRALITY, and EMOTIONAL HOOKS.\n"
                "- For 'Ghost/Horror': You can create fictional scary stories (Creepypasta style).\n"
                "- For 'Kids/Funny': Focus on fun, engagement, and retention.\n"
            )
        
        # Prompt Target Template (QUAN TRỌNG: Yêu cầu AI dùng ngôn ngữ bản địa)
        template = (
            f"ROLE: Expert YouTube Strategist & Viral Content Creator for [{p_str}].\n"
            f"GOAL: Discover high-potential, low-competition 'Blue Ocean' keywords for the topic:[{t_str}].\n"
            f"TARGET MARKET CODES: {c_str} (Output MUST be in the Native Language of each target code).\n"
            f"{intent_hint}\n"
            f"\n"
            f"TASK: Generate 20 high-potential 'Long-tail Keywords' for the topic: [{t_str}].\n"
            f"CRITICAL RULE 1 (DISTRIBUTION): You MUST divide the 20 keywords EVENLY among the target markets: {c_str} (e.g., if 3 countries -> ~7 keywords each).\n"
            f"CRITICAL RULE 2 (COLUMN ALIGNMENT): The first column must be the specific sub-topic of [{t_str}], NOT a random genre.\n"
            f"CRITICAL RULE 3 (EXACT CODE MATCHING): In the [CountryCode] column, you MUST use the EXACT code provided in Target Markets (e.g. if I ask for [NO], you output [NO]).\n"
            f"- If I ask for [NO], you MUST write [NO]. Do not write [Norway] or [NA].\n"
            f"- If I ask for [TW], you MUST write [TW]. Do not write [Zh] or [Taiwan].\n"
            f"\n"
            f"{extra_rule}"
            f"\n"
            f"CRITICAL REQUIREMENTS:\n"
            f"1. PLATFORM OPTIMIZATION: Tailor keywords/titles specifically for [{p_str}] algorithm (e.g., Searchable for YouTube, Viral/Hooky for TikTok/Shorts).\n"
            f"2. NATIVE LANGUAGE: For each target country, Key & Title MUST be in their NATIVE SCRIPT (e.g., Japan -> Kanji, Vietnam -> Vietnamese).\n"
            f"3. FORMATTING RULE: Do NOT include the language name (e.g. 'English', 'Vietnamese') as a separate column. Strictly follow the table format below.\n"
            f"4. TITLE STRATEGY: The Suggested Title must be 'High CTR' & 'Click-worthy' (combining SEO Keyword + Emotional Hook/Benefit/Curiosity). NOT just a boring description.\n"
            f"5. RULE: The Native Viral Title must NOT be a direct translation. It must use local 'Clickbait' triggers (Shock, Numbers, Negativity) relevant to that culture.\n"
            f"6. TRANSLATION: Provide Vietnamese meaning for both Keyword and Title.\n"
            f"\n"
            f"ADDITIONAL STRICT RULES:\n"             
            f"- Each keyword must be a TRUE long-tail keyword (minimum 3–5 words) suited for [{p_str}].\n"
            f"- For non-space languages (JP, CN, KR), keywords must be long descriptive phrases, not short noun phrases.\n"
            f"- Keywords and Titles MUST be 100% native language. NO English mixing.\n"
            f"- Do NOT include any explanations, translations, or English text in parentheses within the Native fields.\n"
            f"- Competition is estimated for YouTube search (Low / Medium only).\n"
            f"- NO emojis, NO hashtags, NO bullet points, NO explanations.\n"
            f"- Output ONLY the formatted keyword list.\n"
            f"\n"
            f"OUTPUT FORMAT (Strictly 6 columns separated by '|'):\n"
            f"[Specific Niche] | [CountryCode] | Native Keyword | VN Meaning of Key | Native Viral Title | VN Meaning of Title\n"
            f"\n"
            f"--- LEARN FROM THESE EXAMPLES (Strictly follow the table structure): ---\n"
            f"Finance | [US] | Passive Income Ideas 2025 | Ý tưởng thu nhập thụ động 2025 | 7 Passive Income Streams That Make $100/Day | 7 nguồn thu nhập thụ động kiếm $100/ngày\n"
            f"Cooking | [VN] | Cách nấu phở bò ngon | Cách nấu phở bò ngon | Bí quyết nấu Phở Bò gia truyền ngon như ngoài hàng | Bí quyết nấu Phở Bò gia truyền ngon như ngoài hàng\n"
            f"Gadgets | [JP] | 100均で買える便利グッズ | Đồ tiện ích mua ở cửa hàng 100 yên | ダイソーの神グッズ！生活が変わるアイテム10選 | Đồ thần thánh ở Daiso! 10 món thay đổi cuộc sống\n"
            f"Horror | [SA] | قصص رعب حقيقية مخيفة | Chuyện ma có thật đáng sợ | قصص رعب حقيقية حدثت بالفعل.. لن تستطيع النوم | Chuyện ma có thật đã xảy ra.. bạn sẽ không thể ngủ\n"
            f"Yoga | [IN] | वजन कम करने के लिए योग | Yoga để giảm cân | 10 मिनट में पेट की चर्बी घटाएं | Giảm mỡ bụng chỉ trong 10 phút tập luyện\n"
            f"---\n"
            f"Strictly following the STRUCTURE and NATIVE LANGUAGE rules above, generate the keyword list for {c_str} on the topic [{t_str}] now:"
        )
        self.txt_prompt_target.setText(template)

    # [MỚI] Cập nhật Label hiển thị công nghệ AI đang dùng
    def update_ai_tech_label(self):
        try:
            ai_factory = AIFactory()
            config = ai_factory.get_worker_config("keyword_researcher")
            if config:
                prov = config.get("provider", "Unknown").upper()
                mod = config.get("model", "Default")
                self.lbl_ai_tech.setText(f"🤖 AI: {prov} ({mod})")
            else:
                self.lbl_ai_tech.setText("🤖 AI: Mặc định (Google)")
        except:
            self.lbl_ai_tech.setText("🤖 AI: Error")

    # [FIX FULLSCREEN] Hàm xử lý Phóng to / Thu nhỏ chuẩn
    def toggle_fullscreen(self, table_widget, btn_widget):
        if btn_widget.isChecked():
            # --- TRƯỜNG HỢP 1: BẬT FULLSCREEN ---
            
            # 1. Lưu lại sự kiện đóng cũ (để sau này trả lại)
            if not hasattr(table_widget, '_original_close_event'):
                table_widget._original_close_event = table_widget.closeEvent
            
            # 2. Định nghĩa sự kiện đóng mới (Monkey Patch)
            # Logic: Khi bấm X, thay vì tắt bảng, ta chỉ đơn giản là "Bỏ tích" nút Fullscreen
            def custom_close_event(event):
                event.ignore() # Ngăn không cho cửa sổ bị hủy
                btn_widget.setChecked(False) # Bỏ tích nút -> Tự động kích hoạt logic Thu nhỏ bên dưới
                
            table_widget.closeEvent = custom_close_event
            
            # 3. Biến thành cửa sổ riêng và phóng to
            table_widget.setWindowFlags(Qt.WindowType.Window)
            table_widget.showMaximized()
            
        else:
            # --- TRƯỜNG HỢP 2: TẮT FULLSCREEN (THU NHỎ) ---
            
            # 1. Trả về dạng Widget con (không phải cửa sổ riêng nữa)
            table_widget.setWindowFlags(Qt.WindowType.Widget)
            
            # 2. Trả lại sự kiện đóng cũ (tránh lỗi về sau)
            if hasattr(table_widget, '_original_close_event'):
                table_widget.closeEvent = table_widget._original_close_event
            
            # 3. Gắn lại vào Layout cũ (Quan trọng nhất để không bị mất bảng)
            # Phải xác định đang ở Tab nào để gắn vào đúng chỗ
            current_tab_idx = self.tabs.currentIndex()
            table_widget.updateGeometry()

            if current_tab_idx == 0: # Tab 1 (Niche Finder)
                # Layout của Tab 1: Vị trí index 2 (Sau GroupBox và trước Thanh công cụ)
                # CEO kiểm tra kỹ layout tab 1, thường là vị trí số 2 hoặc 3
                self.tab_niche.layout().insertWidget(2, table_widget)
                
            elif current_tab_idx == 1: # Tab 2 (Opportunity Hunter)
                # Tab 2 thường có Input(0) -> Progress(1) -> Toolbar(2) -> Table(3)
                self.tab_hunter.layout().insertWidget(3, table_widget)
                
            elif current_tab_idx == 2: # Tab 3 (Spy)
                # Tab 3 thường nằm cuối
                self.tab_spy.layout().addWidget(table_widget)

            # 4. Hiện bảng lên
            table_widget.show()

    # [MỚI] Hàm Tìm kiếm chung
    def search_table(self, table_widget):
        text, ok = QInputDialog.getText(self, "Tìm kiếm", "Nhập từ khóa:")
        if ok and text:
            for i in range(table_widget.rowCount()):
                match = False
                for j in range(table_widget.columnCount()):
                    item = table_widget.item(i, j)
                    if item and text.lower() in item.text().lower():
                        match = True; break
                table_widget.setRowHidden(i, not match)
    
    # --- [BƯỚC 2] HÀM HIỂN THỊ LOG LÊN GIAO DIỆN ---
    def handle_log_message(self, msg):
        # 1. In ra màn hình đen (Console) để debug — an toàn cho Windows cp1252
        try:
            print(f"System Log: {msg}")
        except UnicodeEncodeError:
            print(f"System Log: {msg.encode('ascii', 'replace').decode()}")
        
        # 2. Cập nhật lên dòng chữ vàng (lbl_ai_tech)
        # Giữ lại icon robot cho đẹp
        self.lbl_ai_tech.setText(f"🤖 {msg}")
        
        # 3. Phát tín hiệu ra ngoài (nếu Main Window cần bắt)
        self.log_signal.emit(msg)

    # [FIX LAG] Hàm kích hoạt bộ đệm
    def trigger_update_smooth(self):
        # Mỗi lần bấm, reset lại đồng hồ. 
        # Nếu bấm nhanh quá, đồng hồ đếm lại từ đầu -> Prompt chưa update vội -> Giao diện mượt
        self.debounce_timer.start()
    
    def update_transfer_info(self):
        """Hàm quét bảng để xem đã chọn bao nhiêu từ khóa"""
        selected_count = 0
        preview_list = []
        
        # Quét từng dòng trong bảng
        rows = self.tbl_keywords.rowCount()
        for r in range(rows):
            # Cột 0 là Checkbox
            item_chk = self.tbl_keywords.item(r, 0)
            
            # Nếu ô đó tồn tại và ĐANG TÍCH
            if item_chk and item_chk.checkState() == Qt.CheckState.Checked:
                selected_count += 1
                # Lấy Từ khóa (Cột 5) để hiển thị nháp
                kw = self.tbl_keywords.item(r, 5).text()
                preview_list.append(kw)

        # Cập nhật giao diện bên dưới (lbl_transfer_list - CEO kiểm tra lại tên biến này trong code layout)
        # Giả sử tên biến label bên dưới là self.lbl_step2_status (hoặc tên tương tự CEO đã đặt)
        
        if selected_count == 0:
            self.lbl_step2_status.setText("Chưa chọn mục nào...")
            # Nếu có nút "Chuyển sang Bước 2" thì disable nó đi
            # self.btn_next_step.setEnabled(False) 
        else:
            # Hiện 3 cái đầu làm mẫu
            text_preview = ", ".join(preview_list[:3])
            more = f"... (+{selected_count - 3} cái nữa)" if selected_count > 3 else ""
            
            msg = f"✅ ĐÃ CHỌN: {selected_count} Ý TƯỞNG\n👉 {text_preview}{more}"
            self.lbl_step2_status.setText(msg)
            self.lbl_step2_status.setStyleSheet("color: #00ffea; font-weight: bold;")
            # self.btn_next_step.setEnabled(True)
    
    # [MỚI] Bấm vào ô là tích luôn (Khỏi phải ngắm vào cái hộp bé tí)
    def on_cell_clicked_toggle(self, row, col):
        if col == 0: return # Bấm vào cột 0 thì nó tự xử lý rồi
        item = self.tbl_keywords.item(row, 0)
        if item:
            new_state = Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked
            item.setCheckState(new_state)

    # [MỚI] Xóa an toàn (Có backup)
    def clear_table_safe(self):
        # Backup dữ liệu hiện tại trước khi xóa (nếu chưa có)
        if self.tbl_keywords.rowCount() > 0:
             # Logic backup đơn giản là giữ lại list gốc từ AI
             pass 
        self.tbl_keywords.setRowCount(0)
        self.update_transfer_info()

    # [MỚI] Khôi phục
    def restore_table(self):
        if not self.backup_data_list:
            QMessageBox.information(self, "Trống", "Không có dữ liệu cũ để khôi phục!")
            return
        self.on_keywords_generated(self.backup_data_list, 'keywords')

    # [MỚI] Tìm kiếm Real-time (Ẩn/Hiện dòng)
    def filter_table(self, table, text):
        text = text.lower()
        for i in range(table.rowCount()):
            match = False
            # Quét cột Từ khóa (5) và Title (7) và Nghĩa (6,8)
            for col in [3, 5, 6, 7, 8]: 
                item = table.item(i, col)
                if item and text in item.text().lower():
                    match = True; break
            table.setRowHidden(i, not match)

    # [SỬA] Cập nhật danh sách chuyển (Liệt kê dòng)
    def update_transfer_info(self):
        selected_count = 0
        preview_text = ""
        
        rows = self.tbl_keywords.rowCount()
        for r in range(rows):
            item_chk = self.tbl_keywords.item(r, 0)
            if item_chk and item_chk.checkState() == Qt.CheckState.Checked:
                selected_count += 1
                kw = self.tbl_keywords.item(r, 5).text()
                # country = self.tbl_keywords.item(r, 3).text() # Nếu muốn hiện cả mã nước
                preview_text += f"• {kw}\n"

        if selected_count == 0:
            self.lbl_step2_status.setText("Chưa chọn mục nào. Hãy tích chọn ở bảng trên...")
        else:
            msg = f"✅ ĐÃ CHỌN: {selected_count} TỪ KHÓA\n{preview_text}"
            self.lbl_step2_status.setText(msg)
            self.lbl_step2_status.setStyleSheet("color: #00ffea; font-family: Consolas; font-size: 11px;")
    
    def toggle_all_checkboxes(self, checked):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        
        # Tạm ngắt kết nối để không kích hoạt hàm update liên tục gây lag
        self.tbl_keywords.blockSignals(True)
        
        for i in range(self.tbl_keywords.rowCount()):
            item = self.tbl_keywords.item(i, 0)
            if item:
                item.setCheckState(state)
                # [MỚI] Tô màu hàng loạt
                self.tint_row_color(self.tbl_videos, i, checked)
        self.tbl_keywords.blockSignals(False)
        
        # Cập nhật lại số lượng đã chọn
        self.update_transfer_info()
    
    # --- TÍNH NĂNG LƯU LỊCH SỬ (PERSISTENCE) ---
    def save_keyword_history_to_disk(self, data_list):
        """Lưu danh sách từ khóa xuống ổ cứng"""
        try:
            if not os.path.exists("VEO_DB"): os.makedirs("VEO_DB")
            with open("VEO_DB/radar_keywords_history.json", "w", encoding="utf-8") as f:
                json.dump(data_list, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Lỗi lưu lịch sử: {e}")

    def load_keyword_history_from_disk(self):
        """Đọc danh sách từ khóa từ ổ cứng lên biến nhớ (nhưng chưa hiện ra bảng ngay)"""
        try:
            if os.path.exists("VEO_DB/radar_keywords_history.json"):
                with open("VEO_DB/radar_keywords_history.json", "r", encoding="utf-8") as f:
                    self.backup_data_list = json.load(f)
        except Exception as e:
            print(f"Lỗi đọc lịch sử: {e}")
            self.backup_data_list = []
    
    # --- [NÂNG CẤP] MENU CHUỘT PHẢI ---
    def setup_context_menu(self):
        # Cần gọi hàm này ở cuối _setup_tab_niche: self.setup_context_menu()
        self.tbl_keywords.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tbl_keywords.customContextMenuRequested.connect(self.show_context_menu)

    def show_context_menu(self, pos):
        menu = QMenu(self)
        
        # Action 1: Copy Từ khóa
        action_copy = QAction("📋 Copy Từ khóa này", self)
        action_copy.triggered.connect(lambda: self.copy_cell_content(0)) # 0 là tham số giả
        menu.addAction(action_copy)
        
        # Action 2: Tìm Google nhanh (Kiểm tra xem keyword này hot ko)
        action_google = QAction("🌍 Tìm trên Google", self)
        action_google.triggered.connect(self.search_google_quick)
        menu.addAction(action_google)
        
        menu.addSeparator()
        
        # Action 3: Xóa dòng này
        action_delete = QAction("🗑️ Xóa dòng này", self)
        action_delete.triggered.connect(self.delete_current_row)
        menu.addAction(action_delete)
        
        menu.exec(self.tbl_keywords.viewport().mapToGlobal(pos))

    def copy_cell_content(self, _):
        row = self.tbl_keywords.currentRow()
        if row >= 0:
            kw = self.tbl_keywords.item(row, 5).text() # Cột 5 là Keyword
            QApplication.clipboard().setText(kw)

    def search_google_quick(self):
        row = self.tbl_keywords.currentRow()
        if row >= 0:
            kw = self.tbl_keywords.item(row, 5).text()
            url = QUrl(f"https://www.google.com/search?q={kw}")
            QDesktopServices.openUrl(url)

    def delete_current_row(self):
        row = self.tbl_keywords.currentRow()
        if row >= 0:
            self.tbl_keywords.removeRow(row)
            self.update_transfer_info() # Cập nhật lại số lượng

    def save_hunter_history_to_disk(self):
        """Lưu dữ liệu bảng Tab 2 xuống file JSON (Đã Fix đúng cột)"""
        table_rows = []
        rows = self.tbl_videos.rowCount()
        
        for i in range(rows):
            try:
                # Helper function để lấy text an toàn (tránh lỗi nếu ô rỗng)
                def get_text(col_idx):
                    item = self.tbl_videos.item(i, col_idx)
                    return item.text() if item else ""

                # MAPPING CHUẨN (Cập nhật mới nhất):
                # 0:Check, 1:STT, 2:Thumb, 3:Title, 4:Topic, 5:Country, 6:Duration, 
                # 7:Date, 8:Speed, 9:View, 10:Sub, 11:V/S, 12:Rev, 13:Rate, 
                # 14:Key, 15:Meaning, 16:Link(Ẩn)
                
                # Lưu ý: Cột 2 là Widget ảnh, ta không lấy text được. 
                # (Phiên bản này ta tạm bỏ qua lưu ảnh để file nhẹ, hoặc lưu URL nếu có hidden data)
                
                row_data = {
                    # --- CÁC CỘT HIỂN THỊ ---
                    "title": get_text(3),
                    "topic_label": get_text(4),   # Lưu chủ đề
                    "country_label": get_text(5), # Lưu quốc gia
                    "duration": get_text(6),
                    "date_display": get_text(7),  # Lưu text hiển thị ngày
                    "velocity": get_text(8),
                    "views": get_text(9),
                    "subs": get_text(10),
                    "vs_ratio": get_text(11),
                    "revenue": get_text(12),
                    "rating": get_text(13),
                    
                    # --- 3 CỘT QUAN TRỌNG BỊ MẤT ---
                    "keyword": get_text(14),      # Cột 14
                    "meaning_vi": get_text(15),   # Cột 15
                    "link": get_text(16),         # Cột 16 (Link ẩn)

                    # --- META DATA (Để sort lại cho đúng) ---
                    # Lưu màu sắc rating
                    "color_hex": "#ffffff" 
                }
                
                # Lấy màu thực tế của cột Rating
                item_rate = self.tbl_videos.item(i, 10)
                if item_rate:
                    row_data["color_hex"] = item_rate.foreground().color().name()
                table_rows.append(row_data)
            except Exception as e:
                print(f"Lỗi dòng {i}: {e}")

        # 2. [QUAN TRỌNG] Lấy Context hiện tại (Chủ đề & Quốc gia)
        # Để khi mở lại tool, nó biết lần trước mình đang làm việc với chủ đề nào
        context_data = {
            "niche": getattr(self, 'cached_niche_context', ""),
            "country": getattr(self, 'cached_country_context', "")
        }

        # 3. Đóng gói chung vào 1 cục (Package)
        package = {
            "version": "4.0",
            "context": context_data,   # Lưu ý cái này
            "table_data": table_rows   # Dữ liệu bảng
        }        

        try:
            if not os.path.exists("VEO_DB"): os.makedirs("VEO_DB")
            with open("VEO_DB/radar_hunter_history.json", "w", encoding="utf-8") as f:
                json.dump(package, f, ensure_ascii=False, indent=4)
            print("✅ Đã lưu lịch sử Hunter thành công!")
        except Exception as e:
            print(f"❌ Lỗi lưu file: {e}")

    # [HÀM SỬA LỖI] KHÔI PHỤC LỊCH SỬ CHUẨN
    def load_hunter_history_from_disk(self):
        path = "VEO_DB/radar_hunter_history.json"
        if not os.path.exists(path): return

        try:
            with open(path, "r", encoding="utf-8") as f:
                package = json.load(f)
            
            # Xử lý tương thích ngược
            if isinstance(package, list): data = package # File cũ
            else: data = package.get("table_data", [])

            self.tbl_videos.setRowCount(0)
            self.tbl_videos.setSortingEnabled(False) # Tắt sort khi load

            for i, item in enumerate(data):
                self.tbl_videos.insertRow(i)

                # --- HELPER FUNCTION: TẠO ITEM CHUẨN (Sortable) ---
                def make_item(value, center=True, color=None, bold=False, sort_value=None):
                    it = SortableItem(str(value))
                    if sort_value is not None: 
                        it.setData(Qt.ItemDataRole.UserRole, sort_value)
                    
                    if center: it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if color: it.setForeground(QBrush(QColor(color)))
                    if bold: it.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                    return it
                # ------------------------------------------------

                # 0. Checkbox
                chk = QTableWidgetItem()
                chk.setCheckState(Qt.CheckState.Unchecked)
                chk.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tbl_videos.setItem(i, 0, chk)

                # 1. STT (Sort theo số i+1)
                self.tbl_videos.setItem(i, 1, make_item(str(i + 1), sort_value=i+1))

                # 2. Thumb (Placeholder vì không lưu ảnh)
                lbl = QLabel("📷 Loaded")
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.setStyleSheet("background: #222; color: #555; border: 1px solid #444;")
                self.tbl_videos.setCellWidget(i, 2, lbl)

                # 3. Title (Căn trái)
                t_item = QTableWidgetItem(item.get('title', ''))
                t_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.tbl_videos.setItem(i, 3, t_item)

                # 4, 5, 6: Topic, Country, Duration
                self.tbl_videos.setItem(i, 4, make_item(item.get('topic_label', '')))
                self.tbl_videos.setItem(i, 5, make_item(item.get('country_label', '')))
                self.tbl_videos.setItem(i, 6, make_item(item.get('duration', '')))

                # 7 -> 12: Các chỉ số
                # Cố gắng parse số để sort cho chuẩn nếu có thể
                days_old_sort = 999 
                try: days_old_sort = int(item.get('days_old', 999)) # Cần lưu days_old trong JSON lúc save
                except: pass
                
                self.tbl_videos.setItem(i, 7, make_item(item.get('date_display', ''), sort_value=days_old_sort))
                
                self.tbl_videos.setItem(i, 8, make_item(item.get('velocity', '')))
                self.tbl_videos.setItem(i, 9, make_item(item.get('views', '')))
                self.tbl_videos.setItem(i, 10, make_item(item.get('subs', '')))

                # 11. V/S (Tô màu lại & Sort đúng)
                vs_val_str = item.get('vs_ratio', '0')
                vs_val_float = 0.0
                vs_color = "#ffffff"
                try:
                    vs_val_float = float(vs_val_str)
                    if vs_val_float >= 10: vs_color = "#00ffea"
                    elif vs_val_float >= 3: vs_color = "#f1c40f"
                except: pass
                
                # [FIX LỖI] Truyền đúng giá trị vs_val_str, sort bằng vs_val_float
                self.tbl_videos.setItem(i, 11, make_item(vs_val_str, color=vs_color, bold=True, sort_value=vs_val_float))

                # 12. Revenue
                self.tbl_videos.setItem(i, 12, make_item(item.get('revenue', '')))

                # 13. Rating (Khôi phục màu + điểm sort)
                rate_txt = item.get('rating', '')
                rate_col = item.get('color_hex', '#ffffff')
                
                # Lấy lại điểm sort (money_score) nếu có
                money_score = 0
                try: money_score = float(item.get('money_score', 0))
                except: pass
                
                self.tbl_videos.setItem(i, 13, make_item(rate_txt, color=rate_col, bold=True, sort_value=money_score))

                # --- 14, 15, 16: KHÔI PHỤC 3 CỘT CUỐI ---
                self.tbl_videos.setItem(i, 14, QTableWidgetItem(item.get('keyword', '')))
                self.tbl_videos.setItem(i, 15, QTableWidgetItem(item.get('meaning_vi', '')))
                
                link_url = item.get('link', '')
                self.tbl_videos.setItem(i, 16, QTableWidgetItem(link_url))

                # 17. Nút Xem
                if link_url:
                    btn_watch = QPushButton("▶ Xem")
                    btn_watch.setCursor(Qt.CursorShape.PointingHandCursor)
                    btn_watch.setStyleSheet("background: #333; color: #4da6ff; border: 1px solid #555; border-radius: 4px;")
                    # Dùng biến default arg u=link_url để tránh lỗi lambda
                    btn_watch.clicked.connect(lambda checked, u=link_url: QDesktopServices.openUrl(QUrl(u)))
                    self.tbl_videos.setCellWidget(i, 17, btn_watch)

            self.tbl_videos.setSortingEnabled(True) # Bật lại sort
            # self.tbl_videos.resizeRowsToContents() # Tùy chọn: Bật lên nếu muốn dòng tự giãn (có thể làm chậm nếu list dài)
            self.tbl_videos.scrollToBottom()

            print(f"✅ Đã khôi phục {len(data)} dòng từ lịch sử.")

        except Exception as e:
            print(f"Lỗi load history: {e}")
            # Nếu lỗi quá nặng, tự động reset file để lần sau không bị nữa
            try:
                # os.remove(path) # Tạm thời comment lại, không xóa vội để debug
                print("⚠️ File lịch sử bị lỗi format.")
            except: pass
            
    def clear_hunter_safe(self):
        """Xóa bảng nhưng giữ backup trong RAM để khôi phục"""
        row_count = self.tbl_videos.rowCount()
        if row_count > 0:
            # 1. Backup dữ liệu vào RAM trước khi xóa
            self.temp_hunter_backup = []
            for i in range(row_count):
                # Logic lấy data từng dòng (như hàm save_history cũ)
                # Để nhanh gọn, CEO chỉ cần biết là có dữ liệu
                pass 
            
            # [CÁCH TỐT HƠN]: Không xóa file json trên đĩa
            # Chỉ xóa trên giao diện
            self.tbl_videos.setRowCount(0)
            QMessageBox.information(self, "Đã xóa", "Đã xóa danh sách trên màn hình.\n(File lịch sử cũ vẫn còn, bấm 'Khôi phục' để lấy lại).")
        else:
             self.tbl_videos.setRowCount(0)

    # --- LOGIC REMIX SCRIPT (MỚI) ---
    def run_script_remix(self):
        # Lấy thông tin từ báo cáo phân tích để làm đầu vào
        analysis_data = self.txt_report_en.toPlainText()
        if not analysis_data or "⏳" in analysis_data:
            QMessageBox.warning(self, "Chưa có dữ liệu", "Vui lòng chạy 'Phân Tích Chiến Lược' trước!")
            return
            
        self.txt_script.setText("⏳ AI ĐANG VIẾT LẠI KỊCH BẢN... (Chờ chút nhé, đang sáng tạo...)")
        
        # Gọi Worker với mode 'remix'
        # Truyền vào cả Link video gốc và Bài phân tích
        data = {
            'url': self.txt_video_url.text(),
            'analysis': analysis_data
        }
        self.ai_remixer = RadarAIWorker('remix', data)
        self.ai_remixer.finished.connect(lambda res, _: self.txt_script.setText(res))
        self.ai_remixer.error.connect(lambda e: self.txt_script.setText(f"Lỗi: {e}"))
        self.ai_remixer.start()

    def save_remix_script(self):
        content = self.txt_script.toPlainText()
        if not content: return
        
        path, _ = QFileDialog.getSaveFileName(self, "Lưu Kịch Bản", "KichBan_Moi.txt", "Text Files (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            QMessageBox.information(self, "Xong", "Đã lưu kịch bản về máy!")
    
    # [MỚI] Hàm chọn tất cả cho Tab 2
    def toggle_all_hunter(self, checked):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self.tbl_videos.blockSignals(True) # Tắt tín hiệu để ko lag
        for i in range(self.tbl_videos.rowCount()):
            item = self.tbl_videos.item(i, 0)
            if item:
                item.setCheckState(state)
                # [MỚI] Tô màu hàng loạt
                self.tint_row_color(self.tbl_videos, i, checked)
        self.tbl_videos.blockSignals(False)
    
    # [MỚI] Hàm này đảm bảo bấm vào khoảng trắng của ô Checkbox cũng sẽ tích/bỏ tích
    def on_hunter_cell_clicked(self, row, col):
        # [FIX] Bấm bất kỳ đâu cũng toggle checkbox ở cột 0
        # Trừ khi bấm vào cột Link (13) hoặc cột Xem (14) để tránh conflict
        if col in [13, 14]: return 
        item = self.tbl_videos.item(row, 0) # Luôn lấy item ở cột 0
        if item:
            if col != 0:
                new_state = Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked
                item.setCheckState(new_state)
            # [MỚI] Tô màu
            is_checked = (item.checkState() == Qt.CheckState.Checked)
            self.tint_row_color(self.tbl_videos, row, is_checked)

    def open_video_on_double_click(self, row, col):
        # Lấy link ở cột 13
        item = self.tbl_videos.item(row, 13) # Index 13 là link
        # Hoặc lấy widget nút bấm
        if item and "http" in item.text():
             QDesktopServices.openUrl(QUrl(item.text()))
        else:
            # Fallback nếu cột 13 bị ẩn hoặc rỗng, thử lấy từ widget
            # (Logic tuỳ chỉnh của bạn)
            pass
    def stop_hunter_scan(self):
        """Hàm xử lý khi bấm nút Hủy"""
        if hasattr(self, 'yt_worker') and self.yt_worker.isRunning():
            # 1. Ra lệnh dừng Worker
            self.yt_worker.stop()
            self.yt_worker.is_running = False # Chắc chắn dừng vòng lặp

            # 2. Ngắt kết nối tín hiệu 'finished' để tránh nó tự động Sort/Popup thông báo 'Hoàn tất'
            try: self.yt_worker.finished_signal.disconnect()
            except: pass
            
            # 3. Cập nhật giao diện
            self.lbl_scan_status.setText("🛑 Đã dừng quét (Dữ liệu được bảo toàn).")
            self.btn_stop_scan.setEnabled(False)
            self.reset_hunter_button()
            
            # 4. Bật lại tính năng Sort cho bảng (để user lọc đống đã quét được)
            self.tbl_videos.setSortingEnabled(True)
            self.tbl_videos.sortItems(13, Qt.SortOrder.DescendingOrder)

            # 5. Lưu lại những gì đã tìm được
            self.save_hunter_history_to_disk()

            # 6. Mở khóa nút Quét lại
            self.reset_hunter_button()


    # Hàm bấm nhạy cho Tab 1 (giống Tab 2)
    def on_niche_cell_clicked(self, row, col):
        # [FIX] Bấm bất kỳ đâu cũng toggle checkbox ở cột 0
        item = self.tbl_keywords.item(row, 0) # Luôn lấy item ở cột 0
        if item:
            # Logic đảo trạng thái cũ
            if col != 0: # Nếu ko bấm trực tiếp vào checkbox thì đảo
                new_state = Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked
                item.setCheckState(new_state)
            
            # [MỚI] Tô màu ngay lập tức
            is_checked = (item.checkState() == Qt.CheckState.Checked)
            self.tint_row_color(self.tbl_keywords, row, is_checked)

    # [MỚI] Hàm kiểm tra lịch sử sản xuất (Chống trùng lặp)
    def check_production_history(self, topic, country):
        """
        Trả về: (Trùng hay không, Ngày tạo gần nhất)
        """
        path = "VEO_DB/production_log.json"
        if not os.path.exists(path): return False, None
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                history = json.load(f)
            
            # Tạo key định danh: Topic + Country
            # VD: "Rain on Roof_Vietnam"
            key = f"{topic}_{country}"
            
            if key in history:
                return True, history[key]['date']
        except: pass
        return False, None

    # [MỚI] Hàm ghi lại lịch sử sản xuất
    def log_production_history(self, topic, country):
        path = "VEO_DB/production_log.json"
        history = {}
        
        # Load cũ
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except: pass
            
        # Ghi mới
        import datetime
        key = f"{topic}_{country}"
        history[key] = {
            "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "Created"
        }
        
        # Lưu lại
        with open(path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=4)
    
    def transfer_to_factory(self):
        # 1. Kiểm tra xem đã có dữ liệu Spy chưa
        if not hasattr(self, 'current_spy_data') or not self.current_spy_data:
            # Nếu chưa có biến (do chưa chạy), thử lấy từ ô text
            skeleton = self.txt_report_en.toPlainText()
            if not skeleton or "⏳" in skeleton:
                QMessageBox.warning(self, "Chưa có hàng", "Vui lòng chạy 'GIẢI MÃ DNA' (Nút hồng) trước!")
                return
            # Fallback thủ công nếu biến bị mất
            self.current_spy_data = {
                "skeleton": skeleton,
                "root_keyword": "Remix Video",
                "visual_style": "Cinematic",
                "url": self.txt_video_url.text()
            }

        # 2. Lấy cấu hình từ giao diện Tab 3 (Target)
        target_niche = self.cb_batch_niche.currentText()
        if "---" in target_niche: target_niche = "General Remix"

        # [QUAN TRỌNG] Lấy danh sách NHIỀU quốc gia đã tick
        target_langs = self.cb_batch_lang.get_checked_items()
        if not target_langs:
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng chọn ít nhất 1 Quốc gia/Ngôn ngữ!")
            return

        quantity = self.spin_quantity.value()

        # 3. Đóng gói kiện hàng (PROTOCOL SPY_RESULT)
        # Tạo danh sách n phần tử giống nhau (để Tab 4 tạo n dòng)
        payload_list = []
        skipped_countries = []

        for lang_str in target_langs:
            # Tách tên nước cho gọn (VD: "🇺🇸 Hoa Kỳ (En)..." -> "Hoa Kỳ")
            country_name = lang_str.split('(')[0].strip()
            
            # --- CHECK LỊCH SỬ TRÙNG LẶP ---
            is_dup, last_date = self.check_production_history(target_niche, country_name)
            
            if is_dup:
                # Hỏi ý kiến CEO (Chỉ hỏi 1 lần cho mỗi nước trùng)
                reply = QMessageBox.question(
                    self, 
                    "⚠️ CẢNH BÁO TRÙNG LẶP", 
                    f"Cặp bài trùng:\n🎭 Chủ đề: {target_niche}\n🌍 Quốc gia: {country_name}\n\n"
                    f"Đã từng tạo lúc: {last_date}.\n"
                    f"Bạn có chắc chắn muốn tạo thêm (có thể gây Spam) không?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.No:
                    skipped_countries.append(country_name)
                    continue # Bỏ qua nước này
            
            # [FIX] Lấy Platform động từ UI thay vì hardcode
            selected_platform = self.cb_platform.currentText()
            if not selected_platform or "..." in selected_platform:
                selected_platform = "Youtube Long" # Fallback
            
            base_data = {
                "topic": target_niche,          
                "country": country_name,         
                "platform": selected_platform,
                "key_vua": self.current_spy_data.get("root_keyword", "Spy Keyword"), # Key Vua AI tìm được
                "skeleton": self.current_spy_data.get("skeleton", ""),           # Khung xương
                "visual_style": self.current_spy_data.get("visual_style", ""),   # Style ảnh
                "thumbnail_url": self.current_spy_data.get("url", "")            # Link gốc để tham khảo
            }

            for _ in range(quantity):
                payload_list.append(base_data.copy())

            # Ghi log lịch sử ngay
            self.log_production_history(target_niche, country_name)

        # 4. Gửi hàng đi (Nếu có hàng)
        if not payload_list:
            if skipped_countries:
                QMessageBox.information(self, "Đã hủy", "Đã hủy toàn bộ thao tác do trùng lặp.")
            return

        # 4. GỌI SANG CONTENT TAB (Kết nối Liên Tab)
        # Cách này giả định CEO đã truyền content_tab vào radar_tab hoặc dùng parent
        try:
            # Tìm Content Tab thông qua cửa sổ chính (Cách an toàn nhất)
            main_win = self.window() 

            if hasattr(main_win, 'content_tab'):
                main_win.content_tab.receive_data_from_radar(payload_list)
                # Logic tìm Tab Content thông minh
                target_tab = None
                # Chuyển tab cho CEO thấy kết quả
                if hasattr(main_win, 'tabs'):
                    main_win.tabs.setCurrentWidget(main_win.content_tab)
                elif hasattr(main_win, 'tab_content'): target_tab = main_win.tab_content
                
                if target_tab:
                    target_tab.receive_data_from_radar(payload_list)

                # Chuyển tab
                if hasattr(main_win, 'switch_to_department'): main_win.switch_to_department(1)
                elif hasattr(main_win, 'tabs'): main_win.tabs.setCurrentWidget(target_tab)

                # Thông báo tổng kết
                msg = f"🚀 Đã chuyển {len(payload_list)} nhiệm vụ sang Nhà Máy!"
                if skipped_countries:
                    msg += f"\n\n(Đã bỏ qua {len(skipped_countries)} nước trùng lặp: {', '.join(skipped_countries)})"
                QMessageBox.information(self, "Thành công", msg)

            else:
                QMessageBox.warning(self, "Lỗi Kết Nối", "Không tìm thấy 'Content Tab'. Vui lòng kiểm tra file main.py")
        except Exception as e:
            QMessageBox.critical(self, "Lỗi System", f"Không thể gửi dữ liệu: {e}")

    # [MỚI] Hàm Reset Tab 1
    def reset_tab1_inputs(self):
        # Bỏ chọn Country
        model_c = self.cb_country.model
        for i in range(model_c.rowCount()): model_c.item(i).setCheckState(Qt.CheckState.Unchecked)
        self.cb_country._update_text()
        
        # Bỏ chọn Topic
        model_t = self.cb_topic.model
        for i in range(model_t.rowCount()): model_t.item(i).setCheckState(Qt.CheckState.Unchecked)
        self.cb_topic._update_text()
        
        # Bỏ chọn Platform
        model_p = self.cb_platform.model
        for i in range(model_p.rowCount()): model_p.item(i).setCheckState(Qt.CheckState.Unchecked)
        self.cb_platform._update_text()
        
        self.txt_prompt_target.clear()
    
    def transfer_to_content_factory(self):
        # 1. Lấy dữ liệu từ các ô
        skeleton = self.txt_report_en.toPlainText()
        
        # Lấy cấu hình đích (Target)
        target_niche = self.cb_batch_niche.currentText()
        target_lang = self.cb_batch_lang.currentText()
        quantity = self.spin_quantity.value()
        
        if not skeleton or "⏳" in skeleton:
            QMessageBox.warning(self, "Chưa có hàng", "Vui lòng chạy Phân Tích (Spy) trước!")
            return

        # 2. Đóng gói kiện hàng (PROTOCOL SPY_RESULT)
        payload = {
            "source": "Spy_Module",
            "quantity": quantity,
            "data": {
                "topic": target_niche,
                "country": target_lang,
                "platform": "Youtube Long",
                "key_vua": f"Remix: {target_niche}",
                "skeleton": skeleton,
                "visual_style": "Auto detected from Spy",
                "thumbnail_url": self.txt_video_url.text()
            }
        }
        return payload

    # [MỚI] Lưu trạng thái Spy
    def save_spy_history_to_disk(self):
        try:
            current_data = getattr(self, 'current_spy_data', {})
            safe_spy_data = {
                "root_keyword": current_data.get("root_keyword", ""),
                "url": self.txt_video_url.text(), 
                "thumbnail_url": current_data.get("thumbnail_url", ""),
                "skeleton": current_data.get("skeleton", ""),
                "visual_style": current_data.get("visual_style", ""),
                "ui_title": self.lbl_spy_video_title.text(),
                "ui_channel": self.lbl_spy_channel_name.text(),
                "ui_stats": self.lbl_spy_stats.text(),
                "ui_desc_raw": self.txt_spy_desc_raw.toPlainText(),
                "ui_desc_vi": self.txt_spy_desc_vi.toPlainText()
            }

            data = {
                "url": self.txt_video_url.text(),
                "report_en": self.txt_report_en.toPlainText(),
                "report_vi": self.txt_report_vi.toPlainText(),
                "report_json": self.txt_report_json.toPlainText(),
                "spy_data": safe_spy_data, 
                "cached_niche": getattr(self, 'cached_niche_context', ""),
                "cached_country": getattr(self, 'cached_country_context', "")
            }
            if not os.path.exists("VEO_DB"): os.makedirs("VEO_DB")
            with open("VEO_DB/radar_spy_history.json", "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Lỗi lưu Spy history: {e}")

    # [NÚT 2] CHUYỂN TỪ BẢNG STAGING SANG TAB 4
    def transfer_staging_to_factory(self):
        if self.tbl_staging.rowCount() == 0: return
        
        payload_list = []
        import re
        
        def final_clean(t):
            if not t: return "General"
            t = t.split('(')[0].strip()
            t = re.sub(r'^[^\w\s&,]*', '', t).strip()
            return t

        for i in range(self.tbl_staging.rowCount()):
            if self.tbl_staging.item(i, 0).checkState() == Qt.CheckState.Checked:
                full_data = self.staging_data_full[i]
                
                niche_on_table = self.tbl_staging.item(i, 3).text()
                clean_niche = final_clean(niche_on_table)
                key_vua_on_table = self.tbl_staging.item(i, 4).text()
                qty_on_table = int(self.tbl_staging.item(i, 7).text())
                visual_style = self.tbl_staging.item(i, 8).text()
                ai_thumb_prompt = full_data.get('thumb_prompt', "")
                
                base_data = {
                    "topic": clean_niche,
                    "country": full_data.get('country'),
                    "platform": "Youtube Long",
                    "key_vua": key_vua_on_table,
                    "skeleton": getattr(self, 'current_spy_data', {}).get("skeleton", ""),
                    "visual_style": visual_style,
                    "thumbnail_url": getattr(self, 'current_spy_data', {}).get("thumbnail_url", ""),
                    "initial_visual_prompt": ai_thumb_prompt,
                    "branding_info": {
                        "channel_name": full_data.get('name'),
                        "channel_handle": full_data.get('handle'),
                        "description": full_data.get('bio'), 
                        "visual_identity": { 
                            "logo_prompt": full_data.get('logo_prompt'),
                            "banner_prompt": full_data.get('banner_prompt')
                        }
                    }
                }
                
                for _ in range(qty_on_table):
                    payload_list.append(base_data.copy())
        
        try:
            main_win = self.window()
            if hasattr(main_win, 'content_tab'):
                main_win.content_tab.receive_data_from_radar(payload_list)
                main_win.switch_to_department(1)
                self.save_staging_table()
                self.handle_log_message(f"✅ [Tab 3 -> Tab 4] Chuyển hàng thành công!")
                QMessageBox.information(self, "Thành công", f"🚀 Đã chuyển {len(payload_list)} video vào Nhà Máy!")
            else:
                QMessageBox.warning(self, "Lỗi", "Không tìm thấy Content Tab.")
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Lỗi chuyển dữ liệu: {e}")

    # [MỚI] Tải trạng thái Spy
    def load_spy_history_from_disk(self):
        path = "VEO_DB/radar_spy_history.json"
        if not os.path.exists(path): return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self.txt_video_url.setText(data.get("url", ""))
            self.txt_report_en.setText(data.get("report_en", ""))
            self.txt_report_vi.setText(data.get("report_vi", ""))
            self.txt_report_json.setText(data.get("report_json", ""))

            self.current_spy_data = data.get("spy_data", {})
            self.cached_niche_context = data.get("cached_niche", "")
            self.cached_country_context = data.get("cached_country", "")
            spy_info = data.get("spy_data", {})
            
            if spy_info.get("ui_title"):
                self.lbl_spy_video_title.setText(spy_info["ui_title"])
            if spy_info.get("ui_channel"):
                self.lbl_spy_channel_name.setText(spy_info["ui_channel"])
            if spy_info.get("ui_stats"):
                self.lbl_spy_stats.setText(spy_info["ui_stats"])
            if spy_info.get("ui_desc_raw"):
                self.txt_spy_desc_raw.setText(spy_info["ui_desc_raw"])
            if spy_info.get("ui_desc_vi"):
                self.txt_spy_desc_vi.setText(spy_info["ui_desc_vi"])
                
            thumb_url = spy_info.get("thumbnail_url", "")
            if thumb_url:
                import requests
                from PyQt6.QtGui import QPixmap
                try:
                    d = requests.get(thumb_url, timeout=3).content
                    pix = QPixmap()
                    pix.loadFromData(d)
                    self.lbl_spy_thumb.setPixmap(pix)
                except: pass

            if self.txt_video_url.text():
                self.btn_watch_original.show()

            if self.current_spy_data.get("skeleton"):
                if hasattr(self, 'btn_plan'):
                    self.btn_plan.setEnabled(True)
                    self.btn_plan.setStyleSheet("background: #d35400; color: white; font-weight: bold;")

            self.load_staging_table()        
        except Exception as e:
            print(f"Lỗi tải Spy history: {e}")        
    
    def open_current_spy_video(self):
        url = self.txt_video_url.text()
        if url: QDesktopServices.openUrl(QUrl(url))

    # [NÚT 1] CHẠY AI LÊN KẾ HOẠCH (GENERATE PLAN)
    def run_channel_planning(self):
        # 1. Lấy thông tin
        raw_niche_text = self.cb_batch_niche.currentText()
        
        # [FIX QUAN TRỌNG] Chuẩn hóa Topic về tiếng Anh (Xóa Emoji & Việt)
        def clean_topic_name(text):
            if not text or "---" in text: return "General"
            res = text.split('(')[0].strip()
            # 2. Xóa Emoji (Bằng cách giữ lại ký tự ASCII + dấu &)
            # Hoặc đơn giản hơn: xóa các ký tự đặc biệt ở đầu
            res = re.sub(r'^[^\w\s]*', '', res).strip()
            return res

        target_niche = clean_topic_name(raw_niche_text)

        # [FIX BUG] Lấy danh sách nước ĐÚNG CÁCH
        target_langs_full = self.cb_batch_lang.get_checked_items()
        if not target_langs_full:
            QMessageBox.warning(self, "Thiếu QG", "Vui lòng chọn ít nhất 1 Quốc gia!")
            return
        
        import re
        countries_clean = []
        for c in target_langs_full:
            # 1. Cắt bỏ phần trong ngoặc (...)
            name_only = c.split('(')[0]
            # 2. Xóa Emoji và ký tự lạ, chỉ giữ chữ cái và số
            # \w bao gồm chữ cái unicode (Tiếng Việt, Nhật...)
            clean_name = re.sub(r'[^\w\s]', '', name_only).strip()
            countries_clean.append(clean_name)
        
        # [LOG]
        self.handle_log_message(f"🏗️ [Tab 3] Đang cho AI kiến trúc sư thiết kế kênh cho {len(countries_clean)} quốc gia...")

        # 2. Khóa giao diện & Chạy Worker
        self.tbl_staging.setRowCount(0)
        self.tbl_staging.setRowCount(len(countries_clean))
        # Điền tạm chữ "Loading..."
        for i, c in enumerate(countries_clean):
            self.tbl_staging.setItem(i, 2, QTableWidgetItem(c))
            self.tbl_staging.setItem(i, 9, QTableWidgetItem("⏳ Đang nghĩ tên..."))
            
        self.planner_worker = QuickPlannerWorker(target_niche, countries_clean, self.current_spy_data)
        self.planner_worker.finished.connect(self.on_planning_done)
        self.planner_worker.start()
        
    # [HÀM MỚI] Xử lý khi AI Lên kế hoạch xong (Điền bảng + Lưu dữ liệu ngầm)
    def on_planning_done(self, results):
        self.staging_data_full = results # Lưu toàn bộ (bao gồm bio, prompt) vào biến nhớ
        
        # Lấy Key Vua từ dữ liệu Spy hiện tại
        root_key = "Remix Video"
        if hasattr(self, 'current_spy_data'):
            root_key = self.current_spy_data.get('root_keyword', root_key)

        # Visual Style lấy từ Spy
        vis_style = "Cinematic, 4K"
        if hasattr(self, 'current_spy_data'):
            vis_style = self.current_spy_data.get('visual_style', vis_style)

        # Lấy thông tin SL và Niche từ giao diện
        qty = self.spin_quantity.value()
        original_niche = self.cb_batch_niche.currentText()

        self.tbl_staging.setRowCount(0) # Xóa cũ
        self.tbl_staging.setRowCount(len(results))
        
        for i, res in enumerate(results):
            # Cột 0: Checkbox (Mặc định chọn hết)
            chk = QTableWidgetItem()
            chk.setCheckState(Qt.CheckState.Checked) 
            self.tbl_staging.setItem(i, 0, chk)
            
            # Cột 1: STT
            stt = QTableWidgetItem(str(i + 1))
            stt.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tbl_staging.setItem(i, 1, stt)
            
            # Cột 2: QG
            self.tbl_staging.setItem(i, 2, QTableWidgetItem(res.get('country')))

            # Cột 3: Niche Gốc [MỚI]
            self.tbl_staging.setItem(i, 3, QTableWidgetItem(original_niche))

            # 4: Key Vua [MỚI] - Cho phép sửa tay nếu muốn
            final_key = res.get('native_target_keyword')
            if not final_key: 
                final_key = root_key
            key_item = QTableWidgetItem(final_key)
            # [MỚI] Hiện Prompt Thumb khi di chuột vào Key
            thumb_hint = f"🎨 Ý tưởng Thumb AI:\n{res.get('thumb_prompt')}"
            key_item.setToolTip(thumb_hint)
            self.tbl_staging.setItem(i, 4, key_item)
            
            # Cột 5: Tên Kênh (Có Tooltip chứa Bio)
            name_item = QTableWidgetItem(res.get('name'))
            # [QUAN TRỌNG] Nhét Mô tả vào Tooltip
            bio_text = f"Mô tả: {res.get('bio')}\n\n(Dữ liệu này sẽ chuyển sang Tab 4)"
            name_item.setToolTip(bio_text)
            self.tbl_staging.setItem(i, 5, name_item)
            
            # Cột 6: Handle
            self.tbl_staging.setItem(i, 6, QTableWidgetItem(res.get('handle')))

            # Cột 7: Số lượng Video [MỚI]
            self.tbl_staging.setItem(i, 7, QTableWidgetItem(str(qty)))
            
            # Cột 8: Style (Có Tooltip chứa Prompt Logo/Banner)
            style_item = QTableWidgetItem(vis_style)
            # [QUAN TRỌNG] Nhét Prompt vào Tooltip
            prompt_info = f"Logo Prompt: {res.get('logo_prompt')}\n\nBanner Prompt: {res.get('banner_prompt')}"
            style_item.setToolTip(prompt_info)
            self.tbl_staging.setItem(i, 8, style_item)
            
            # Cột 9: Trạng thái
            self.tbl_staging.setItem(i, 9, QTableWidgetItem("Sẵn sàng"))

            # --- [CHÈN VÀO ĐÂY] ---
            self.save_staging_table() # <--- Lưu ngay khi AI làm xong

        QMessageBox.information(self, "Xong", "Đã lên kế hoạch chi tiết!\n(Di chuột vào Tên kênh để xem Mô tả, vào Style để xem Prompt).")

    # [HÀM MỚI] Select All cho Staging Table
    def toggle_all_staging(self, checked):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(self.tbl_staging.rowCount()):
            item = self.tbl_staging.item(i, 0)
            if item:
                item.setCheckState(state)
                # [MỚI] Tô màu hàng loạt
                self.tint_row_color(self.tbl_videos, i, checked)
    
    # [HÀM MỚI] Bấm vào ô bất kỳ để tích chọn
    def on_staging_cell_clicked(self, row, col):
        if col == 0: 
            # Trường hợp bấm trực tiếp checkbox, phải bắt sự kiện itemChanged hoặc xử lý riêng
            # Nhưng để đơn giản, ta cứ tô màu ở đây, nếu chưa ăn thì dùng itemChanged
            item = self.tbl_staging.item(row, 0)
            self.tint_row_color(self.tbl_staging, row, item.checkState() == Qt.CheckState.Checked)
            return

        item = self.tbl_staging.item(row, 0)
        if item:
            new_state = Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked
            item.setCheckState(new_state)
            
            # [MỚI] Tô màu
            self.tint_row_color(self.tbl_staging, row, new_state == Qt.CheckState.Checked)

    # [NÚT 2] CHUYỂN TỪ BẢNG STAGING SANG TAB 4
    def transfer_staging_to_factory(self):
        if self.tbl_staging.rowCount() == 0: return
        
        payload_list = []
        quantity = self.spin_quantity.value()
        
        # Lấy base info
        spy_base = getattr(self, 'current_spy_data', {})
        skeleton = spy_base.get('skeleton', "")
        thumb_url = spy_base.get('url', "")

        for i in range(self.tbl_staging.rowCount()):
            if self.tbl_staging.item(i, 0).checkState() == Qt.CheckState.Checked:
                full_data = self.staging_data_full[i]
                
                # [MỚI] Lấy Niche từ cột 3 trên bảng
                # (Vì CEO có thể đã sửa key cho từng dòng)
                niche_on_table = self.tbl_staging.item(i, 3).text()

                # Cột 4: Key Vua
                key_vua_on_table = self.tbl_staging.item(i, 4).text()
                                
                # Cột 7: Số lượng (SL)
                qty_on_table = int(self.tbl_staging.item(i, 7).text())

                # Lấy Visual Style từ cột 8
                visual_style = self.tbl_staging.item(i, 8).text()
                
                # [MỚI] Lấy Prompt Thumb mà AI Planner đã nghĩ ra
                ai_thumb_prompt = full_data.get('thumb_prompt', "")

                base_data = {
                    "topic": niche_on_table,
                    "country": full_data.get('country'),
                    "platform": "Youtube Long",
                    "key_vua": key_vua_on_table, # Dùng key từ bảng
                    "skeleton": skeleton,
                    "visual_style": visual_style,
                    "thumbnail_url": thumb_url,
                    "initial_visual_prompt": ai_thumb_prompt,
                    "branding_info": {
                        "channel_name": full_data.get('name'),
                        "channel_handle": full_data.get('handle'),
                        "description": full_data.get('bio'), 
                        "visual_identity": { 
                            "logo_prompt": full_data.get('logo_prompt'),
                            "banner_prompt": full_data.get('banner_prompt')
                        }
                    }
                }
                
                for _ in range(quantity):
                    payload_list.append(base_data.copy())
        
        # [LOG]
        self.handle_log_message(f"📦 [Tab 3] Đang đóng gói và vận chuyển {len(payload_list)} nhiệm vụ sang Nhà Máy (Tab 4)...")

        try:
            main_win = self.window()
            if hasattr(main_win, 'content_tab'):
                main_win.content_tab.receive_data_from_radar(payload_list)
                main_win.switch_to_department(1) # Chuyển tab

                # --- [CHÈN VÀO ĐÂY] ---
                self.save_staging_table() # <--- Lưu lại trạng thái cuối cùng trước khi chuyển

                # [LOG]
                self.handle_log_message(f"✅ [Tab 3 -> Tab 4] Chuyển hàng thành công!")

                QMessageBox.information(self, "Thành công", f"🚀 Đã chuyển {len(payload_list)} video vào Nhà Máy!")
            else:
                QMessageBox.warning(self, "Lỗi", "Không tìm thấy Content Tab.")
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", str(e))
    
    # [HÀM MỚI] NÚT LÀM TƯƠI / KHÔI PHỤC GỐC
    def restore_original_choices(self):
        """Khôi phục lại lựa chọn từ biến nhớ (Cache)"""
        
        # Lấy dữ liệu từ biến nhớ (nếu không có thì báo)
        niche = getattr(self, 'cached_niche_context', 'Chưa có dữ liệu')
        country = getattr(self, 'cached_country_context', 'Chưa có dữ liệu')
        
        # [FIX] Hiển thị thông báo đẹp, không hiện số 67 nữa
        msg = (
            f"🔄 Đang khôi phục cài đặt gốc từ Video đã chọn:\n\n"
            f"📍 Chủ đề gốc: {niche}\n"
            f"📍 Quốc gia gốc: {country}\n\n"
            f"Bạn có muốn áp dụng không?"
        )
        
        reply = QMessageBox.question(self, "Khôi phục", msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            # Gọi lại thuật toán thông minh
            self.apply_smart_sync()
            QMessageBox.information(self, "Xong", "✅ Đã khôi phục lựa chọn theo video gốc!")
    
    def clear_spy_tab(self):
        self.txt_video_url.clear()

        self.txt_report_en.clear()
        self.txt_report_vi.clear()
        # [MỚI] Xóa ô JSON Thô
        if hasattr(self, 'txt_report_json'):
            self.txt_report_json.clear()
        self.lbl_spy_video_title.setText("--- Video Title ---")
        self.lbl_spy_channel_name.setText("👤 Channel Name")
        self.lbl_spy_stats.setText("👁️ --- views • ❤️ --- likes")

        self.lbl_spy_thumb.clear()
        self.lbl_spy_thumb.setText("Waiting for Thumbnail...")
        self.lbl_spy_thumb.setStyleSheet("background: #000;")
        self.current_spy_data = {}

        # [FIX] Ẩn nút xem video gốc
        if hasattr(self, 'btn_watch_original'):
            self.btn_watch_original.hide()

        # [FIX] Xóa nội dung trong Tab Mô tả
        if hasattr(self, 'txt_spy_desc_raw'):
            self.txt_spy_desc_raw.clear()
        if hasattr(self, 'txt_spy_desc_vi'):
            self.txt_spy_desc_vi.clear()

        # 4. Reset dữ liệu đệm
        self.current_spy_data = {}

        # --- [MỚI] XÓA BẢNG NHÂN BẢN (STAGING TABLE) ---
        if hasattr(self, 'tbl_staging'):
            self.tbl_staging.setRowCount(0)

        # Xóa dữ liệu đệm của bảng này
        self.staging_data_full = []

        # [MỚI] Khóa lại nút Plan
        if hasattr(self, 'btn_plan'):
            self.btn_plan.setEnabled(False)
            self.btn_plan.setStyleSheet("background: #444; color: #888; font-weight: bold; border: 1px solid #555;")
            self.btn_plan.setToolTip("⚠️ Hãy chạy 'GIẢI MÃ DNA' ở trên trước để có dữ liệu!")
    
    # --- [TÍNH NĂNG MỚI] LƯU/KHÔI PHỤC BẢNG STAGING (TAB 3) ---
    def save_staging_table(self):
        """Lưu dữ liệu bảng Nhân bản xuống ổ cứng"""
        rows = self.tbl_staging.rowCount()
        data = []
        # --- HÀM HELPER: LẤY DỮ LIỆU AN TOÀN (CHỐNG CRASH) ---
        def safe_get_text(row, col):
            item = self.tbl_staging.item(row, col)
            if item is None: return "" # Nếu ô chưa tạo -> Trả về rỗng
            return item.text()

        def safe_get_tooltip(row, col):
            item = self.tbl_staging.item(row, col)
            if item is None: return ""
            return item.toolTip()
        # -----------------------------------------------------

        for i in range(rows):
            # 1. Checkbox (Cột 0)
            item_chk = self.tbl_staging.item(i, 0)
            is_checked = False
            if item_chk is not None:
                is_checked = (item_chk.checkState() == Qt.CheckState.Checked)
            
            # [FIX LỖI CỦA CEO TẠI ĐÂY] 
            # Dùng hàm an toàn safe_get_tooltip thay vì gọi trực tiếp .toolTip()
            raw_thumb_tooltip = safe_get_tooltip(i, 4)
            clean_thumb_prompt = raw_thumb_tooltip.replace("🎨 Ý tưởng Thumb AI:\n", "")

            row_data = {
                "checked": is_checked,
                "country": safe_get_text(i, 2),
                "niche": safe_get_text(i, 3),
                "key_vua": safe_get_text(i, 4),
                "name": safe_get_text(i, 5),
                "bio": safe_get_tooltip(i, 5), # Mẹo: Lấy Bio từ Tooltip
                "handle": safe_get_text(i, 6),
                "qty": safe_get_text(i, 7),
                "style": safe_get_text(i, 8),
                "prompt_info": safe_get_tooltip(i, 8), # Mẹo: Lấy Prompt từ Tooltip
                "status": safe_get_text(i, 9),
                # Lưu thêm các trường ẩn nếu có (như thumb_prompt ở cột key)
                "thumb_prompt": clean_thumb_prompt
            }
            data.append(row_data)
        
        # Lưu cả biến staging_data_full (chứa dữ liệu gốc từ AI)
        full_package = {
            "table_rows": data,
            "raw_ai_data": getattr(self, 'staging_data_full', [])
        }

        try:
            if not os.path.exists("VEO_DB"): os.makedirs("VEO_DB")
            with open("VEO_DB/radar_staging_save.json", "w", encoding="utf-8") as f:
                json.dump(full_package, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Lỗi lưu Staging: {e}")

    def load_staging_table(self):
        """Khôi phục bảng Staging khi mở lại"""
        path = "VEO_DB/radar_staging_save.json"
        if not os.path.exists(path): return
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                package = json.load(f)
            
            rows_data = package.get("table_rows", [])
            self.staging_data_full = package.get("raw_ai_data", [])
            
            self.tbl_staging.setRowCount(0)
            self.tbl_staging.setRowCount(len(rows_data))
            
            for i, d in enumerate(rows_data):
                # 0. Checkbox
                chk = QTableWidgetItem()
                chk.setCheckState(Qt.CheckState.Checked if d["checked"] else Qt.CheckState.Unchecked)
                self.tbl_staging.setItem(i, 0, chk)
                
                # 1. STT
                stt = QTableWidgetItem(str(i + 1)); stt.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tbl_staging.setItem(i, 1, stt)
                
                # Các cột khác
                self.tbl_staging.setItem(i, 2, QTableWidgetItem(d["country"]))
                self.tbl_staging.setItem(i, 3, QTableWidgetItem(d["niche"]))
                
                # Key Vua + Tooltip Thumb
                key_item = QTableWidgetItem(d["key_vua"])
                key_item.setToolTip(f"🎨 Ý tưởng Thumb AI:\n{d.get('thumb_prompt', '')}")
                self.tbl_staging.setItem(i, 4, key_item)
                
                # Name + Tooltip Bio
                name_item = QTableWidgetItem(d["name"])
                name_item.setToolTip(d["bio"])
                self.tbl_staging.setItem(i, 5, name_item)
                
                self.tbl_staging.setItem(i, 6, QTableWidgetItem(d["handle"]))
                self.tbl_staging.setItem(i, 7, QTableWidgetItem(d["qty"]))
                
                # Style + Tooltip Prompt
                style_item = QTableWidgetItem(d["style"])
                style_item.setToolTip(d["prompt_info"])
                self.tbl_staging.setItem(i, 8, style_item)
                
                self.tbl_staging.setItem(i, 9, QTableWidgetItem(d["status"]))

        except Exception as e:
            print(f"Lỗi load Staging: {e}")

