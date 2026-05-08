"""
VEO SUITE V3.2 — Render UI Components
=======================================
Widget cho Editor Tab:
  - TimelineBlock: Card đại diện 1 cảnh trên Timeline
"""

import os
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap


class TimelineBlock(QWidget):
    """
    Đại diện cho 1 cảnh (Scene) trên Timeline.
    Card to, dễ thao tác, có ảnh thumbnail + thời lượng.
    """
    def __init__(self, index, image_path, duration, parent_callback=None):
        super().__init__()
        self.index = index
        self.image_path = image_path
        self.duration = duration
        self.callback = parent_callback  # Gọi lại khi bị click
        
        self.setFixedSize(160, 140)
        self.setStyleSheet("""
            QWidget { 
                background-color: #2d2d30; 
                border: 1px solid #444; 
                border-radius: 5px; 
            }
            QWidget:hover { border: 1px solid #00e6e6; background-color: #3e3e42; }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # 1. Thumbnail (Ảnh đại diện cảnh)
        self.lbl_thumb = QLabel()
        self.lbl_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_thumb.setStyleSheet("background: #000; border: none;")
        self.lbl_thumb.setScaledContents(True)
        if os.path.exists(image_path):
            self.lbl_thumb.setPixmap(QPixmap(image_path))
        else:
            self.lbl_thumb.setText("❌ Mất ảnh")
            
        layout.addWidget(self.lbl_thumb)
        
        # 2. Thông tin (Số thứ tự + Thời lượng)
        lbl_info = QLabel(f"Scene {index+1} | ⏱️ {duration:.1f}s")
        lbl_info.setStyleSheet("color: #ccc; font-size: 10px; border: none; background: transparent;")
        lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_info)

    def mousePressEvent(self, event):
        """Bắt sự kiện click để báo cho Editor chính."""
        if self.callback:
            self.callback(self.index, self.image_path)
