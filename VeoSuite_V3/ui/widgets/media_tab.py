import requests
import os
import json
import time
import random
import asyncio
import shutil
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFrame, QSplitter, QTextEdit, QGroupBox, QComboBox, 
    QSlider, QScrollArea, QAbstractItemView, QListWidget, 
    QListWidgetItem, QLineEdit, QMessageBox, QTableWidget, 
    QTableWidgetItem, QHeaderView, QCheckBox, QMenu, QRadioButton, QButtonGroup,
    QSizePolicy, QFileDialog, QApplication, QInputDialog, QGridLayout, QProgressBar, QDialog
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl, QSize, QTimer, QObject
from PyQt6.QtGui import QIcon, QColor, QFont, QAction, QPixmap, QImage, QCursor
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from services.voice_constants import get_voice_list_by_country
from google import genai
from google.genai import types
from services.ai_factory import AIFactory
from services.render_service import RenderService
from services.thumbnail_composer import ThumbnailComposer

VOICE_CONFIG_FILE = "VEO_DB/voice_engine_config.json"


from modules.assets_factory.constants import *
from modules.assets_factory.ui_components import *
from modules.assets_factory.workers import *

# --- KHỐI IMPORT AN TOÀN (SAFE IMPORT BLOCK) ---
try:
    from services.database_manager import DatabaseManager
    DB_AVAILABLE = True
except ImportError:
    print("⚠️ Cảnh báo: Thiếu services/database_manager.py")
    DB_AVAILABLE = False
    
try:
    from services.audio_service import AudioService
    AUDIO_AVAILABLE = True
except ImportError:
    AudioService = None
    AUDIO_AVAILABLE = False
    print("⚠️ Cảnh báo: Thiếu services/audio_service.py")
    
try:
    from services.stock_service import StockService 
    STOCK_AVAILABLE = True
except ImportError:
    StockService = None
    STOCK_AVAILABLE = False
    
