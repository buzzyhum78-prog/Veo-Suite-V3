"""
VEO SUITE V3.2 — Database Manager Bridge
==========================================
DEPRECATED: File này chỉ là cầu nối tương thích ngược.
Import thật nằm ở: database/db_manager.py

Các tab UI cũ (content_tab, media_tab, editor_tab) vẫn import từ đây.
Khi refactor từng tab (Phase 3-5), sẽ đổi import sang database.db_manager
và xoá file này.
"""

# Re-export để code cũ không bị lỗi
from database.db_manager import DatabaseManager

__all__ = ["DatabaseManager"]
