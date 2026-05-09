import os
import json
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, 
    QTabWidget, QMessageBox, QGroupBox, QFormLayout, QLineEdit, 
    QTextEdit, QComboBox, QDateTimeEdit, QCheckBox, QScrollArea,
    QFrame, QSplitter, QDialog, QDialogButtonBox
)
from PyQt6.QtCore import Qt, QDateTime, pyqtSignal
from PyQt6.QtGui import QFont, QColor

# NOTE: OpsTab is intentionally NOT imported here. The Ops Center belongs to
# the AdminTab (Quản Trị) sub-tab tree (`ui/admin_tab.py:setup_ops_tab` adds
# `OpsTab()` as the "🛡️ An Ninh & VPS" sub-tab). Re-introducing it inside
# PublisherTab causes the same widget to render twice with two competing
# inline stylesheets, which the user perceives as the app "jumping into
# another UI" when navigating between Phát Hành and Quản Trị. See PR-5b1.
from modules.publisher.account_manager import PublisherAccountManager
from modules.publisher.platforms import AVAILABLE_PLATFORMS, get_platform_instance
from modules.publisher.constants import get_next_golden_hour

class AddAccountDialog(QDialog):
    """Cửa sổ Popup thêm tài khoản API mới"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Thêm Tài Khoản Nền Tảng Mới")
        self.setMinimumWidth(400)
        self.layout = QVBoxLayout(self)
        
        # Form chọn nền tảng
        self.form = QFormLayout()
        
        self.cb_platform = QComboBox()
        self.cb_platform.addItems(list(AVAILABLE_PLATFORMS.keys()))
        self.cb_platform.currentTextChanged.connect(self.on_platform_changed)
        self.form.addRow("Chọn Nền Tảng:", self.cb_platform)
        
        self.txt_account_name = QLineEdit()
        self.txt_account_name.setPlaceholderText("VD: Kênh Keto US")
        self.form.addRow("Tên Nhận Diện:", self.txt_account_name)
        
        # Container chứa các trường nhập (thay đổi linh hoạt theo nền tảng)
        self.dynamic_fields_container = QWidget()
        self.dynamic_form = QFormLayout(self.dynamic_fields_container)
        self.form.addRow(self.dynamic_fields_container)
        
        self.layout.addLayout(self.form)
        
        # Nút Save/Cancel
        self.btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.btns.accepted.connect(self.accept)
        self.btns.rejected.connect(self.reject)
        self.layout.addWidget(self.btns)
        
        # Init giao diện lần đầu
        self.field_inputs = {}
        self.on_platform_changed(self.cb_platform.currentText())

    def clear_dynamic_fields(self):
        for i in reversed(range(self.dynamic_form.count())): 
            widget_to_remove = self.dynamic_form.itemAt(i).widget()
            if widget_to_remove:
                widget_to_remove.setParent(None)
        self.field_inputs.clear()

    def on_platform_changed(self, platform_name):
        self.clear_dynamic_fields()
        
        if platform_name == "YouTube":
            lbl = QLabel(
                "<b>📌 HƯỚNG DẪN CÀI ĐẶT YOUTUBE API:</b><br><br>"
                "1. Truy cập <b>Google Cloud Console</b> (console.cloud.google.com) và tạo một Project mới.<br>"
                "2. Kích hoạt <b>YouTube Data API v3</b> trong thư viện API.<br>"
                "3. Thiết lập <b>OAuth consent screen</b> (Chọn External, thêm test user nếu cần).<br>"
                "4. Vào Credentials > Tạo <b>OAuth client ID</b> (Chọn Desktop app).<br>"
                "5. Tải file JSON về, đổi tên thành <b>client_secret.json</b> và copy vào thư mục:<br>"
                "   <i style='color:#e74c3c;'>VEO_DB/credentials/youtube/</i><br><br>"
                "<i>*Không cần nhập Token ở đây. Sau khi lưu, ở lần Upload đầu tiên, phần mềm sẽ mở trình duyệt để bạn xác thực tài khoản.</i>"
            )
            lbl.setWordWrap(True)
            lbl.setStyleSheet("background: #2c3e50; padding: 10px; border-radius: 5px;")
            self.dynamic_form.addRow(lbl)
            
        elif platform_name == "Facebook Reels":
            lbl = QLabel(
                "<b>📌 HƯỚNG DẪN LẤY TOKEN FACEBOOK:</b><br>"
                "Vào <b>developers.facebook.com</b> > Tạo App > Graph API Explorer.<br>"
                "Tạo 'Page Access Token' (Loại Never Expire) với các quyền: <i>pages_show_list, pages_read_engagement, pages_manage_posts</i>."
            )
            lbl.setWordWrap(True)
            self.dynamic_form.addRow(lbl)
            self.field_inputs['page_id'] = QLineEdit()
            self.dynamic_form.addRow("Page ID:", self.field_inputs['page_id'])
            self.field_inputs['access_token'] = QLineEdit()
            self.dynamic_form.addRow("Page Access Token:", self.field_inputs['access_token'])
            
        elif platform_name == "Instagram":
            lbl = QLabel(
                "<b>📌 HƯỚNG DẪN LẤY IG USER ID:</b><br>"
                "Instagram của bạn phải là tài khoản <b>Business</b> hoặc <b>Creator</b> và đã liên kết với Fanpage Facebook.<br>"
                "Dùng Graph API để lấy IG User ID thông qua Fanpage."
            )
            lbl.setWordWrap(True)
            self.dynamic_form.addRow(lbl)
            self.field_inputs['ig_user_id'] = QLineEdit()
            self.dynamic_form.addRow("IG User ID:", self.field_inputs['ig_user_id'])
            self.field_inputs['access_token'] = QLineEdit()
            self.dynamic_form.addRow("Page Access Token:", self.field_inputs['access_token'])
            
        elif platform_name == "TikTok":
            lbl = QLabel(
                "<b>📌 HƯỚNG DẪN LẤY SESSION ID:</b><br>"
                "1. Đăng nhập TikTok trên trình duyệt Web.<br>"
                "2. Nhấn <b>F12</b> > Chọn tab <b>Application</b> (hoặc Storage).<br>"
                "3. Trong mục Cookies, tìm khóa có tên <b>sessionid</b> và copy giá trị dán vào đây."
            )
            lbl.setWordWrap(True)
            self.dynamic_form.addRow(lbl)
            self.field_inputs['session_id'] = QLineEdit()
            self.dynamic_form.addRow("Session ID (Cookie):", self.field_inputs['session_id'])

    def get_data(self):
        platform = self.cb_platform.currentText()
        account_name = self.txt_account_name.text().strip()
        credentials = {key: inp.text().strip() for key, inp in self.field_inputs.items()}
        return platform, account_name, credentials


class PublisherTab(QWidget):
    """Trung tâm Phát hành & Tự động hóa Đa nền tảng"""
    log_signal = pyqtSignal(str)
    def __init__(self):
        super().__init__()
        self.acc_manager = PublisherAccountManager()
        self._build_ui()
        self.refresh_accounts_data()
        
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # --- Header ---
        header = QHBoxLayout()
        lbl_title = QLabel("📡 TRUNG TÂM PHÁT HÀNH & TỰ ĐỘNG HÓA")
        lbl_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #00e6e6; padding: 5px;")
        header.addWidget(lbl_title)
        
        btn_refresh = QPushButton("🔄 Làm Mới Trạng Thái API")
        btn_refresh.setFixedWidth(180)
        btn_refresh.clicked.connect(self.refresh_accounts_data)
        header.addWidget(btn_refresh)
        
        btn_import = QPushButton("📥 NHẬP TỪ PHÒNG DỰNG (AUTO)")
        btn_import.setStyleSheet("background: #8e44ad; color: white; font-weight: bold;")
        btn_import.clicked.connect(self.action_scan_production)
        header.addWidget(btn_import)
        
        layout.addLayout(header)
        
        # --- Main Tabs ---
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabBar::tab { padding: 10px 20px; font-weight: bold; }
            QTabBar::tab:selected { background-color: #2980b9; color: white; }
        """)
        
        self.tabs.addTab(self._build_account_tab(), "🔑 Quản Lý Tài Khoản (API)")
        self.tabs.addTab(self._build_upload_config_tab(), "⚙️ Cấu Hình Phát Hành")
        self.tabs.addTab(self._build_scheduler_tab(), "📅 Hàng Đợi & Lên Lịch")

        # OpsTab is provided by AdminTab (Quản Trị → "🛡️ An Ninh & VPS"). It is
        # intentionally NOT instantiated here — see import block above and PR-5b1.
        layout.addWidget(self.tabs)

    def _build_account_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        
        lbl_info = QLabel("Quản lý khóa API, OAuth2 và Session Cookie cho các nền tảng. Hệ thống hỗ trợ đa tài khoản (Multilogin).")
        lbl_info.setWordWrap(True)
        layout.addWidget(lbl_info)
        
        self.table_accounts = QTableWidget(0, 5)
        self.table_accounts.setHorizontalHeaderLabels(["Nền tảng", "Tên Kênh / Profile", "Trạng thái Liên kết", "Phương thức", "Hành động"])
        self.table_accounts.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_accounts.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table_accounts)
        
        btn_add_account = QPushButton("➕ Thêm Tài Khoản Nền Tảng Mới")
        btn_add_account.setStyleSheet("background: #27ae60; color: white; padding: 8px; font-weight: bold;")
        btn_add_account.clicked.connect(self._open_add_account_dialog)
        layout.addWidget(btn_add_account)
        
        return w

    def _open_add_account_dialog(self):
        dialog = AddAccountDialog(self)
        if dialog.exec():
            platform, name, credentials = dialog.get_data()
            if not name:
                QMessageBox.warning(self, "Lỗi", "Vui lòng điền tên nhận diện kênh!")
                return
            self.acc_manager.add_account(platform, name, credentials)
            self.refresh_accounts_data()
            QMessageBox.information(self, "Thành công", f"Đã lưu thông tin tài khoản: {name}")

    def refresh_accounts_data(self):
        """Đọc từ JSON DB và nạp lên Bảng & Combobox"""
        accounts = self.acc_manager.load_accounts()
        
        # 1. Update Table
        self.table_accounts.setRowCount(len(accounts))
        for i, acc in enumerate(accounts):
            plat_name = acc.get("platform")
            plat_instance = get_platform_instance(plat_name)
            
            # Giao tiếp với Plugin để check status (Hoặc báo fake status nếu plugin chưa code check live)
            status_text = plat_instance.get_status() if plat_instance else acc.get("status", "Unknown")
            auth_method = plat_instance.auth_method if plat_instance else "Unknown"

            self.table_accounts.setItem(i, 0, QTableWidgetItem(plat_name))
            self.table_accounts.setItem(i, 1, QTableWidgetItem(acc.get("account_name")))
            
            item_status = QTableWidgetItem(status_text)
            if "✅" in status_text: item_status.setForeground(QColor("#2ecc71"))
            elif "⚠️" in status_text: item_status.setForeground(QColor("#f1c40f"))
            else: item_status.setForeground(QColor("#e74c3c"))
            self.table_accounts.setItem(i, 2, item_status)
            
            self.table_accounts.setItem(i, 3, QTableWidgetItem(auth_method))
            
            # Nút xóa
            btn_del = QPushButton("❌ Xóa")
            btn_del.setStyleSheet("color: #e74c3c; font-weight: bold;")
            btn_del.clicked.connect(lambda checked, a_id=acc.get("id"): self._delete_account(a_id))
            self.table_accounts.setCellWidget(i, 4, btn_del)

        # 2. Update Combobox (Dropdown)
        if hasattr(self, 'cb_target_account'):
            self.cb_target_account.clear()
            self.cb_target_account.addItem("--- Chọn kênh liên kết ---", userData=None)
            for acc in accounts:
                display_name = f"[{acc.get('platform')}] {acc.get('account_name')}"
                self.cb_target_account.addItem(display_name, userData=acc)

    def _delete_account(self, account_id):
        reply = QMessageBox.question(self, "Xác nhận", "Bạn có chắc muốn xóa tài khoản API này không?", 
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.acc_manager.delete_account(account_id)
            self.refresh_accounts_data()

    def _build_upload_config_tab(self):
        w = QWidget()
        main_layout = QHBoxLayout(w)
        
        # --- LEFT PANEL ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        grp_source = QGroupBox("1. Nguồn Video & Đích Đến")
        form_source = QFormLayout(grp_source)
        
        self.cb_target_platform = QComboBox()
        self.cb_target_platform.addItems(["Tất cả nền tảng (Đăng chéo)"] + list(AVAILABLE_PLATFORMS.keys()))
        form_source.addRow("Nền tảng:", self.cb_target_platform)
        
        self.cb_target_account = QComboBox() # Được nạp động từ DB
        form_source.addRow("Kênh nhận (API):", self.cb_target_account)
        
        self.txt_video_path = QLineEdit("C:/VeoSuite_Exports/video_final.mp4")
        btn_browse = QPushButton("📁")
        btn_browse.setFixedWidth(30)
        box_path = QHBoxLayout()
        box_path.addWidget(self.txt_video_path)
        box_path.addWidget(btn_browse)
        form_source.addRow("File Video:", box_path)
        
        self.txt_thumb_path = QLineEdit("C:/VeoSuite_Exports/thumb.jpg")
        btn_browse_thumb = QPushButton("🖼️")
        btn_browse_thumb.setFixedWidth(30)
        box_thumb = QHBoxLayout()
        box_thumb.addWidget(self.txt_thumb_path)
        box_thumb.addWidget(btn_browse_thumb)
        form_source.addRow("Thumbnail:", box_thumb)
        
        left_layout.addWidget(grp_source)
        
        grp_settings = QGroupBox("2. Cài Đặt Phát Hành")
        form_settings = QFormLayout(grp_settings)
        
        self.cb_visibility = QComboBox()
        self.cb_visibility.addItems(["Công khai (Public)", "Không công khai (Unlisted)", "Riêng tư (Private)"])
        form_settings.addRow("Quyền riêng tư:", self.cb_visibility)
        
        self.chk_schedule = QCheckBox("Lên lịch đăng (Schedule)")
        self.dt_publish_time = QDateTimeEdit(QDateTime.currentDateTime())
        self.dt_publish_time.setCalendarPopup(True)
        self.dt_publish_time.setEnabled(False)
        self.chk_schedule.toggled.connect(self.dt_publish_time.setEnabled)
        
        box_schedule = QHBoxLayout()
        box_schedule.addWidget(self.chk_schedule)
        box_schedule.addWidget(self.dt_publish_time)
        form_settings.addRow("Thời gian:", box_schedule)
        
        left_layout.addWidget(grp_settings)
        main_layout.addWidget(left_panel, 1)
        
        # --- RIGHT PANEL ---
        right_panel = QScrollArea()
        right_panel.setWidgetResizable(True)
        right_content = QWidget()
        right_layout = QVBoxLayout(right_content)
        right_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        grp_meta = QGroupBox("3. Siêu Dữ Liệu Chi Tiết (SEO & Metadata)")
        form_meta = QFormLayout(grp_meta)
        
        self.txt_title = QLineEdit("Stop Wasting Sleep! This AI Rain Sound Is Your Future Hack")
        form_meta.addRow("Tiêu đề (Title):", self.txt_title)
        
        self.txt_desc = QTextEdit("Mô tả chuẩn SEO được AI sinh ra...")
        self.txt_desc.setMaximumHeight(100)
        form_meta.addRow("Mô tả (Desc):", self.txt_desc)
        
        self.txt_tags = QTextEdit("rain sounds, sleep hack, future tech, asmr")
        self.txt_tags.setMaximumHeight(50)
        form_meta.addRow("Thẻ (Tags):", self.txt_tags)
        
        self.cb_category = QComboBox()
        self.cb_category.addItems(["24 - Entertainment", "27 - Education", "28 - Science & Technology", "22 - People & Blogs"])
        form_meta.addRow("Danh mục (Category):", self.cb_category)
        
        self.chk_made_for_kids = QCheckBox("Video này dành cho trẻ em (COPPA)")
        form_meta.addRow("Trẻ em:", self.chk_made_for_kids)
        
        right_layout.addWidget(grp_meta)
        
        grp_short = QGroupBox("4. Cấu Hình Nền Tảng Video Ngắn")
        form_short = QFormLayout(grp_short)
        
        self.chk_tiktok_duet = QCheckBox("Cho phép Duet/Stitch (TikTok)")
        self.chk_tiktok_duet.setChecked(True)
        form_short.addRow("Tương tác:", self.chk_tiktok_duet)
        
        self.chk_copyright_check = QCheckBox("Chạy kiểm tra bản quyền âm nhạc trước khi đăng")
        self.chk_copyright_check.setChecked(True)
        form_short.addRow("Bản quyền:", self.chk_copyright_check)
        
        right_layout.addWidget(grp_short)
        
        btn_add_queue = QPushButton("📥 THÊM VÀO HÀNG ĐỢI PHÁT HÀNH")
        btn_add_queue.setToolTip("BƯỚC 5: Kiểm tra lại Metadata (SEO) và thêm video vào danh sách chuẩn bị đăng.")
        btn_add_queue.setStyleSheet("background: #d35400; color: white; font-size: 14px; font-weight: bold; padding: 12px;")
        btn_add_queue.clicked.connect(self._do_add_queue)
        right_layout.addWidget(btn_add_queue)
        
        right_panel.setWidget(right_content)
        main_layout.addWidget(right_panel, 1)
        
        return w

    def _build_scheduler_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("Tiến trình Upload Thực tế qua API. Nếu lỗi mạng, hệ thống sẽ tự động Retry."))
        btn_start_queue = QPushButton("▶ BẮT ĐẦU CHẠY HÀNG ĐỢI")
        btn_start_queue.setToolTip("BƯỚC 5: Nhấn để bắt đầu quá trình Upload tự động lên các nền tảng thông qua API.")
        btn_start_queue.setStyleSheet("background: #e74c3c; color: white; font-weight: bold; padding: 5px 15px;")
        btn_start_queue.clicked.connect(self._start_upload_queue)
        header_layout.addStretch()
        header_layout.addWidget(btn_start_queue)
        layout.addLayout(header_layout)
        
        self.table_queue = QTableWidget(0, 7)
        self.table_queue.setHorizontalHeaderLabels([
            "Nền tảng", "Kênh nhận", "Tiêu đề Video", "Chế độ", "Thời gian Đăng", "Trạng thái Upload", "Action"
        ])
        self.table_queue.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_queue.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table_queue)
        
        # Biến nhớ queue
        self.publish_queue = []
        
        return w

    def _do_add_queue(self):
        # 1. Thu thập thông tin từ UI
        selected_acc_data = self.cb_target_account.currentData()
        if not selected_acc_data:
            QMessageBox.warning(self, "Lỗi", "Vui lòng chọn một Kênh đích đã liên kết API!")
            return
            
        task = {
            "account_info": selected_acc_data, # Dữ liệu từ AccountManager
            "video_path": self.txt_video_path.text(),
            "metadata": {
                "title": self.txt_title.text(),
                "description": self.txt_desc.toPlainText(),
                "tags": [t.strip() for t in self.txt_tags.toPlainText().split(",")],
                "privacyStatus": "public" if "Public" in self.cb_visibility.currentText() else "private",
                "made_for_kids": self.chk_made_for_kids.isChecked()
            },
            "schedule": self.dt_publish_time.dateTime().toString() if self.chk_schedule.isChecked() else "Ngay lập tức",
            "status": "⏳ Sẵn sàng tải lên"
        }
        
        self.publish_queue.append(task)
        self._refresh_queue_table()
        
        self.tabs.setCurrentIndex(2) # Chuyển sang Tab hàng đợi
        QMessageBox.information(self, "Thành công", f"Đã thêm video vào hàng đợi để tải lên {selected_acc_data['account_name']}.")

    def _refresh_queue_table(self):
        self.table_queue.setRowCount(len(self.publish_queue))
        for i, task in enumerate(self.publish_queue):
            acc = task["account_info"]
            self.table_queue.setItem(i, 0, QTableWidgetItem(acc["platform"]))
            self.table_queue.setItem(i, 1, QTableWidgetItem(acc["account_name"]))
            self.table_queue.setItem(i, 2, QTableWidgetItem(task["metadata"]["title"]))
            self.table_queue.setItem(i, 3, QTableWidgetItem(task["metadata"]["privacyStatus"]))
            self.table_queue.setItem(i, 4, QTableWidgetItem(task["schedule"]))
            
            st_item = QTableWidgetItem(task["status"])
            if "✅" in task["status"]: st_item.setForeground(QColor("#2ecc71"))
            elif "❌" in task["status"]: st_item.setForeground(QColor("#e74c3c"))
            else: st_item.setForeground(QColor("#f39c12"))
            self.table_queue.setItem(i, 5, st_item)
            
            btn_run = QPushButton("🚀 Tải Ngay")
            btn_run.clicked.connect(lambda checked, idx=i: self._execute_single_upload(idx))
            self.table_queue.setCellWidget(i, 6, btn_run)

    def _execute_single_upload(self, index):
        task = self.publish_queue[index]
        acc_info = task["account_info"]
        plat_name = acc_info["platform"]
        
        task["status"] = "🔄 Đang tải lên..."
        self._refresh_queue_table()
        self.window().repaint() # Ép giao diện vẽ lại
        
        # 1. Khởi tạo Plugin
        plugin = get_platform_instance(plat_name)
        if not plugin:
            task["status"] = "❌ Lỗi: Không tìm thấy Plugin"
            self._refresh_queue_table()
            return
            
        # 2. Đăng nhập / Truyền Key
        if not plugin.authenticate(acc_info.get("credentials", {})):
            task["status"] = "❌ Lỗi: Xác thực API thất bại"
            self._refresh_queue_table()
            return
            
        # 3. Upload thật (Sẽ gọi file youtube_api.py, facebook_api.py...)
        result = plugin.upload_video(task["video_path"], task["metadata"])
        
        if result.get("status") == "success":
            task["status"] = f"✅ Xong! (URL: {result.get('video_id', 'Đã lưu')})"
        else:
            err = result.get("error", "Lỗi không xác định")
            task["status"] = f"❌ Lỗi: {err[:50]}..."
            
        self._refresh_queue_table()

    def _start_upload_queue(self):
        # Chạy toàn bộ các dòng đang 'Sẵn sàng'
        for i, task in enumerate(self.publish_queue):
            if "Sẵn sàng" in task["status"]:
                self._execute_single_upload(i)

    def action_scan_production(self):
        """Quét toàn bộ VEO_DB để tìm các video đã render xong và có meta chuẩn"""
        import glob
        self.log_signal.emit("🔍 Đang quét kho thành phẩm từ Editor...")
        
        # Tìm tất cả file production_package.json
        packages = glob.glob("VEO_DB/**/production_package.json", recursive=True)
        
        if not packages:
            QMessageBox.information(self, "Trống", "Không tìm thấy video nào đã render xong trong VEO_DB.")
            return
            
        count = 0
        accounts = self.acc_manager.load_accounts()
        
        for pkg_path in packages:
            try:
                with open(pkg_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                
                # Tìm video tương ứng trong cùng thư mục
                folder = os.path.dirname(pkg_path)
                video_files = [f for f in os.listdir(folder) if f.endswith(".mp4") and "_final" in f]
                if not video_files: continue
                
                v_path = os.path.join(folder, video_files[0])
                
                # Kiểm tra xem video này đã có trong queue chưa
                if any(q["video_path"] == v_path for q in self.publish_queue):
                    continue
                
                # LOGIC SMART MAPPING (Khớp kênh)
                target_acc = None
                meta_channel = meta.get("channel", "").lower()
                meta_topic = meta.get("topic", "").lower()
                
                # Ưu tiên khớp tên kênh, sau đó đến chủ đề
                for acc in accounts:
                    acc_name = acc["account_name"].lower()
                    if meta_channel in acc_name or meta_topic in acc_name:
                        target_acc = acc
                        break
                
                if not target_acc and accounts: target_acc = accounts[0] # Fallback
                
                # [MỚI] Tự động lên lịch theo Giờ Vàng của Quốc gia
                country = meta.get("country", "Global")
                golden_time = get_next_golden_hour(country)
                
                if target_acc:
                    task = {
                        "account_info": target_acc,
                        "video_path": v_path,
                        "metadata": {
                            "title": meta.get("title", "Untitled Video"),
                            "description": meta.get("description", ""),
                            "tags": meta.get("tags", []),
                            "privacyStatus": "public",
                            "made_for_kids": False
                        },
                        "schedule": golden_time.strftime("%Y-%m-%d %H:%M"),
                        "status": "⏳ Đã lên lịch (Giờ Vàng)"
                    }
                    self.publish_queue.append(task)
                    count += 1
            except Exception as e:
                print(f"Lỗi đọc package {pkg_path}: {e}")
        
        if count > 0:
            self._refresh_queue_table()
            self.tabs.setCurrentIndex(2) # Chuyển sang Tab hàng đợi
            QMessageBox.information(self, "Thành công", f"Đã tự động nhập {count} video mới vào hàng đợi phát hành!")
        else:
            QMessageBox.information(self, "Thông báo", "Không có video mới nào cần nhập.")

    def log_system(self, message):
        print(f"[Publish] {message}")