# ============================================================================
# 🧠 AI DIRECTOR BRAIN (MA TRẬN CẤU HÌNH THÔNG MINH)
# ============================================================================
# GIAO DIỆN CHÍNH: MEDIA FACTORY V8.0
# ============================================================================
class MediaTab(QWidget):
    log_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        # 1. Khởi tạo Manager
        self.db = DatabaseManager() if DB_AVAILABLE else None
        
        # 2. Player Nhạc & Voice
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)

        # [THÊM DÒNG NÀY] Biến đếm số lần bấm Preview để chống xung đột
        self.preview_gen_id = 0
        self.preview_workers_pool = [] # Hồ chứa các worker để không bị Garbage Collection giết nhầm

        # [CTO ADD] Quản lý danh sách Thumbnail
        self.thumb_candidates = [] # List đường dẫn ảnh
        self.current_thumb_idx = 0

        # [NÂNG CẤP] Timer & Sự kiện Player
        self.timer = QTimer(self)
        self.timer.setInterval(100) # Cập nhật mỗi 0.1 giây
        self.timer.timeout.connect(self.update_player_ui)
        
        # Kết nối sự kiện để UI nhảy số
        self.player.positionChanged.connect(self.on_position_changed)
        self.player.durationChanged.connect(self.on_duration_changed)
        
        # 3. Biến trạng thái
        self.current_project_index = -1
        self.current_task = None
        self.log_signal.emit("🎬 Đã khởi tạo Tab Media Factory.")
        
        # Reset UI
        self.current_task_data = {}
        self.tasks_map = {}
        
        self.batch_queue = []
        self.is_batch_running = False
        
        self.brand_workers_pool = []
        self.current_style = "Auto Detect"

        # 4. Giao diện
        self._build_ui()
        self._apply_style()
        
        # 5. Load dữ liệu
        if hasattr(self, 'list_projects'):
            self.refresh_project_list()



    def _build_ui(self):
        """Xây dựng giao diện 3 Tầng chuẩn Hiến pháp V3.2"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ============================================================
        # TẦNG 1: THANH CÔNG CỤ (ACTION BAR)
        # ============================================================
        action_bar = QFrame()
        action_bar.setStyleSheet("background: #252526; border-bottom: 1px solid #333;")
        action_bar.setFixedHeight(50)
        l_action = QHBoxLayout(action_bar)
        l_action.setContentsMargins(10, 5, 10, 5)

        # Nhóm Nhập Liệu
        self.btn_paste = QPushButton("📋 Paste JSON")
        self.btn_paste.setToolTip("Dán dữ liệu từ Clipboard và tự động điền")
        self.btn_paste.clicked.connect(self.action_paste_json)
        
        btn_import = QPushButton("📂 Import File")
        btn_import.clicked.connect(self.action_import)
        
        btn_sync = QPushButton("🔄 Force Sync")
        btn_sync.setToolTip("Quét lại ổ cứng để cập nhật trạng thái")
        btn_sync.refresh_project_list = self.refresh_project_list
        btn_sync.clicked.connect(self.refresh_project_list)
        
        l_action.addWidget(self.btn_paste)
        l_action.addWidget(btn_import)
        l_action.addWidget(btn_sync)

        # Nhóm Xử Lý (Giữa)
        l_action.addStretch()
        self.btn_fix = QPushButton("🧠 Auto-Fix Missing")
        self.btn_fix.setStyleSheet("color: #f1c40f; border: 1px solid #555; background: #333;")
        l_action.addWidget(self.btn_fix)
        l_action.addStretch()

        # --- [THÊM NÚT NÀY] ---
        self.btn_auto_brand = QPushButton("🎨 Auto-Brand All")
        self.btn_auto_brand.setToolTip("Tự động vẽ Logo & Banner cho các kênh chưa có")
        self.btn_auto_brand.setStyleSheet("background: #8e44ad; color: white; font-weight: bold;")
        self.btn_auto_brand.clicked.connect(self.action_batch_generate_brand)
        l_action.addWidget(self.btn_auto_brand)
        # ----------------------

        # Nhóm Vận Hành (Phải)
        self.btn_batch = QPushButton("⚡ TẠO FULL (Kênh)")
        self.btn_batch.setStyleSheet("background: #27ae60; color: white; font-weight: bold; padding: 5px 15px; border-radius: 4px;")
        self.btn_batch.clicked.connect(lambda: self.batch_action("full_run"))
        
        self.btn_stop = QPushButton("⛔ STOP")
        self.btn_stop.setStyleSheet("background: #c0392b; color: white; font-weight: bold; padding: 5px 15px; border-radius: 4px;")
        self.btn_stop.clicked.connect(self.action_stop_all)
        
        l_action.addWidget(self.btn_batch)
        l_action.addWidget(self.btn_stop)

        main_layout.addWidget(action_bar)

        # ============================================================
        # TẦNG 2 + 3: SPLITTER DỌC (MONITOR + WORKBENCH)
        # ============================================================
        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # --- TẦNG 2: KHU VỰC GIÁM SÁT (MONITOR AREA) ---
        monitor_widget = QWidget()
        l_mon = QVBoxLayout(monitor_widget)
        l_mon.setContentsMargins(0,0,0,0)
        
        mon_split = QSplitter(Qt.Orientation.Horizontal)
        
        # Cột 1: Danh sách Kênh
        col_chan = self._create_monitor_column("📺 DANH SÁCH KÊNH", "#f39c12")
        self.list_projects = QListWidget()
        self.list_projects.setAlternatingRowColors(False)
        self.list_projects.itemClicked.connect(self.on_project_selected)
        col_chan.layout().addWidget(self.list_projects)
        mon_split.addWidget(col_chan)
        
        # Cột 2: Danh sách Video (Tasks)
        col_vid = self._create_monitor_column("🎬 DANH SÁCH VIDEO", "#3498db")
        self.table_mon = QTableWidget(0, 7)
        self.table_mon.verticalHeader().setVisible(False)
        self.table_mon.setHorizontalHeaderLabels(["STT", "Tiêu đề Video(Title)", "🎙️ Voice", "🖼️ Visual", "🎵 Music", "🎨 Thumb", "Trạng thái"])
        self.table_mon.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents) # Cột STT tự động co dãn
        self.table_mon.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch) # Cột tiêu đề giãn
        self.table_mon.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents) # Voice
        self.table_mon.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents) # Visual
        self.table_mon.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents) # Music
        self.table_mon.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents) # Thumb
        self.table_mon.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents) # Trạng thái (Tự giãn theo chữ)
        
        self.table_mon.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_mon.itemClicked.connect(self.on_monitor_row_clicked)
        col_vid.layout().addWidget(self.table_mon)
        mon_split.addWidget(col_vid)

        mon_split.setStretchFactor(0, 3) # Kênh nhỏ
        mon_split.setStretchFactor(1, 7) # Video rộng nhất

        l_mon.addWidget(mon_split)
        
        self.main_splitter.addWidget(monitor_widget)

        # --- TẦNG 3: XƯỞNG SẢN XUẤT (WORKBENCH) ---
        scroll_bench = QScrollArea()
        scroll_bench.setWidgetResizable(True)
        scroll_bench.setStyleSheet("QScrollArea {border: none; background: #1e1e1e;}")
        
        self.bench_widget = QWidget()
        self.bench_layout = QVBoxLayout(self.bench_widget)
        self.bench_layout.setContentsMargins(10, 10, 10, 30)
        self.bench_layout.setSpacing(15)

        # A. KHỐI CHỈ HUY (COMMAND DECK)
        self.setup_command_deck()

        # B. HEADER CỘT
        self.setup_header_columns()

        # C. CÁC LUỒNG SẢN XUẤT (FLOWS)
        self.create_flow("LUỒNG 2: VOICE FACTORY (Sản xuất Âm thanh)", self.setup_flow_voice)
        self.create_flow("LUỒNG 3: VISUAL PIPELINE (Sản xuất Ảnh/Video)", self.setup_flow_visual)
        self.create_flow("LUỒNG 4: THUMBNAIL STUDIO", self.setup_flow_thumbnail)
        self.create_flow("LUỒNG 5: MUSIC & SFX", self.setup_flow_music)

        # D. FOOTER (XUẤT KHO)
        footer = QHBoxLayout(); footer.addStretch()
        
        btn_send_editor = QPushButton("🚀 CHUYỂN SANG DỰNG PHIM (VEO EDITOR)")
        btn_send_editor.setMinimumHeight(50); btn_send_editor.setMinimumWidth(250)
        btn_send_editor.setStyleSheet("background: #8e44ad; color: white; font-weight: bold; font-size: 14px; border-radius: 5px;")
        btn_send_editor.clicked.connect(self.action_send_to_editor)
        
        btn_export = QPushButton("💾 Xuất ra máy tính (Dựng Premiere)")
        btn_export.setMinimumHeight(50); btn_export.setMinimumWidth(250)
        btn_export.setStyleSheet("background: #e67e22; color: white; font-weight: bold; font-size: 14px; border-radius: 5px;")
        btn_export.clicked.connect(self.action_final_export)
        
        footer.addWidget(btn_send_editor)
        footer.addWidget(btn_export)
        self.bench_layout.addLayout(footer)

        scroll_bench.setWidget(self.bench_widget)
        self.main_splitter.addWidget(scroll_bench)

        # Tỷ lệ chia màn hình: Monitor 3 phần, Workbench 7 phần
        self.main_splitter.setStretchFactor(0, 3) 
        self.main_splitter.setStretchFactor(1, 7)
        
        main_layout.addWidget(self.main_splitter)

    def _create_monitor_column(self, title, color_code):
        """Helper tạo khung cột Monitor cho đẹp"""
        w = QWidget()
        l = QVBoxLayout(w); l.setContentsMargins(0,0,0,0); l.setSpacing(0)
        lbl = QLabel(title)
        lbl.setStyleSheet(f"background:#1e1e1e; color:{color_code}; font-weight:bold; padding:5px; border-bottom:1px solid #444;")
        l.addWidget(lbl)
        return w

    def setup_command_deck(self):
        """KHỐI CHỈ HUY - TRÁI TIM CỦA HIẾN PHÁP V3.2"""
        grp = QGroupBox("🎛️ TRUNG TÂM CHỈ HUY (COMMAND DECK)")
        grp.setStyleSheet("QGroupBox {font-weight: bold; color: #f1c40f; border: 1px solid #555; background: #222; margin-top: 10px;}")
        layout = QHBoxLayout(grp)
        layout.setSpacing(20)

        # --- CÁNH TRÁI (55%): BRAND KÊNH ---
        left_panel = QWidget()
        l_left = QHBoxLayout(left_panel); l_left.setContentsMargins(0,0,0,0)
        
        # Logo & Banner
        v_img = QVBoxLayout()
        # [CTO FIX] Dùng ZoomableLabel thay cho QLabel thường
        self.lbl_logo = ZoomableLabel(is_banner=False); self.lbl_logo.setFixedSize(80, 80)
        self.lbl_logo.setText("LOGO")
        self.lbl_logo.setStyleSheet("border: 1px dashed #666; background: #000;")
        self.lbl_logo.setScaledContents(True)
        
        self.btn_redraw_logo = QPushButton("🔄 Vẽ Logo")
        self.btn_redraw_logo.setFixedWidth(80)
        self.btn_redraw_logo.setToolTip("Vẽ lại Logo theo DNA kênh")
        self.btn_redraw_logo.clicked.connect(lambda: self.action_redraw_brand("logo"))
                
        v_img.addWidget(self.lbl_logo); v_img.addWidget(self.btn_redraw_logo)
        l_left.addLayout(v_img)

        v_banner = QVBoxLayout()
        # [CTO FIX] Dùng ZoomableLabel
        self.lbl_banner = ZoomableLabel(is_banner=True); self.lbl_banner.setFixedSize(142, 80) # Tỷ lệ 16:9
        self.lbl_banner.setText("BANNER")
        self.lbl_banner.setStyleSheet("border: 1px dashed #666; background: #000;")
        self.lbl_banner.setScaledContents(True)
        
        self.btn_redraw_banner = QPushButton("🔄 Vẽ Banner")
        self.btn_redraw_banner.setFixedWidth(142)
        self.btn_redraw_banner.setToolTip("Vẽ lại Banner theo DNA kênh")
        self.btn_redraw_banner.clicked.connect(lambda: self.action_redraw_brand("banner"))

        v_banner.addWidget(self.lbl_banner); v_banner.addWidget(self.btn_redraw_banner)
        l_left.addLayout(v_banner)

        # Thông tin Text (Channel Info)
        v_info = QVBoxLayout()
        self.lbl_channel_name = QLabel("CHƯA CHỌN KÊNH")
        self.lbl_channel_name.setStyleSheet("font-size: 18px; font-weight: 900; color: #f1c40f; font-family: 'Segoe UI Black';")
        self.lbl_channel_name.setWordWrap(True)

        self.lbl_channel_desc = QLabel("--- Mô tả kênh ---")
        self.lbl_channel_desc.setStyleSheet("color: #95a5a6; font-size: 11px; font-style: italic;")
        self.lbl_channel_desc.setWordWrap(True)
        self.lbl_channel_desc.setMaximumHeight(45)
        
        self.lbl_dna_tags = QLabel("🎨 DNA: N/A")
        self.lbl_dna_tags.setStyleSheet("color: #00e6e6; font-weight: bold;")
        
        self.chk_brand_thumb = QCheckBox("✅ Ép màu Brand vào Thumbnail")
        self.chk_brand_thumb.setChecked(True)
        self.chk_brand_thumb.setStyleSheet("color: #27ae60; font-size: 11px;")
        
        v_info.addWidget(self.lbl_channel_name)
        v_info.addWidget(self.lbl_channel_desc)
        v_info.addWidget(self.lbl_dna_tags)
        v_info.addWidget(self.chk_brand_thumb)
        v_info.addStretch()
        l_left.addLayout(v_info)

        layout.addWidget(left_panel, 55)
        
        # Vách ngăn
        line = QFrame(); line.setFrameShape(QFrame.Shape.VLine); line.setStyleSheet("color: #444;")
        layout.addWidget(line)

        # --- CÁNH PHẢI (45%): VIDEO INFO ---
        right_panel = QWidget()
        l_right = QVBoxLayout(right_panel); l_right.setContentsMargins(0,0,0,0)
        
        self.lbl_video_title = QLabel("--- Tiêu đề Video ---")
        self.lbl_video_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #f39c12;")
        self.lbl_video_title.setWordWrap(True)
        
        self.lbl_batch_status = QLabel("Trạng thái: Sẵn sàng.")
        self.log_signal.emit("🎬 Đã khởi tạo Tab Media Factory.")
        self.lbl_config_status = QLabel("⚙️ Config: Waiting...")
        self.lbl_config_status.setStyleSheet("color: #7f8c8d; font-style: italic;")
        
        h_btn_vid = QHBoxLayout()
        btn_demo = QPushButton("▶ Demo 1 Phần")
        btn_demo.clicked.connect(self.action_demo_part)
        
        self.btn_run_single = QPushButton("🎬 TẠO FULL (Video này)")
        self.btn_run_single.setStyleSheet("background: #d35400; font-weight: bold;")
        self.btn_run_single.clicked.connect(self.action_full_video_single)
        
        self.btn_render_final = QPushButton("🎥 RENDER VIDEO CUỐI")
        self.btn_render_final.setToolTip("Tự động ghép Voice + Ảnh + Nhạc + Phụ đề → Video hoàn chỉnh (FFmpeg)")
        self.btn_render_final.setStyleSheet("background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #8e44ad,stop:1 #3498db); font-weight: bold; color: white; padding: 6px;")
        self.btn_render_final.clicked.connect(self.action_render_final_video)
        
        h_btn_vid.addWidget(btn_demo)
        h_btn_vid.addWidget(self.btn_run_single)
        h_btn_vid.addWidget(self.btn_render_final)
        
        l_right.addWidget(self.lbl_video_title)
        l_right.addWidget(self.lbl_config_status)
        l_right.addStretch()
        l_right.addLayout(h_btn_vid)
        
        layout.addWidget(right_panel, 45)

        self.bench_layout.addWidget(grp)

    def setup_header_columns(self):
        h_head = QHBoxLayout()
        h_head.addWidget(QLabel("INPUT DATA (Nguyên liệu)", styleSheet="background:#333;padding:5px;font-weight:bold;color:#ccc"), 35)
        h_head.addWidget(QLabel("CONFIG (Cấu hình)", styleSheet="background:#2c3e50;padding:5px;font-weight:bold;color:#3498db"), 25)
        h_head.addWidget(QLabel("OUTPUT (Sản phẩm)", styleSheet="background:#145a32;padding:5px;font-weight:bold;color:#2ecc71"), 40)
        self.bench_layout.addLayout(h_head)

    def create_flow(self, title, setup_func):
        w1, w2, w3 = setup_func()
        self.create_flow_ui(title, w1, w2, w3)

    def create_flow_ui(self, title, w1, w2, w3):
        grp = QGroupBox(title)
        grp.setStyleSheet("""
            QGroupBox {font-weight: bold; border: 1px solid #444; margin-top: 10px; background: #1e1e1e;} 
            QGroupBox::title {subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #f39c12;}
        """)
        l = QHBoxLayout(grp)
        l.setContentsMargins(5, 10, 5, 5); l.setSpacing(10)
        
        if w1: l.addWidget(w1, 35)
        else: l.addWidget(QLabel("Lỗi Cột 1"), 35)
            
        if w2: l.addWidget(w2, 25)
        else: l.addWidget(QLabel("Lỗi Cột 2"), 25)
            
        if w3: l.addWidget(w3, 40)
        else: l.addWidget(QLabel("Lỗi Cột 3"), 40)
            
        self.bench_layout.addWidget(grp)

    # ============================================================
    # 🏭 LUỒNG 2: VOICE FACTORY (BƯỚC 1)
    # ============================================================
    def setup_flow_voice(self):
        # C1: Input Script
        c1 = QWidget(); l1 = QVBoxLayout(c1); l1.setContentsMargins(0,0,0,0)
        self.txt_voice_in = QTextEdit()
        self.txt_voice_in.setPlaceholderText("Nội dung kịch bản Voice...")
        l1.addWidget(QLabel("📜 <b>BƯỚC 1:</b> KỊCH BẢN GIỌNG NÓI (Text):")); l1.addWidget(self.txt_voice_in)

        # C2: Config
        c2 = QWidget(); l2 = QVBoxLayout(c2)
        
        self.cb_voice_eng = QComboBox(); self.cb_voice_eng.addItems(["Auto (AI Director)", "Google TTS", "Edge TTS (Free)", "OpenAI TTS", "LuxTTS (Voice Clone)"])
        l2.addWidget(QLabel("Engine:")); l2.addWidget(self.cb_voice_eng)

        self.cb_voice_name = QComboBox()
        # --- [THÊM ĐOẠN NÀY] NẠP DANH SÁCH GIỌNG ---
        # Mặc định lấy giọng US hoặc VN tùy bạn, ở đây ví dụ lấy VN
        voices = get_voice_list_by_country("VN") 
        for v in voices:
        # Lưu ID thực vào data ẩn, hiển thị tên đẹp ra ngoài
            self.cb_voice_name.addItem(f"{v['gender']} - {v['name']}", v['id'])
        # -------------------------------------------
        l2.addWidget(QLabel("Speaker (Giọng):")); l2.addWidget(self.cb_voice_name)

        # [NEW] Chọn file audio mẫu cho LuxTTS
        l2.addWidget(QLabel("File Mẫu (LuxTTS Voice Clone):"))
        h_ref = QHBoxLayout()
        self.txt_ref_audio = QLineEdit()
        self.txt_ref_audio.setPlaceholderText("Đường dẫn file audio 3-10s...")
        btn_browse_ref = QPushButton("📁")
        btn_browse_ref.setFixedWidth(40)
        btn_browse_ref.clicked.connect(lambda: self._browse_ref_audio())
        h_ref.addWidget(self.txt_ref_audio); h_ref.addWidget(btn_browse_ref)
        l2.addLayout(h_ref)

        # Slider Rate
        l2.addWidget(QLabel("Tốc độ (Rate):"))
        h_rate = QHBoxLayout()
        self.sl_rate = QSlider(Qt.Orientation.Horizontal); self.sl_rate.setRange(-50, 50); self.sl_rate.setValue(0)
        self.lbl_rate_val = QLabel("0%")
        self.sl_rate.valueChanged.connect(lambda v: self.lbl_rate_val.setText(f"{v}%"))
        h_rate.addWidget(self.sl_rate); h_rate.addWidget(self.lbl_rate_val)
        l2.addLayout(h_rate)

        # Slider Pitch
        l2.addWidget(QLabel("Cao độ (Pitch):"))
        h_pitch = QHBoxLayout()
        self.sl_pitch = QSlider(Qt.Orientation.Horizontal); self.sl_pitch.setRange(-50, 50); self.sl_pitch.setValue(0)
        self.lbl_pitch_val = QLabel("0Hz")
        self.sl_pitch.valueChanged.connect(lambda v: self.lbl_pitch_val.setText(f"{v}Hz"))
        h_pitch.addWidget(self.sl_pitch); h_pitch.addWidget(self.lbl_pitch_val)
        l2.addLayout(h_pitch)

        self.btn_gen_voice = QPushButton("🎙️ TẠO VOICE (Full)")
        self.btn_gen_voice.setStyleSheet("background: #e67e22; font-weight:bold; padding: 8px;")
        self.btn_gen_voice.clicked.connect(self.action_single_voice)
        
        # [SỬA LẠI] Thêm self. để điều khiển khóa nút
        self.btn_preview_voice = QPushButton("🎧 Nghe thử 3 câu") 
        self.btn_preview_voice.clicked.connect(self.action_preview_voice)
        self.btn_preview_voice.setStyleSheet("background: #34495e; border: 1px dashed #7f8c8d;")
        
        l2.addWidget(self.btn_preview_voice); l2.addWidget(self.btn_gen_voice); l2.addStretch()

        # C3: Player & Output
        c3 = QWidget(); l3 = QVBoxLayout(c3)
        
        # Player Control
        h_play = QHBoxLayout()
        btn_p = QPushButton("▶"); btn_p.setFixedWidth(40); btn_p.clicked.connect(self.toggle_play)
        btn_s = QPushButton("⏹"); btn_s.setFixedWidth(40); btn_s.clicked.connect(self.player.stop)
        
        self.seek_voice = ClickableSlider(Qt.Orientation.Horizontal)
        self.seek_voice.setRange(0, 100)
        # Logic update seekbar theo duration thực tế cần kết nối signal durationChanged của player
        
        h_play.addWidget(btn_p); h_play.addWidget(btn_s); h_play.addWidget(self.seek_voice)
        
        self.lbl_voice_time = QLabel("00:00 / 00:00")
        self.lbl_voice_time.setAlignment(Qt.AlignmentFlag.AlignRight)
        
        # --- [MỚI] TRẠNG THÁI FILE (VOICE + SUB) ---
        h_status = QHBoxLayout()
        
        # Cột Voice
        v_voice = QVBoxLayout()
        self.lbl_voice_out = QLabel("❌ No Audio")
        self.lbl_voice_out.setStyleSheet("color: #e74c3c; font-size: 11px;")
        v_voice.addWidget(QLabel("Audio:"))
        v_voice.addWidget(self.lbl_voice_out)
        
        # Cột Subtitle (Mới)
        v_sub = QVBoxLayout()
        self.lbl_sub_out = QLabel("❌ No Sub")
        self.lbl_sub_out.setStyleSheet("color: #e74c3c; font-size: 11px;")
        v_sub.addWidget(QLabel("Subtitle:"))
        v_sub.addWidget(self.lbl_sub_out)
        
        h_status.addLayout(v_voice)
        h_status.addLayout(v_sub)
        # ---------------------------------------------

        # --- [MỚI] HÀNG NÚT CHỨC NĂNG ---
        h_tools = QHBoxLayout()

        # Nút xem Sub
        self.btn_view_sub = QPushButton("👁️ Xem Sub")
        self.btn_view_sub.setToolTip("Xem nội dung file .srt")
        self.btn_view_sub.setStyleSheet("background: #34495e; padding: 4px; font-size: 11px;")
        self.btn_view_sub.clicked.connect(self.action_view_subtitle) # Hàm này sẽ viết ở bước 3
        self.btn_view_sub.setEnabled(False)

        # [THÊM] Nút mở thư mục lấy file
        self.btn_open_folder = QPushButton("📂 Mở thư mục (Lấy Sub)")
        self.btn_open_folder.setStyleSheet("background: #34495e; padding: 5px; border: 1px solid #555;")
        self.btn_open_folder.clicked.connect(self.open_current_folder)
        self.btn_open_folder.setEnabled(False) # Khóa khi chưa có file

        h_tools.addWidget(self.btn_view_sub)
        h_tools.addWidget(self.btn_open_folder)

        l3.addLayout(h_play)
        l3.addWidget(self.lbl_voice_time)
        l3.addLayout(h_status) # Thêm layout trạng thái mới
        l3.addLayout(h_tools)  # Thêm hàng nút mới
        l3.addStretch()

        return c1, c2, c3

    # ============================================================
    # 🏭 LUỒNG 3: VISUAL PIPELINE (BƯỚC 2)
    # ============================================================
    def setup_flow_visual(self):
        # C1: Input
        c1 = QWidget(); l1 = QVBoxLayout(c1)
        l1.addWidget(QLabel("<b>BƯỚC 2:</b> PHÂN CẢNH HÌNH ẢNH (Visual Script):"))
        self.list_visual_in = QListWidget()
        self.list_visual_in.setAlternatingRowColors(True)
        self.list_visual_in.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list_visual_in.verticalScrollBar().valueChanged.connect(self.sync_scroll_vis_out)
        l1.addWidget(self.list_visual_in)

        # C2: Config
        c2 = QWidget(); l2 = QVBoxLayout(c2)
        
        # PHONG CÁCH (Visual Style) - [NÂNG CẤP PREMIUM]
        l2.addWidget(QLabel("<b>🎨 PHONG CÁCH VIDEO:</b>"))
        
        # ── SCROLL AREA PHONG CÁCH (Cuộn NGANG để xem 20+ mẫu) ──
        self.scroll_style = HorizontalScrollArea()
        self.scroll_style.setFixedHeight(160)
        self.scroll_style.setWidgetResizable(True)
        self.scroll_style.setStyleSheet("""
            QScrollArea { background: #1a1a1a; border: none; }
            QScrollBar:horizontal {
                height: 8px; background: #111; border-radius: 4px;
            }
            QScrollBar::handle:horizontal {
                background: #444; border-radius: 4px; min-width: 30px;
            }
            QScrollBar::handle:horizontal:hover { background: #666; }
        """)
        # BẬT horizontal scroll để cuộn ngang xem 20+ style cards
        self.scroll_style.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_style.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Cho phép cuộn ngang bằng wheel chuột
        self.scroll_style.horizontalScrollBar().setSingleStep(120)
        
        style_container = QWidget()
        style_layout = QHBoxLayout(style_container)
        style_layout.setContentsMargins(5, 5, 5, 5)
        style_layout.setSpacing(8)
        
        # ═══ Load 20+ phong cách từ STYLE_CATALOG (Pixelle-Video inspired) ═══
        from modules.assets_factory.prompt_templates import STYLE_CATALOG
        
        # Card đầu tiên: Auto Detect (luôn đứng đầu)
        auto_card = StyleCardWidget(
            "Auto Detect", icon_path=None, emoji="🤖",
            color_accent="#2ecc71", description="AI tự phân tích kịch bản và chọn phong cách phù hợp nhất"
        )
        auto_card.clicked.connect(self.on_style_selected)
        style_layout.addWidget(auto_card)
        
        self.style_cards = [auto_card]
        
        for style_data in STYLE_CATALOG:
            icon_file = f"VEO_DB/style_icons/{style_data['name'].replace(' ', '_')}.jpg"
            card = StyleCardWidget(
                style_data["name"],
                icon_path=icon_file,
                emoji=style_data.get("emoji", "🎨"),
                color_accent=style_data.get("color_accent", "#3498db"),
                description=style_data.get("description", "")
            )
            card.clicked.connect(self.on_style_selected)
            style_layout.addWidget(card)
            self.style_cards.append(card)
        
        style_layout.addStretch()
        self.scroll_style.setWidget(style_container)
        l2.addWidget(self.scroll_style)
        
        # Mặc định chọn Auto Detect
        if self.style_cards: 
            self.current_style = "Auto Detect"
            self.style_cards[0].selected = True
            self.style_cards[0].update_style()
        
        # Lựa chọn Nguồn (Source)
        l2.addWidget(QLabel("<b>🖼️ NGUỒN ẢNH:</b>"))
        self.cb_vis_source = QComboBox()
        self.cb_vis_source.addItems([
            "⚡ Hybrid (80% Stock + 20% AI)", 
            "🤖 100% AI Generated (Vẽ toàn bộ)", 
            "📷 100% Stock Footage (Ảnh thật)"
        ])
        self.cb_vis_source.setToolTip("Chọn cách tool lấy tư liệu hình ảnh. Hybrid là chế độ cân bằng và nhanh nhất.")
        l2.addWidget(self.cb_vis_source)
        
        # --- [MỚI] THÊM CHỌN TỶ LỆ KHUNG HÌNH ---
        l2.addWidget(QLabel("<b>📐 TỶ LỆ KHUNG HÌNH:</b>"))
        self.cb_ratio = QComboBox()
        self.cb_ratio.addItems(["⚡ Auto (Theo nền tảng)", "16:9 (Ngang - Youtube)", "9:16 (Dọc - Shorts/Tiktok)"])
        l2.addWidget(self.cb_ratio)
        
        self.cb_vis_format = QComboBox(); self.cb_vis_format.addItems(["Video (Ưu tiên)", "Image Only"])
        l2.addWidget(self.cb_vis_format)

        # [VEO PRO UPGRADE] Pro Audio Toggle
        self.chk_pro_audio = QCheckBox("🚀 Enable Pro Audio (Local)")
        self.chk_pro_audio.setToolTip("Kích hoạt Demucs & Kokoro (Yêu cầu cài đặt local)")
        self.chk_pro_audio.setStyleSheet("color: #f1c40f; font-weight: bold;")
        l2.addWidget(self.chk_pro_audio)

        self.btn_find_visual = QPushButton("🖼️ TÌM & TẠO (AUTO)")
        self.btn_find_visual.setToolTip("BƯỚC 2: AI Director sẽ tự động phân tích từng câu thoại và chọn hình ảnh/video phù hợp nhất.")
        self.btn_find_visual.setStyleSheet("background: #8e44ad; font-weight: bold; padding: 10px;")
        self.btn_find_visual.clicked.connect(self.action_auto_visual)
        l2.addWidget(self.btn_find_visual)
        l2.addStretch()

        # C3: Output Preview
        c3 = QWidget(); l3 = QVBoxLayout(c3); l3.setContentsMargins(0,0,0,0)
        l3.addWidget(QLabel("Media Output (Sync Scroll):"))
        
        self.list_visual_out = QListWidget()
        self.list_visual_out.itemClicked.connect(self.on_visual_output_clicked)
        self.list_visual_out.setIconSize(QSize(160, 90)) # Thumbnail to
        self.list_visual_out.setSpacing(5)
        self.list_visual_out.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel) # [FIX] Cuộn mượt
        # Kết nối thanh cuộn ngược lại
        self.list_visual_out.verticalScrollBar().valueChanged.connect(self.sync_scroll_vis_in)
        
        l3.addWidget(self.list_visual_out)
        
        # [VEO UPGRADE] AI Quality Check Control
        self.btn_ai_qa = QPushButton("🔍 AI QUALITY CHECK")
        self.btn_ai_qa.setToolTip("Gửi video cho AI để kiểm tra lỗi render (Audio pops, Visual jumps)")
        self.btn_ai_qa.setStyleSheet("background: #27ae60; font-weight: bold; padding: 8px; border-radius: 4px;")
        self.btn_ai_qa.clicked.connect(self.action_ai_qa)
        l3.addWidget(self.btn_ai_qa)

        return c1, c2, c3

    def sync_scroll_vis_out(self, val):
        """Khi cuộn bên Input -> Cuộn bên Output (Dùng tỷ lệ để đồng bộ đúng)"""
        sb_in = self.list_visual_in.verticalScrollBar()
        sb_out = self.list_visual_out.verticalScrollBar()
        if sb_in.maximum() > 0 and sb_out.maximum() > 0:
            ratio = val / sb_in.maximum()
            target = int(ratio * sb_out.maximum())
        else:
            target = val
        if sb_out.value() != target:
            sb_out.blockSignals(True)
            sb_out.setValue(target)
            sb_out.blockSignals(False)

    def sync_scroll_vis_in(self, val):
        """Khi cuộn bên Output -> Cuộn bên Input (Dùng tỷ lệ để đồng bộ đúng)"""
        sb_in = self.list_visual_in.verticalScrollBar()
        sb_out = self.list_visual_out.verticalScrollBar()
        if sb_out.maximum() > 0 and sb_in.maximum() > 0:
            ratio = val / sb_out.maximum()
            target = int(ratio * sb_in.maximum())
        else:
            target = val
        if sb_in.value() != target:
            sb_in.blockSignals(True)
            sb_in.setValue(target)
            sb_in.blockSignals(False)

    # ============================================================
    # LUỒNG 4: THUMBNAIL STUDIO
    # ============================================================
    def setup_flow_thumbnail(self):
        # C1: Input
        c1 = QWidget(); l1 = QVBoxLayout(c1)
        self.txt_thumb_prompt = QTextEdit()
        self.txt_thumb_prompt.setPlaceholderText("Mô tả hình ảnh Thumbnail...")
        l1.addWidget(QLabel("Prompt Hình ảnh:")); l1.addWidget(self.txt_thumb_prompt)

        self.txt_thumb_text = QLineEdit()
        self.txt_thumb_text.setPlaceholderText("Chữ trên ảnh (Text Overlay)...")
        l1.addWidget(QLabel("Text Overlay:")); l1.addWidget(self.txt_thumb_text)

        # C2: Config
        c2 = QWidget(); l2 = QVBoxLayout(c2)
        l2.addWidget(QLabel("Số lượng tạo:"))
        self.spin_thumb_qty = QComboBox(); self.spin_thumb_qty.addItems(["1 phương án", "2 phương án", "4 phương án"])
        l2.addWidget(self.spin_thumb_qty)

        # Nút Tạo Full
        self.btn_create_full = QPushButton("⚡ TẠO THUMBNAIL (FULL)")
        self.btn_create_full.setToolTip("Tự động: Tìm Sticker -> Vẽ Nền -> Ghép Layer")
        self.btn_create_full.setStyleSheet("background: #d35400; font-weight:bold; font-size: 14px; padding: 12px;")
        self.btn_create_full.clicked.connect(self.action_generate_full_thumbnail) # Hàm mới
        l2.addWidget(self.btn_create_full)

        # [NEW] Nút AI Auto Thumbnail (Pipeline yt_thumbnail_creator)
        self.btn_ai_auto_thumb = QPushButton("🤖 AI AUTO THUMBNAIL")
        self.btn_ai_auto_thumb.setToolTip("Pipeline AI tự động: Phân tích Topic → Tạo Assets → Xóa nền → Ghép lớp")
        self.btn_ai_auto_thumb.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #8E2DE2, stop:1 #4A00E0);"
            "font-weight:bold; font-size: 14px; padding: 12px; color: white; border-radius: 6px;"
        )
        self.btn_ai_auto_thumb.clicked.connect(self.action_ai_auto_thumbnail)
        l2.addWidget(self.btn_ai_auto_thumb)
        l2.addStretch()


        # C3: Preview Slider
        c3 = QWidget(); l3 = QVBoxLayout(c3)
        # [CTO FIX 1] Dùng ZoomableLabel để Zoom và set tỷ lệ 16:9
        self.lbl_thumb_preview = ZoomableLabel(is_banner=True) 
        #self.lbl_thumb_preview.setFixedSize(320, 180) # Chuẩn 16:9 (Scale nhỏ)
        self.lbl_thumb_preview.setText("NO PREVIEW")
        self.lbl_thumb_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_thumb_preview.setStyleSheet("border: 2px dashed #444; background: #000;")
        self.lbl_thumb_preview.setMinimumHeight(350)
        self.lbl_thumb_preview.setScaledContents(True)
        
        # Thanh điều hướng
        h_nav = QHBoxLayout()

        # Nút Đổi Bố Cục (Re-roll Layout)
        self.btn_reroll_layout = QPushButton("🎲 Đổi Bố Cục")
        self.btn_reroll_layout.setStyleSheet("background: #2980b9; font-weight: bold;")
        self.btn_reroll_layout.clicked.connect(self.action_randomize_layout) # Hàm mới

        self.btn_prev_thumb = QPushButton("<")
        self.btn_prev_thumb.clicked.connect(lambda: self.nav_thumb_step(-1))

        # --- [CTO ADD] NÚT XÓA ẢNH ĐANG XEM ---
        self.btn_delete_thumb = QPushButton("🗑️ Xóa")
        self.btn_delete_thumb.setStyleSheet("background: #c0392b; font-weight: bold;")
        self.btn_delete_thumb.setToolTip("Xóa bỏ phương án này khỏi danh sách")
        self.btn_delete_thumb.clicked.connect(self.action_delete_current_thumb)
        # --------------------------------------

        self.btn_next_thumb = QPushButton(">")
        self.btn_next_thumb.clicked.connect(lambda: self.nav_thumb_step(1))

        #h_nav = QHBoxLayout()
        # [CTO UPDATE] Ô tích tự động chọn ảnh hiện tại
        self.chk_select_thumb = QCheckBox("✅ Đang dùng ảnh này")
        self.chk_select_thumb.setChecked(True) # Luôn tích
        self.chk_select_thumb.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents) # Khóa click chuột, chỉ để hiển thị
        self.chk_select_thumb.setStyleSheet("color: #2ecc71; font-weight: bold; font-size: 13px;")

        # [CTO FIX 3] Nút Tải xuống thủ công
        self.btn_dl_thumb = QPushButton("⬇ Tải Về Máy")
        self.btn_dl_thumb.setFixedWidth(120)
        self.btn_dl_thumb.setToolTip("Lưu ảnh hiện tại ra máy")
        self.btn_dl_thumb.clicked.connect(self.action_download_current_thumb)

        h_nav.addWidget(self.btn_prev_thumb)
        h_nav.addWidget(self.btn_reroll_layout)
        h_nav.addWidget(self.btn_delete_thumb)
        h_nav.addWidget(self.chk_select_thumb)
        h_nav.addWidget(self.btn_next_thumb)
        h_nav.addWidget(self.btn_dl_thumb)
        
        # Label đếm số (1/4)
        self.lbl_thumb_count = QLabel("0/0")
        self.lbl_thumb_count.setAlignment(Qt.AlignmentFlag.AlignCenter)

        l3.addWidget(QLabel("Kết quả:"))
        l3.addWidget(self.lbl_thumb_preview)
        l3.addWidget(self.lbl_thumb_count)
        l3.addLayout(h_nav)

        return c1, c2, c3

    # ============================================================
    # 🏭 LUỒNG 5: MUSIC & SFX (BƯỚC 3)
    # ============================================================
    def setup_flow_music(self):
        # C1: Input
        c1 = QWidget(); l1 = QVBoxLayout(c1)
        self.txt_music_key = QLineEdit()
        self.txt_music_key.setPlaceholderText("Vui, Buồn, Kịch tính...")
        l1.addWidget(QLabel("<b>BƯỚC 3:</b> TÌM NHẠC NỀN & SFX:")); l1.addWidget(self.txt_music_key)
        l1.addStretch()

        # C2: Action
        c2 = QWidget(); l2 = QVBoxLayout(c2)
        self.btn_search_music = QPushButton("🔎 Tìm thủ công")
        self.btn_search_music.setStyleSheet("background: #34495e; padding: 6px;")
        self.btn_search_music.clicked.connect(self.action_search_music_online)

        self.btn_auto_music = QPushButton("⚡ TỰ ĐỘNG (AUTO)")
        self.btn_auto_music.setToolTip("BƯỚC 3: AI sẽ phân tích 'Mood' của video và tự động tìm nhạc nền phù hợp trên Pixabay/Pexels.")
        self.btn_auto_music.setStyleSheet("background: #16a085; font-weight: bold; padding: 10px; color: white;")
        self.btn_auto_music.clicked.connect(self.action_auto_music)

        self.btn_import_music = QPushButton("📂 NHẬP FILE MP3")
        self.btn_import_music.setStyleSheet("background: #e67e22; font-weight: bold; padding: 8px;")
        self.btn_import_music.clicked.connect(self.action_import_music)
        
        # [VEO PRO UPGRADE] Vocal Strip Button
        self.btn_strip_vocal = QPushButton("🎙️ TÁCH LỜI (STRIP VOCAL)")
        self.btn_strip_vocal.setToolTip("Dùng AI Demucs để tách lời khỏi nhạc")
        self.btn_strip_vocal.setStyleSheet("background: #2c3e50; border: 1px solid #f1c40f; color: #f1c40f; padding: 8px;")
        self.btn_strip_vocal.clicked.connect(self.action_strip_vocal)

        l2.addWidget(QLabel("Hành động:"))
        l2.addWidget(self.btn_auto_music)
        l2.addWidget(self.btn_search_music)
        l2.addWidget(self.btn_import_music)
        l2.addWidget(self.btn_strip_vocal)
        l2.addStretch()
        # C3: Output List & Player
        c3 = QWidget(); l3 = QVBoxLayout(c3)
        self.list_music_res = QListWidget() # List kết quả tìm kiếm
        self.list_music_res.setFixedHeight(100)
        # [ADDED] Kết nối click để nghe thử nhạc Online
        self.list_music_res.itemClicked.connect(self.on_search_result_clicked)
        
        l3.addWidget(QLabel("Kết quả tìm kiếm:"))
                
        # Mini Player cho nhạc
        h_m = QHBoxLayout()
        btn_mp = QPushButton("▶"); btn_mp.setFixedWidth(30); btn_mp.clicked.connect(self.play_music_preview)
        btn_ms = QPushButton("⏹"); btn_ms.setFixedWidth(30); btn_ms.clicked.connect(self.player.stop)
        self.lbl_music_file = QLabel("[Chưa chọn file]")
        
        h_m.addWidget(btn_mp); h_m.addWidget(btn_ms); h_m.addWidget(self.lbl_music_file)
        l3.addLayout(h_m)
        l3.addWidget(self.list_music_res)

        return c1, c2, c3

    def setup_header_columns(self):
        """Tiêu đề 3 cột cho dễ nhìn"""
        h_head = QHBoxLayout()
        # Tỷ lệ 35 - 25 - 40
        lbl1 = QLabel("INPUT DATA (Nguyên liệu)"); lbl1.setStyleSheet("background:#2c3e50; padding:5px; font-weight:bold; color:#ccc")
        lbl2 = QLabel("CONFIG (Cấu hình)"); lbl2.setStyleSheet("background:#2c3e50; padding:5px; font-weight:bold; color:#3498db")
        lbl3 = QLabel("OUTPUT (Sản phẩm)"); lbl3.setStyleSheet("background:#2c3e50; padding:5px; font-weight:bold; color:#2ecc71")
        
        h_head.addWidget(lbl1, 35)
        h_head.addWidget(lbl2, 25)
        h_head.addWidget(lbl3, 40)
        self.bench_layout.addLayout(h_head)

    # ========================================================================
    # 🧠 LOGIC 1: ĐẠO DIỄN AI (AUTO DIRECTOR)
    # ========================================================================
    def on_monitor_row_clicked(self, item):
        """Khi CEO bấm vào 1 dòng Video -> Kích hoạt Đạo diễn AI & Auto-Config"""
        if not item: return
        row = item.row()
        if row not in self.tasks_map: return
        
        # 1. Load dữ liệu task
        self.current_task = self.tasks_map[row]
        self.current_task['row_index'] = row
        display_title = self.current_task.get('title') or self.current_task.get('key_vua')
        self.log_signal.emit(f"🎯 Đã chọn video: {display_title}")

        # Hiển thị Tiêu đề Video (Ưu tiên Title)
        display_title = self.current_task.get('title') or self.current_task.get('key_vua')
        self.lbl_video_title.setText(f"🎬 {display_title}")    
                
        # 2. Reset giao diện sạch sẽ
        self.txt_voice_in.clear()
        self.list_visual_in.clear()
        self.txt_music_key.clear()
        self.txt_thumb_prompt.clear()
        self.txt_thumb_text.clear() # Reset ô text thumb
        self.list_visual_out.clear()

        # --- [QUAN TRỌNG] BƯỚC 1: GỌI ĐẠO DIỄN AI SET MẶC ĐỊNH TRƯỚC ---
        # Hàm này sẽ set Tone giọng, Tốc độ, và cả Visual Style mặc định theo Kênh
        self._apply_ai_director_config() 
        # ---------------------------------------------------------------

        # 3. [QUAN TRỌNG] NẠP DỮ LIỆU TỪ "KHO TỔNG" (DATABASE JSON)
        # Chúng ta ưu tiên đọc từ script_content trong DB trước, vì nó là mới nhất
        raw_script = self.current_task.get("script_content", "")
        has_data_in_ram = False

        if raw_script:
            # Gọi hàm phân tích JSON (tôi sẽ viết hàm helper này ngay dưới)
            parsed = self._extract_data_from_script(raw_script)
            if parsed:
                has_data_in_ram = True
                self.txt_voice_in.setText(parsed['voice'])
                self.txt_music_key.setText(parsed['music'])
                self.txt_thumb_prompt.setText(parsed['thumb_prompt'])
                self.txt_thumb_text.setText(parsed['thumb_text'])

                # --- [CTO FIX] TỰ ĐỘNG CẤU HÌNH VISUAL SOURCE ---
                ratio_str = parsed.get("visual_ratio", "").lower()
                print(f"🤖 Auto Config Visual: {ratio_str}")                
                
                # Logic: Nếu có chữ "100% ai" -> Chọn AI. Còn lại ưu tiên Stock (Hybrid)
                self.cb_vis_source.blockSignals(True) # Khóa để không giật
                if "100% ai" in ratio_str or "no stock" in ratio_str:
                    self.cb_vis_source.setCurrentIndex(1) # 100% AI
                elif "100% stock" in ratio_str:
                    self.cb_vis_source.setCurrentIndex(2) # 100% Stock
                else:
                    self.cb_vis_source.setCurrentIndex(0) # Hybrid (Mặc định)
                self.cb_vis_source.blockSignals(False)
                # ------------------------------------------------

                # B. PHONG CÁCH (Style)
                style_str = parsed.get("visual_style", "")
                if not style_str:
                    prof = self.projects[self.current_project_index].get("channel_profile", {})
                    style_str = prof.get("visual_style_preset", "Cinematic")
                
                # [CTO FIX] Chuyển đổi từ ComboBox sang Style Cards logic
                self.on_style_selected(style_str)

                # 3. TỰ ĐỘNG CHỌN TỶ LỆ (ASPECT RATIO)
                # Dựa vào Platform của dự án
                proj = self.projects[self.current_project_index]
                platform = proj.get("platform", "Youtube").lower()                
                self.cb_ratio.blockSignals(True)
                if any(x in platform for x in ["short", "tiktok", "reel", "story"]):
                    self.cb_ratio.setCurrentIndex(1) # Dọc (9:16)
                else:
                    self.cb_ratio.setCurrentIndex(0) # Ngang (16:9)
                self.cb_ratio.blockSignals(False)
                # -----------------------------------------------   
                
                
                # === FORMAT SCENE INPUT với widget cố định 120px (khớp Output) ===
                for idx, scene in enumerate(parsed['visuals']):
                    self._add_visual_in_item(idx + 1, scene)

        # 4. [FALLBACK] Nếu trong RAM không có (hoặc user đã sửa tay và lưu file), mới load từ File            
        path = self.current_task.get('pj_path', '')
        if not has_data_in_ram and path and os.path.exists(path):
            self._load_file_content(os.path.join(path, "voice.txt"), self.txt_voice_in)
            self._load_file_content(os.path.join(path, "music.txt"), self.txt_music_key)
            # 1. Load Prompt vẽ ảnh
            self._load_file_content(os.path.join(path, "thumbnail.txt"), self.txt_thumb_prompt)
            # 2. Load Text Overlay (Chữ trên ảnh)
            self._load_file_content(os.path.join(path, "text_thumb.txt"), self.txt_thumb_text)          
            # Load Scenes List
            sc_file = os.path.join(path, "scenes_visual.txt")
            if os.path.exists(sc_file):
                with open(sc_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    for idx, line in enumerate(lines):
                        if line.strip():
                            self._add_visual_in_item(idx + 1, line.strip())
            self._apply_ai_director_config()

        # 5. Load Preview Output (Cột bên phải)
        self.load_visual_preview()
        self.check_files_status()

        # [CTO FIX 2] LOAD LẠI THUMBNAIL CŨ (NẾU CÓ)
        self.thumb_candidates = [] # Reset list
        self.current_thumb_idx = 0
        
        path = self.current_task.get('pj_path', '')
        thumb_dir = os.path.join(path, "thumb_candidates")
        
        if os.path.exists(thumb_dir):
            # Quét tất cả file jpg/png trong folder candidates
            files = sorted([f for f in os.listdir(thumb_dir) if f.lower().endswith(('.jpg', '.png'))])
            for f in files:
                self.thumb_candidates.append(os.path.join(thumb_dir, f))
        
        # Nếu có thumbnail.jpg chính thức -> Thêm vào đầu danh sách
        final_thumb = os.path.join(path, "thumbnail.jpg")
        if os.path.exists(final_thumb):
            if final_thumb not in self.thumb_candidates:
                self.thumb_candidates.insert(0, final_thumb)

        # Hiển thị ảnh đầu tiên
        self.update_thumb_preview_ui()

    # ============================================================
    # 🧠 LOGIC 2: HỖ TRỢ PHÂN TÍCH KỊCH BẢN
    # --- HÀM PHỤ TRỢ MỚI: TÁCH DỮ LIỆU TỪ JSON KỊCH BẢN ---
    def _extract_data_from_script(self, raw_text):
        """Đào dữ liệu từ JSON hỗn độn của AI Content"""
        if not raw_text: return None
        try:
            import re
            import json
            
            # Tìm JSON trong text (nếu có rác xung quanh)
            json_str = raw_text
            if "```json" in raw_text:
                json_str = raw_text.split("```json")[1].split("```")[0].strip()
            elif "{" in raw_text:
                # Tìm từ { đầu đến } cuối
                start = raw_text.find('{')
                end = raw_text.rfind('}') + 1
                json_str = raw_text[start:end]
                
            data = json.loads(json_str)
            
            # Trích xuất dữ liệu
            result = {
                "voice": "", "music": "", "thumb_prompt": "", 
                "thumb_text": "", "visuals": [],
                "visual_ratio": ""
            }
            
            # 1. Lấy Visual Rules (Cấu hình nguồn ảnh)
            # Tìm trong visual_rules hoặc visual_controller
            vr = data.get("VISUAL_RULES", {}) or data.get("VISUAL_CONTROLLER", {}).get("Settings", {})
            result["visual_ratio"] = vr.get("ratio", "") or vr.get("Ratio", "")

            # 2. Marketing Kit (Thumb & Text)
            mk = data.get("marketing_kit", {})
            if not mk and "marketing_kit" not in data: mk = data # Fallback
            
            result["thumb_prompt"] = mk.get("thumbnail_prompt", "")
            result["thumb_text"] = mk.get("thumbnail_text", "")
            
            # 3. Audio & Music
            ad = data.get("audio_director", {}) or data.get("audio_engineer_recipe", {})
            # Tìm keyword nhạc
            music = ad.get("music_keywords", "") or ad.get("music_mood", "") or \
                    ad.get("layer_2_music_search", "")
            result["music"] = music
            
            # 4. Kịch bản & Visuals
            sb = data.get("script_board", []) or data.get("scenes", [])            
            voice_acc = ""
            for scene in sb:
                # Voice
                txt = scene.get("voice_text", "") or scene.get("narration", "")
                if txt: voice_acc += f"{txt}\n\n"
                
                # Visual
                vis = scene.get("visual_prompt", "") or scene.get("visual_desc", "")
                if vis: result["visuals"].append(vis.replace("\n", " ").strip())
                
            result["voice"] = voice_acc.strip()

            # [THÊM] Lấy Visual Style
            style = ""
            # Tìm trong visual_identity (marketing kit)
            if "visual_identity" in data:
                style = data["visual_identity"].get("style_preset", "")
            # Hoặc tìm trong visual_rules
            if not style:
                style = vr.get("style", "") or vr.get("Art_Style", "")
                
            result["visual_style"] = style
            
            return result
            
        except Exception as e:
            print(f"Lỗi parse JSON trong MediaTab: {e}")
            return None
        
    def _apply_ai_director_config(self):
        """Hàm tự động chỉnh thông số Voice dựa trên Quốc gia & Chủ đề"""
        if self.current_project_index < 0: return
        
        proj = self.projects[self.current_project_index]
        country = proj.get("country", "Global")
        topic = proj.get("topic", "General")
        
        # Import bộ não
        from services.voice_constants import get_smart_voice_config, get_voice_list_by_country
        
        # 1. Lấy cấu hình gợi ý
        config = get_smart_voice_config(country, topic)
        self.lbl_config_status.setText(f"⚙️ Director: {config.get('style_tag', 'Auto')} | 🏳️ {country}")
        
        # 2. Chỉnh Slider Rate/Pitch (Tự động vặn núm)
        try:
            r = int(config.get("rate", "+0%").replace("%", "").replace("+", ""))
            p = int(config.get("pitch", "+0Hz").replace("Hz", "").replace("+", ""))
            self.sl_rate.setValue(r)
            self.sl_pitch.setValue(p)
        except: pass
        
        # 3. Auto chọn Giọng phù hợp quốc gia
        self.cb_voice_name.blockSignals(True)
        self.cb_voice_name.clear()
        voices = get_voice_list_by_country(country.split('~')[0].strip())
        
        # Nạp list giọng
        for v in voices:
            self.cb_voice_name.addItem(v['full_name'], v['id'])
            
        # Chọn giọng King (được gợi ý)
        suggested_id = config.get("voice_id", "")
        idx = self.cb_voice_name.findData(suggested_id)
        if idx >= 0:
            self.cb_voice_name.setCurrentIndex(idx)
        elif self.cb_voice_name.count() > 0:
            self.cb_voice_name.setCurrentIndex(0)
            
        self.cb_voice_name.blockSignals(False)
        
    def _load_file_content(self, filepath, widget):
        """Helper đọc file an toàn"""
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if isinstance(widget, QTextEdit): widget.setText(content)
                elif isinstance(widget, QLineEdit): widget.setText(content)

    # ========================================================================
    # 🏭 LOGIC 2: DÂY CHUYỀN SẢN XUẤT (ACTION HANDLERS)
    # ========================================================================    
    
    def _browse_ref_audio(self):
        """Mở hộp thoại chọn file âm thanh mẫu cho LuxTTS."""
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn Audio Mẫu (LuxTTS)", "",
            "Audio Files (*.wav *.mp3 *.m4a *.flac);;All Files (*)"
        )
        if path:
            self.txt_ref_audio.setText(path)

    def action_single_voice(self):
        """Tạo Voice cho 1 video đang chọn"""
        if not self.current_task:
            return QMessageBox.warning(self, "Chưa chọn", "Vui lòng chọn 1 Video bên trái trước!")
            
        self.log_signal.emit("🎙️ BƯỚC 1: Đang khởi tạo giọng đọc AI...")
        # ... logic tạo voice ...
        """Tạo Voice (Có xử lý Silent Mode cho kênh nhạc/thiền)"""
        if not self.current_task: return
        self.log_signal.emit("🎙️ Bắt đầu tiến trình tạo Voice...")
        
        # 1. Lấy text từ ô Input (Đã được nạp từ JSON)
        text = self.txt_voice_in.toPlainText().strip()
        path = self.current_task.get('pj_path', '')        
                
        # Nếu vẫn rỗng -> Dừng ngay lập tức để không Crash tool
        if not path:
            QMessageBox.critical(self, "Lỗi Dữ Liệu", "Chưa xác định được thư mục lưu!\nVui lòng chọn lại Kênh bên trái để hệ thống tính toán đường dẫn.")
            return
        # ---------------------------------------------

        # Tạo thư mục nếu chưa có
        if not os.path.exists(path): os.makedirs(path, exist_ok=True)
        out_path = os.path.join(path, "voice.mp3")

       # --- [CTO FIX] LOGIC SILENT MODE (CHẾ ĐỘ IM LẶNG) ---
        # Danh sách từ khóa báo hiệu không cần đọc
        keywords_silent = ["(NO VOICE", "(SILENT", "NO_VOICE", "AUDIO LAYERS PLAYING ONLY"]
        is_silent = False
        
        if any(k in text.upper() for k in keywords_silent) or len(text) < 5:
            is_silent = True
        
        if is_silent:
            self.log("🔕 Phát hiện chế độ Silent/Music. Đang tạo file MP3 im lặng...")
            
            try:
                # Dùng FFmpeg tạo 10 giây im lặng (Dummy Audio) để khâu Dựng phim không bị lỗi
                import subprocess
                cmd = f'ffmpeg -f lavfi -i anullsrc=r=44100:cl=mono -t 10 -q:a 9 -acodec libmp3lame -y "{out_path}"'
                
                # Chạy ẩn không hiện cửa sổ đen
                subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                # 2. [QUAN TRỌNG] TẠO FILE SUBTITLE GIẢ (Để đèn báo Xanh)
                # Nội dung sub là "(Music)" hiển thị trong 5 giây đầu
                srt_content = "1\n00:00:00,000 --> 00:00:05,000\n(Music / Âm thanh gốc)"
                with open(os.path.join(path, "voice.srt"), "w", encoding="utf-8") as f: f.write(srt_content)

                # Báo thành công giả lập
                self.on_voice_done(True, "✅ Đã tạo Voice Im Lặng (Silent Mode) & Sub giả", out_path)
                return # THOÁT NGAY, KHÔNG GỌI API NỮA
                
            except Exception as e:
                self.log(f"⚠️ Lỗi tạo Silent MP3: {e}. (Cần cài FFmpeg)")
                return

        # [CTO FIX] Map lựa chọn từ giao diện sang mã Provider
        selected_engine_idx = self.cb_voice_eng.currentIndex()
        provider_map = {
            0: "auto",      # Auto (AI Director)
            1: "google",    # Google TTS
            2: "edge",      # Edge TTS
            3: "openai",    # OpenAI TTS
            4: "luxtts"     # LuxTTS (Voice Clone)
        }
        selected_provider = provider_map.get(selected_engine_idx, "auto")

        # Meta data (Lấy từ giao diện - Nơi Đạo diễn AI đã chỉnh)
        meta = {
            "rate": f"{self.sl_rate.value()}%",
            "pitch": f"{self.sl_pitch.value()}Hz",
            "voice_id": self.cb_voice_name.currentData(),            
            "provider_override": selected_provider,
            "reference_audio": self.txt_ref_audio.text().strip()
        }
        # Fallback nếu currentData() bị rỗng (do chưa load xong danh sách)
        if not meta["voice_id"]:
             # Nếu đang làm kênh Global/US -> Fallback về giọng Mỹ
            current_proj = self.projects[self.current_project_index] if self.current_project_index >= 0 else {}
            country = current_proj.get("country", "VN")
            
            if "US" in country or "Global" in country:
                meta["voice_id"] = "en-US-AvaNeural" # Giọng nữ chuẩn Mỹ
            else:
                meta["voice_id"] = "vi-VN-HoaiMyNeural" # Giọng nữ chuẩn Việt
        
        # 2. Khóa nút & Chạy Worker (Hiệu ứng UI của #1)
        self.btn_gen_voice.setEnabled(False); self.btn_gen_voice.setText("⏳ Đang render...")
        self.log(f"🎙️ Bắt đầu tạo Voice cho ID {self.current_task['id']} (Provider: {selected_provider})...")
        print(f"DEBUG: Voice Text Len={len(text)}, Provider={selected_provider}, VoiceID={meta['voice_id']}")
        
        self.voice_worker = VoiceWorker(text, out_path, meta)
        self.voice_worker.finished_signal.connect(self.on_voice_done)
        # [ADDED] Kết nối sự kiện dừng để mở lại nút
        self.voice_worker.finished.connect(self.on_worker_finished)
        self.voice_worker.start()

    def on_voice_done(self, success, msg, path):
        """Voice làm xong thì báo cáo (Chuẩn V3.2)"""
        # 1. Mở khóa và Reset tên nút
        self.btn_gen_voice.setEnabled(True)
        self.btn_gen_voice.setText("🎙️ TẠO VOICE (Full)")
        
        self.log(f"{'✅' if success else '❌'} {msg}")
        
        if success:
            # --- [CTO FIX] CHỐNG CHÉO LUỒNG (RACE CONDITION) ---
            # Kiểm tra xem file vừa tạo xong (path) có nằm trong thư mục của task đang chọn không?
            # Nếu CEO đã bấm sang Video khác, thì self.current_task['pj_path'] sẽ khác path vừa tạo.
            
            if not self.current_task: return
            
            # Chuẩn hóa đường dẫn để so sánh (tránh lỗi dấu / và \)
            current_dir = os.path.normpath(self.current_task.get('pj_path', ''))
            created_file_dir = os.path.normpath(os.path.dirname(path))
            
            # Chỉ cập nhật UI nếu đúng là video đang mở
            if current_dir == created_file_dir:
                # 1. Bật đèn xanh & Mở khóa nút Folder
                self.lbl_voice_out.setText("✅ Ready (MP3+SRT)")
                self.lbl_voice_out.setStyleSheet("color:#2ecc71; font-weight:bold")
                self.btn_open_folder.setEnabled(True)
                
                # 2. Nạp file vào Player
                self.player.setSource(QUrl.fromLocalFile(path))
                
                # 3. Update bảng (cột 2)
                self.check_files_status() 

                # Update trạng thái trong bảng danh sách (Table Monitor)
                # Tìm dòng tương ứng để tích V
                row = self.current_task.get('row_index', -1) # Cần lưu row_index lúc click (xem bên dưới)
                # (Nếu lười lưu row_index thì chỉ cần gọi check_files_status là đủ cho UI chính)
                if row >= 0:
                    # Cập nhật cột Voice (Cột 2)
                    has_sub = os.path.exists(path.replace(".mp3", ".srt"))
                    icon = "🔊+📝" if has_sub else "🔊"
                    
                    item_icon = QTableWidgetItem(icon)
                    item_icon.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.table_mon.setItem(row, 2, item_icon)
                    
                    # Cập nhật cột Trạng Thái (Cột 6) - Logic All or Nothing
                    # Lấy lại trạng thái các file khác để tính toán
                    vis_path = os.path.join(current_dir, "visuals")
                    has_vis = os.path.exists(vis_path) and len(os.listdir(vis_path)) > 0
                    has_music = os.path.exists(os.path.join(current_dir, "background.mp3"))
                    has_thumb = os.path.exists(os.path.join(current_dir, "thumbnail.jpg"))
                    
                    status_txt = "⚪ Chưa làm"
                    if has_vis and has_music and has_thumb: # Đã có Voice (vừa tạo xong) + 3 món kia
                        status_txt = "🟢 Sẵn sàng dựng"
                    else:
                        # Logic báo thiếu
                        missing = []
                        if not has_vis: missing.append("Visual")
                        if not has_music: missing.append("Music")
                        if not has_thumb: missing.append("Thumb")
                        status_txt = f"🟡 Thiếu: {', '.join(missing)}"
                        
                    item_stt = QTableWidgetItem(status_txt)
                    if "🟢" in status_txt: item_stt.setForeground(QColor("#2ecc71"))
                    else: item_stt.setForeground(QColor("#f1c40f"))
                    
                    self.table_mon.setItem(row, 6, item_stt)
                # -------------------------------------------------------------
            
            else:
                self.log(f"⚠️ Voice hoàn thành ngầm cho video khác: {os.path.basename(current_dir)}")
            
            # 4. Nếu đang chạy Batch -> Chuyển sang việc tiếp theo (Luôn chạy dù có đang xem hay không)
            if self.is_batch_running:
                QTimer.singleShot(1000, self.process_next_batch_item)




    # --- HÀM PHỤ TRỢ AN TOÀN (Thêm vào class MediaTab nếu chưa có) ---
    def on_worker_finished_safe(self, btn_widget, reset_text):
        """Mở khóa nút an toàn khi worker dừng"""
        if btn_widget:
            btn_widget.setEnabled(True)
            btn_widget.setText(reset_text)
        
        # Nếu đang chạy Batch -> Gọi tiếp cái sau
        if hasattr(self, 'is_batch_running') and self.is_batch_running:
             # Dùng QTimer để tránh đệ quy sâu gây crash
             QTimer.singleShot(1000, self.process_next_batch_item)
    
    def action_view_subtitle(self):
        """Mở hộp thoại xem nội dung file Subtitle"""
        if not self.current_task: return
        path = self.current_task.get("pj_path", "")
        srt_path = os.path.join(path, "voice.srt")
        
        if os.path.exists(srt_path):
            try:
                with open(srt_path, "r", encoding="utf-8") as f:
                    content = f.read()
                
                # Tạo Dialog để hiển thị
                dlg = QDialog(self)
                dlg.setWindowTitle(f"Nội dung Subtitle - {self.current_task.get('key_vua')}")
                dlg.setMinimumSize(500, 400)
                
                l = QVBoxLayout(dlg)
                txt = QTextEdit()
                txt.setPlainText(content)
                txt.setReadOnly(True) # Chỉ xem, không sửa trực tiếp ở đây
                txt.setStyleSheet("font-family: Consolas; font-size: 12px; background: #222; color: #0f0;")
                
                btn_close = QPushButton("Đóng")
                btn_close.clicked.connect(dlg.close)
                
                l.addWidget(QLabel("File: voice.srt"))
                l.addWidget(txt)
                l.addWidget(btn_close)
                
                dlg.exec()
            except Exception as e:
                QMessageBox.warning(self, "Lỗi", f"Không đọc được file: {e}")

    def on_style_selected(self, name):
        """Xử lý khi người dùng chọn 1 Style Card"""
        self.current_style = name
        for card in self.style_cards:
            card.selected = (card.name == name)
            card.update_style()
        self.log(f"🎨 Đã chọn phong cách: {name}")

    def on_visual_done(self, success, msg, first_img):
        """Xử lý khi Worker Visual chạy xong (Chuẩn V3.2)"""
        # Mở khóa nút bấm
        self.btn_find_visual.setEnabled(True)
        self.btn_find_visual.setText("🖼️ TÌM & TẠO (AUTO)")
        
        # Ghi log
        self.log(f"{'✅' if success else '❌'} {msg}")
        
        if success:
            # 1. Load ảnh ra khung Preview
            self.load_visual_preview()
            # 2. Bật đèn xanh trên bảng Video
            self.check_files_status()
            
            # 3. Nếu đang chạy Batch (Tạo Full Kênh) -> Chuyển sang việc tiếp theo sau 1 giây
            if self.is_batch_running:
                QTimer.singleShot(1000, self.process_next_batch_item)

    # ========================================================================
    # 📦 LOGIC 3: HÀNG ĐỢI TỰ ĐỘNG (BATCH QUEUE)
    # ========================================================================
    
    def batch_action(self, action_type):
        """Nút bấm quyền lực: TẠO FULL KÊNH (Chuẩn V3.2 - Có đổi màu nút STOP)"""
        if self.current_project_index < 0: 
            return QMessageBox.warning(self, "Lỗi", "Chưa chọn Kênh nào!")
        
        proj = self.projects[self.current_project_index]
        tasks = proj.get("tasks", [])
        
        # --- [FIX QUAN TRỌNG] Tái tạo đường dẫn gốc cho Dự án ---
        try:
            p_plat = self._sanitize_filename(proj.get("platform", "Youtube"))
            p_coun = self._sanitize_filename(proj.get("country", "Global").split('~')[0])
            p_top = self._sanitize_filename(proj.get("topic", "General"))
            base_project_path = os.path.join("VEO_DB", p_plat, p_coun, p_top)
        except:
            base_project_path = ""
        # -------------------------------------------------------

        # Lọc ra các việc cần làm
        self.batch_queue = []

        for t in tasks:
            # 1. TÍNH TOÁN ĐƯỜNG DẪN CHO TỪNG BÀI (Nếu chưa có)
            if 'pj_path' not in t or not t['pj_path']:
                # Nếu đã có output_path trong DB thì dùng luôn
                if t.get("output_path") and os.path.exists(t.get("output_path")):
                    t['pj_path'] = t.get("output_path")
                else:
                    # Nếu chưa có (bài mới), tự tạo đường dẫn dự kiến
                    safe_key = self._sanitize_filename(t.get("key_vua", "Untitled"))
                    # Xác định Shorts/Long
                    is_short = any(x in p_plat.lower() for x in ["short", "tiktok", "reel"])
                    p_type = "Shorts" if is_short else "Long"
                    
                    # Đường dẫn dự kiến: VEO_DB/.../Key_Vua/Long/ID_Title
                    # Lưu ý: Ở bước này ta chưa biết Title thật, tạm dùng ID_KeyVua
                    task_folder_name = f"{t['id']}_{safe_key}"[:50]
                    t['pj_path'] = os.path.join(base_project_path, safe_key, p_type, task_folder_name)
                    
                    # Tạo luôn thư mục để tránh lỗi file not found sau này
                    if not os.path.exists(t['pj_path']):
                        try: os.makedirs(t['pj_path'])
                        except: pass

            path = t['pj_path'] # Giờ thì chắc chắn đã có path
            # Rule: Chưa có Voice -> Thêm việc Voice
            if not os.path.exists(os.path.join(path, "voice.mp3")):
                self.batch_queue.append({"type": "VOICE", "task": t})
            
            # Rule: Chưa có Visual -> Thêm việc Visual
            vis_dir = os.path.join(path, "visuals")
            if not os.path.exists(vis_dir) or not os.listdir(vis_dir):
                self.batch_queue.append({"type": "VISUAL", "task": t})

            # Rule: Chưa có Music -> Thêm việc Music (Chuẩn V3.2)
            if not os.path.exists(os.path.join(path, "background.mp3")):
                self.batch_queue.append({"type": "MUSIC", "task": t})

            # Rule: Chưa có Thumbnail -> Thêm việc Thumbnail
            if not os.path.exists(os.path.join(path, "thumbnail.jpg")):
                self.batch_queue.append({"type": "THUMBNAIL", "task": t})
        
        if not self.batch_queue:
            return QMessageBox.information(self, "Tuyệt vời", "Toàn bộ video trong kênh này đã ĐỦ nguyên liệu!")    
        
        # Kích hoạt chế độ chạy ngầm
        self.is_batch_running = True
        self.btn_batch.setText(f"⛔ STOP ({len(self.batch_queue)})")
        self.btn_batch.setStyleSheet("background: #c0392b; color: white; font-weight: bold;") # Đổi màu đỏ
        self.log(f"🚀 BẮT ĐẦU CHẠY BATCH: {len(self.batch_queue)} tác vụ đang xếp hàng...")
        
        self.process_next_batch_item()

    def process_next_batch_item(self):
        """Hàm đệ quy xử lý từng việc một (Chuẩn V3.2)"""
        # 1. Kiểm tra cờ dừng (Nếu bấm Stop thì thoát ngay)
        if not self.is_batch_running: return 
        
        # 2. Kiểm tra hết hàng đợi
        if not self.batch_queue:
            self.is_batch_running = False
            # Reset nút bấm về màu xanh
            self.btn_batch.setText("⚡ TẠO FULL (Kênh)")
            self.btn_batch.setStyleSheet("background: #27ae60; color: white; font-weight: bold;")
            self.log("🏁 BATCH HOÀN TẤT! Đã xử lý xong tất cả.")
            QMessageBox.information(self, "Xong", "Đã chạy xong toàn bộ hàng đợi!")
            return

        # 3. Lấy việc tiếp theo
        job = self.batch_queue.pop(0)
        
        # [CTO FIX] Kiểm tra an toàn khóa 'task'
        if not job or "task" not in job:
            self.log("⚠️ Cảnh báo: Batch job không hợp lệ (thiếu metadata task). Bỏ qua...")
            QTimer.singleShot(500, self.process_next_batch_item)
            return
            
        self.current_task = job["task"] # Quan trọng: Set task hiện tại để các hàm action hiểu
        
        # 4. Cập nhật UI để CEO biết đang làm con nào
        self.lbl_video_title.setText(f"🔄 [AUTO] Đang làm: {self.current_task.get('key_vua')}")
        self.btn_batch.setText(f"⛔ STOP ({len(self.batch_queue)})")
        
        # 5. Phân phối việc
        if job["type"] == "VOICE":
            # Cần load text voice lên trước thì hàm action mới có cái để đọc
            v_file = os.path.join(self.current_task['pj_path'], "voice.txt")
            self._load_file_content(v_file, self.txt_voice_in)
            
            # Gọi hàm tạo (Nó sẽ tự gọi lại process_next_batch_item khi xong)
            self.action_single_voice()
            
        elif job["type"] == "VISUAL":
            # Load scenes lên list
            sc_file = os.path.join(self.current_task['pj_path'], "scenes_visual.txt")
            self.list_visual_in.clear()
            if os.path.exists(sc_file):
                with open(sc_file, "r", encoding="utf-8") as f:
                    for l in f: self.list_visual_in.addItem(l.strip())
            
            # Gọi hàm tạo
            self.action_auto_visual()

        elif job["type"] == "MUSIC":
            # Nạp Keyword Music
            m_key = self.current_task.get("topic", "Cinematic") # Fallback topic
            self.txt_music_key.setText(m_key)
            
            # Gọi hàm tạo
            self.action_auto_music()
            
        elif job["type"] == "THUMBNAIL":
            # Gán số lượng mặc định là 1 và gọi tự động
            self.spin_thumb_qty.setCurrentText("1 ảnh")
            self.action_generate_full_thumbnail()

    def action_stop_all(self):
        """Cách 3: Dừng an toàn (Safe Stop via Flag) - ĐÃ FIX"""
        
        # 1. Ngắt việc nạp thêm task mới
        self.is_batch_running = False
        self.batch_queue = [] 
        self.log("⚠️ Đang gửi lệnh dừng... Vui lòng đợi worker hoàn tất tác vụ hiện tại.")

        # 2. Gửi tín hiệu dừng cho Voice Worker (nếu đang chạy)
        if hasattr(self, 'voice_worker') and self.voice_worker.isRunning():
            self.voice_worker.stop() # Gọi hàm stop() ta vừa viết trong Worker

        # 3. Gửi tín hiệu dừng cho Visual Worker (nếu đang chạy)
        if hasattr(self, 'vis_worker') and self.vis_worker.isRunning():
            if hasattr(self.vis_worker, 'stop'):
                 self.vis_worker.stop()
            else:
                 self.vis_worker.terminate() # Fallback nếu chưa có hàm stop
                 self.vis_worker.wait()
            
        # 4. Đổi trạng thái nút
        self.btn_batch.setText("⏳ ĐANG DỪNG...")
        self.btn_batch.setEnabled(False)
    
    def action_create_brand_assets(self):
        """Vẽ Logo/Banner dùng Pollinations (Free)"""
        if self.current_project_index < 0: 
            QMessageBox.warning(self, "Chưa chọn kênh", "Vui lòng chọn 1 Kênh bên trái trước!")
            return
        
        # Tạm thời dùng key giả để bypass check, vì Pollinations không cần key
        self.api_key_cache = "free-mode" 
        
        # Tạo folder lưu
        # Logic lấy đường dẫn folder kênh (Tạm thời lưu vào thư mục chạy tool/Brand_Assets nếu chưa có path chuẩn)
        proj = self.projects[self.current_project_index]
        save_dir = os.path.join("VEO_DB", "projects", self._sanitize_filename(proj['name']), "Brand_Assets")
        if not os.path.exists(save_dir): os.makedirs(save_dir)
        
        self.log(f"🎨 Đang vẽ AI... (Lưu tại: {save_dir})")
        self.btn_regen_brand.setEnabled(False); self.btn_regen_brand.setText("⏳ Đang vẽ...")

        # Lấy prompt từ DNA kênh
        prof = proj.get("channel_profile", {})
        brand = prof.get("brand_identity", {})
        
        # Prompt thông minh: Nếu không có prompt riêng, tự chế từ Mood
        mood = brand.get("mood", "Professional")
        color = brand.get("color_palette", "Modern")
        
        logo_prompt = f"Minimalist logo design, {mood} style, main color {color}, vector art, white background"
        banner_prompt = f"Youtube channel banner, {mood} atmosphere, abstract {color} theme, cinematic lighting, 4k, wide angle"

        # Chạy Worker
        self.worker_logo = BrandArtistWorker("", logo_prompt, "logo", save_dir)
        self.worker_logo.finished_signal.connect(self.on_brand_done)
        self.worker_logo.start()
        
        self.worker_banner = BrandArtistWorker("", banner_prompt, "banner", save_dir)
        self.worker_banner.finished_signal.connect(self.on_brand_done)
        self.worker_banner.start()

    def on_brand_done(self, success, msg, img_type, path):
        """Xử lý khi vẽ xong (Có chốt chặn an ninh chống nhầm kênh)"""
        # Mở lại nút tương ứng
        if img_type == "logo":
            self.btn_redraw_logo.setEnabled(True); self.btn_redraw_logo.setText("🔄 Vẽ Logo")
            lbl_target = self.lbl_logo
            w, h = 80, 80
        else:
            self.btn_redraw_banner.setEnabled(True); self.btn_redraw_banner.setText("🔄 Vẽ Banner")
            lbl_target = self.lbl_banner
            w, h = 142, 80
            
        self.log(msg)
        if success and os.path.exists(path):
            # --- [CTO FIX] CHỐNG NHẦM KÊNH (TARGET LOCK) ---
            # Kiểm tra xem file vừa vẽ xong có thuộc về kênh đang mở không?
            # So sánh thư mục chứa file vừa tạo với thư mục Brand hiện tại
            if not hasattr(self, 'current_brand_path'): return
            
            created_dir = os.path.normpath(os.path.dirname(path))
            current_view_dir = os.path.normpath(self.current_brand_path)
            
            if created_dir != current_view_dir:
                self.log(f"⚠️ Ảnh {img_type} đã xong nhưng bạn đã chuyển kênh. Không hiển thị để tránh nhầm lẫn.")
                return # Dừng lại ngay, không update giao diện
            # ------------------------------------------------
            
            # Nếu đúng kênh -> Nạp ảnh gốc để Zoom & Hiển thị
            lbl_target.set_high_res(path)
            
            # Hiển thị ảnh nhỏ (Thumbnail)
            pix = QPixmap(path)
            lbl_target.setPixmap(pix.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
            lbl_target.setStyleSheet("border: 1px solid #00e6e6;")
#            if img_type == 'logo': self.lbl_logo.setPixmap(pix.scaled(60, 60))
#            else: self.lbl_banner.setPixmap(pix.scaled(120, 60))
        self.log(msg)

    # --- [LOGIC MỚI] XỬ LÝ NÚT BẤM BỔ SUNG ---
    def play_music_preview(self):
        """Nghe thử file nhạc nền (Local) - Code #2 Chuẩn"""
        # Lấy đường dẫn từ current_task
        if not self.current_task: return
        path = self.current_task.get('pj_path', '')
        
        # Giả định file nhạc tên là background.mp3
        music_path = os.path.join(path, "background.mp3")
        
        if os.path.exists(music_path):
            self.player.setSource(QUrl.fromLocalFile(music_path))
            self.player.play()
            self.log(f"🎵 Đang phát preview: {os.path.basename(music_path)}")
        else:
            self.log("❌ Không tìm thấy file background.mp3 để nghe thử.")
            QMessageBox.warning(self, "Missing", "Chưa có file nhạc (background.mp3) trong thư mục dự án.")

    def on_search_result_clicked(self, item):
        """[ADDED] Hàm mới: Click vào list nhạc tìm kiếm để nghe thử ngay"""
        url = item.data(Qt.ItemDataRole.UserRole) # Lấy URL từ data ẩn
        if url:
            self.player.setSource(QUrl(url))
            self.player.play()
            self.log(f"🎵 Đang nghe thử Online: {item.text()}")
    
    def on_worker_finished(self):
        """[ADDED] Hàm này tự động chạy khi Worker thực sự tắt hẳn"""
        self.log("✅ Worker đã dừng hẳn/hoàn thành.")
        
        # Reset lại nút Batch
        if hasattr(self, 'btn_batch'):
            self.btn_batch.setText("⚡ TẠO FULL (Kênh)")
            self.btn_batch.setEnabled(True)
            self.btn_batch.setStyleSheet("background: #27ae60; color: white; font-weight: bold;")
        
        # Mở lại các nút chức năng lẻ (nếu bị khóa)
        if hasattr(self, 'btn_gen_voice'): 
            self.btn_gen_voice.setEnabled(True)
            self.btn_gen_voice.setText("🎙️ TẠO VOICE (Full)")
            
        if hasattr(self, 'btn_find_visual'): 
            self.btn_find_visual.setEnabled(True)
            self.btn_find_visual.setText("🖼️ TÌM & TẠO (AUTO)")
    
    # ============================================================
    # 🎨 LOGIC LUỒNG 4: THUMBNAIL STUDIO (BỔ SUNG)
    # ============================================================
    def action_generate_thumbnail(self):
        """Gọi AI vẽ Thumbnail dựa trên Prompt + Text"""
        if not self.current_task: 
            return QMessageBox.warning(self, "Chưa chọn", "Vui lòng chọn 1 video trước!")

        # 1. Lấy thông tin
        # Lấy Prompt nền (Không chứa text)
        base_prompt = self.txt_thumb_prompt.toPlainText().strip()
        # Lấy Text Overlay
        overlay_text = self.txt_thumb_text.text().strip()
        if not overlay_text: 
            # Nếu không nhập, lấy Key Vua nhưng phải VIẾT HOA
            overlay_text = self.current_task.get('key_vua', 'VIDEO TITLE')[:30].upper()
        else:
            overlay_text = overlay_text.upper() # <--- Ép viết hoa toàn bộ
        
        if not base_prompt:
            base_prompt = f"Youtube thumbnail background for {self.current_task.get('key_vua','')}, high contrast, 4k, viral style"

        # [CTO STRATEGY] BƯỚC 1: SỬA PROMPT ĐỂ AI KHÔNG VIẾT CHỮ
        # Chúng ta muốn một khoảng trống bên trái (Negative Space) để code chèn chữ vào
        clean_prompt = f"{base_prompt}, clean background, no text, negative space on the left, high quality"
        
        # [CTO UPGRADE] 2. EMOTION AMPLIFIER (Kích thích cảm xúc)
        # Tự động thêm từ khóa cảm xúc dựa trên Mood của kênh
        proj = self.projects[self.current_project_index]
        mood = proj.get("channel_profile", {}).get("brand_identity", {}).get("mood", "").lower()
        
        emotion_boost = ""
        if "horror" in mood or "scary" in mood:
            emotion_boost = "extreme close-up face, terrified expression, wide open eyes, screaming mouth, dramatic lighting, scary atmosphere"
        elif "funny" in mood or "kids" in mood:
            emotion_boost = "excited face, laughing, exaggerated expression, vibrant colors, mouth open, fun vibe"
        elif "money" in mood or "rich" in mood:
            emotion_boost = "shocked face, holding money, luxurious background, golden lighting, success vibe"
        else:
            emotion_boost = "high contrast, intense look, professional lighting, clear focus on subject"

        # Cấu trúc Prompt chuẩn: [Subject] + [Emotion] + [Background] + [No Text Rule]
        final_prompt = (
            f"{base_prompt}, {emotion_boost}. "
            "Clean background on the left side (negative space). "
            "High contrast, 8k resolution, trending on artstation. "
            "NO TEXT, NO LETTERS, NO WATERMARK."
        )

        # 3. Khóa nút
        self.btn_thumb.setEnabled(False)
        self.btn_thumb.setText("⏳ Đang vẽ nền...")
        self.log(f"🎨 Đang vẽ nền (No Text): {clean_prompt[:50]}...")
        
        # 4. Xác định nơi lưu
        path = self.current_task.get("pj_path", "")
        self.thumb_temp_dir = os.path.join(path, "thumb_candidates")
        if not os.path.exists(self.thumb_temp_dir): os.makedirs(self.thumb_temp_dir)
        
        # 5. Gọi Worker vẽ (Lưu ý: Chỉ vẽ nền raw)
        # Sử dụng tham số số lượng từ GUI
        qty = int(self.spin_thumb_qty.currentText().split()[0])
        self.thumb_workers = []
        
        for i in range(qty):
            import uuid
            uid = uuid.uuid4().hex[:4]
            # Đặt tên file là raw_...
            name = f"raw_thumb_{i+1}_{uid}" 
            
            worker = BrandArtistWorker(clean_prompt, name, self.thumb_temp_dir)
            # Truyền thêm overlay_text để bước sau dùng
            worker.overlay_text = overlay_text 
            worker.finished_signal.connect(self.on_thumb_layer1_done)
            self.thumb_workers.append(worker)
            worker.start()
            QTimer.singleShot(i * 1000, worker.start)
    
    def on_thumb_layer1_done(self, success, msg, img_type, raw_path):
        """Vẽ nền xong -> Gọi hàm ghép chung (để tái sử dụng logic ngôn ngữ)"""
        if not success or not os.path.exists(raw_path):
            self.log(f"❌ Lỗi vẽ nền: {msg}")
            self.btn_thumb.setEnabled(True); self.btn_thumb.setText("🖼️ VẼ NỀN")
            return

        self.log(f"✅ Có nền raw: {os.path.basename(raw_path)}. Đang ghép layout chuẩn...")
        
        # Gọi hàm ghép chung (Hàm chứa logic ngôn ngữ dài ngoằng phía trên)
        self._run_composer_merge(raw_path, layout_mode="standard")
        
        self.btn_thumb.setEnabled(True); self.btn_thumb.setText("🖼️ VẼ NỀN")

    def on_one_thumb_done(self, success, msg, img_type, path):
        """Khi 1 ảnh vẽ xong"""
        if success and os.path.exists(path):
            self.thumb_candidates.append(path)
            self.log(f"✅ Đã có phương án: {os.path.basename(path)}")
            
            # Tự động hiển thị ảnh mới nhất
            self.current_thumb_idx = len(self.thumb_candidates) - 1
            self.update_thumb_preview_ui()

        # Mở khóa nút khi đã vẽ đủ (hoặc tương đối)
        qty = int(self.spin_thumb_qty.currentText().split()[0])
        if len(self.thumb_candidates) >= 1: # Có ít nhất 1 ảnh là mở nút
            self.btn_thumb.setEnabled(True)
            self.btn_thumb.setText("🎨 VẼ THUMBNAIL (AI)")

    def update_thumb_preview_ui(self):
        """Hàm cập nhật hiển thị ảnh Thumbnail + TỰ ĐỘNG CHỐT ẢNH"""
        total = len(self.thumb_candidates)
        self.lbl_thumb_count.setText(f"{self.current_thumb_idx + 1}/{total}" if total > 0 else "0/0")
        
        if total > 0 and 0 <= self.current_thumb_idx < total:
            path = self.thumb_candidates[self.current_thumb_idx]
            
            # 1. Nạp ảnh lên giao diện
            self.lbl_thumb_preview.set_high_res(path)
            pix = QPixmap(path)
            self.lbl_thumb_preview.setPixmap(pix.scaled(
                320, 180, # Tỷ lệ 16:9
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            ))
            self.lbl_thumb_preview.setStyleSheet("border: 2px solid #2ecc71;")
            
            # 2. [CTO UPGRADE] TỰ ĐỘNG LƯU (AUTO-SAVE) LÀM THUMBNAIL CHÍNH
            if self.current_task and self.current_task.get('pj_path'):
                try:
                    dest_path = os.path.join(self.current_task['pj_path'], "thumbnail.jpg")
                    import shutil
                    shutil.copy2(path, dest_path) # Copy ngầm ảnh đang xem thành ảnh chính
                    
                    # Bật đèn xanh trên bảng danh sách video (Cột 5)
                    row = self.current_task.get('row_index', -1)
                    if row >= 0: 
                        item = QTableWidgetItem("✅")
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                        self.table_mon.setItem(row, 5, item)
                    
                    # Cập nhật lại cột Trạng thái tổng (nếu đủ 4 món sẽ xanh)
                    self.check_files_status()
                except Exception as e:
                    self.log(f"⚠️ Lỗi Auto-save thumbnail: {e}")
                    
        else:
            self.lbl_thumb_preview.clear()
            self.lbl_thumb_preview.high_res_pixmap = None
            self.lbl_thumb_preview.setText("NO PREVIEW")
            self.lbl_thumb_preview.setStyleSheet("border: 2px dashed #555; color: #555;")

    def nav_thumb_step(self, step):
        """Nút Prev/Next"""
        if not self.thumb_candidates: return
        new_idx = self.current_thumb_idx + step
        # Loop vòng tròn
        if new_idx < 0: new_idx = len(self.thumb_candidates) - 1
        if new_idx >= len(self.thumb_candidates): new_idx = 0
        
        self.current_thumb_idx = new_idx
        self.update_thumb_preview_ui()

    def action_download_current_thumb(self):
        """Tải ảnh đang xem về máy"""
        if not self.thumb_candidates: return
        curr_path = self.thumb_candidates[self.current_thumb_idx]
        
        save_path, _ = QFileDialog.getSaveFileName(self, "Lưu ảnh", "", "Images (*.jpg *.png)")
        if save_path:
            import shutil
            shutil.copy2(curr_path, save_path)
            self.log(f"💾 Đã lưu ảnh ra: {save_path}")

    # ============================================================
    # 🎵 LOGIC LUỒNG 5: MUSIC & SFX (BỔ SUNG)
    # ============================================================
    def action_auto_music(self):
        """Tự động tìm và tải nhạc (Luồng 5 Auto)"""
        if not self.current_task: 
            return QMessageBox.warning(self, "Chưa chọn", "Vui lòng chọn 1 video trước!")
        self.log_signal.emit("🎵 Bắt đầu tìm kiếm nhạc nền...")
            
        keyword = self.txt_music_key.text().strip()
        
        path = self.current_task.get("pj_path", "")
        if not path: return
        dest = os.path.join(path, "background.mp3")
        
        # [AUTO DETECT MOOD] Đọc kịch bản để tự bắt mood nhạc
        if not keyword or keyword.lower() in ["cinematic", "general", "auto"]:
            self.log("🤖 AI đang đọc kịch bản để bắt mạch cảm xúc (Mood)...")
            try:
                voice_file = os.path.join(path, "voice.txt")
                if os.path.exists(voice_file):
                    with open(voice_file, "r", encoding="utf-8") as f:
                        script = f.read()[:500] # Đọc 500 ký tự đầu
                    prompt = f"Phân tích cảm xúc của kịch bản sau: '{script}'. Trả về đúng 2-3 từ khóa tiếng Anh ngắn gọn để tìm nhạc nền (ví dụ: suspense cinematic, sad piano, upbeat lofi, epic orchestral). Không giải thích."
                    success, res = AIFactory().execute_custom_ai("google", prompt, "gemini-2.0-flash")
                    if success:
                        keyword = res.replace('"', '').replace('.', '').strip()
                        self.txt_music_key.setText(keyword)
                        self.log(f"✨ AI đề xuất nhạc: '{keyword}'")
            except: pass
            
        if not keyword: keyword = "Cinematic background"
            
        self.log(f"🎵 Bắt đầu săn lùng nhạc: '{keyword}'...")
        self.btn_auto_music.setEnabled(False)
        self.btn_auto_music.setText("⏳ Đang tải...")
        
        self.music_auto_worker = MusicAutoWorker(keyword, dest)
        self.music_auto_worker.finished_signal.connect(self.on_auto_music_done)
        self.music_auto_worker.start()

    def on_auto_music_done(self, success, msg, path):
        self.btn_auto_music.setEnabled(True)
        self.btn_auto_music.setText("⚡ TỰ ĐỘNG (AUTO)")
        
        if success:
            self.log(msg)
            self.lbl_music_file.setText(f"✅ {os.path.basename(path)}")
            self.lbl_music_file.setStyleSheet("color: #2ecc71; font-weight: bold;")
            
            # Cập nhật player và bảng
            self.player.setSource(QUrl.fromLocalFile(path))
            self.check_files_status()
            
            row = self.current_task.get('row_index', -1)
            if row >= 0: self.table_mon.setItem(row, 4, QTableWidgetItem("✅"))
            
            # THÊM VÀO LIST KẾT QUẢ ĐỂ LỰA CHỌN (Luồng 5)
            self.list_music_res.clear()
            item = QListWidgetItem(f"AI: {os.path.basename(path)}")
            item.setData(Qt.ItemDataRole.UserRole, path)
            self.list_music_res.addItem(item)
            
            # --- [BATCH] Chạy tiếp task sau ---
            if hasattr(self, 'is_batch_running') and self.is_batch_running:
                QTimer.singleShot(1000, self.process_next_batch_item)
        else:
            self.log(f"❌ {msg}")
            # Thử tìm trong Thư viện mặc định nếu AI lỗi (Fall-back thông minh)
            self._try_apply_default_music()

            # Nếu đang chạy Batch thì vẫn tiếp tục task sau dù lỗi nhạc (để không bị đứng hình)
            if hasattr(self, 'is_batch_running') and self.is_batch_running:
                QTimer.singleShot(1000, self.process_next_batch_item)
            else:
                QMessageBox.warning(self, "Lỗi tải nhạc", msg)

    def action_search_music_online(self):
        """Mở trình duyệt để tìm nhạc (Thủ công)"""
        keyword = self.txt_music_key.text()
        if not keyword: keyword = "Cinematic"
        
        import webbrowser
        # Tìm trên Pixabay Music
        url = f"https://pixabay.com/music/search/{keyword}/"
        webbrowser.open(url)
        self.log(f"🌍 Đang mở trình duyệt tìm nhạc: {keyword}")

    def on_music_res_clicked(self, item):
        """Khi click vào 1 bản nhạc trong list kết quả -> Nghe thử và Chốt"""
        path = item.data(Qt.ItemDataRole.UserRole)
        if path and os.path.exists(path):
            self.player.setSource(QUrl.fromLocalFile(path))
            self.player.play()
            
            # Chốt luôn file này làm background.mp3 cho task hiện tại
            if self.current_task:
                dest = os.path.join(self.current_task['pj_path'], "background.mp3")
                if os.path.normpath(path) != os.path.normpath(dest):
                    import shutil
                    shutil.copy2(path, dest)
                
                self.lbl_music_file.setText(f"✅ {os.path.basename(path)}")
                self.lbl_music_file.setStyleSheet("color: #2ecc71; font-weight: bold;")
                self.check_files_status()

    def action_scan_music_library(self):
        """Quét thư mục nhạc cục bộ để nạp vào danh sách lựa chọn"""
        lib_path = os.path.abspath("VEO_ASSETS/Music_Library")
        if not os.path.exists(lib_path): 
            os.makedirs(lib_path, exist_ok=True)
            return self.log("📁 Thư viện nhạc trống. Vui lòng copy file .mp3 vào VEO_ASSETS/Music_Library")

        self.list_music_res.clear()
        files = [f for f in os.listdir(lib_path) if f.lower().endswith(('.mp3', '.wav'))]
        for f in files:
            it = QListWidgetItem(f"Library: {f}")
            it.setData(Qt.ItemDataRole.UserRole, os.path.join(lib_path, f))
            self.list_music_res.addItem(it)
        
        self.log(f"📚 Đã nạp {len(files)} bản nhạc từ thư viện máy tính.")

    def _try_apply_default_music(self):
        """Fallback: Lấy bản nhạc đầu tiên trong thư viện nếu không tìm được nhạc AI"""
        lib_path = os.path.abspath("VEO_ASSETS/Music_Library")
        if os.path.exists(lib_path) and self.current_task:
            files = [f for f in os.listdir(lib_path) if f.lower().endswith(('.mp3', '.wav'))]
            if files:
                f_path = os.path.join(lib_path, files[0])
                dest = os.path.join(self.current_task['pj_path'], "background.mp3")
                import shutil
                shutil.copy2(f_path, dest)
                self.log(f"🛡️ AI lỗi. Đã dùng nhạc mặc định: {files[0]}")
                return True
        return False

    def action_import_music(self):
        """Nhập file nhạc từ máy tính vào làm background.mp3 và hiện ở Kết quả"""
        if not self.current_task: return
        
        f_path, _ = QFileDialog.getOpenFileName(self, "Chọn file nhạc nền", "", "Audio Files (*.mp3 *.wav *.m4a)")
        if f_path:
            try:
                dest = os.path.join(self.current_task['pj_path'], "background.mp3")
                shutil.copy2(f_path, dest)
                
                # Hiển thị ở nhãn trạng thái
                self.lbl_music_file.setText(f"✅ {os.path.basename(f_path)}")
                self.lbl_music_file.setStyleSheet("color: #2ecc71; font-weight: bold;")
                
                # THÊM VÀO LIST KẾT QUẢ ĐỂ LỰA CHỌN (Luồng 5)
                self.list_music_res.clear()
                item = QListWidgetItem(f"Local: {os.path.basename(f_path)}")
                item.setData(Qt.ItemDataRole.UserRole, dest)
                self.list_music_res.addItem(item)
                
                self.log(f"🎵 Đã nhập nhạc: {os.path.basename(f_path)}")
                self.check_files_status()
                
                # Play thử
                self.player.setSource(QUrl.fromLocalFile(dest))
                
                # Update Bảng
                row = self.current_task.get('row_index', -1)
                if row >= 0: self.table_mon.setItem(row, 4, QTableWidgetItem("✅"))
                
            except Exception as e:
                QMessageBox.critical(self, "Lỗi", f"Không copy được nhạc: {e}")

    # ========================================================================
    # 🩹 CÁC HÀM BỔ TRỢ (HELPER FUNCTIONS) - QUAN TRỌNG
    # ========================================================================
    
    def _sanitize_filename(self, name):
        """Lọc tên file để tạo folder không bị lỗi Windows"""
        if not name: return "Untitled"
        import re
        # Chỉ giữ lại chữ cái, số, khoảng trắng, gạch ngang
        clean_name = re.sub(r'[^\w\s\-\.]', '', str(name))
        return clean_name.strip()

    def _clean_json_script(self, raw_text):
        """Lọc sạch kịch bản: Bỏ các ký tự JSON thừa, chỉ lấy lời thoại"""
        if not raw_text: return ""
        text_str = str(raw_text).strip()
        
        # Nếu là JSON, cố gắng parse lấy value
        try:
            if "{" in text_str and "}" in text_str:
                import json
                import re
                text_str = re.sub(r',\s*}', '}', text_str) 
                data = json.loads(text_str)
                
                # Tìm các key phổ biến chứa lời thoại
                for key in ["voice_text", "voice", "content", "script"]:
                    if key in data:
                        return str(data[key])
        except:
            pass # Nếu lỗi parse JSON thì coi như text thường

        # Xử lý text thường: Xóa các dòng code block ```json
        lines = text_str.split('\n')
        clean_lines = []
        for line in lines:
            if "```" in line: continue
            if '"voice_text":' in line: continue # Bỏ dòng key json nếu còn sót
            clean_lines.append(line)
            
        return "\n".join(clean_lines).strip()
    
    def action_send_to_editor(self):
        """Chuyển trạng thái sang Sẵn sàng dựng và báo cho Editor"""
        if not self.current_task:
            return QMessageBox.warning(self, "Chưa chọn", "Vui lòng chọn 1 video để chuyển!")
            
        src_path = self.current_task.get("pj_path", "")
        if not src_path or not os.path.exists(src_path):
            return QMessageBox.warning(self, "Lỗi", "Thư mục nguồn không tồn tại!")
            
        has_voice = os.path.exists(os.path.join(src_path, "voice.mp3"))
        vis_path = os.path.join(src_path, "visuals")
        has_visuals = os.path.exists(vis_path) and len(os.listdir(vis_path)) > 0
        
        if not (has_voice and has_visuals):
            return QMessageBox.warning(self, "Chưa đủ nguyên liệu", "Cần phải có Voice và Ảnh/Video để dựng phim!")
            
        # Update database
        p_id = self.current_project_index
        t_id = self.current_task.get("id")
        if self.db and hasattr(self.db, "update_task_status"):
            self.db.update_task_status(p_id, t_id, "Sẵn sàng dựng")
        else:
            self.log("⚠️ Cảnh báo: DatabaseManager không hỗ trợ update_task_status hoặc chưa khởi tạo.")
        self.current_task["status"] = "Sẵn sàng dựng"
        
        QMessageBox.information(self, "Thành công", "Đã chốt nguyên liệu! Vui lòng mở Tab Dựng Phim và bấm 'Nhận Nguyên Liệu'.")

    def action_import(self):
        f, _ = QFileDialog.getOpenFileName(self, "Nhập File", "", "Files (*.*)")
        if f: self.log(f"Import: {f}")

    def action_final_export(self):
        """Xuất toàn bộ tài nguyên ra thư mục sạch để dựng phim"""
        if not self.current_task:
            return QMessageBox.warning(self, "Chưa chọn", "Vui lòng chọn 1 video để xuất kho!")
        self.log_signal.emit(f"💾 Bắt đầu xuất kho bộ nguyên liệu: {self.current_task.get('key_vua')}")
            
        # 1. Lấy thông tin nguồn
        src_path = self.current_task.get("pj_path", "")
        if not src_path or not os.path.exists(src_path):
            return QMessageBox.warning(self, "Lỗi", "Thư mục nguồn không tồn tại!")

        # 2. Chọn nơi lưu
        # Mặc định lấy tên Key Vua làm tên thư mục
        folder_name = self._sanitize_filename(self.current_task.get("key_vua", "Export_Video"))
        dest_root = QFileDialog.getExistingDirectory(self, "Chọn nơi lưu bộ nguyên liệu dựng phim")
        
        if not dest_root: return # Người dùng bấm hủy
        
        # Tạo thư mục đích: [Nơi chọn]/[Tên Video]_Assets
        final_dir = os.path.join(dest_root, f"{folder_name}_Assets")
        if not os.path.exists(final_dir): os.makedirs(final_dir)
        
        self.log(f"📦 Bắt đầu xuất kho sang: {final_dir}")
        self.btn_export = self.sender() # Lấy nút bấm để disable
        if self.btn_export: self.btn_export.setEnabled(False); self.btn_export.setText("⏳ Đang đóng gói...")
        
        try:
            # --- BƯỚC A: XUẤT ÂM THANH (AUDIO) ---
            audio_dir = os.path.join(final_dir, "1_Audio")
            if not os.path.exists(audio_dir): os.makedirs(audio_dir)
            
            # 1. Voice
            voice_src = os.path.join(src_path, "voice.mp3")
            if os.path.exists(voice_src):
                shutil.copy2(voice_src, os.path.join(audio_dir, "1_Voice_Main.mp3"))
            
            # 2. Music
            music_src = os.path.join(src_path, "background.mp3")
            if os.path.exists(music_src):
                shutil.copy2(music_src, os.path.join(audio_dir, "2_Music_BG.mp3"))
                
            # 3. SFX (Nếu có file sfx.txt hoặc folder sfx)
            # (Tạm thời bỏ qua, mở rộng sau)

            # --- BƯỚC B: XUẤT HÌNH ẢNH (FOOTAGE) ---
            visual_dir = os.path.join(final_dir, "2_Footage")
            if not os.path.exists(visual_dir): os.makedirs(visual_dir)
            
            src_vis_dir = os.path.join(src_path, "visuals")
            if os.path.exists(src_vis_dir):
                files = sorted(os.listdir(src_vis_dir))
                for i, f in enumerate(files):
                    if f.lower().endswith(('.jpg', '.png', '.mp4', '.mov')):
                        # Đánh số thứ tự để khi import vào Premiere nó đúng thứ tự
                        # Ví dụ: 001_Canh1.jpg, 002_Canh2.mp4
                        new_name = f"{i+1:03d}_{f}" 
                        shutil.copy2(os.path.join(src_vis_dir, f), os.path.join(visual_dir, new_name))

            # --- BƯỚC C: XUẤT KỊCH BẢN & META ---
            doc_dir = os.path.join(final_dir, "3_Docs")
            if not os.path.exists(doc_dir): os.makedirs(doc_dir)
            
            # Copy các file text quan trọng
            for txt in ["voice.txt", "thumbnail.txt", "text_thumb.txt", "meta.json"]:
                t_src = os.path.join(src_path, txt)
                if os.path.exists(t_src):
                    shutil.copy2(t_src, os.path.join(doc_dir, txt))
                    
            # --- BƯỚC D: XUẤT THUMBNAIL ĐÃ CHỌN ---
            if hasattr(self, 'thumb_candidates') and self.thumb_candidates and self.current_thumb_idx >= 0:
                try:
                    selected_thumb_path = self.thumb_candidates[self.current_thumb_idx]
                    if os.path.exists(selected_thumb_path):
                        ext = os.path.splitext(selected_thumb_path)[1]
                        thumb_dest = os.path.join(final_dir, f"0_Thumbnail_Final{ext}")
                        shutil.copy2(selected_thumb_path, thumb_dest)
                except Exception as e:
                    self.log(f"⚠️ Cảnh báo: Lỗi khi copy Thumbnail: {e}")

            # Mở thư mục kết quả
            os.startfile(final_dir)
            QMessageBox.information(self, "Xong", "✅ Đã đóng gói xong nguyên liệu!\nSẵn sàng dựng phim.")
            self.log("🏁 Xuất kho hoàn tất.")

        except Exception as e:
            QMessageBox.critical(self, "Lỗi Xuất Kho", str(e))
            self.log(f"❌ Lỗi xuất kho: {e}")
            
        finally:
            if self.btn_export: 
                self.btn_export.setEnabled(True)
                self.btn_export.setText("🚀 XUẤT KHO SANG DỰNG PHIM")

    def refresh_project_list(self):
        """Nạp danh sách kênh với giao diện dễ nhìn hơn"""
        self.list_projects.clear()
        self.table_mon.setRowCount(0)
        
        if not self.db: 
            self.list_projects.addItem("⚠️ Lỗi kết nối DB")
            return

        self.projects = self.db.load_projects()
        
        for p in self.projects:
            tasks = p.get("tasks", [])
            total = len(tasks)
            
            # --- LOGIC ĐÈN BÁO (THÔNG MINH HƠN) ---
            # Đếm số bài đã xong (có file voice.mp3 là coi như xong bước 1)
            done_count = 0
            for t in tasks:
                # [CTO FIX] Chỉ khi trạng thái là "Sẵn sàng dựng" thì mới tính là Xong
                # Không đếm dựa trên file voice.mp3 đơn thuần nữa
                st = t.get("status", "")
                if "Sẵn sàng dựng" in st or "Ready" in st:
                    done_count += 1
            
            if total == 0:
                icon = "⚪" # Trống
                status_text = "Empty"
            elif done_count == total:
                icon = "🟢" # Đã xong hết
                status_text = "Done"
            elif done_count > 0:
                icon = "🟡" # Đang làm dở
                status_text = f"{done_count}/{total}"
            else:
                icon = "🔴" # Chưa làm gì
                status_text = "New"

            # Tạo Item hiển thị đẹp hơn
            display_text = f"{icon} {p['name']}  [{status_text}]"
            item = QListWidgetItem(display_text)
            
            # Lưu dữ liệu ngầm vào item
            item.setData(Qt.ItemDataRole.UserRole, p)
            
            self.list_projects.addItem(item)
            
        self.log(f"Đã tải {len(self.projects)} kênh (Logic đèn: 🔴Mới - 🟡Đang chạy - 🟢Xong).")

    def on_project_selected(self, item): #1
        """Logic khi chọn Kênh: Cập nhật Command Deck (Đã Fix tên biến)"""
        project = item.data(Qt.ItemDataRole.UserRole)
        self.current_project_index = self.list_projects.row(item)
        
        # 1. Update Channel Metadata (Command Center)
        ch_name = project.get("name", "Unknown Channel")
        self.lbl_channel_name.setText(ch_name.upper())
        self.lbl_channel_desc.setText(project.get("description", "Sẵn sàng sản xuất nội dung hàng loạt."))
        self.log_signal.emit(f"📺 Đã chọn kênh: {ch_name}")
        
        prof = project.get("channel_profile", {})
        vis_id = prof.get("visual_identity", {})
        brand_id = prof.get("brand_identity", {}) or vis_id
        
        dna_mood = vis_id.get('mood') or brand_id.get('mood') or "Cinematic"
        dna_color = vis_id.get('color_palette') or brand_id.get('color_palette') or "Modern"
        dna_style = vis_id.get('art_style') or "Realistic"

        self.lbl_dna_tags.setText(f"🎨 DNA: {dna_style} | {dna_mood} | {dna_color}")
        if dna_color.startswith("#"): 
            self.lbl_dna_tags.setStyleSheet(f"color: {dna_color}; font-weight: bold; font-size: 13px;")
        else: 
            self.lbl_dna_tags.setStyleSheet("color: #00e6e6; font-weight: bold; font-size: 13px;")
        
        # Update config status
        self.lbl_config_status.setText(f"⚙️ Config: {project.get('platform', 'N/A')} | {project.get('country', 'Global')}")
        
        # 2. TÍNH TOÁN ĐƯỜNG DẪN GỐC (BASE PATH)
        try:
            p_plat = self._sanitize_filename(project.get("platform", "Youtube"))
            p_coun = self._sanitize_filename(project.get("country", "Global").split('~')[0])
            p_top = self._sanitize_filename(project.get("topic", "General"))
            base_project_path = os.path.join("VEO_DB", p_plat, p_coun, p_top)
            
            # Cập nhật đường dẫn cho Brand Worker
            self.current_brand_path = os.path.join(base_project_path, "Brand_Assets")
            if not os.path.exists(self.current_brand_path): os.makedirs(self.current_brand_path)
        
            # --- START: LOAD LOGO & BANNER ---                
            # 1. Xử lý Logo
            logo_path = os.path.join(self.current_brand_path, "logo.jpg")
            has_logo = os.path.exists(logo_path)

            if has_logo:
                # [CTO FIX] Nạp ảnh gốc để Zoom trước
                self.lbl_logo.set_high_res(logo_path)
                # Sau đó nạp ảnh nhỏ để hiển thị
                pix = QPixmap(logo_path).scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                self.lbl_logo.setPixmap(pix)
                self.lbl_logo.setStyleSheet("border: 1px solid #00e6e6;")
            else:
                self.lbl_logo.clear(); self.lbl_logo.setText("ĐANG VẼ...")
                self.lbl_logo.setStyleSheet("border: 2px dashed #f1c40f; color: #f1c40f; background: #222; font-size: 10px;")
                # [CTO AUTO] Kích hoạt vẽ Logo tự động
                self.log(f"🤖 Auto: Chưa thấy Logo -> Gọi AI vẽ ngay...")
                self.action_redraw_brand("logo")

            # 2. Xử lý Banner
            banner_path = os.path.join(self.current_brand_path, "banner.jpg")
            has_banner = os.path.exists(banner_path)
            
            if has_banner:
                # [CTO FIX] Nạp ảnh gốc để Zoom
                self.lbl_banner.set_high_res(banner_path)
                pix = QPixmap(banner_path).scaled(142, 80, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                self.lbl_banner.setPixmap(pix)
                self.lbl_banner.setStyleSheet("border: 1px solid #00e6e6;")
            else:
                self.lbl_banner.clear(); self.lbl_banner.setText("ĐANG VẼ...")
                self.lbl_banner.setStyleSheet("border: 2px dashed #f1c40f; color: #f1c40f; background: #222; font-size: 10px;")
                # [CTO AUTO] Kích hoạt vẽ Banner tự động
                self.log(f"🤖 Auto: Chưa thấy Banner -> Gọi AI vẽ ngay...")
                self.action_redraw_brand("banner")

            # --- END: LOAD LOGO & BANNER ---
            
        except:
            base_project_path = ""        

        # 3. VẼ BẢNG VÀ CẤP PHÁT ĐƯỜNG DẪN CON
        self.table_mon.setRowCount(0)
        self.tasks_map = {}
        
        tasks = project.get("tasks", [])
        for i, t in enumerate(tasks):
            self.table_mon.insertRow(i)
            
            # --- CỘT 0: STT (Số thứ tự: 1, 2, 3...) ---
            item_stt = QTableWidgetItem(str(i + 1))
            item_stt.setTextAlignment(Qt.AlignmentFlag.AlignCenter) # Căn giữa STT
            self.table_mon.setItem(i, 0, item_stt)
            
            # --- CỘT 1: TIÊU ĐỀ ---
            display_title = t.get('title') if t.get('title') else t.get('key_vua', 'No Title')
            self.table_mon.setItem(i, 1, QTableWidgetItem(display_title))
            
            # --- [QUAN TRỌNG] XÁC ĐỊNH ĐƯỜNG DẪN CHUẨN ---
            # Ưu tiên lấy path đã lưu, nếu không có thì tự tính toán (như logic dự đoán)
            path = t.get("output_path", "")
            
            if not path:
                # Logic dự đoán đường dẫn (để check file kể cả khi chưa lưu DB)
                try:
                    safe_key = self._sanitize_filename(t.get("key_vua", "Untitled"))
                    p_plat = project.get("platform", "Youtube").lower()
                    is_short = any(x in p_plat for x in ["short", "tiktok", "reel"])
                    p_type = "Shorts" if is_short else "Long"
                    if base_project_path:
                        task_folder_name = f"{t['id']}_{safe_key}"[:50]
                        path = os.path.join(base_project_path, safe_key, p_type, task_folder_name)
                except:
                    path = ""
            
            # --- CỘT 2-5: TRẠNG THÁI FILE (CHECK THỰC TẾ TRÊN Ổ CỨNG) ---
            path = t.get("output_path", "")
            if not path: path = t.get("pj_path", "") # Fallback nếu chưa có output_path
            
            # 1. Check Voice (Có file mp3 > 1 KB)
            f_voice = os.path.join(path, "voice.mp3") if path else ""
            bool_voice = os.path.exists(f_voice) and os.path.getsize(f_voice) > 100
            
            # 2. Check Visual (Folder tồn tại và có ít nhất 1 file)
            f_vis_dir = os.path.join(path, "visuals") if path else ""
            bool_visual = False
            if path and os.path.exists(f_vis_dir):
                # Đếm xem có file ảnh/video nào không
                files = [f for f in os.listdir(f_vis_dir) if f.lower().endswith(('.jpg', '.png', '.mp4'))]
                if len(files) > 0: bool_visual = True

            # 3. Music: Có file nhạc nền
            f_music = os.path.join(path, "background.mp3") if path else ""
            bool_music = os.path.exists(f_music) and os.path.getsize(f_music) > 100

            # 4. Thumb: Có file ảnh thumb
            f_thumb = os.path.join(path, "thumbnail.jpg") if path else ""
            bool_thumb = os.path.exists(f_thumb) and os.path.getsize(f_thumb) > 100

            # --- HÀM HELPER: TẠO ITEM CĂN GIỮA ---
            def make_center_item(text):
                it = QTableWidgetItem(text)
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                return it
            
            # --- HIỂN THỊ CÁC CỘT ICON (2, 3, 4, 5) ---
            # Voice
            icon_voice = "❌"
            if bool_voice:
                # Check thêm sub để hiển thị icon xịn
                if os.path.exists(os.path.join(path, "voice.srt")): icon_voice = "🔊+📝"
                else: icon_voice = "🔊"
            # Set Icon (✅ / ❌)
            self.table_mon.setItem(i, 2, make_center_item(icon_voice))

            # Visual
            self.table_mon.setItem(i, 3, make_center_item("✅" if bool_visual else "❌"))
            
            # Music
            self.table_mon.setItem(i, 4, make_center_item("✅" if bool_music else "❌"))
            
            # Thumb
            self.table_mon.setItem(i, 5, make_center_item("✅" if bool_thumb else "❌"))
            
            # --- CỘT 6: TRẠNG THÁI (TÍNH TOÁN LẠI 100%) ---
            final_status = "⚪ Chưa làm" # Mặc định
            
            # Điều kiện nghiêm ngặt: Đủ 4 món
            if bool_voice and bool_visual and bool_music and bool_thumb:
                final_status = "🟢 Sẵn sàng dựng (Full)"
            # Nếu chỉ có 1 trong các thành phần -> Đang làm
            elif bool_voice or bool_visual or bool_music or bool_thumb:
                # Tính toán xem thiếu cái gì để báo (Option nâng cao)
                missing = []
                if not bool_voice: missing.append("Voice")
                if not bool_visual: missing.append("Visual")
                if not bool_music: missing.append("Music")
                if not bool_thumb: missing.append("Thumb")
                
                # Nếu thiếu nhiều quá thì ghi "Đang làm...", thiếu ít thì ghi cụ thể
                if len(missing) <= 2:
                    final_status = f"🟡 Thiếu: {', '.join(missing)}"
                else:
                    final_status = "🟡 Đang sản xuất..."
            
            item_status = QTableWidgetItem(final_status)
            
            # Tô màu chữ
            if "🟢" in final_status: item_status.setForeground(QColor("#2ecc71")) # Xanh lá
            elif "🟡" in final_status: item_status.setForeground(QColor("#f1c40f")) # Vàng
            else: item_status.setForeground(QColor("#7f8c8d")) # Xám
            
            self.table_mon.setItem(i, 6, item_status)
            
            # --- LƯU LẠI PATH ĐỂ DÙNG SAU ---
            t['pj_path'] = path 
            self.tasks_map[i] = t
            
        # Update Table Selection
        if tasks:
            self.table_mon.selectRow(0)
            self.on_monitor_row_clicked(self.table_mon.item(0, 0))

    def action_view_subtitle(self):
        """Mở dialog xem nội dung file SRT"""
        if not self.current_task: return
        path = self.current_task.get("pj_path", "")
        srt_f = os.path.join(path, "voice.srt")
        if os.path.exists(srt_f):
            try:
                with open(srt_f, "r", encoding="utf-8") as f:
                    content = f.read()
                
                dlg = QDialog(self)
                dlg.setWindowTitle("👁️ XEM PHỤ ĐỀ (SRT)")
                dlg.resize(400, 500)
                l = QVBoxLayout(dlg)
                txt = QTextEdit()
                txt.setPlainText(content)
                txt.setReadOnly(True)
                l.addWidget(txt)
                dlg.exec()
            except Exception as e:
                self.log(f"❌ Không mở được sub: {e}")
        else:
            QMessageBox.warning(self, "Thiếu file", "Không tìm thấy file voice.srt")

    def open_current_folder(self):
        """Mở thư mục dự án hiện tại"""
        if not self.current_task: return
        path = self.current_task.get("pj_path", "")
        if path and os.path.exists(path):
            os.startfile(path)
        else:
            QMessageBox.warning(self, "Lỗi", "Thư mục không tồn tại!")

    def action_demo_part(self):
        """Demo 1 phần: Tạo Voice và 1 Cảnh Visual duy nhất để kiểm tra chất lượng"""
        if not self.current_task: return
        self.log("🎬 Bắt đầu chạy DEMO (Voice + Cảnh 1)...")
        
        # 1. Tạo Voice (Như bình thường)
        self.action_single_voice()
        
        # 2. Tạo Visual nhưng giới hạn chỉ 1 cảnh
        self.action_auto_visual(max_scenes=1)

    def action_full_video_single(self):
        """Tạo Full (Video này): Chạy toàn bộ quy trình cho 1 video duy nhất"""
        if not self.current_task: return
        confirm = QMessageBox.question(self, "Xác nhận", f"Sản xuất TOÀN BỘ nguyên liệu cho video: '{self.current_task.get('key_vua')}'?")
        if confirm == QMessageBox.StandardButton.Yes:
            self.log(f"⚡ Đang nạp video '{self.current_task.get('key_vua')}' vào dây chuyền sản xuất...")
            t = self.current_task
            path = t.get('pj_path', '')
            
            self.batch_queue = []
            # Chỉ thêm những khâu chưa làm
            if not os.path.exists(os.path.join(path, "voice.mp3")):
                self.batch_queue.append({"type": "VOICE", "task": t})
            
            vis_dir = os.path.join(path, "visuals")
            if not os.path.exists(vis_dir) or not os.listdir(vis_dir):
                self.batch_queue.append({"type": "VISUAL", "task": t})
                
            if not os.path.exists(os.path.join(path, "background.mp3")):
                self.batch_queue.append({"type": "MUSIC", "task": t})
                
            if not os.path.exists(os.path.join(path, "thumbnail.jpg")):
                self.batch_queue.append({"type": "THUMBNAIL", "task": t})
            
            if not self.batch_queue:
                QMessageBox.information(self, "Tuyệt vời", "Video này đã ĐỦ nguyên liệu!")
                return
                
            self.is_batch_running = True
            self.process_next_batch_item()

    def action_render_final_video(self):
        """🎥 Render video hoàn chỉnh bằng FFmpeg (Voice + Visuals + BGM + Subtitle)"""
        if not self.current_task:
            return QMessageBox.warning(self, "Chưa chọn", "Vui lòng chọn 1 video trước!")
        
        path = self.current_task.get("pj_path", "")
        if not path:
            return QMessageBox.warning(self, "Lỗi", "Không tìm thấy thư mục dự án!")
        
        # Kiểm tra nguyên liệu
        from services.video_assembler import VideoAssembler
        assembler = VideoAssembler(path)
        issues, warnings = assembler.check_prerequisites()
        
        if issues:
            msg = "Thiếu nguyên liệu:\n\n" + "\n".join(issues)
            if warnings:
                msg += "\n\n" + "\n".join(warnings)
            msg += "\n\nHãy tạo đủ nguyên liệu trước (Voice, Visual) rồi thử lại."
            return QMessageBox.warning(self, "Chưa đủ nguyên liệu", msg)
        
        # Xác nhận render
        warning_text = ""
        if warnings:
            warning_text = "\n⚠️ " + "\n⚠️ ".join(warnings)
        
        confirm = QMessageBox.question(
            self, "Render Video", 
            f"🎬 Sẵn sàng ghép video cho '{self.current_task.get('key_vua', 'N/A')}'?\n{warning_text}\n\n"
            f"Nguyên liệu sẽ được ghép bằng FFmpeg với hiệu ứng Ken Burns và phụ đề."
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        
        self.log("🎬 Bắt đầu RENDER VIDEO CUỐI...")
        self.btn_render_final.setEnabled(False)
        self.btn_render_final.setText("⏳ Đang Render...")
        
        # Chạy trong thread để không đông UI
        from modules.assets_factory.workers import GenericWorker
        
        def do_render():
            asm = VideoAssembler(path)
            success, msg, out_path = asm.assemble(progress_callback=lambda m: self.log_signal.emit(m))
            return (success, msg, out_path)
        
        self.render_worker = GenericWorker(do_render)
        self.render_worker.finished_signal.connect(self.on_render_done)
        self.render_worker.start()
    
    def on_render_done(self, result):
        """Callback khi render xong."""
        self.btn_render_final.setEnabled(True)
        self.btn_render_final.setText("🎥 RENDER VIDEO CUỐI")
        
        if isinstance(result, tuple) and len(result) == 3:
            success, msg, out_path = result
            self.log(msg)
            if success and out_path:
                QMessageBox.information(self, "🎉 Thành công!", f"Video đã được render thành công!\n\n📁 {out_path}")
                # Mở folder chứa video
                try:
                    os.startfile(os.path.dirname(out_path))
                except: pass
        else:
            self.log(f"⚠️ Render trả về kết quả không mong đợi: {result}")

    def action_auto_visual(self, max_scenes=None):
        """Bấm nút Tìm/Tạo Ảnh (Có hỗ trợ giới hạn cảnh cho Demo)"""
        if not self.current_task: return
        self.log_signal.emit("🖼️ Bắt đầu quy trình sản xuất Visual Pipeline...")

        path = self.current_task.get('pj_path', '')
        scenes_file = os.path.join(path, "scenes_visual.txt")
        
        # 1. Lưu scenes list
        content = ""
        count = self.list_visual_in.count()
        if max_scenes: count = min(count, max_scenes)
        
        for i in range(count):
            item = self.list_visual_in.item(i)
            # Ưu tiên UserRole (widget-based item mới), fallback sang text() (item cũ)
            text = item.data(Qt.ItemDataRole.UserRole) or item.text()
            content += text + "\n"
        
        if not os.path.exists(path): os.makedirs(path, exist_ok=True)
        with open(scenes_file, "w", encoding="utf-8") as f: f.write(content)
        
        # 2. Lấy cấu hình
        ratio_idx = self.cb_ratio.currentIndex()
        orientation = "portrait" if ratio_idx == 1 else "landscape"
        source_idx = self.cb_vis_source.currentIndex()
        ai_percentage = 100 if source_idx == 1 else (0 if source_idx == 2 else 20)
        current_style = self.current_style
        
        self.btn_find_visual.setEnabled(False)
        self.btn_find_visual.setText("⏳ Đang tạo Visual..." if not max_scenes else "⏳ Đang tạo DEMO...")

        # 3. Chạy Worker
        self.vis_worker = VisualWorker(scenes_file, path, ai_percentage)
        self.vis_worker.orientation = orientation
        self.vis_worker.style_config = current_style
        self.vis_worker.progress_signal.connect(self.log)
        self.vis_worker.scene_finished_signal.connect(lambda idx: self.load_visual_preview())
        self.vis_worker.finished_signal.connect(self.on_visual_done)
        self.vis_worker.finished.connect(lambda: self.on_worker_finished_safe(self.btn_find_visual, "🖼️ TÌM & TẠO (AUTO)"))
        self.vis_worker.start()
    
    def action_redraw_brand(self, asset_type):
        """Hàm vẽ lại Logo hoặc Banner (Fix Crash + Đọc Prompt chuẩn từ File)"""
        if self.current_project_index < 0:
            return QMessageBox.warning(self, "Chưa chọn", "Vui lòng chọn 1 Kênh bên trái trước!")
            
        # --- 1. TÁI TẠO ĐƯỜNG DẪN (Để đảm bảo luôn tìm thấy folder) ---
        if not hasattr(self, 'current_brand_path') or not self.current_brand_path:
            try:
                proj = self.projects[self.current_project_index]
                p_plat = self._sanitize_filename(proj.get("platform", "Youtube"))
                p_coun = self._sanitize_filename(proj.get("country", "Global").split('~')[0])
                p_top = self._sanitize_filename(proj.get("topic", "General"))
                
                base_path = os.path.join("VEO_DB", p_plat, p_coun, p_top, "Brand_Assets")
                if not os.path.exists(base_path): os.makedirs(base_path)
                self.current_brand_path = base_path
            except Exception as e:
                self.log(f"❌ Lỗi đường dẫn Brand: {e}")
                return

        # --- 2. TÌM PROMPT (ƯU TIÊN ĐỌC TỪ FILE TEXT BÊN BIÊN TẬP) ---
        prompt_file_name = f"{asset_type}_prompt.txt"
        prompt_path = os.path.join(self.current_brand_path, prompt_file_name)
        prompt = ""
        
        # A. Đọc từ File .txt (Ưu tiên số 1 - Đồng bộ với Tab Content)
        if os.path.exists(prompt_path):
            try:
                with open(prompt_path, "r", encoding="utf-8") as f: prompt = f.read().strip()
                self.log(f"📂 Đã load Prompt từ file: {prompt_file_name}")
            except: pass

        # B. Nếu không có file -> Tìm trong Database (Backup)
        if not prompt:
            proj = self.projects[self.current_project_index]
            vis_id = proj.get("channel_profile", {}).get("visual_identity", {})
            prompt = vis_id.get(f"{asset_type}_prompt", "")

        # C. Nếu vẫn không có -> TỰ CHẾ PROMPT DỰA TRÊN DNA (Fallback thông minh)
        if not prompt:
            proj = self.projects[self.current_project_index]
            prof = proj.get("channel_profile", {})
            vis_id = prof.get("visual_identity", {})
            brand_id = prof.get("brand_identity", {})
            
            dna_mood = vis_id.get('mood') or brand_id.get('mood') or "Professional"
            dna_color = vis_id.get('color_palette') or brand_id.get('color_palette') or "Modern Color"
            dna_style = vis_id.get('art_style') or "Minimalist"
            t_name = proj.get("name", "Channel")
            # [QUAN TRỌNG] Lấy thêm Chủ đề để AI không bị bí
            t_topic = proj.get("topic", "General")

            if asset_type == "logo":
                # [CTO FIX] Prompt bắt buộc vẽ biểu tượng cụ thể theo chủ đề
                prompt = (f"A modern vector logo icon for a Youtube channel about '{t_topic}', named '{t_name}'. "
                          f"Style: {dna_style}. Main colors: {dna_color}. Vibe: {dna_mood}. "
                          f"The design should be a clean, recognizable symbol representing '{t_topic}', not generic. "
                          f"High quality, isolated on white background.")
            else:
                # Banner thì cần cảnh rộng
                prompt = (f"A wide Youtube channel banner background art for topic '{t_topic}', named '{t_name}'. "
                          f"Style: {dna_style}. Colors: {dna_color}. Atmosphere: {dna_mood}. "
                          f"Cinematic lighting, highly detailed, 4k resolution, no text.")
            
            self.log(f"🧠 Không thấy file prompt, đã tự tạo prompt theo DNA & Chủ đề.")
            # [Tùy chọn] Ghi ngược prompt tự chế ra file để lần sau dùng lại
            try:
                with open(prompt_path, "w", encoding="utf-8") as f: f.write(prompt)
            except: pass

        # --- [CỰC QUAN TRỌNG] IN RA PROMPT ĐỂ DEBUG ---
        # CEO nhìn vào dòng log này để biết chính xác tool đang bắt AI vẽ cái gì
        self.log(f"🚀 Đang gửi Prompt đi vẽ ({asset_type}): \n--> \"{prompt}\"")

        # --- 3. GỌI WORKER AN TOÀN (DÙNG POOL ĐỂ CHỐNG CRASH) ---
        btn_target = self.btn_redraw_logo if asset_type == "logo" else self.btn_redraw_banner
        btn_target.setEnabled(False)
        btn_target.setText("⏳")
        self.log(f"🎨 Đang vẽ {asset_type.upper()}... Prompt: {prompt[:30]}...")
        
        # [CTO FIX] Tạo biến cục bộ (local variable) thay vì self.brand_worker
        # Điều này giúp nhiều worker chạy cùng lúc mà không đè lên nhau
        worker = BrandArtistWorker(prompt, asset_type, self.current_brand_path)
        
        # Hàm dọn dẹp khi xong (xóa worker khỏi hồ chứa)
        def cleanup():
            if worker in self.brand_workers_pool:
                self.brand_workers_pool.remove(worker)
            worker.deleteLater()

        worker.finished_signal.connect(self.on_brand_done)
        worker.finished.connect(cleanup) # Tự xóa mình khỏi pool khi xong
        
        # Thêm vào hồ chứa để Python không xóa nhầm khi đang chạy
        self.brand_workers_pool.append(worker)
        
        worker.start()

    def on_brand_done(self, success, msg, img_type, path):
        """Xử lý khi vẽ xong"""
        # Mở lại nút
        if img_type == "logo":
            self.btn_redraw_logo.setEnabled(True); self.btn_redraw_logo.setText("🔄")
            lbl_target = self.lbl_logo
            w, h = 80, 80
        else:
            self.btn_redraw_banner.setEnabled(True); self.btn_redraw_banner.setText("🔄")
            lbl_target = self.lbl_banner
            w, h = 142, 80 # Tỷ lệ 16:9
            
        self.log(msg)
        
        if success and os.path.exists(path):
            # [CTO FIX] Quan trọng: Nạp ảnh gốc vào để chức năng Zoom hoạt động
            lbl_target.set_high_res(path)

            # Hiển thị ngay lập tức (Force reload hình ảnh)
            pix = QPixmap(path)
            # Dùng SmoothTransformation để ảnh không bị răng cưa khi co giãn
            lbl_target.setPixmap(pix.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
            lbl_target.setStyleSheet("border: 1px solid #00e6e6;") # Viền xanh báo hiệu mới

    def action_paste_json(self):
        """Smart Paste: Hợp nhất tính năng sạch (Clean) và nạp Scenes (Chuẩn V3.2)"""
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        
        # 1. Kiểm tra trống (Ưu điểm của #2)
        if not text:
            return QMessageBox.warning(self, "Trống", "Clipboard không có nội dung!")
            
        # 2. Điền và Lọc rác cho ô Voice (Ưu điểm của #2)
        clean_voice = self._clean_json_script(text)
        self.txt_voice_in.setText(clean_voice)
        
        # 3. Phân tích JSON để điền các ô khác
        try:
            data = json.loads(text)
            self.log("✅ Đã nhận diện cấu trúc JSON!")
            
            # Nạp Topic/Music
            if "topic" in data: self.txt_music_key.setText(data["topic"])
            
            # Nạp Thumbnail Prompt (Ưu điểm của #2)
            if "thumbnail_prompt" in data: self.txt_thumb_prompt.setText(data["thumbnail_prompt"])
            
            # Nạp Danh sách Cảnh/Visual (Ưu điểm của #1)
            if "scenes" in data and isinstance(data["scenes"], list): 
                self.list_visual_in.clear()
                for s in data["scenes"]: 
                    self.list_visual_in.addItem(s)
            
        except json.JSONDecodeError:
            self.log("⚠️ Đã Paste text thô (Không phải JSON chuẩn).")
        except Exception as e:
            self.log(f"⚠️ Lỗi khi phân tích dữ liệu: {str(e)}")

    def load_visual_preview(self, path=None):
        """
        Load ảnh/video vào list output. 
        QUAN TRỌNG: Phải gióng hàng 1:1 với list_visual_in để Sync Scroll hoạt động hoàn hảo.
        """
        if not isinstance(path, str):
            path = None

        if not path:
            if not self.current_task: return
            path = self.current_task.get("pj_path", "")

        vis_dir = os.path.join(path, "visuals")
        self.list_visual_out.clear()
        
        # Lấy số lượng phân cảnh từ cột Input
        scene_count = self.list_visual_in.count()
        if scene_count == 0:
             # Nếu list input trống, thử quét folder visuals lấy file thô
             if os.path.exists(vis_dir):
                 files = sorted([f for f in os.listdir(vis_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.mp4'))])
                 for idx, f in enumerate(files):
                     self._add_media_item(os.path.join(vis_dir, f), idx + 1)
             return

        # Duyệt theo đúng số lượng Scene bên Input
        for i in range(scene_count):
            scene_num = i + 1
            found_path = None
            
            # Tìm file bắt đầu bằng scene_XX_
            if os.path.exists(vis_dir):
                for f in os.listdir(vis_dir):
                    if f.startswith(f"scene_{scene_num:02d}_") and f.lower().endswith(('.png', '.jpg', '.jpeg', '.mp4')):
                        found_path = os.path.join(vis_dir, f)
                        break
            
            if found_path:
                self._add_media_item(found_path, scene_num)
            else:
                # Nếu chưa có file -> Thêm Placeholder để giữ hàng
                self._add_placeholder_item(scene_num)

    def _add_visual_in_item(self, scene_num: int, scene_text: str):
        """Thêm 1 item phân cảnh vào list Input với chiều cao cố định 120px (khớp Output để sync scroll đúng)."""
        item = QListWidgetItem(self.list_visual_in)
        item.setSizeHint(QSize(-1, 120))

        w = QWidget()
        w.setFixedHeight(120)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        # Tiêu đề SCENE (nhỏ, màu nhạt)
        lbl_title = QLabel(f"SCENE {scene_num}:")
        lbl_title.setStyleSheet("color: #f39c12; font-weight: bold; font-size: 11px;")

        # Nội dung mô tả cảnh (word wrap)
        lbl_text = QLabel(scene_text)
        lbl_text.setWordWrap(True)
        lbl_text.setStyleSheet("color: #ccc; font-size: 11px;")
        lbl_text.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(lbl_title)
        layout.addWidget(lbl_text)
        layout.addStretch()

        # Lưu text vào UserRole để các hàm khác có thể lấy
        item.setData(Qt.ItemDataRole.UserRole, scene_text)

        self.list_visual_in.setItemWidget(item, w)

    def _add_media_item(self, file_path, scene_num):
        """Thêm 1 item media thật vào list output"""
        item = QListWidgetItem(self.list_visual_out)
        item.setSizeHint(QSize(-1, 120)) # Chiều cao cố định 120px
        
        widget = MediaItemWidget(file_path, label_text=f"SCENE {scene_num}:", parent_list=self.list_visual_out)
        self.list_visual_out.setItemWidget(item, widget)
        item.setData(Qt.ItemDataRole.UserRole, file_path)

    def _add_placeholder_item(self, scene_num):
        """Thêm 1 ô trống (Waiting) để giữ hàng gióng thẳng với Input"""
        item = QListWidgetItem(self.list_visual_out)
        item.setSizeHint(QSize(-1, 120))
        
        w = QWidget()
        w.setFixedHeight(120)
        l = QHBoxLayout(w)
        lbl = QLabel(f"SCENE {scene_num}: ⏳ ĐANG ĐỢI TẠO...")
        lbl.setStyleSheet("color: #555; font-style: italic; font-weight: bold; border: 1px dashed #333; border-radius: 5px;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(lbl)
        
        self.list_visual_out.setItemWidget(item, w)
    
    def check_files_status(self):
        """Kiểm tra và bật đèn xanh các file đã có (Chuẩn V3.2: Full Voice + Music)"""
        if not self.current_task: return
        path = self.current_task.get("pj_path", "")
        
        # 1. Check Voice (MP3)
        mp3_path = os.path.join(path, "voice.mp3")
        has_mp3 = os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 0
        
        if has_mp3:
            self.lbl_voice_out.setText("✅ Ready")
            self.lbl_voice_out.setStyleSheet("color:#2ecc71; font-weight:bold")
            self.btn_open_folder.setEnabled(True)
        else:
            self.lbl_voice_out.setText("❌ Missing")
            self.lbl_voice_out.setStyleSheet("color:#e74c3c;")
            self.btn_open_folder.setEnabled(False)

        # 2. Check Subtitle (SRT) - [MỚI]
        srt_path = os.path.join(path, "voice.srt")
        has_srt = os.path.exists(srt_path) and os.path.getsize(srt_path) > 0
        
        if has_srt:
            self.lbl_sub_out.setText("✅ Ready")
            self.lbl_sub_out.setStyleSheet("color:#2ecc71; font-weight:bold")
            self.btn_view_sub.setEnabled(True) # Mở khóa nút xem
        else:
            self.lbl_sub_out.setText("❌ Missing")
            self.lbl_sub_out.setStyleSheet("color:#e74c3c;")
            self.btn_view_sub.setEnabled(False) # Khóa nút xem

        # 3. Check Music (Như cũ)
        if os.path.exists(os.path.join(path, "background.mp3")):
            self.lbl_music_file.setText("✅ Có nhạc")
            self.lbl_music_file.setStyleSheet("color:#2ecc71; font-weight:bold")
        else:
            self.lbl_music_file.setText("❌ Thiếu")
            self.lbl_music_file.setStyleSheet("color:#7f8c8d; font-style:italic;")

    def _apply_style(self):
        self.setStyleSheet("""
            QWidget { background: #1e1e1e; color: #eee; font-family: 'Segoe UI'; font-size: 13px; }
            QListWidget { 
                background: #202020; 
                border: 1px solid #333; 
                font-size: 13px;
                color: #ddd;
            }
            QListWidget::item { 
                padding: 12px 5px; 
                border-bottom: 1px solid #444; 
            }
            QListWidget::item:selected { 
                background: #2c3e50; 
                color: #f1c40f;      
                border-left: 5px solid #e74c3c; 
            }
            QTableWidget { background: #252526; border: 1px solid #444; gridline-color: #333; }
            QHeaderView::section { background: #2c3e50; padding: 5px; font-weight: bold; border: 1px solid #444; }
            QTextEdit, QLineEdit { background: #333; border: 1px solid #555; padding: 5px; border-radius: 3px; }
            QPushButton { padding: 6px 12px; border-radius: 4px; background: #444; border: 1px solid #555; }
            QPushButton:hover { background: #555; border: 1px solid #777; }
        """)

    def log(self, msg):
        import datetime
        t = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_signal.emit(f"[Xưởng Media] {msg}")
        #self.txt_log.append(f"[{t}] {msg}")
    
    def on_visual_output_clicked(self, item):
        """Click vào file output -> Play Video hoặc mở Ảnh"""
        path = item.data(Qt.ItemDataRole.UserRole)
        if not path or not os.path.exists(path): return

        if path.lower().endswith(('.mp4', '.mov', '.avi')):
            # Play Video
            self.player.setSource(QUrl.fromLocalFile(path))
            self.player.play()
            self.log(f"▶ Đang xem: {os.path.basename(path)}")
        else:
            # Xem Ảnh (Mở bằng trình xem ảnh mặc định của Win)
            # Hoặc hiển thị lên label preview (nếu bạn muốn code thêm)
            os.startfile(path)
            self.log(f"📷 Đã mở ảnh: {os.path.basename(path)}")
    
    def action_preview_voice(self):
        raw_text = self.txt_voice_in.toPlainText()
        if not raw_text: return
        
        # --- [CTO FIX] CHẶN PREVIEW NẾU LÀ SILENT MODE ---
        # Nếu kịch bản là im lặng -> Báo luôn, không gọi API tốn tiền/lỗi
        keywords_silent = ["(NO VOICE", "(SILENT", "NO_VOICE", "AUDIO LAYERS PLAYING ONLY"]
        if any(k in raw_text.upper() for k in keywords_silent) or len(raw_text) < 5:
            QMessageBox.information(self, "Chế độ Im Lặng", "Video này được cấu hình là Nhạc/Thiền (Silent).\nKhông có giọng đọc để nghe thử!")
            return
        # -------------------------------------------------

        # 1. TĂNG SỐ THỨ TỰ (Gen ID)
        if not hasattr(self, 'preview_gen_id'): self.preview_gen_id = 0
        self.preview_gen_id += 1
        current_gen_id = self.preview_gen_id 

        # 2. Dừng Player nhẹ nhàng
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.stop()
        
        # 3. Tạo tên file UUID
        import uuid, time
        temp_dir = os.path.abspath("VEO_TEMP")
        if not os.path.exists(temp_dir): os.makedirs(temp_dir)        
        
        # Dọn dẹp file cũ > 5 phút (Chạy trong try-catch để không bao giờ crash)
        try:
            for f in os.listdir(temp_dir):
                if f.endswith(".mp3"):
                    f_path = os.path.join(temp_dir, f)
                    if time.time() - os.path.getctime(f_path) > 500: # 500s = 5 phút
                        try: os.remove(f_path)
                        except: pass
        except: pass

        unique_name = f"pre_{current_gen_id}_{uuid.uuid4().hex[:6]}.mp3"
        temp_path = os.path.join(temp_dir, unique_name)
        
        # 4. Chuẩn bị text
        preview_text = raw_text[:150].replace('\n', ' ').strip() + "..."
        
        selected_engine_idx = self.cb_voice_eng.currentIndex()
        provider_map = {
            0: "auto",      # Auto (AI Director)
            1: "google",    # Google TTS
            2: "edge",      # Edge TTS
            3: "openai"     # OpenAI TTS
        }
        selected_provider = provider_map.get(selected_engine_idx, "auto")
        # 5. Cấu hình
        meta = {
            "rate": f"{self.sl_rate.value()}%",
            "pitch": f"{self.sl_pitch.value()}Hz",
            "voice_id": self.cb_voice_name.currentData(), 
            "provider_override": selected_provider
        }
        
        # 6. UI Feedback
        self.btn_gen_voice.setEnabled(False) 
        if hasattr(self, 'btn_preview_voice'):
            self.btn_preview_voice.setText(f"⏳ ({current_gen_id})...")
            self.btn_preview_voice.setEnabled(False) # Khóa nút 1 chút

        # 7. KHỞI TẠO WORKER VÀ ĐƯA VÀO POOL (QUAN TRỌNG NHẤT)
        worker = VoiceWorker(preview_text, temp_path, meta)
        
        # Hàm dọn dẹp (Chạy khi worker xong)
        def cleanup_worker():
            if worker in self.preview_workers_pool:
                self.preview_workers_pool.remove(worker)
            worker.deleteLater() # Xóa khỏi bộ nhớ an toàn

        # Hàm xử lý kết quả
        def on_preview_done(success, msg, path):
            # Luôn dọn dẹp worker dù thành công hay thất bại
            cleanup_worker()

            # Kiểm tra ID: Nếu ID này đã cũ -> Bỏ qua, không làm gì cả
            if current_gen_id != self.preview_gen_id: return 

            # Mở khóa nút (Chỉ khi là lệnh mới nhất)
            self.btn_gen_voice.setEnabled(True)
            if hasattr(self, 'btn_preview_voice'):
                self.btn_preview_voice.setEnabled(True)
                self.btn_preview_voice.setText("🎧 Nghe thử 3 câu")

            if success and os.path.exists(path) and os.path.getsize(path) > 0:
                self.player.setSource(QUrl.fromLocalFile(path))
                self.player.play()
                self.log(f"▶ Preview #{current_gen_id}: {os.path.basename(path)}")
            else:
                print(f"Lỗi Preview #{current_gen_id}: {msg}")

        # Kết nối tín hiệu
        worker.finished_signal.connect(on_preview_done)
        
        # [MẤU CHỐT] Thêm vào hồ chứa để Python không giết nó giữa chừng
        self.preview_workers_pool.append(worker)
        
        worker.start()
        
        # Mở lại nút sau 1.5 giây (Anti-Spam Click)
        QTimer.singleShot(1500, lambda: self.btn_preview_voice.setEnabled(True) if hasattr(self, 'btn_preview_voice') else None)
    
    def action_batch_generate_brand(self):
        """Quét toàn bộ dự án, kênh nào chưa có Logo/Banner thì vẽ tự động"""
        missing_jobs = []
        
        self.log("🔍 Đang quét các kênh thiếu nhận diện thương hiệu...")
        
        for i, proj in enumerate(self.projects):
            # Tái tạo đường dẫn (Logic giống on_project_selected)
            try:
                p_plat = self._sanitize_filename(proj.get("platform", "Youtube"))
                p_coun = self._sanitize_filename(proj.get("country", "Global").split('~')[0])
                p_top = self._sanitize_filename(proj.get("topic", "General"))
                base_path = os.path.join("VEO_DB", p_plat, p_coun, p_top, "Brand_Assets")
                
                # Check Logo
                if not os.path.exists(os.path.join(base_path, "logo.jpg")):
                    missing_jobs.append({"index": i, "type": "logo", "path": base_path, "proj": proj})
                
                # Check Banner
                if not os.path.exists(os.path.join(base_path, "banner.jpg")):
                    missing_jobs.append({"index": i, "type": "banner", "path": base_path, "proj": proj})
                    
            except: continue

        if not missing_jobs:
            return QMessageBox.information(self, "Tuyệt vời", "Tất cả các kênh đều đã có đủ Logo & Banner!")

        confirm = QMessageBox.question(self, "Xác nhận", f"Tìm thấy {len(missing_jobs)} hạng mục còn thiếu.\nBạn có muốn AI vẽ tự động ngay bây giờ?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if confirm == QMessageBox.StandardButton.No: return

        # Chạy Queue (Hàng đợi)
        self.brand_queue = missing_jobs
        self.is_brand_batch_running = True
        self.btn_auto_brand.setEnabled(False)
        self.btn_auto_brand.setText(f"⏳ Đang vẽ ({len(missing_jobs)})...")
        
        self.process_next_brand_item()

    def process_next_brand_item(self):
        if not hasattr(self, 'brand_queue') or not self.brand_queue:
            self.is_brand_batch_running = False
            self.btn_auto_brand.setEnabled(True)
            self.btn_auto_brand.setText("🎨 Auto-Brand All")
            QMessageBox.information(self, "Xong", "Đã vẽ xong toàn bộ Logo/Banner còn thiếu!")
            return

        job = self.brand_queue.pop(0)
        
        # Lấy Prompt
        prof = job['proj'].get("channel_profile", {})
        visuals = prof.get("visual_identity", {})
        prompt = visuals.get(f"{job['type']}_prompt", "")
        
        if not prompt: # Fallback Prompt
            t_name = job['proj'].get("name", "Channel")
            mood = prof.get("brand_identity", {}).get("mood", "Professional")
            if job['type'] == 'logo':
                prompt = f"Vector logo for '{t_name}', style {mood}, minimalist, white background"
            else:
                prompt = f"Youtube banner for '{t_name}', style {mood}, cinematic, 4k"

        self.log(f"🎨 Auto-Brand [{len(self.brand_queue)} left]: Vẽ {job['type']} cho kênh '{job['proj']['name']}'...")
        
        # Gọi Worker
        self.brand_batch_worker = BrandArtistWorker(prompt, job['type'], job['path'])
        
        # Kết nối xong thì gọi tiếp cái sau
        self.brand_batch_worker.finished_signal.connect(lambda s, m, t, p: self.on_brand_batch_done(s, m, t, p, job['index']))
        self.brand_batch_worker.start()

    def on_brand_batch_done(self, success, msg, img_type, path, proj_index):
        self.log(msg)
        
        # Nếu đang xem đúng dự án đó thì cập nhật UI luôn
        if success and self.current_project_index == proj_index:
            self.on_project_selected(self.list_projects.item(proj_index))
            
        # Gọi cái tiếp theo
        QTimer.singleShot(5000, self.process_next_brand_item)
    
    # ==========================================
    # 🎮 DÁN ĐOẠN NÀY VÀO TRONG CLASS MediaTab
    # ==========================================
    def toggle_play(self):
        """Bấm nút Play/Pause"""
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.timer.stop()
            if hasattr(self, 'btn_play'): self.btn_play.setText("▶")
        else:
            self.player.play()
            self.timer.start()
            if hasattr(self, 'btn_play'): self.btn_play.setText("⏸")

    def update_player_ui(self):
        """Timer gọi hàm này để đẩy thanh trượt"""
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState and not self.seek_voice.isSliderDown():
            self.seek_voice.blockSignals(True)
            self.seek_voice.setValue(self.player.position())
            self.seek_voice.blockSignals(False)

    def on_position_changed(self, position):
        """Khi file chạy -> Cập nhật số giây"""
        duration = self.player.duration()
        self.lbl_voice_time.setText(f"{self.format_time(position)} / {self.format_time(duration)}")
        if not self.seek_voice.isSliderDown():
            self.seek_voice.setValue(position)

    def on_duration_changed(self, duration):
        """Khi file load xong -> Cập nhật tổng thời gian"""
        self.seek_voice.setRange(0, duration)
        self.lbl_voice_time.setText(f"00:00 / {self.format_time(duration)}")

    def format_time(self, ms):
        """Đổi mili-giây sang 00:00"""
        seconds = (ms // 1000) % 60
        minutes = (ms // 60000)
        return f"{minutes:02}:{seconds:02}"

    def open_current_folder(self):
        """Mở thư mục chứa file MP3/SRT (Đã Fix lỗi Windows Path)"""
        # Kiểm tra nếu task hiện tại hợp lệ
        if self.current_task and self.current_task.get('pj_path'):
            path = self.current_task['pj_path']
            # Chuẩn hóa đường dẫn cho Windows (dấu ngược \)
            path = os.path.normpath(path)
            
            if os.path.exists(path):
                try:
                    os.startfile(path)
                    self.log(f"📂 Đã mở thư mục: {path}")
                except Exception as e:
                    self.log(f"❌ Lỗi mở folder: {e}")
            else:
                self.log(f"❌ Thư mục không tồn tại: {path}")
        else:
            self.log("⚠️ Chưa chọn Video nào để mở thư mục!")
    
    def set_position(self, position):
        """Kéo thanh trượt"""
        self.player.setPosition(position)
    
    def stop_player(self):
        """Dừng hẳn"""
        self.player.stop()
        self.timer.stop()
        if hasattr(self, 'btn_play'): self.btn_play.setText("▶")
        self.seek_voice.setValue(0)

    # --- [NEW] LOGIC TẠO STICKER AI & TÁCH NỀN ---
    # --- [CTO UPGRADE] TỰ ĐỘNG HÓA TẠO STICKER ---
    def action_create_ai_sticker(self):
        """
        Tự động đọc Tiêu đề Video -> Suy luận Sticker -> Vẽ -> Tách nền -> Lưu kho
        """
        if not self.current_task: 
            return QMessageBox.warning(self, "Lỗi", "Vui lòng chọn 1 Video để AI biết cần vẽ gì!")

        # 1. Lấy thông tin ngữ cảnh (Tiêu đề + Chủ đề)
        title = self.current_task.get('key_vua', '')
        proj = self.projects[self.current_project_index]
        topic = proj.get("topic", "")
        
        # Gộp lại để phân tích
        context_text = f"{title} {topic}"
        
        # 2. Gọi bộ não để lấy Prompt tự động
        auto_prompt = get_auto_sticker_prompt(context_text)
        
        self.log(f"🧠 AI suy luận Sticker: '{auto_prompt}' (từ tiêu đề: {title})")
        
        # 3. UI Feedback
        self.btn_create_sticker.setEnabled(False)
        self.btn_create_sticker.setText("⏳ AI đang vẽ Sticker...")
        
        # 4. Thiết lập đường dẫn lưu (Lưu vào kho chung của Dự án để tái sử dụng)
        # Thay vì lưu vào folder temp, ta lưu vào folder assets của dự án
        pj_path = self.current_task.get("pj_path", "")
        # Lấy thư mục gốc của dự án (VEO_DB/Platform/Country/Topic/Brand_Assets/stickers)
        # Nhưng để đơn giản và gắn liền với video, ta lưu vào thư mục sticker của video hiện tại trước
        sticker_dir = os.path.join(pj_path, "stickers")
        if not os.path.exists(sticker_dir): os.makedirs(sticker_dir)
        
        import uuid
        file_name = f"sticker_auto_{uuid.uuid4().hex[:4]}"
        
        # 5. Gọi Worker vẽ (Giống hệt cũ, nhưng prompt là tự động)
        self.sticker_worker = BrandArtistWorker(auto_prompt, "logo", sticker_dir)
        self.sticker_worker.sticker_name = file_name
        self.sticker_worker.finished_signal.connect(self.on_sticker_drawn)
        self.sticker_worker.start()

    def on_sticker_drawn(self, success, msg, img_type, raw_path):
        """Khi AI vẽ xong -> Gọi Composer tách nền"""
        if success:
            self.log(f"🎨 Đã vẽ xong base, đang tách nền: {os.path.basename(raw_path)}")
            
            # Gọi Composer tách nền
            composer = ThumbnailComposer()
            clean_path = raw_path.replace(".jpg", ".png").replace(".jpeg", ".png")
            
            ok = composer.remove_background(raw_path, clean_path)
            
            if ok:
                self.log(f"✂️ Đã tách nền thành công: {os.path.basename(clean_path)}")
                # Lưu đường dẫn sticker mới nhất vào biến để dùng khi ghép
                self.current_sticker_path = clean_path
                QMessageBox.information(self, "Xong", "Đã tạo Sticker thành công!\nBây giờ hãy bấm 'Vẽ Nền' hoặc 'Đổi Bố Cục' để ghép vào.")
            else:
                self.log("❌ Lỗi tách nền (Kiểm tra thư viện rembg).")
        
        self.btn_create_sticker.setEnabled(True); self.btn_create_sticker.setText("🎨 TẠO STICKER (AI)")

    # --- [NEW] LOGIC RE-ROLL LAYOUT ---
    def action_randomize_layout(self):
        """Xáo lại vị trí Text/Sticker trên nền cũ"""
        if not self.thumb_candidates: 
            return QMessageBox.warning(self, "Chưa có ảnh", "Vui lòng tạo Thumbnail (Vẽ nền) trước!")
            
        # Lấy ảnh nền gốc (Raw) - Cần lưu lại raw path khi tạo lần đầu
        # Ở đây ta dùng mẹo: Lấy ảnh raw từ thumb_temp_dir (file bắt đầu bằng raw_)
        raw_files = [f for f in os.listdir(self.thumb_temp_dir) if f.startswith("raw_")]
        if not raw_files: return
        
        raw_path = os.path.join(self.thumb_temp_dir, raw_files[0]) # Lấy đại cái đầu tiên
        
        # Chọn chế độ layout ngẫu nhiên
        modes = ["standard", "swap", "center"]
        new_mode = random.choice(modes)
        
        self.log(f"🎲 Đang thử bố cục: {new_mode.upper()}...")
        
        # Gọi lại quy trình ghép (Composer)
        self._run_composer_merge(raw_path, layout_mode=new_mode)

    # --- HÀM GHÉP CHUNG (ĐÃ HỒI SINH BỘ TỪ ĐIỂN ĐA NGÔN NGỮ) ---
    def _run_composer_merge(self, raw_path, layout_mode="standard"):
        """Hàm này chịu trách nhiệm tính toán Text và gọi Composer"""
        
        # 1. Lấy Text Chính (Primary)
        # Ưu tiên lấy từ ô nhập liệu, nếu rỗng thì lấy Key Vua
        t1 = self.txt_thumb_text.text().strip()
        if not t1:
            t1 = self.current_task.get('key_vua', 'VIDEO TITLE')
        t1 = t1.upper() # Luôn viết hoa cho đẹp

        # 2. Lấy Text Phụ (CTA Button) - LOGIC CŨ ĐƯỢC CHUYỂN VÀO ĐÂY
        proj = self.projects[self.current_project_index]
        target_country = proj.get("country", "VN").upper()
        
        cta_map = {
            # --- TIER 1: KHO BÁU TỶ ĐÔ ---
            "US": "WATCH NOW", "AU": "WATCH NOW", "CA": "WATCH NOW", "GB": "WATCH NOW",
            "CH": "ANSEHEN", "NO": "SE NÅ", "NZ": "WATCH NOW",
            # --- TIER 2: CHÂU ÂU ---
            "DE": "ANSEHEN", "NL": "KIJK NU", "SE": "TITTA NU", "DK": "SE NU",
            "FI": "KATSO NYT", "FR": "REGARDER", "IE": "WATCH NOW", "AT": "ANSEHEN",
            # --- TIER 3: CHÂU Á ---
            "QA": "شاهد الآن", "AE": "شاهد الآن", "SG": "WATCH NOW",
            "JP": "今すぐ見る", "KR": "지금 보세요", "IL": "צפו עכשיו",
            "SA": "شاهد الآن", "HK": "立即觀看", "TW": "立即觀看", "KW": "شاهد الآن",
            "CN": "立即观看",
            # --- TIER 4-7 ---
            "ES": "VER AHORA", "IT": "GUARDA ORA", "PT": "VER AGORA",
            "PL": "OGLĄDAJ", "CZ": "SLEDOVAT", "GR": "ΔΕΙΤΕ ΤΩΡΑ",
            "HU": "NÉZD MEG", "RU": "СМОТРЕТЬ", "TR": "İZLE",
            "BR": "ASSISTIR", "MX": "VER AHORA", "IN": "WATCH NOW",
            "VN": "XEM NGAY", "ID": "TONTON", "PH": "WATCH NOW", "TH": "ดูเลย",
            "LA": "ເບິ່ງເລີຍ", "KH": "ទស្សនា",
            "GLOBAL": "WATCH NOW"
        }

        # Tìm CTA theo quốc gia
        t2 = "WATCH NOW"
        for code, text in cta_map.items():
            if code in target_country:
                t2 = text
                break
        if "Việt Nam" in target_country or "VN" in target_country: t2 = "XEM NGAY"

        # 3. Lấy Sticker (Nếu đã tạo trước đó)
        sticker = getattr(self, 'current_sticker_path', None)
        
        # 4. Lấy màu Brand
        brand_color = proj.get("channel_profile", {}).get("visual_identity", {}).get("color_palette", "#FF0000")
        brand_mood = proj.get("channel_profile", {}).get("brand_identity", {}).get("mood", "Cinematic")

        # 5. Gọi Composer để ghép
        # 
        composer = ThumbnailComposer()
        
        import uuid
        # Tạo tên file output ngẫu nhiên để không bị cache đè
        out_name = f"final_thumb_{layout_mode}_{uuid.uuid4().hex[:4]}.png"
        out_path = os.path.join(self.thumb_temp_dir, out_name)
        
        # Lấy topic hiện tại (đã set ở bước 1)
        topic = getattr(self, 'current_topic', 'General')

        success, final_path = composer.create_thumbnail(
            bg_path=raw_path,
            text_primary=t1,
            text_secondary=t2,
            output_path=out_path,
            brand_color=brand_color,
            mood=brand_mood,
            layout_mode=layout_mode,
            sticker_path=sticker,
            topic=topic
        )
        
        if success:
            # Thêm vào danh sách hiển thị
            self.thumb_candidates.append(final_path)
            # Chuyển view sang ảnh mới nhất
            self.current_thumb_idx = len(self.thumb_candidates) - 1
            self.update_thumb_preview_ui()
    
    # =========================================================
    # 🏭 QUY TRÌNH TẠO THUMBNAIL TỰ ĐỘNG (PIPELINE V3.0 - ANTI CRASH)
    # =========================================================
    
    def action_generate_full_thumbnail(self):
        """Nhạc trưởng: Điều phối Sticker -> Background -> Composer"""
        if not self.current_task: 
            return QMessageBox.warning(self, "Chưa chọn", "Vui lòng chọn 1 Video trước!")
        self.log_signal.emit("⚡ Đang khởi động dây chuyền sản xuất Thumbnail Studio...")
            
        # --- [CTO FIX 1] CHỤP SNAPSHOT CONTEXT (CHỐNG LẪN LỘN VIDEO) ---
        # Lưu lại toàn bộ trạng thái tại thời điểm bấm nút
        proj = self.projects[self.current_project_index]
        self.thumb_context = {
            "task": self.current_task,
            "proj_idx": self.current_project_index,
            "proj_data": proj,
            "path": self.current_task.get("pj_path", ""),
            "text1": self.txt_thumb_text.text().strip() or self.current_task.get('key_vua', 'TITLE').upper(),
            "bg_prompt": self.txt_thumb_prompt.toPlainText().strip(),
            "qty": int(self.spin_thumb_qty.currentText().split()[0]) # Lấy số lượng
        }

        # Phân tích Topic (Chuẩn hóa)
        raw_topic = proj.get("topic", "").lower()
        title_text = self.current_task.get('key_vua', '').lower()
        full_context = f"{raw_topic} {title_text}"

        TOPIC_MAP = {
            "money": "Money", "crypto": "Money", "finance": "Money", "rich": "Money",
            "horror": "Horror", "scary": "Horror", "crime": "Horror", "mystery": "Horror",
            "kids": "Kids", "baby": "Kids", "toy": "Kids",
            "animal": "Animals", "cat": "Animals", "dog": "Animals", "pet": "Animals",
            "tech": "Tech", "ai": "Tech", "robot": "Tech", "future": "Tech",
            "fact": "Facts", "space": "Facts", "history": "Facts", "earth": "Facts",
            "relax": "Chill", "lofi": "Chill", "rain": "Chill", "sleep": "Chill",
            "quote": "Emotional", "sad": "Emotional", "love": "Emotional", "stoic": "Emotional"
        }

        self.thumb_context["topic"] = "General"
        for key, folder_name in TOPIC_MAP.items():
            if key in full_context:
                self.thumb_context["topic"] = folder_name
                break
        # ---------------------------------------------------------------
            
        self.log(f"🚀 Bắt đầu quy trình Thumbnail. Topic: {self.thumb_context['topic']} | Số lượng: {self.thumb_context['qty']}")
        self.btn_create_full.setEnabled(False)
        self.btn_create_full.setText("⏳ Đang tìm Sticker...")

        # Bước 1: Săn Sticker
        sticker_repo = os.path.join("assets", "overlays", "Stickers", self.thumb_context["topic"])
        if not os.path.exists(sticker_repo): os.makedirs(sticker_repo)
        
        existing_stickers = [f for f in os.listdir(sticker_repo) if f.endswith('.png')]
        
        if existing_stickers:
            self.thumb_context["sticker_path"] = os.path.join(sticker_repo, random.choice(existing_stickers))
            self.log(f"✅ Đã tìm thấy Sticker trong kho.")
            self._step_2_generate_background()
        else:
            self.log(f"🔍 Kho rỗng. Gọi AI vẽ Sticker mới...")
            sticker_prompt = get_auto_sticker_prompt(full_context)
            import uuid
            s_name = f"sticker_{self.thumb_context['topic']}_{uuid.uuid4().hex[:4]}"
            
            self.sticker_worker = BrandArtistWorker(sticker_prompt, s_name, sticker_repo) # Dùng s_name thay vì "logo"
            self.sticker_worker.finished_signal.connect(self._on_pipeline_sticker_done)
            self.sticker_worker.start()

    def _on_pipeline_sticker_done(self, success, msg, img_type, raw_path):
        if success and os.path.exists(raw_path):
            clean_path = raw_path.replace(".jpg", ".png").replace(".jpeg", ".png")
            composer = ThumbnailComposer()
            if composer.remove_background(raw_path, clean_path):
                self.thumb_context["sticker_path"] = clean_path
                self.log("✅ Đã tạo & tách nền Sticker mới.")
                try: os.remove(raw_path) 
                except: pass
            else:
                self.thumb_context["sticker_path"] = None
        else:
            self.thumb_context["sticker_path"] = None
            
        self._step_2_generate_background()

    def _step_2_generate_background(self):
        """Bước 2: Vẽ nền Background (Sử dụng Context & Chống khóa file)"""
        self.btn_create_full.setText(f"⏳ Đang vẽ {self.thumb_context['qty']} Nền...")
        
        base_prompt = self.thumb_context["bg_prompt"] or f"{self.thumb_context['topic']} background, cinematic lighting, high contrast, blurry background"
        clean_prompt = f"{base_prompt}, no text, empty space on the left, 8k resolution"
        
        self.thumb_temp_dir = os.path.join(self.thumb_context["path"], "thumb_candidates")
        if not os.path.exists(self.thumb_temp_dir): os.makedirs(self.thumb_temp_dir)
        
        self.bg_workers_pool = []
        import uuid
        
        qty = self.thumb_context["qty"]
        for i in range(qty):
            # [CTO FIX 2] TRÁNH GHI ĐÈ FILE: Đặt tên file nền duy nhất cho mỗi worker
            bg_name = f"raw_bg_{i+1}_{uuid.uuid4().hex[:4]}" 
            
            worker = BrandArtistWorker(clean_prompt, bg_name, self.thumb_temp_dir)
            worker.finished_signal.connect(self._on_pipeline_bg_done)
            self.bg_workers_pool.append(worker)
            
            worker.start()

    def _on_pipeline_bg_done(self, success, msg, img_type, bg_path):
        """Bước 3: Lắp ráp từng phương án"""
        if success and os.path.exists(bg_path):
            self.log(f"🎨 Đã có nền {os.path.basename(bg_path)}. Đang ghép layer...")
            self._run_composer_merge(bg_path, layout_mode="standard")
        else:
            self.log(f"❌ Lỗi vẽ nền: {msg}")
            
        # Kiểm tra xem tất cả các worker vẽ nền đã chạy xong chưa
        all_done = all(not w.isRunning() for w in self.bg_workers_pool)
        
        if all_done:
            self.btn_create_full.setEnabled(True)
            self.btn_create_full.setText("⚡ TẠO THUMBNAIL (FULL)")
            self.log("🏁 Hoàn tất quy trình tạo hàng loạt Thumbnail!")
            
            # [CTO FIX] Tiếp tục vòng lặp BATCH nếu đang chạy Auto-Pilot
            if getattr(self, 'is_batch_running', False):
                # Lưu ảnh đầu tiên làm thumbnail chính thức
                if getattr(self, 'thumb_candidates', []):
                    try:
                        import shutil
                        dest_path = os.path.join(self.thumb_context["path"], "thumbnail.jpg")
                        shutil.copy(self.thumb_candidates[0], dest_path)
                    except: pass
                # Đợi 1 chút để UI kịp phản hồi rồi gọi tiếp queue
                QTimer.singleShot(1000, self.process_next_batch_item)

    # --- [NEW] AI AUTO THUMBNAIL (Lấy cảm hứng yt_thumbnail_creator) ---
    def action_ai_auto_thumbnail(self):
        """🤖 Pipeline tự động: AI Director → Generate Assets → rembg → Composite"""
        if not self.current_task: 
            return QMessageBox.warning(self, "Chưa chọn", "Vui lòng chọn 1 Video trước!")
        
        path = self.current_task.get("pj_path", "")
        if not path:
            return QMessageBox.warning(self, "Lỗi", "Không tìm thấy thư mục dự án!")
        
        # Thu thập context
        proj = self.projects[self.current_project_index]
        topic = self.current_task.get("key_vua", "YouTube Video")
        title_override = self.txt_thumb_text.text().strip() or None
        
        # Brand color
        brand_color = proj.get("channel_profile", {}).get("visual_identity", {}).get("color_palette", "#FF0000")
        # Country
        country = proj.get("country", "US")
        
        # Output path
        thumb_dir = os.path.join(path, "thumb_candidates")
        os.makedirs(thumb_dir, exist_ok=True)
        import uuid
        output_path = os.path.join(thumb_dir, f"ai_auto_{uuid.uuid4().hex[:6]}.png")
        
        self.log("🤖 [AI Auto Thumbnail] Đang khởi động pipeline...")
        self.btn_ai_auto_thumb.setEnabled(False)
        self.btn_ai_auto_thumb.setText("⏳ AI đang xử lý...")
        
        # Spawn worker
        from modules.assets_factory.workers import ThumbnailAIWorker
        self._ai_thumb_worker = ThumbnailAIWorker(
            topic=topic,
            output_path=output_path,
            title_override=title_override,
            brand_color=brand_color,
            country=country
        )
        self._ai_thumb_worker.progress_signal.connect(self.log)
        self._ai_thumb_worker.finished_signal.connect(self._on_ai_thumb_done)
        self._ai_thumb_worker.start()
    
    def _on_ai_thumb_done(self, success, msg, output_path):
        """Callback khi AI Thumbnail pipeline hoàn tất."""
        self.btn_ai_auto_thumb.setEnabled(True)
        self.btn_ai_auto_thumb.setText("🤖 AI AUTO THUMBNAIL")
        
        if success and output_path and os.path.exists(output_path):
            self.thumb_candidates.append(output_path)
            self.current_thumb_idx = len(self.thumb_candidates) - 1
            self.update_thumb_preview_ui()
            self.log(f"🎉 AI Thumbnail hoàn tất! ({os.path.basename(output_path)})")
            
            # Auto-save as thumbnail.jpg
            try:
                import shutil
                path = self.current_task.get("pj_path", "")
                if path:
                    dest = os.path.join(path, "thumbnail.jpg")
                    shutil.copy(output_path, dest)
                    self.log(f"💾 Đã lưu thumbnail chính thức → thumbnail.jpg")
            except Exception as e:
                self.log(f"⚠️ Không lưu được thumbnail chính: {e}")
        else:
            self.log(f"❌ AI Thumbnail thất bại: {msg}")
            QMessageBox.warning(self, "AI Thumbnail", f"Tạo thumbnail không thành công:\n{msg}")

    # --- [NEW] LOGIC RE-ROLL LAYOUT ---
    def action_randomize_layout(self):
        """Xáo lại vị trí Text/Sticker trên nền cũ"""
        if not self.thumb_candidates: 
            return QMessageBox.warning(self, "Chưa có ảnh", "Vui lòng tạo Thumbnail (Vẽ nền) trước!")
            
        if not hasattr(self, 'thumb_temp_dir') or not os.path.exists(self.thumb_temp_dir):
            return QMessageBox.warning(self, "Chức năng cũ", "Chức năng 'Đổi bố cục' hiện tại chỉ hỗ trợ chế độ 'Vẽ nền + Text' thủ công. Chế độ AI Auto sẽ sinh ảnh hoàn chỉnh.")
            
        raw_files = [f for f in os.listdir(self.thumb_temp_dir) if f.startswith("raw_")]
        if not raw_files: return
        
        raw_path = os.path.join(self.thumb_temp_dir, raw_files[0])
        modes = ["standard", "swap", "center"]
        new_mode = random.choice(modes)
        
        self.log(f"🎲 Đang thử bố cục: {new_mode.upper()}...")
        
        # [CTO FIX 3] Nếu CEO tự bấm nút Đổi Bố Cục, phải CẬP NHẬT LẠI SNAPSHOT từ giao diện
        if not hasattr(self, 'thumb_context'):
            self.thumb_context = {}
            
        self.thumb_context["text1"] = self.txt_thumb_text.text().strip() or self.current_task.get('key_vua', 'TITLE').upper()
        self.thumb_context["proj_data"] = self.projects[self.current_project_index]
        self.thumb_context["sticker_path"] = getattr(self, 'current_sticker_path', None)
        self.thumb_context["topic"] = getattr(self, 'current_topic', 'General')
        
        self._run_composer_merge(raw_path, layout_mode=new_mode)

    # --- HÀM GHÉP CHUNG (ĐỌC TỪ SNAPSHOT CHỨ KHÔNG ĐỌC TỪ GIAO DIỆN) ---
    def _run_composer_merge(self, raw_path, layout_mode="standard"):
        """Hàm này chịu trách nhiệm tính toán Text và gọi Composer"""
        
        # 1. Lấy dữ liệu an toàn từ Snapshot Context
        t1 = self.thumb_context["text1"].upper()
        proj = self.thumb_context["proj_data"]
        topic = self.thumb_context["topic"]
        sticker = self.thumb_context.get("sticker_path")
        
        target_country = proj.get("country", "VN").upper()
        
        # 2. Ngôn ngữ CTA Button
        cta_map = {
            "US": "WATCH NOW", "AU": "WATCH NOW", "CA": "WATCH NOW", "GB": "WATCH NOW",
            "DE": "ANSEHEN", "FR": "REGARDER", "JP": "今すぐ見る", "KR": "지금 보세요",
            "ES": "VER AHORA", "IT": "GUARDA ORA", "RU": "СМОТРЕТЬ", "IN": "WATCH NOW",
            "VN": "XEM NGAY", "TH": "ดูเลย", "ID": "TONTON", "GLOBAL": "WATCH NOW"
        }

        t2 = "WATCH NOW"
        for code, text in cta_map.items():
            if code in target_country:
                t2 = text; break
        if "Việt Nam" in target_country or "VN" in target_country: t2 = "XEM NGAY"
        
        # 3. Màu Brand
        brand_color = proj.get("channel_profile", {}).get("visual_identity", {}).get("color_palette", "#FF0000")
        brand_mood = proj.get("channel_profile", {}).get("brand_identity", {}).get("mood", "Cinematic")

        # 4. Gọi Composer để ghép
        composer = ThumbnailComposer()
        import uuid
        out_name = f"final_thumb_{layout_mode}_{uuid.uuid4().hex[:4]}.png"
        out_path = os.path.join(self.thumb_temp_dir, out_name)
        
        success, final_path = composer.create_thumbnail(
            bg_path=raw_path,
            text_primary=t1,
            text_secondary=t2,
            output_path=out_path,
            brand_color=brand_color,
            mood=brand_mood,
            layout_mode=layout_mode,
            sticker_path=sticker,
            topic=topic
        )
        
        if success:
            self.thumb_candidates.append(final_path)
            self.current_thumb_idx = len(self.thumb_candidates) - 1
            # Hàm này đã được cài Auto-Save ở bước trước
            self.update_thumb_preview_ui()
        else:
            # [CTO FIX] NẾU LỖI GHÉP LỚP, PHẢI HIỆN RA LOG ĐỂ BIẾT!
            self.log(f"❌ Lỗi Composer: {final_path}")

    # --- [NEW] LOGIC XÓA THUMBNAIL TẠI LUỒNG ---
    def action_delete_current_thumb(self):
        """Xóa ảnh Thumbnail đang hiển thị trên màn hình"""
        if not self.thumb_candidates: 
            return # Không có ảnh nào để xóa
            
        curr_idx = self.current_thumb_idx
        curr_path = self.thumb_candidates[curr_idx]
        
        # 1. Xóa file vật lý khỏi ổ cứng (thư mục thumb_candidates)
        try:
            if os.path.exists(curr_path):
                os.remove(curr_path)
        except Exception as e:
            self.log(f"⚠️ Không thể xóa file vật lý: {e}")
            
        # 2. Xóa khỏi danh sách bộ nhớ của Tool
        self.thumb_candidates.pop(curr_idx)
        
        # 3. Cập nhật lại UI
        if not self.thumb_candidates:
            # Đã xóa hết sạch
            self.current_thumb_idx = 0
            self.update_thumb_preview_ui() # Hàm này sẽ tự reset về "NO PREVIEW"
            
            # Hủy đèn báo xanh vì không còn Thumbnail nào
            row = self.current_task.get('row_index', -1)
            if row >= 0: 
                item = QTableWidgetItem("❌")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table_mon.setItem(row, 5, item)
            self.check_files_status()
        else:
            # Nếu vẫn còn ảnh khác, lùi index lại cho khỏi lỗi "Out of range"
            if self.current_thumb_idx >= len(self.thumb_candidates):
                self.current_thumb_idx = len(self.thumb_candidates) - 1
            self.update_thumb_preview_ui()
            
        self.log_signal.emit("🗑️ Đã xóa 1 phương án Thumbnail.")

    # =========================================================================
    # [NEW] PRO AUDIO: Vocal Strip Logic
    # =========================================================================

    def action_strip_vocal(self):
        """Gọi Demucs Worker để tách âm"""
        if not self.current_task:
            return QMessageBox.warning(self, "Chưa chọn", "Vui lòng chọn 1 Video trước!")
            
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Chọn file âm thanh/video để tách lời", "", "Audio/Video (*.mp3 *.wav *.mp4 *.mkv)"
        )
        
        if not file_path: return
        
        pj_path = self.current_task.get("pj_path", "")
        out_dir = os.path.join(pj_path, "audio_pro")
        os.makedirs(out_dir, exist_ok=True)
        
        from modules.render.pro_workers import AudioSeparatorWorker
        
        self.btn_strip_vocal.setEnabled(False)
        self.btn_strip_vocal.setText("⏳ Đang tách âm...")
        self.log_signal.emit(f"🧠 Đang tách lời từ: {os.path.basename(file_path)}")
        
        self.sep_worker = AudioSeparatorWorker(file_path, out_dir)
        self.sep_worker.progress_signal.connect(self.log_signal.emit)
        self.sep_worker.finished_signal.connect(self.on_strip_vocal_done)
        self.sep_worker.start()

    def on_strip_vocal_done(self, success, msg, results):
        self.btn_strip_vocal.setEnabled(True)
        self.btn_strip_vocal.setText("🎙️ TÁCH LỜI (STRIP VOCAL)")
        
        if success:
            self.log_signal.emit(f"✅ {msg}")
            vocal = results.get("vocals")
            no_vocal = results.get("no_vocals")
            QMessageBox.information(self, "Xong", f"Đã tách âm thành công!\n\nVocals: {vocal}\nBGM: {no_vocal}")
            # Mở thư mục kết quả
            os.startfile(os.path.dirname(vocal))
        else:
            self.log_signal.emit(f"❌ {msg}")
            QMessageBox.critical(self, "Lỗi", msg)

    # =========================================================================
    # [NEW] AGENTIC QA: AI Self-Evaluation Logic
    # =========================================================================

    def action_ai_qa(self):
        """Kiểm định chất lượng video bằng AI (Vision-based)"""
        if not self.current_task:
            return QMessageBox.warning(self, "Chưa chọn", "Vui lòng chọn 1 Video trước!")
            
        pj_path = self.current_task.get("pj_path", "")
        # Tìm file video đã render
        video_path = os.path.join(pj_path, "final_video.mp4")
        if not os.path.exists(video_path):
            # Thử tìm file batch
            t_id = self.current_task.get("id", "")
            video_path = os.path.join(pj_path, f"batch_{t_id}_final.mp4")

        if not os.path.exists(video_path):
            return QMessageBox.warning(self, "Thiếu file", "Chưa thấy video render. Hãy Render Video trước!")

        summary_path = video_path.replace(".mp4", "_summary.png")
        
        # Nếu chưa có ảnh summary, tạo ngay
        if not os.path.exists(summary_path):
            self.log_signal.emit("📊 Đang khởi tạo Timeline Summary cho AI...")
            self.render_service.generate_production_summary(video_path, summary_path)
            
        if not os.path.exists(summary_path):
            return QMessageBox.critical(self, "Lỗi", "Không thể tạo ảnh tóm tắt video để kiểm định.")

        self.log_signal.emit("🔍 Đang gửi dữ liệu cho AI QA (Kiểm định viên)...")
        self.btn_ai_qa.setEnabled(False)
        self.btn_ai_qa.setText("⏳ AI đang kiểm định...")

        # Chạy QA trong Thread để không treo UI
        class QAWorker(QThread):
            result_signal = pyqtSignal(bool, str)
            def __init__(self, ai_factory, img_path):
                super().__init__()
                self.ai = ai_factory
                self.img = img_path
            def run(self):
                prompt = (
                    "Bạn là chuyên gia kiểm định video (QA Director). Hãy phân tích ảnh Timeline Summary này "
                    "(trên là filmstrip, dưới là waveform). Kiểm tra: \n"
                    "1. Có đoạn nào bị đen hoàn toàn không?\n"
                    "2. Biểu đồ sóng âm (waveform) có bị đứt đoạn (silence) quá dài không?\n"
                    "3. Các khung hình có sự thay đổi logic không?\n"
                    "Trả về nhận xét ngắn gọn và kết luận: ĐẠT hoặc KHÔNG ĐẠT."
                )
                # Dùng Google Gemini (mặc định cho role visual_qa)
                suc, res = self.ai.execute_custom_ai("google", prompt, role="visual_qa", image_path=self.img)
                self.result_signal.emit(suc, res)

        self.qa_worker = QAWorker(self.ai, summary_path)
        self.qa_worker.result_signal.connect(self._on_qa_finished)
        self.qa_worker.start()

    def _on_qa_finished(self, success, result):
        self.btn_ai_qa.setEnabled(True)
        self.btn_ai_qa.setText("🔍 AI QUALITY CHECK")
        if success:
            self.log_signal.emit(f"✅ AI QA DONE: {result}")
            # Hiển thị kết quả
            msg = QMessageBox(self)
            msg.setWindowTitle("AI Quality Assurance Report")
            msg.setText("### KẾT QUẢ KIỂM ĐỊNH AI ###")
            msg.setInformativeText(result)
            msg.setIcon(QMessageBox.Icon.Information)
            msg.exec()
        else:
            self.log_signal.emit(f"❌ AI QA FAILED: {result}")
            QMessageBox.critical(self, "Lỗi QA", f"Không thể thực hiện kiểm định: {result}")
