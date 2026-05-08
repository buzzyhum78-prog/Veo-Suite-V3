
import os
import sys
import time
import json
import random
import requests
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *
from PyQt6.QtMultimedia import *

import os
import sys
import json
import re
import datetime
import time
import threading # Để dịch không bị đơ máy
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QFrame, QSplitter, QTableWidget, QProgressDialog,
    QHeaderView, QAbstractItemView, QSpinBox, QCheckBox,
    QGroupBox, QFormLayout, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QTableWidgetItem, QTextEdit, QApplication, QScrollArea, QSizePolicy,
    QGridLayout, QInputDialog, QFileDialog, QDialog, QDialogButtonBox, QMenu, QToolButton
)
from PyQt6.QtGui import QFont, QColor, QCursor
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from deep_translator import GoogleTranslator
from services.database_manager import DatabaseManager
from services.ai_factory import AIFactory      


from modules.content.constants import *

class NewProjectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Khởi Tạo Kênh / Dự Án Mới")
        self.setMinimumWidth(450)
        self.setStyleSheet("background: #252526; color: white; font-size: 13px;")
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Tiêu đề
        lbl_info = QLabel("🚀 THIẾT LẬP KÊNH THỦ CÔNG (CREATIVE MODE)")
        lbl_info.setStyleSheet("font-weight: bold; color: #f1c40f; font-size: 14px;")
        lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_info)

        # Form chọn thông tin
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        # 1. Chọn Nền tảng
        self.cb_platform = QComboBox()
        self.cb_platform.addItems(PLATFORMS_DATA)
        form.addRow("Nền tảng:", self.cb_platform)
        
        # 2. Chọn Quốc gia (ĐÃ LỌC BỎ CÁC DÒNG TIÊU ĐỀ '---')
        self.cb_country = QComboBox()
        # Chỉ lấy các dòng không bắt đầu bằng ---
        clean_countries = [c for c in COUNTRIES_DATA if not c.startswith("---")]
        self.cb_country.addItems(clean_countries)
        form.addRow("Quốc gia:", self.cb_country)
        
        # 3. Chọn Chủ đề (ĐÃ LỌC BỎ CÁC DÒNG TIÊU ĐỀ '---')
        self.cb_topic = QComboBox()
        clean_topics = [t for t in TOPICS_DATA if not t.startswith("---")]
        self.cb_topic.addItems(clean_topics)
        form.addRow("Chủ đề:", self.cb_topic)
        
        layout.addLayout(form)

        # Ghi chú
        lbl_note = QLabel("ℹ️ Lưu ý: Dự án tạo mới sẽ chưa có Video. Hãy dùng chức năng 'Nhập Key' hoặc 'Bào Key' sau khi tạo.")
        lbl_note.setWordWrap(True)
        lbl_note.setStyleSheet("color: #aaa; font-style: italic; margin-top: 10px;")
        layout.addWidget(lbl_note)

        # Nút OK/Cancel
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        # Style nút
        btns.setStyleSheet("""
            QPushButton { background: #34495e; color: white; padding: 6px 15px; border-radius: 4px; }
            QPushButton[text="OK"] { background: #27ae60; font-weight: bold; }
            QPushButton[text="Cancel"] { background: #c0392b; }
        """)

        layout.addWidget(btns)

    def get_data(self):
        return (
            self.cb_platform.currentText(),
            self.cb_country.currentText(),
            self.cb_topic.currentText()
        )
    
# --- CLASS CHẠY NGẦM (WORKER) - ĐỂ Ở CUỐI FILE ---
