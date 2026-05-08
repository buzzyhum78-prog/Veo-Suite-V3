"""
VEO SUITE V3.2 — Assets Factory UI Components
===============================================
Các Widget tuỳ chỉnh cho Media Tab:
  - ZoomableLabel: Ảnh có popup zoom khi hover
  - ClickableSlider: Slider click-to-seek
  - MediaItemWidget: Card hiển thị file media trong list
"""

from PyQt6.QtCore import pyqtSignal
import os
import logging

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QMessageBox, QDialog, QSizePolicy, QScrollArea
)
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QPixmap, QCursor, QWheelEvent

logger = logging.getLogger("VeoSuite.AssetsFactory.UI")


# ============================================================================
# NHÃN THÔNG MINH (RÊ CHUỘT ĐỂ ZOOM)
# ============================================================================
class ZoomableLabel(QLabel):
    def __init__(self, parent=None, is_banner=False):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.high_res_pixmap = None  # Lưu ảnh gốc chất lượng cao
        self.zoom_popup = None
        self.is_banner = is_banner  # Để biết tỷ lệ khung hình popup

    def set_high_res(self, pixmap_path):
        """Lưu đường dẫn ảnh gốc để chuẩn bị zoom."""
        if os.path.exists(pixmap_path):
            self.high_res_pixmap = QPixmap(pixmap_path)

    def enterEvent(self, event):
        """Chuột vào -> Hiện Popup Zoom."""
        super().enterEvent(event)
        if not self.high_res_pixmap or self.high_res_pixmap.isNull():
            return

        # 1. Tạo Popup không viền
        self.zoom_popup = QDialog(self, Qt.WindowType.FramelessWindowHint | Qt.WindowType.ToolTip)
        self.zoom_popup.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.zoom_popup.setStyleSheet("background: #000; border: 2px solid #f39c12;")
        
        v_layout = QVBoxLayout(self.zoom_popup)
        v_layout.setContentsMargins(2, 2, 2, 2)
        
        lbl_zoom = QLabel()
        
        # 2. Tính toán kích thước popup (To gấp 4-5 lần ảnh gốc)
        target_w = 500 if self.is_banner else 400
        target_h = 280 if self.is_banner else 400
        
        # Scale ảnh gốc chất lượng cao vào popup
        scaled_pix = self.high_res_pixmap.scaled(
            target_w, target_h, 
            Qt.AspectRatioMode.KeepAspectRatio, 
            Qt.TransformationMode.SmoothTransformation
        )
        lbl_zoom.setPixmap(scaled_pix)
        v_layout.addWidget(lbl_zoom)
        
        # 3. Định vị popup ngay cạnh con trỏ chuột
        pos = QCursor.pos()
        self.zoom_popup.move(pos.x() + 20, pos.y() + 20)
        self.zoom_popup.show()

    def leaveEvent(self, event):
        """Chuột ra -> Đóng Popup."""
        super().leaveEvent(event)
        if self.zoom_popup:
            self.zoom_popup.close()
            self.zoom_popup = None


# ============================================================================
# SCROLL AREA CUỘN NGANG (STYLE CARDS GALLERY)
# Wheel chuột tự động cuộn NGANG thay vì dọc
# ============================================================================
class HorizontalScrollArea(QScrollArea):
    """QScrollArea được tùy chỉnh: wheel chuột cuộn ngang."""
    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        sb = self.horizontalScrollBar()
        sb.setValue(sb.value() - delta)
        event.accept()


# ============================================================================
# SLIDER CHO PHÉP CLICK ĐỂ TUA
# ============================================================================
class ClickableSlider(QSlider):
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            val = self.minimum() + ((self.maximum() - self.minimum()) * event.pos().x()) / self.width()
            self.setValue(int(val))
            event.accept()
            # Gửi signal sliderMoved để logic cũ xử lý
            self.sliderMoved.emit(int(val))
        super().mousePressEvent(event)


