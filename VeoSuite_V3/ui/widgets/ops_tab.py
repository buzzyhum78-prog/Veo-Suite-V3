import sys
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, 
    QFrame, QTabWidget, QProgressBar, QMessageBox, QGroupBox, 
    QFormLayout, QLineEdit, QTextEdit, QComboBox
)
from PyQt6.QtGui import QColor, QFont, QIcon
from PyQt6.QtCore import Qt

class OpsTab(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # --- HEADER ---
        header = QHBoxLayout()
        lbl_title = QLabel("🛡️ TRUNG TÂM QUẢN TRỊ & AN NINH (OPS CENTER)")
        lbl_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #00e6e6;")
        
        # Các nút hành động nhanh
        btn_import_radar = QPushButton("🚀 Tạo Kênh Từ Radar")
        btn_import_radar.setStyleSheet("background: #8e44ad; color: white; font-weight: bold;")
        btn_import_radar.setToolTip("Lấy dữ liệu Trend từ Radar để khởi tạo kênh mới tự động")
        
        btn_add_existing = QPushButton("🔗 Liên kết Kênh có sẵn")
        btn_add_existing.setStyleSheet("background: #27ae60; color: white;")
        
        header.addWidget(lbl_title)
        header.addStretch()
        header.addWidget(btn_import_radar)
        header.addWidget(btn_add_existing)
        layout.addLayout(header)

        # --- DASHBOARD TỔNG QUAN (Mini Stats) ---
        stats_frame = QFrame()
        stats_frame.setStyleSheet("background: #252526; border-radius: 6px; padding: 10px;")
        s_layout = QHBoxLayout(stats_frame)
        
        # Hàm tạo thẻ thống kê nhỏ
        def create_stat_card(label, value, color):
            vbox = QVBoxLayout()
            l1 = QLabel(label); l1.setStyleSheet("color: #aaa; font-size: 12px;")
            l2 = QLabel(value); l2.setStyleSheet(f"color: {color}; font-size: 20px; font-weight: bold;")
            vbox.addWidget(l1); vbox.addWidget(l2); vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
            return vbox

        s_layout.addLayout(create_stat_card("Tổng Số Kênh", "12", "#fff"))
        s_layout.addLayout(create_stat_card("Kênh Hoạt Động", "10", "#2ecc71"))
        s_layout.addLayout(create_stat_card("Cảnh Báo Rủi Ro", "2", "#e74c3c"))
        s_layout.addLayout(create_stat_card("Doanh Thu Hôm Nay", "$1,240", "#f1c40f"))
        
        layout.addWidget(stats_frame)

        # --- MAIN TABS ---
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_channel_vault(), "🏦 KHO KÊNH (CHANNEL VAULT)")
        self.tabs.addTab(self._build_security_tab(), "🛡️ AN NINH MẠNG (SECURITY)")
        self.tabs.addTab(self._build_analytics_tab(), "📊 HIỆU SUẤT (ANALYTICS)")
        layout.addWidget(self.tabs)

    def _build_channel_vault(self):
        widget = QWidget()
        l = QVBoxLayout(widget)
        
        # Toolbar lọc
        tb = QHBoxLayout()
        tb.addWidget(QLabel("Lọc theo:"))
        tb.addWidget(QComboBox()) # Placeholder cho filter Topic
        tb.addWidget(QComboBox()) # Placeholder cho filter Country
        btn_health_check = QPushButton("🩺 KIKTRA SỨC KHỎE TOÀN BỘ")
        btn_health_check.setStyleSheet("background: #d35400; color: white;")
        btn_health_check.clicked.connect(lambda: QMessageBox.information(self, "Health Check", "Đang quét API Youtube...\nPhát hiện 1 kênh bị gậy bản quyền!"))
        tb.addStretch()
        tb.addWidget(btn_health_check)
        l.addLayout(tb)

        # Bảng Kênh
        self.table_channels = QTableWidget(0, 7)
        headers = ["Tên Kênh", "Chủ đề", "Quốc gia", "Trạng thái", "Proxy IP", "Video chờ", "Hành động"]
        self.table_channels.setHorizontalHeaderLabels(headers)
        self.table_channels.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_channels.verticalHeader().setVisible(False)
        self.table_channels.setAlternatingRowColors(True)
        self.table_channels.setStyleSheet("background: #1e1e1e; border: none;")
        
        # Mock Data
        mock_data = [
            ("Keto US Daily", "Sức khỏe", "🇺🇸 US", "🟢 Sống tốt", "192.168.1.10 (Clean)", "2", "Sửa"),
            ("Mysterious World", "Kinh dị", "🇬🇧 UK", "🟡 Cảnh báo (1 gậy)", "104.22.33.1 (Flag)", "0", "Kháng cáo"),
            ("Review Phim Hay", "Review", "🇻🇳 VN", "🟢 Sống tốt", "Tự nhiên (Home)", "5", "Sửa"),
        ]
        
        for i, row in enumerate(mock_data):
            self.table_channels.insertRow(i)
            for j, val in enumerate(row):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 3: # Cột trạng thái
                    if "🟢" in val: item.setForeground(QColor("#2ecc71"))
                    elif "🟡" in val: item.setForeground(QColor("#f1c40f"))
                    elif "🔴" in val: item.setForeground(QColor("#e74c3c"))
                self.table_channels.setItem(i, j, item)
                
        l.addWidget(self.table_channels)
        return widget



    def _build_security_tab(self):
        widget = QWidget()
        l = QVBoxLayout(widget)
        
        # Cấu hình Proxy
        grp_proxy = QGroupBox("🌐 CẤU HÌNH PROXY & FINGERPRINT")
        form = QFormLayout()
        
        txt_proxy_list = QTextEdit()
        txt_proxy_list.setPlaceholderText("Dán danh sách Proxy (IP:Port:User:Pass) vào đây...\nMỗi dòng 1 Proxy.")
        txt_proxy_list.setMaximumHeight(100)
        
        cb_rotate = QComboBox(); cb_rotate.addItems(["Xoay vòng theo Kênh (Mỗi kênh 1 IP cố định)", "Xoay vòng theo Phiên (Mỗi lần mở đổi IP)"])
        
        btn_check_proxy = QPushButton("Kiểm tra Proxy sống/chết")
        
        form.addRow("Danh sách Proxy:", txt_proxy_list)
        form.addRow("Chế độ xoay:", cb_rotate)
        form.addRow("", btn_check_proxy)
        
        grp_proxy.setLayout(form)
        l.addWidget(grp_proxy)
        
        # Cảnh báo
        grp_alert = QGroupBox("🚨 HỆ THỐNG CẢNH BÁO SỚM")
        vbox = QVBoxLayout()
        vbox.addWidget(QLabel("Gửi thông báo về Telegram/Email khi:"))
        vbox.addWidget(QPushButton("Login lạ xuất hiện"))
        vbox.addWidget(QPushButton("Kênh bị tụt view bất thường (>50%)"))
        vbox.addWidget(QPushButton("Kênh bị tắt kiếm tiền"))
        grp_alert.setLayout(vbox)
        l.addWidget(grp_alert)
        l.addStretch()
        
        return widget

    def _build_analytics_tab(self):
        widget = QWidget()
        l = QVBoxLayout(widget)
        l.addWidget(QLabel("📈 BIỂU ĐỒ TĂNG TRƯỞNG (Placeholder)"))
        
        # Giả lập biểu đồ bằng Progress Bar cho vui mắt
        for metric in ["Views (24h)", "Subscribers", "Revenue"]:
            h = QHBoxLayout()
            h.addWidget(QLabel(f"{metric}:"), 1)
            p = QProgressBar()
            p.setValue(75)
            p.setStyleSheet("QProgressBar::chunk { background: #3498db; }")
            h.addWidget(p, 4)
            l.addLayout(h)
            
        l.addStretch()
        return widget

    def _apply_style(self):
        self.setStyleSheet("""
            QWidget { background-color: #121212; color: #e0e0e0; font-family: 'Segoe UI'; }
            QTableWidget::item { padding: 5px; }
            QGroupBox { border: 1px solid #444; border-radius: 6px; margin-top: 15px; font-weight: bold; }
            QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top center; padding: 0 5px; color: #00e6e6; }
        """)