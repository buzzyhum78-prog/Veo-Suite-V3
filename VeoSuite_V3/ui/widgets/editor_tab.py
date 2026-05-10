import os
import json
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFrame, QSplitter, QScrollArea, QTabWidget, QGridLayout,
    QListWidget, QListWidgetItem, QProgressBar, QMessageBox, 
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QComboBox, QSpinBox, QFileDialog
)
from PyQt6.QtCore import Qt, QSize, QTimer, QUrl, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QIcon, QAction, QColor
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

# Import các service
from services.database_manager import DatabaseManager
from services.render_service import RenderService
from ui.style_kit import apply_kind  # PR-5e: dynamic-property style helpers

# ============================================================================
# 🧱 CLASS: TIMELINE BLOCK (KHỐI CẢNH THÔNG MINH)
# ============================================================================

from modules.render.ui_components import *
from modules.render.workers import *

# ============================================================================
# 🎬 CLASS CHÍNH: EDITOR TAB (PHÒNG DỰNG PHIM)
# ============================================================================
class EditorTab(QWidget):
    log_signal = pyqtSignal(str)
    def __init__(self):
        super().__init__()
        self.db = DatabaseManager()
        self.render_service = RenderService()
        self.current_project_index = -1
        self.current_task_data = None
        
        self.projects = [] # Cache dữ liệu
        
        # UI Setup
        self._build_ui()
        self._apply_styles()
        
        # Load data ban đầu
        self.refresh_project_list()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # --- PHẦN 1: HEADER (Thanh công cụ) ---
        header = QFrame()
        header.setObjectName("editorHeader")  # PR-5e: styled via global QSS
        header.setFixedHeight(50)
        h_layout = QHBoxLayout(header)

        self.lbl_status = QLabel("🎬 EDITOR READY")
        self.lbl_status.setObjectName("sectionTitleLabel")  # PR-5e: cyan section title via global QSS
        self.lbl_status.setStyleSheet("font-size: 14px;")  # PR-5e: only override font-size, colour comes from global

        btn_refresh = QPushButton("📥 NHẬN NGUYÊN LIỆU TỪ MEDIA")
        btn_refresh.setToolTip("Lấy toàn bộ dữ liệu video đã hoàn thành từ Media Factory sang để dựng phim.")
        apply_kind(btn_refresh, "warning")  # PR-5e
        btn_refresh.clicked.connect(self.refresh_project_list)

        btn_send_pub = QPushButton("🚀 CHUYỂN SANG PHÁT HÀNH")
        btn_send_pub.setToolTip("Gửi video đã render xong sang bộ phận Phát hành để Upload.")
        apply_kind(btn_send_pub, "ai_magic")  # PR-5e
        btn_send_pub.clicked.connect(self.action_send_to_publisher)
        
        h_layout.addWidget(self.lbl_status)
        h_layout.addStretch()
        h_layout.addWidget(btn_refresh)
        h_layout.addWidget(btn_send_pub)
        
        main_layout.addWidget(header)
        
        # --- PHẦN 2: CHIA CỘT (LIST KÊNH | WORKSPACE) ---
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Cột Trái: Danh sách Video sẵn sàng dựng
        # Chỉ hiện những video đã có status "Ready" hoặc "Sẵn sàng"
        self.list_ready_tasks = QListWidget()
        self.list_ready_tasks.setFixedWidth(250)
        self.list_ready_tasks.itemClicked.connect(self.on_task_selected)
        splitter.addWidget(self.list_ready_tasks)
        
        # Cột Phải: Không gian làm việc (TAB: STUDIO | BATCH QUEUE)
        self.tabs = QTabWidget()
        
        # >>> TAB 1: STUDIO (Dựng thủ công)
        self.tab_studio = QWidget()
        self._build_studio_ui()
        self.tabs.addTab(self.tab_studio, "🎨 STUDIO (Thủ công)")
        
        # >>> TAB 2: RENDER FACTORY (Chạy hàng loạt)
        self.tab_batch = QWidget()
        self._build_batch_ui()
        self.tabs.addTab(self.tab_batch, "🏭 RENDER QUEUE (Tự động)")
        
        splitter.addWidget(self.tabs)
        splitter.setStretchFactor(1, 1) # Cột phải to hơn
        
        main_layout.addWidget(splitter)

    def _build_studio_ui(self):
        """Giao diện Dựng phim thủ công: Preview + Timeline"""
        layout = QVBoxLayout(self.tab_studio)
        
        # A. KHU VỰC PREVIEW (Trên)
        preview_area = QWidget()
        p_layout = QHBoxLayout(preview_area)
        
        # Player (Trái)
        self.preview_container = QFrame()
        self.preview_container.setObjectName("previewContainer")  # PR-5e: styled via global QSS
        self.preview_container.setMinimumSize(640, 360)
        pc_layout = QVBoxLayout(self.preview_container)
        pc_layout.setContentsMargins(0, 0, 0, 0)
        
        # Màn hình ảnh
        self.video_player_placeholder = QLabel()
        self.video_player_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pc_layout.addWidget(self.video_player_placeholder)
        
        # Lớp phủ Subtitle (Hiện trên ảnh)
        self.lbl_sub_overlay = QLabel("")
        self.lbl_sub_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_sub_overlay.setObjectName("subtitleOverlay")  # PR-5e: styled via global QSS
        self.lbl_sub_overlay.setFixedHeight(60)
        pc_layout.addWidget(self.lbl_sub_overlay, alignment=Qt.AlignmentFlag.AlignBottom)
        
        # Bộ điều khiển âm thanh
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        
        self.btn_play_audio = QPushButton("▶ NGHE THỬ")
        self.btn_play_audio.clicked.connect(self.action_play_preview)
        apply_kind(self.btn_play_audio, "primary")  # PR-5e

        self.btn_stop_audio = QPushButton("⏹ DỪNG")
        self.btn_stop_audio.clicked.connect(lambda: self.media_player.stop())
        apply_kind(self.btn_stop_audio, "danger")  # PR-5e
        
        # Property Panel (Phải) - Chỉnh sửa thông tin Block đang chọn
        prop_panel = QFrame()
        prop_panel.setFixedWidth(300)
        prop_panel.setObjectName("propertyPanel")  # PR-5e: styled via global QSS
        prop_layout = QVBoxLayout(prop_panel)
        prop_layout.addWidget(QLabel("💎 ASSET STATUS"))
        
        self.lbl_asset_voice = QLabel("🎙️ Voice: --")
        self.lbl_asset_music = QLabel("🎵 Music: --")
        self.lbl_asset_sub = QLabel("📝 Subtitle: --")
        self.lbl_asset_thumb = QLabel("🖼️ Thumbnail: --")
        
        for lbl in [self.lbl_asset_voice, self.lbl_asset_music, self.lbl_asset_sub, self.lbl_asset_thumb]:
            prop_layout.addWidget(lbl)
            
        prop_layout.addSpacing(10)
        prop_layout.addWidget(QLabel("📝 SCENE PROPERTIES"))
        
        self.lbl_scene_idx = QLabel("Scene: --")
        from PyQt6.QtWidgets import QTextEdit
        self.txt_scene_content = QTextEdit()
        self.txt_scene_content.setReadOnly(True)
        self.txt_scene_content.setMaximumHeight(80)
        self.txt_scene_content.setPlaceholderText("Kịch bản phân cảnh...")
        
        self.input_duration = QSpinBox(); self.input_duration.setSuffix(" sec")
        self.input_duration.setRange(1, 60) # Cho phép từ 1s đến 60s
        self.btn_change_img = QPushButton("🖼️ Thay ảnh khác")
        self.btn_change_img.clicked.connect(self.action_change_image)
        self.current_selected_block_index = -1
        self.current_selected_img_path = ""
        
        prop_layout.addWidget(self.lbl_scene_idx)
        prop_layout.addWidget(self.txt_scene_content)
        prop_layout.addWidget(QLabel("Thời lượng:"))
        prop_layout.addWidget(self.input_duration)
        prop_layout.addWidget(self.btn_change_img)
        prop_layout.addStretch()
        
        # Nút Render Video này
        self.btn_render_single = QPushButton("🚀 RENDER VIDEO NÀY")
        self.btn_render_single.setToolTip("BƯỚC 4: Kết hợp Voice + Hình ảnh + Nhạc + Sub thành video hoàn chỉnh.")
        apply_kind(self.btn_render_single, "warning")  # PR-5e
        self.btn_render_single.setMinimumHeight(40)
        self.btn_render_single.clicked.connect(self.action_render_single)
        prop_layout.addWidget(self.btn_render_single)

        self.btn_stop_render = QPushButton("🛑 DỪNG RENDER")
        apply_kind(self.btn_stop_render, "danger")  # PR-5e
        self.btn_stop_render.setMinimumHeight(35)
        self.btn_stop_render.clicked.connect(self.action_stop_render)
        self.btn_stop_render.setEnabled(False)
        prop_layout.addWidget(self.btn_stop_render)
        
        p_layout.addWidget(self.preview_container, stretch=3)
        p_layout.addWidget(prop_panel, stretch=1)
        
        # Thêm nút play/stop vào dưới preview container
        audio_btns = QHBoxLayout()
        audio_btns.addWidget(self.btn_play_audio)
        audio_btns.addWidget(self.btn_stop_audio)
        layout.addLayout(audio_btns)
        
        layout.addWidget(preview_area, stretch=2)
        
        # B. TIMELINE AREA (Dưới)
        lbl_tm = QLabel("🎞️ SMART TIMELINE (Kéo sang phải để xem hết)")
        lbl_tm.setObjectName("timelineLabel")  # PR-5e: bold caption via global QSS
        layout.addWidget(lbl_tm)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(180) # Chiều cao cố định cho timeline
        scroll.setObjectName("timelineScroll")  # PR-5e: dark background via global QSS
        
        self.timeline_container = QWidget()
        self.timeline_layout = QHBoxLayout(self.timeline_container)
        self.timeline_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.timeline_layout.setSpacing(10)
        
        scroll.setWidget(self.timeline_container)
        layout.addWidget(scroll, stretch=1)

    def _build_batch_ui(self):
        """Giao diện chạy hàng loạt"""
        layout = QVBoxLayout(self.tab_batch)
        
        # Toolbar
        toolbar = QHBoxLayout()
        self.btn_scan_ready = QPushButton("🔍 Quét bài Sẵn sàng")
        self.btn_scan_ready.clicked.connect(self.scan_ready_tasks)
        
        self.btn_start_batch = QPushButton("▶ CHẠY RENDER ALL")
        self.btn_start_batch.setToolTip("BƯỚC 4: Tự động render hàng loạt tất cả các video đang chờ trong danh sách.")
        apply_kind(self.btn_start_batch, "success")  # PR-5e
        self.btn_start_batch.clicked.connect(self.action_batch_render)

        self.btn_stop_batch = QPushButton("🛑 STOP BATCH")
        apply_kind(self.btn_stop_batch, "danger")  # PR-5e
        self.btn_stop_batch.clicked.connect(self.action_stop_batch)
        self.btn_stop_batch.setEnabled(False)
        
        toolbar.addWidget(self.btn_scan_ready)
        toolbar.addStretch()
        toolbar.addWidget(self.btn_start_batch)
        toolbar.addWidget(self.btn_stop_batch)
        layout.addLayout(toolbar)
        
        # Table Queue
        self.table_queue = QTableWidget(0, 4)
        self.table_queue.setHorizontalHeaderLabels(["ID", "Dự án", "Tiêu đề Video", "Trạng thái Render"])
        self.table_queue.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table_queue)
        
        # Log
        self.txt_batch_log = QLabel("Trạng thái: Đang chờ lệnh...")
        layout.addWidget(self.txt_batch_log)

    def _apply_styles(self):
        # PR-5e: previously injected a local stylesheet that duplicated (and
        # diverged from) the global DARK_THEME_STYLESHEET applied at app start.
        # The global theme now owns QListWidget / QPushButton / QTabWidget /
        # QTabBar styling for every tab, so this method is intentionally a
        # no-op. Kept as a hook for future Editor-specific tweaks.
        return None

    # ========================================================================
    # 🧠 LOGIC XỬ LÝ DỮ LIỆU
    # ========================================================================
    def refresh_project_list(self):
        """Load danh sách các Video có trạng thái 'Sẵn sàng dựng'"""
        self.list_ready_tasks.clear()
        self.projects = self.db.load_projects() # Reload từ DB
        self.log_signal.emit(f"📥 Đã tải {len(self.projects)} dự án từ Database.")
        
        for p_idx, proj in enumerate(self.projects):
            tasks = proj.get("tasks", [])
            for t in tasks:
                # Điều kiện vào phòng dựng:
                # 1. Có file voice.mp3
                # 2. Có folder visuals và có ảnh bên trong
                # 3. Status có chữ "Ready", "Sẵn sàng" hoặc "Xong"
                path = t.get("output_path", "")
                if not path or not os.path.exists(path): continue
                
                has_voice = os.path.exists(os.path.join(path, "voice.mp3"))
                vis_path = os.path.join(path, "visuals")
                has_visuals = os.path.exists(vis_path) and len(os.listdir(vis_path)) > 0
                
                # Check status text (Optional, nhưng nên có để lọc rác)
                st_text = t.get("status", "")
                is_ready_flag = "Ready" in st_text or "Sẵn sàng" in st_text or "Xong" in st_text
                
                if has_voice and has_visuals:
                    item_text = f"[{proj['name']}] {t.get('key_vua', 'No Title')}"
                    item = QListWidgetItem(item_text)
                    
                    # Lưu data vào item để truy xuất nhanh
                    item_data = {
                        "p_idx": p_idx,
                        "task_id": t["id"],
                        "path": path,
                        "title": t.get("key_vua")
                    }
                    item.setData(Qt.ItemDataRole.UserRole, item_data)
                    
                    if is_ready_flag:
                        item.setIcon(QIcon("icons/video_ready.png")) # Nếu có icon
                        item.setForeground(QColor("#2ecc71")) # Xanh lá
                    else:
                        item.setForeground(QColor("#f1c40f")) # Vàng (đủ file nhưng chưa tick ready)
                        
                    self.list_ready_tasks.addItem(item)

    def on_task_selected(self, item):
        """Khi chọn 1 video -> Load vào Studio"""
        data = item.data(Qt.ItemDataRole.UserRole)
        self.current_task_data = data
        path = data["path"]
        
        self.lbl_status.setText(f"🎬 ĐANG DỰNG: {data['title']}")
        
        # 1. Load Voice Duration
        voice_path = os.path.join(path, "voice.mp3")
        duration = self.render_service.get_audio_duration(voice_path)
        
        # 2. Load Visuals
        vis_dir = os.path.join(path, "visuals")
        if not os.path.exists(vis_dir): return
        
        images = sorted([os.path.join(vis_dir, f) for f in os.listdir(vis_dir) 
                         if f.lower().endswith(('.jpg', '.png'))])
        
        if not images: return
        
        # 3. Load kịch bản và Metadata (Sợi chỉ đỏ)
        self.current_scenes_text = []
        v_file = os.path.join(path, "voice.txt")
        if os.path.exists(v_file):
            try:
                with open(v_file, "r", encoding="utf-8") as f:
                    self.current_scenes_text = [line.strip() for line in f.readlines() if line.strip()]
            except: pass
            
        m_file = os.path.join(path, "meta.json")
        if os.path.exists(m_file):
            try:
                with open(m_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                    for k, v in meta.items(): self.current_task_data[k] = v
                self.lbl_status.setText(f"🎬 ĐANG DỰNG: {self.current_task_data.get('title', data['title'])}")
            except: pass
        
        # 4. Tính toán Timeline Blocks
        # Logic: Chia đều thời gian (như trong render_service)
        per_img_time = duration / len(images)
        
        # 4. Vẽ lên Timeline UI
        self.clear_timeline()
        
        for i, img in enumerate(images):
            block = TimelineBlock(i, img, per_img_time, self.on_block_clicked)
            self.timeline_layout.addWidget(block)
            
        # 5. Load Preview (Ảnh đầu tiên)
        self.video_player_placeholder.setPixmap(
            QPixmap(images[0]).scaled(640, 360, Qt.AspectRatioMode.KeepAspectRatio)
        )
        if self.current_scenes_text:
             self.lbl_sub_overlay.setText(self.current_scenes_text[0])
        
        # 6. Kiểm tra các nguyên liệu đi kèm
        self._check_asset_status(path)
        
        # 7. Stop bất kỳ âm thanh nào đang chạy
        self.media_player.stop()

    def action_play_preview(self):
        """Nghe thử âm thanh (Voice) trước khi render"""
        if not self.current_task_data: return
        
        voice_path = os.path.join(self.current_task_data["path"], "voice.mp3")
        if os.path.exists(voice_path):
            self.media_player.setSource(QUrl.fromLocalFile(os.path.abspath(voice_path)))
            self.audio_output.setVolume(1.0)
            self.media_player.play()
            self.lbl_status.setText("🔊 Đang phát Voice...")
        else:
            QMessageBox.warning(self, "Thiếu file", "Không tìm thấy file voice.mp3 để nghe thử!")

    def _check_asset_status(self, path):
        """Quét thư mục và cập nhật đèn báo nguyên liệu"""
        voice_ok = os.path.exists(os.path.join(path, "voice.mp3"))
        music_ok = os.path.exists(os.path.join(path, "background.mp3"))
        sub_ok = os.path.exists(os.path.join(path, "voice.srt"))
        # Check thumbnail: có thể là thumbnail.png hoặc final_thumb...
        thumb_ok = os.path.exists(os.path.join(path, "thumbnail.png")) or \
                   (os.path.exists(os.path.join(path, "thumb_candidates")) and len(os.listdir(os.path.join(path, "thumb_candidates"))) > 0)
        
        self.lbl_asset_voice.setText(f"🎙️ Voice: {'✅ OK' if voice_ok else '❌ Trống'}")
        self.lbl_asset_voice.setStyleSheet(f"color: {'#2ecc71' if voice_ok else '#e74c3c'}")
        
        self.lbl_asset_music.setText(f"🎵 Music: {'✅ OK' if music_ok else '❌ Trống'}")
        self.lbl_asset_music.setStyleSheet(f"color: {'#2ecc71' if music_ok else '#e74c3c'}")
        
        self.lbl_asset_sub.setText(f"📝 Subtitle: {'✅ OK' if sub_ok else '❌ Trống'}")
        self.lbl_asset_sub.setStyleSheet(f"color: {'#2ecc71' if sub_ok else '#e74c3c'}")
        
        self.lbl_asset_thumb.setText(f"🖼️ Thumbnail: {'✅ OK' if thumb_ok else '❌ Trống'}")
        self.lbl_asset_thumb.setStyleSheet(f"color: {'#2ecc71' if thumb_ok else '#e74c3c'}")

    def clear_timeline(self):
        # Xóa các widget cũ trong layout
        while self.timeline_layout.count():
            child = self.timeline_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def on_block_clicked(self, index, img_path):
        """Khi click vào 1 block"""
        self.current_selected_block_index = index
        self.current_selected_img_path = img_path
        self.lbl_scene_idx.setText(f"Scene: {index+1}")
        
        # Hiển thị nội dung kịch bản của scene đó
        content = ""
        if hasattr(self, 'current_scenes_text') and index < len(self.current_scenes_text):
            content = self.current_scenes_text[index]
            self.txt_scene_content.setText(content)
            self.lbl_sub_overlay.setText(content) # Hiện lên màn hình preview
        else:
            self.txt_scene_content.setText("-- Không có nội dung --")
            self.lbl_sub_overlay.setText("")
            
        # Hiện ảnh đó lên màn hình preview
        self.video_player_placeholder.setPixmap(
            QPixmap(img_path).scaled(640, 360, Qt.AspectRatioMode.KeepAspectRatio)
        )
        
        # Lấy giá trị thời lượng hiện tại của block (nếu TimelineBlock có hàm get_duration)
        # Giả định block chia đều, ta set tạm vào ô input
        block_widget = self.timeline_layout.itemAt(index).widget()
        if hasattr(block_widget, 'duration'):
            self.input_duration.setValue(int(block_widget.duration))
        
    def action_change_image(self):
        """Cho phép người dùng tải lên ảnh khác đè vào Scene hiện tại"""
        if self.current_selected_block_index == -1 or not self.current_selected_img_path:
            QMessageBox.warning(self, "Lỗi", "Vui lòng chọn một Scene (ảnh) trên Timeline trước!")
            return
            
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Chọn ảnh thay thế", "", "Images (*.png *.jpg *.jpeg)"
        )
        
        if file_path:
            import shutil
            try:
                # Copy đè file mới vào file cũ
                shutil.copy2(file_path, self.current_selected_img_path)
                
                # Cập nhật lại UI Preview
                self.video_player_placeholder.setPixmap(
                    QPixmap(self.current_selected_img_path).scaled(640, 360, Qt.AspectRatioMode.KeepAspectRatio)
                )
                
                # Cập nhật lại icon trên Timeline
                block_widget = self.timeline_layout.itemAt(self.current_selected_block_index).widget()
                if hasattr(block_widget, 'update_image'):
                    block_widget.update_image(self.current_selected_img_path)
                    
                QMessageBox.information(self, "Thành công", "Đã thay đổi ảnh cho Scene này!")
            except Exception as e:
                QMessageBox.critical(self, "Lỗi Copy File", str(e))

    # ========================================================================
    # 🚀 ACTION RENDER
    # ========================================================================
    def action_stop_render(self):
        """Dừng render đơn lẻ đang chạy"""
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.stop()
            self.lbl_status.setText("🛑 Đã dừng render.")
        self.btn_render_single.setEnabled(True)
        self.btn_render_single.setText("🚀 RENDER VIDEO NÀY")
        self.btn_stop_render.setEnabled(False)

    def action_render_single(self):
        """Render 1 video đang chọn ở Studio"""
        if not self.current_task_data:
            QMessageBox.warning(self, "Chưa chọn", "Vui lòng chọn video bên trái!")
            return
            
        path = self.current_task_data["path"]
        output_file = os.path.join(path, "final_video.mp4")
        
        self.btn_render_single.setEnabled(False)
        self.btn_render_single.setText("⏳ Đang render...")
        self.btn_stop_render.setEnabled(True)
        
        # Thu thập Metadata để đóng gói
        metadata = {
            "title": self.current_task_data.get("title", ""),
            "description": self.current_task_data.get("description", ""),
            "tags": self.current_task_data.get("tags", ""),
            "topic": self.current_task_data.get("topic", ""),
            "country": self.current_task_data.get("country", ""),
            "channel": self.current_task_data.get("channel", "Default"),
            "render_date": os.path.getmtime(path)
        }
        
        # Gọi Worker
        self.worker = EditorRenderWorker(self.render_service, path, output_file, metadata=metadata)
        self.worker.finished_signal.connect(self.on_render_single_done)
        self.worker.start()
        
    def on_render_single_done(self, success, msg, out_path):
        self.btn_render_single.setEnabled(True)
        self.btn_render_single.setText("🚀 RENDER VIDEO NÀY")
        self.btn_stop_render.setEnabled(False)
        
        if success:
            # 1. Tạo production_package.json
            import json
            folder = os.path.dirname(os.path.abspath(out_path))
            pkg_path = os.path.join(folder, "production_package.json")
            with open(pkg_path, "w", encoding="utf-8") as f:
                json.dump(self.worker.metadata, f, ensure_ascii=False, indent=4)
                
            # 2. Update DB status
            p_id = self.current_task_data.get("p_idx")
            t_id = self.current_task_data.get("id")
            if p_id is not None and t_id is not None:
                self.db.update_task_status(p_id, t_id, "Chờ phát hành")
                
            QMessageBox.information(self, "Xong", f"Video đã ra lò:\n{out_path}\nĐã đóng gói siêu dữ liệu để phát hành!")
            os.startfile(folder)
        else:
            QMessageBox.critical(self, "Lỗi Render", msg)

    def action_send_to_publisher(self):
        QMessageBox.information(self, "Chuyển kho", "Đã chốt thành phẩm! Vui lòng qua Tab Phát Hành và bấm 'Quét Nguồn/Nhận Video'.")

    # ========================================================================
    # 🏭 BATCH QUEUE LOGIC
    # ========================================================================
    def scan_ready_tasks(self):
        """Quét toàn bộ DB lấy các bài sẵn sàng đưa vào Queue"""
        self.table_queue.setRowCount(0)
        row = 0
        
        # Lấy data từ list_ready_tasks (vì nó đã lọc sẵn rồi)
        for i in range(self.list_ready_tasks.count()):
            item = self.list_ready_tasks.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            
            self.table_queue.insertRow(row)
            self.table_queue.setItem(row, 0, QTableWidgetItem(str(data["task_id"])))
            
            # Tên dự án (Lấy lại từ DB cho chắc)
            p_name = self.projects[data["p_idx"]]["name"]
            self.table_queue.setItem(row, 1, QTableWidgetItem(p_name))
            
            self.table_queue.setItem(row, 2, QTableWidgetItem(data["title"]))
            self.table_queue.setItem(row, 3, QTableWidgetItem("Sẵn sàng"))
            
            # Lưu path vào item ẩn
            self.table_queue.item(row, 0).setData(Qt.ItemDataRole.UserRole, data["path"])
            
            row += 1
            
        self.txt_batch_log.setText(f"Tìm thấy {row} video sẵn sàng render.")

    def action_batch_render(self):
        """Chạy render lần lượt từ trên xuống"""
        count = self.table_queue.rowCount()
        if count == 0: return
        
        self.batch_queue_paths = []
        for i in range(count):
            path = self.table_queue.item(i, 0).data(Qt.ItemDataRole.UserRole)
            self.batch_queue_paths.append((i, path)) # Lưu index dòng và đường dẫn
            
        self.is_batch_running = True
        self.btn_start_batch.setEnabled(False)
        self.btn_stop_batch.setEnabled(True)
        
        self.process_next_batch_item()

    def action_stop_batch(self):
        """Dừng khẩn cấp hàng đợi"""
        self.is_batch_running = False
        if hasattr(self, 'batch_worker'):
            self.batch_worker.stop()
        self.btn_start_batch.setEnabled(True)
        self.btn_stop_batch.setEnabled(False)
        self.txt_batch_log.setText("⚠️ HÀNG ĐỢI ĐÃ BỊ DỪNG BỞI NGƯỜI DÙNG.")
        
    def process_next_batch_item(self):
        if not self.batch_queue_paths:
            self.is_batch_running = False
            self.btn_start_batch.setEnabled(True)
            QMessageBox.information(self, "Xong", "Đã render xong toàn bộ hàng đợi!")
            return
            
        # Lấy item tiếp theo
        row_idx, path = self.batch_queue_paths.pop(0)
        
        # Update UI
        self.table_queue.setItem(row_idx, 3, QTableWidgetItem("⏳ Đang render..."))
        self.table_queue.scrollToItem(self.table_queue.item(row_idx, 0))
        
        # Tên file phải có _final để PublisherTab nhận diện được
        t_id = self.table_queue.item(row_idx, 0).text()
        output_file = os.path.join(path, f"batch_{t_id}_final.mp4")
        
        # Tạo metadata cho batch item
        import time
        metadata = {
            "title": self.table_queue.item(row_idx, 2).text(),
            "description": "Video rendered by Batch Processor",
            "tags": ["shorts", "batch"],
            "channel": self.table_queue.item(row_idx, 1).text(),
            "render_date": time.time()
        }
        
        # Gọi Worker (giữ tham chiếu self.batch_worker)
        self.batch_worker = EditorRenderWorker(self.render_service, path, output_file, metadata=metadata)
        # Dùng lambda để truyền row_idx và metadata vào callback
        self.batch_worker.finished_signal.connect(lambda s, m, o: self.on_batch_item_done(s, m, o, row_idx, metadata))
        self.batch_worker.start()
        
    def on_batch_item_done(self, success, msg, out_path, row_idx, metadata):
        if success:
            self.table_queue.setItem(row_idx, 3, QTableWidgetItem("✅ Xong"))
            # Tạo production_package.json
            import json
            folder = os.path.dirname(os.path.abspath(out_path))
            pkg_path = os.path.join(folder, "production_package.json")
            with open(pkg_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, ensure_ascii=False, indent=4)
        else:
            self.table_queue.setItem(row_idx, 3, QTableWidgetItem("❌ Lỗi"))
            
        # Chạy cái tiếp theo sau 1s
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(1000, self.process_next_batch_item)