# ============================================================================
# CARD CHỌN PHONG CÁCH (STYLE CARD) - PREMIUM V3.3
# Lấy cảm hứng từ Pixelle-Video template gallery
# ============================================================================
class StyleCardWidget(QWidget):
    clicked = pyqtSignal(str) # Emit style name

    def __init__(self, name, icon_path=None, parent=None, emoji="🎨", color_accent="#3498db", description=""):
        super().__init__(parent)
        self.name = name
        self.selected = False
        self.color_accent = color_accent
        self.setFixedSize(110, 130)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if description:
            self.setToolTip(f"🎨 {name}\n{description}")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(3)
        
        # Thumbnail Style (lớn hơn, viền gradient)
        self.lbl_icon = QLabel()
        self.lbl_icon.setFixedSize(100, 65)
        self.lbl_icon.setScaledContents(True)
        if icon_path and os.path.exists(icon_path):
            self.lbl_icon.setPixmap(QPixmap(icon_path))
            self.lbl_icon.setStyleSheet(f"border-radius: 6px; border: 1px solid {color_accent}40;")
        else:
            # Placeholder thông minh: Emoji lớn + nền gradient
            self.lbl_icon.setText(emoji)
            self.lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.lbl_icon.setStyleSheet(f"""
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 #1a1a2e, stop:1 {color_accent}30);
                color: white; border-radius: 6px; font-size: 28px;
                border: 1px solid {color_accent}50;
            """)
            
        # Badge màu nhỏ
        self.lbl_badge = QLabel(f" {emoji} {name} ")
        self.lbl_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_badge.setStyleSheet(f"""
            font-size: 9px; color: #ddd; font-weight: bold;
            background: {color_accent}30; border-radius: 8px; 
            padding: 2px 4px;
        """)
        self.lbl_badge.setWordWrap(True)
        
        layout.addWidget(self.lbl_icon)
        layout.addWidget(self.lbl_badge)
        
        self._apply_base_style()

    def _apply_base_style(self):
        if self.selected:
            self.setStyleSheet(f"""
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #34495e, stop:1 #2c3e50);
                border: 2px solid {self.color_accent}; border-radius: 10px;
            """)
            self.lbl_badge.setStyleSheet(f"""
                font-size: 9px; color: {self.color_accent}; font-weight: bold;
                background: {self.color_accent}25; border-radius: 8px;
                padding: 2px 4px;
            """)
        else:
            self.setStyleSheet("""
                background: #1e1e1e; border: 1px solid #333; border-radius: 10px;
            """)
            self.lbl_badge.setStyleSheet(f"""
                font-size: 9px; color: #aaa; font-weight: bold;
                background: {self.color_accent}15; border-radius: 8px;
                padding: 2px 4px;
            """)

    def update_style(self):
        """Public API — giữ tương thích ngược."""
        self._apply_base_style()

    def enterEvent(self, event):
        """Hover effect."""
        if not self.selected:
            self.setStyleSheet(f"""
                background: #2a2a2a; 
                border: 1px solid {self.color_accent}80; 
                border-radius: 10px;
            """)
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """Un-hover."""
        self._apply_base_style()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self.clicked.emit(self.name)
        super().mousePressEvent(event)


