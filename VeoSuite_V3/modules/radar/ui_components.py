
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




# --- CLASS MỚI: GIÚP BẢNG VỪA HIỆN CHỮ, VỪA SẮP XẾP THEO SỐ ---
class SortableItem(QTableWidgetItem):
    def __lt__(self, other):
        # Lấy giá trị sắp xếp ngầm (UserRole)
        val1 = self.data(Qt.ItemDataRole.UserRole)
        val2 = other.data(Qt.ItemDataRole.UserRole)
        
        # Nếu cả 2 đều có số -> So sánh số
        if val1 is not None and val2 is not None:
            try:
                return float(val1) < float(val2)
            except:
                pass # Nếu lỗi thì fallback về so sánh chữ
        
        # Fallback: Thử so sánh text nhưng bỏ dấu phẩy (cho trường hợp không set UserRole)
        try:
            t1 = self.text().replace(",", "").replace(".", "").strip()
            t2 = other.text().replace(",", "").replace(".", "").strip()
            return float(t1) < float(t2)
        except:
            return super().__lt__(other)
    
class ZoomableLabel(QLabel):
    """Hiển thị ảnh thumbnail, hover vào tự động zoom to"""
    def __init__(self, img_url, parent=None):
        super().__init__(parent)
        self.img_url = img_url
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setFixedSize(120, 68)
        self.setScaledContents(True)
        self.setStyleSheet("border: 1px solid #444; background: #000;")
        self.popup = None
        self.full_pixmap = None
        if img_url:
            self.setText("📷 LOADING...")

    def set_high_res_pixmap(self, pixmap):
        """Lưu ảnh gốc để dùng khi zoom"""
        self.full_pixmap = pixmap
        # Hiển thị bản thu nhỏ trên bảng
        self.setPixmap(pixmap.scaled(120, 68, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def enterEvent(self, event):
        if not self.full_pixmap: return # Nếu chưa có ảnh thì thôi
        
        # Tạo popup
        self.popup = QLabel(self.window(), flags=Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.popup.setStyleSheet("border: 2px solid #00ffea; background: #000;")
        
        # [QUAN TRỌNG] Show ảnh gốc (full_pixmap) thay vì lấy ảnh thumbnail phóng to
        # Scale ảnh gốc xuống kích thước vừa mắt (VD: 480px) nhưng vẫn giữ độ nét
        display_pix = self.full_pixmap.scaled(480, 270, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        
        self.popup.setPixmap(display_pix)
        self.popup.adjustSize()
        
        # Tính vị trí hiển thị (tránh bị che)
        pos = QCursor.pos()
        self.popup.move(pos.x() + 20, pos.y() + 20)
        self.popup.show()

    def leaveEvent(self, event):
        if self.popup:
            self.popup.close()
            self.popup.deleteLater()
            self.popup = None

class CheckBoxHeader(QHeaderView):
    """Header tùy chỉnh có Checkbox ở cột đầu tiên"""
    checkBoxClicked = pyqtSignal(bool)

    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.isOn = False

    def paintSection(self, painter, rect, logicalIndex):
        painter.save()
        super().paintSection(painter, rect, logicalIndex)
        painter.restore()

        if logicalIndex == 0: # Chỉ vẽ ở cột 0
            option = QStyleOptionButton()
            option.rect = QRect(rect.x() + 5, rect.y() + 5, 20, 20) # Căn chỉnh vị trí
            option.state = QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_Active
            if self.isOn:
                option.state |= QStyle.StateFlag.State_On
            else:
                option.state |= QStyle.StateFlag.State_Off
            
            self.style().drawPrimitive(QStyle.PrimitiveElement.PE_IndicatorCheckBox, option, painter)

    def mousePressEvent(self, event):
        # Kiểm tra nếu click vào vùng của Checkbox cột 0
        click_x = event.pos().x()
        # Vị trí cột 0 bắt đầu từ sectionViewportPosition(0)
        # Giả sử checkbox nằm trong khoảng 0-30px đầu tiên
        if 0 <= click_x <= 30:
            self.isOn = not self.isOn
            self.checkBoxClicked.emit(self.isOn)
            self.viewport().update()
        super().mousePressEvent(event)

class CheckableComboBox(QComboBox):
    """Combobox đa chọn siêu nhạy - Click đâu cũng ăn"""
    # [MỚI] Tín hiệu báo thay đổi dữ liệu ngay lập tức
    selectionChanged = pyqtSignal()

    """Combobox cho phép chọn nhiều mục"""
    def __init__(self):
        super().__init__()
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.closeOnLineEditClick = False
        
        self.lineEdit().installEventFilter(self)
        self.view().viewport().installEventFilter(self)

        self.model = QStandardItemModel(self)
        self.setModel(self.model)
        self.view().pressed.connect(self.handle_item_pressed)

        # [FIX QUAN TRỌNG] Ép Font Emoji cho cả ô nhập liệu và danh sách xổ xuống
        # Windows cần font này để hiện icon màu, nếu không sẽ ra đen trắng hoặc chữ cái
        emoji_font = QFont("Segoe UI Emoji", 10)
        self.setFont(emoji_font)          # Set cho ô hiển thị chính
        self.view().setFont(emoji_font)   # Set cho danh sách xổ xuống
        
        self.addItem("--- Chọn nhiều mục ---")

    def handle_item_pressed(self, index):
        item = self.model.itemFromIndex(index)
        # Nếu click vào dòng tiêu đề hoặc dòng bị disable -> Bỏ qua
        if not item.isEnabled() or "---" in item.text(): 
            return
        if item.checkState() == Qt.CheckState.Checked:
            item.setCheckState(Qt.CheckState.Unchecked)
        else:
            item.setCheckState(Qt.CheckState.Checked)
        self._update_text()
        # [QUAN TRỌNG] Bắn tín hiệu ra ngoài ngay lập tức để Prompt cập nhật
        self.selectionChanged.emit()

    def addItems(self, items):
        # [FIX ICON] Ép dùng font Emoji để hiện cờ đẹp trên Windows
        emoji_font = QFont("Segoe UI Emoji", 10)

        for text in items:
            item = QStandardItem(text)
            # Set font chuyên trị Emoji cho tất cả các dòng
            item.setFont(emoji_font)

            if "---" in text: # Dòng tiêu đề
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                item.setForeground(QColor("#00e6e6"))
                # Tiêu đề thì cho đậm lên tí
                bold_font = QFont("Segoe UI Emoji", 9, QFont.Weight.Bold)
                item.setFont(bold_font)
            else:
                item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                item.setData(Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)
            self.model.appendRow(item)

    def get_checked_items(self):
        checked = []
        for i in range(self.model.rowCount()):
            item = self.model.item(i)
            if "---" in item.text(): 
                continue
            if item.checkState() == Qt.CheckState.Checked:
                checked.append(item.text())
        return checked
    
    def _update_text(self):
        items = self.get_checked_items()
        text = ", ".join(items) if items else "--- Chọn nhiều mục ---"
        self.lineEdit().setText(text)

    def eventFilter(self, widget, event):
        # Bắt sự kiện click vào ô text
        if widget == self.lineEdit() and event.type() == event.Type.MouseButtonRelease:
            if self.view().isVisible():
                self.hidePopup()
            else:
                self.showPopup()
            return True
        return super().eventFilter(widget, event)
    
class BaseResultTable(QTableWidget):
    """Bảng chuẩn giao diện Dark Mode"""
    def __init__(self, headers):
        super().__init__()
        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.horizontalHeader().setStretchLastSection(True)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        self.setStyleSheet("""
            QTableWidget { background-color: #1e1e1e; gridline-color: #333; border: none; font-size: 13px; }
            QHeaderView::section { background-color: #252526; color: #ddd; padding: 5px; border: 1px solid #333; font-weight: bold; }
            QTableWidget::item:selected { background-color: #0d7377; color: white; }
        """)

# =============================================================================
# 3. WORKER THREADS (XỬ LÝ ĐA LUỒNG)
# =============================================================================
