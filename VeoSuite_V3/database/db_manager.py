"""
VEO SUITE V3.2 — Database Manager
===================================
Quản lý kết nối và schema SQLite + JSON project storage.
Schema chuẩn hoá — ĐÂY LÀ FILE DUY NHẤT QUẢN LÝ DATABASE.
"""

import json
import os
import sqlite3
import logging
from pathlib import Path
from typing import Optional, Dict, Any
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger("VeoSuite.DB")


class DatabaseManager:
    """
    Singleton quản lý Database SQLite cho VEO SUITE V3.2.
    
    Usage:
        db = DatabaseManager()                  # Dùng path mặc định
        db = DatabaseManager("/path/to/db")     # Chỉ định path
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            self.db_path = Path(__file__).parent / "veo_suite.db"
        else:
            self.db_path = Path(db_path)

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection: Optional[sqlite3.Connection] = None
        self._initialize_database()

    # =========================================================================
    # PRIVATE: Kết nối & Khởi tạo
    # =========================================================================

    def _get_connection(self) -> sqlite3.Connection:
        """Tạo hoặc tái sử dụng kết nối."""
        if self.connection is None:
            self.connection = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
            )
            self.connection.execute("PRAGMA foreign_keys = ON")
            self.connection.row_factory = sqlite3.Row
        return self.connection

    def _initialize_database(self):
        """Tạo các bảng nếu chưa tồn tại."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # ── Bảng PROJECTS ──
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    mode TEXT NOT NULL DEFAULT 'manual',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT status_check CHECK (status IN ('draft', 'rendering', 'done')),
                    CONSTRAINT mode_check CHECK (mode IN ('manual', 'auto'))
                )
            """)

            # ── Bảng SCENES ──
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scenes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    sequence_order INTEGER NOT NULL,
                    text_content TEXT,
                    audio_path TEXT,
                    duration_ms INTEGER DEFAULT 0,
                    image_prompt TEXT,
                    image_path TEXT,
                    image_source TEXT DEFAULT 'stock',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    CONSTRAINT image_source_check CHECK (image_source IN ('stock', 'ai'))
                )
            """)

            # ── Index cho scenes ──
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_scenes_project_id 
                ON scenes(project_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_scenes_sequence 
                ON scenes(project_id, sequence_order)
            """)

            # ── Bảng SETTINGS (key-value store) ──
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    description TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # ── Bảng ACCOUNTS (cho phòng Ops) ──
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    username TEXT NOT NULL,
                    cookies TEXT,
                    proxy TEXT,
                    status TEXT DEFAULT 'warmup',
                    last_used DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    notes TEXT,
                    CONSTRAINT status_check CHECK (status IN ('warmup', 'money', 'burn')),
                    UNIQUE(platform, username)
                )
            """)

            # Khởi tạo settings mặc định
            self._init_default_settings(cursor)

            conn.commit()
            logger.info(f"Database ready: {self.db_path}")

        except sqlite3.Error as e:
            logger.error(f"Database init error: {e}")
            conn.rollback()
            raise

    def _init_default_settings(self, cursor: sqlite3.Cursor):
        """Insert settings mặc định nếu chưa có."""
        defaults = [
            ("app_version", "3.2.0", "Phiên bản ứng dụng"),
            ("theme", "dark", "Giao diện (dark/light)"),
            ("ffmpeg_path", "ffmpeg", "Đường dẫn FFmpeg"),
            ("output_resolution", "1920x1080", "Độ phân giải video"),
            ("output_fps", "30", "FPS video đầu ra"),
        ]
        for key, value, desc in defaults:
            cursor.execute(
                "INSERT OR IGNORE INTO settings (key, value, description) VALUES (?, ?, ?)",
                (key, value, desc)
            )

    # =========================================================================
    # PUBLIC: Kiểm tra & Thống kê
    # =========================================================================

    def check_db_integrity(self) -> bool:
        """Kiểm tra toàn vẹn database."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Kiểm tra bảng tồn tại
            required = ['projects', 'scenes', 'settings', 'accounts']
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN (?, ?, ?, ?)",
                required
            )
            existing = [row[0] for row in cursor.fetchall()]
            if len(existing) != len(required):
                missing = set(required) - set(existing)
                logger.error(f"Missing tables: {missing}")
                return False

            # PRAGMA integrity_check
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()[0]
            if result != "ok":
                logger.error(f"Integrity check failed: {result}")
                return False

            # Foreign key check
            cursor.execute("PRAGMA foreign_key_check")
            fk_errors = cursor.fetchall()
            if fk_errors:
                logger.error(f"FK violations: {fk_errors}")
                return False

            return True

        except sqlite3.Error as e:
            logger.error(f"Integrity check error: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Lấy thống kê database."""
        conn = self._get_connection()
        cursor = conn.cursor()
        stats = {}

        try:
            cursor.execute("SELECT COUNT(*) FROM projects")
            stats['total_projects'] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM scenes")
            stats['total_scenes'] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM accounts")
            stats['total_accounts'] = cursor.fetchone()[0]

            if self.db_path.exists():
                stats['db_size_mb'] = round(self.db_path.stat().st_size / (1024 * 1024), 2)
            else:
                stats['db_size_mb'] = 0

        except Exception as e:
            logger.error(f"Stats error: {e}")
            stats = {'total_projects': 0, 'total_scenes': 0,
                     'total_accounts': 0, 'db_size_mb': 0}

        return stats

    # =========================================================================
    # PUBLIC: CRUD helpers (dùng chung cho các module)
    # =========================================================================

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Chạy SQL và commit."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, params)
        conn.commit()
        return cursor

    def fetch_all(self, sql: str, params: tuple = ()) -> list:
        """Chạy SELECT, trả về list of Row."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, params)
        return cursor.fetchall()

    def fetch_one(self, sql: str, params: tuple = ()):
        """Chạy SELECT, trả về 1 row hoặc None."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, params)
        return cursor.fetchone()

    def close(self):
        """Đóng kết nối."""
        if self.connection:
            self.connection.close()
            self.connection = None
            logger.info("Database connection closed")

    # =========================================================================
    # JSON PROJECT STORAGE (Backward compat với UI cũ)
    # UI cũ lưu projects dạng JSON list trong VEO_DB/projects.json
    # Sẽ migrate sang SQLite thuần khi refactor từng tab (Phase 3-5)
    # =========================================================================

    @property
    def db_folder(self) -> str:
        """Trả về thư mục VEO_DB (backward compat)."""
        folder = os.path.join(
            Path(__file__).parent.parent, "VEO_DB"
        )
        os.makedirs(folder, exist_ok=True)
        return folder

    def load_projects(self, filename: str = "projects.json") -> list:
        """Load projects từ JSON file."""
        filepath = os.path.join(self.db_folder, filename)
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    return data
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Cannot load {filename}: {e}")
        return []

    def save_projects(self, projects: list, filename: str = "projects.json"):
        """Save projects vào JSON file."""
        filepath = os.path.join(self.db_folder, filename)
        try:
            os.makedirs(self.db_folder, exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(projects, f, indent=2, ensure_ascii=False)
            logger.debug(f"Projects saved: {len(projects)} items -> {filename}")
        except IOError as e:
            logger.error(f"Cannot save {filename}: {e}")

    def update_task_status(self, p_id: int, t_id: int, status: str):
        """Backward compatibility: Cập nhật trạng thái của 1 task trong JSON storage."""
        projects = self.load_projects()
        if 0 <= p_id < len(projects):
            proj = projects[p_id]
            for t in proj.get("tasks", []):
                if t.get("id") == t_id:
                    t["status"] = status
                    self.save_projects(projects)
                    return True
        return False