# ============================================================================
# GIAO DIỆN TÙY CHỈNH CHO TỪNG FILE MEDIA (PREMIUM LOOK)
# ============================================================================
class MediaItemWidget(QWidget):
    def __init__(self, file_path, label_text="", parent_list=None):
        super().__init__()
        self.file_path = file_path
        self.parent_list = parent_list 
        
        # 1. Xác định loại file
        ext = os.path.splitext(file_path)[1].lower()
        self.is_video = ext in ['.mp4', '.mov', '.avi']
        filename = os.path.basename(file_path)
        
        # 2. Xác định nguồn (AI hay Stock) dựa vào tên file
        is_ai = "_AI" in filename or "pollinations" in filename.lower()
        
        # Phân tích sâu công nghệ
        tech_text = "AUTO"
        if "pexels" in filename.lower(): tech_text = "PEXELS STOCK"
        elif "pixabay" in filename.lower(): tech_text = "PIXABAY STOCK"
        elif "pollinations" in filename.lower(): tech_text = "POLLINATIONS AI"
        elif "luma" in filename.lower(): tech_text = "LUMA VIDEO"
        
        # Premium Colors
        type_color = "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8e44ad, stop:1 #9b59b6)" if is_ai else "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2980b9, stop:1 #3498db)"
        type_text = f"🤖 {tech_text}" if is_ai else f"🎥 {tech_text}"
        
        if not self.is_video and not is_ai:
            type_text = f"📷 {tech_text}"

        self.setFixedHeight(120)
        self.setObjectName("MediaItem")
        self.setStyleSheet("""
            #MediaItem { 
                background: rgba(45, 45, 45, 180); 
                border: 1px solid #444; 
                border-radius: 10px; 
            }
            #MediaItem:hover {
                background: rgba(60, 60, 60, 220);
                border: 1px solid #3498db;
            }
        """)
        
        # 3. Layout ngang
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(12)

        # NHÃN SCENE (Vàng Gold rực rỡ)
        if label_text:
            lbl_scene = QLabel(label_text)
            lbl_scene.setStyleSheet("font-weight: 900; color: #f1c40f; font-size: 15px; font-family: 'Segoe UI Black';")
            lbl_scene.setFixedWidth(85)
            lbl_scene.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            layout.addWidget(lbl_scene)

        # --- CỘT 1: THUMBNAIL (LỚN HƠN, BO GÓC) ---
        lbl_thumb = QLabel()
        lbl_thumb.setFixedSize(120, 68)  # Tỷ lệ 16:9 
        lbl_thumb.setStyleSheet("background: #000; border-radius: 6px; border: 1px solid #555;")
        lbl_thumb.setScaledContents(True)
        
        if self.is_video:
            lbl_thumb.setText("▶ VIDEO")
            lbl_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_thumb.setStyleSheet("background: #111; color: #3498db; font-weight:bold; font-size: 10px; border: 1px solid #3498db; border-radius: 6px;")
        else:
            pix = QPixmap(file_path)
            if not pix.isNull():
                lbl_thumb.setPixmap(pix.scaled(120, 68, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
            
        layout.addWidget(lbl_thumb)
        
        # --- CỘT 2: THÔNG TIN ---
        info_layout = QVBoxLayout()
        info_layout.setSpacing(5)
        
        lbl_name = QLabel(filename)
        lbl_name.setStyleSheet("font-weight: bold; color: #ffffff; font-size: 12px;")
        lbl_name.setWordWrap(True)
        
        lbl_badge = QLabel(f" {type_text} ")
        lbl_badge.setStyleSheet(f"background: {type_color}; color: white; border-radius: 12px; font-size: 10px; padding: 4px 10px; font-weight: bold;")
        lbl_badge.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        
        info_layout.addWidget(lbl_name)
        info_layout.addWidget(lbl_badge)
        layout.addLayout(info_layout, stretch=1)
        
        # --- CỘT 3: NÚT BẤM (ICON TRÒN) ---
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(6)

        if self.is_video:
            btn_play = QPushButton("▶")
            btn_play.setFixedSize(32, 32)
            btn_play.setStyleSheet("background: #27ae60; border-radius: 16px; color: white; font-weight: bold;")
            btn_play.setCursor(Qt.CursorShape.PointingHandCursor)
            actions_layout.addWidget(btn_play)
            
        btn_open = QPushButton("📂")
        btn_open.setFixedSize(32, 32)
        btn_open.setStyleSheet("background: #34495e; border-radius: 16px; color: white;")
        btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_open.clicked.connect(self.open_folder)
        actions_layout.addWidget(btn_open)

        btn_del = QPushButton("✕")
        btn_del.setFixedSize(28, 28)
        btn_del.setStyleSheet("background: transparent; color: #e74c3c; border: 1px solid #e74c3c; border-radius: 14px; font-weight: bold;")
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.clicked.connect(self.delete_file)
        actions_layout.addWidget(btn_del)
        
        layout.addLayout(actions_layout)

    def open_folder(self):
        try:
            folder = os.path.dirname(self.file_path)
            if os.path.exists(folder):
                os.startfile(folder)
        except Exception as e:
            logger.warning(f"Cannot open folder: {e}")

    def delete_file(self):
        confirm = QMessageBox.question(
            self, "Xác nhận xóa", "Bạn có chắc chắn muốn xóa vĩnh viễn file này?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            try:
                if os.path.exists(self.file_path):
                    os.remove(self.file_path)
                
                if self.parent_list:
                    for i in range(self.parent_list.count()):
                        item = self.parent_list.item(i)
                        if self.parent_list.itemWidget(item) == self:
                            self.parent_list.takeItem(i)
                            break
            except Exception as e:
                logger.error(f"Error deleting file {self.file_path}: {e}")

    def open_folder(self):
        try:
            folder = os.path.dirname(self.file_path)
            os.startfile(folder)
        except Exception as e:
            logger.warning(f"Cannot open folder: {e}")

    def delete_file(self):
        confirm = QMessageBox.question(
            self, "Xóa", "Bạn muốn xóa file này vĩnh viễn?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            try:
                os.remove(self.file_path)
                # Tự xóa mình khỏi list
                if self.parent_list:
                    for i in range(self.parent_list.count()):
                        item = self.parent_list.item(i)
                        if self.parent_list.itemWidget(item) == self:
                            self.parent_list.takeItem(i)
                            break
            except Exception as e:
                logger.error(f"Error deleting file {self.file_path}: {e}")
