"""
VEO SUITE V3.2 — Database Manager
===================================
Quản lý kết nối và schema SQLite + JSON project storage.
Schema chuẩn hoá — ĐÂY LÀ FILE DUY NHẤT QUẢN LÝ DATABASE.
"""

import json
import logging
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

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
        # Kết nối SQLite mở với check_same_thread=False để dùng từ nhiều
        # QThread; phải tự serialize ghi/đọc bằng RLock để tránh race.
        self._lock = threading.RLock()
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
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            try:
                self._create_schema(cursor)
                self._init_default_settings(cursor)
                conn.commit()
                logger.info(f"Database ready: {self.db_path}")
            except sqlite3.Error as e:
                logger.error(f"Database init error: {e}")
                conn.rollback()
                raise

    def _create_schema(self, cursor: sqlite3.Cursor) -> None:
        """Tạo các bảng + index nếu chưa tồn tại."""
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

        # ── Bảng PUBLISH_QUEUE (cho phòng Publisher) ──
        # Hàng đợi upload bền vững (qua restart). Scheduler quét bảng này
        # và gọi YouTubeUploader / TikTokUploader / ... theo platform.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS publish_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                video_path TEXT NOT NULL,
                title TEXT,
                description TEXT,
                tags TEXT,                       -- CSV
                privacy_status TEXT DEFAULT 'private',
                schedule_time DATETIME NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                result_url TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT pq_status_check CHECK (
                    status IN ('pending', 'running', 'done', 'failed', 'cancelled')
                )
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_publish_queue_status
            ON publish_queue(status, schedule_time)
        """)

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
            with self._lock:
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
        stats: Dict[str, Any] = {}
        try:
            with self._lock:
                conn = self._get_connection()
                cursor = conn.cursor()
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
        except sqlite3.Error as e:
            logger.error(f"Stats error: {e}")
            stats = {'total_projects': 0, 'total_scenes': 0,
                     'total_accounts': 0, 'db_size_mb': 0}
        return stats

    # =========================================================================
    # PUBLIC: CRUD helpers (dùng chung cho các module)
    # =========================================================================

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Chạy SQL và commit."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(sql, params)
            conn.commit()
            return cursor

    def fetch_all(self, sql: str, params: tuple = ()) -> list:
        """Chạy SELECT, trả về list of Row."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(sql, params)
            return cursor.fetchall()

    def fetch_one(self, sql: str, params: tuple = ()):
        """Chạy SELECT, trả về 1 row hoặc None."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(sql, params)
            return cursor.fetchone()

    def close(self):
        """Đóng kết nối."""
        with self._lock:
            if self.connection:
                self.connection.close()
                self.connection = None
                logger.info("Database connection closed")

    # =========================================================================
    # PUBLIC: Native SQLite CRUD — projects / scenes
    # (PR-4) Thay dần cho JSON storage ở phần dưới. Các tab UI có thể chuyển
    # sang dùng API này khi sẵn sàng; legacy load/save_projects vẫn còn để
    # tránh break các tab chưa refactor.
    # =========================================================================

    def create_project(self, name: str, mode: str = "manual") -> int:
        """Tạo project mới, trả về project_id."""
        cur = self.execute(
            "INSERT INTO projects (name, mode) VALUES (?, ?)",
            (name, mode),
        )
        return int(cur.lastrowid)

    def get_project(self, project_id: int) -> Optional[Dict[str, Any]]:
        """Lấy 1 project theo id (hoặc None)."""
        row = self.fetch_one(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        )
        return dict(row) if row else None

    def list_projects(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List tất cả project (tuỳ chọn lọc theo status)."""
        if status:
            rows = self.fetch_all(
                "SELECT * FROM projects WHERE status = ? ORDER BY id DESC",
                (status,),
            )
        else:
            rows = self.fetch_all("SELECT * FROM projects ORDER BY id DESC")
        return [dict(r) for r in rows]

    def update_project(self, project_id: int, **fields: Any) -> bool:
        """Cập nhật các trường của project. Bỏ qua các trường lạ."""
        ALLOWED = {"name", "status", "mode"}
        clean = {k: v for k, v in fields.items() if k in ALLOWED}
        if not clean:
            return False
        sets = ", ".join(f"{k} = ?" for k in clean)
        params = tuple(clean.values()) + (project_id,)
        cur = self.execute(
            f"UPDATE projects SET {sets}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            params,
        )
        return cur.rowcount > 0

    def delete_project(self, project_id: int) -> bool:
        """Xoá project (cascade xoá scenes nhờ FK ON DELETE CASCADE)."""
        cur = self.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        return cur.rowcount > 0

    def add_scene(
        self,
        project_id: int,
        sequence_order: int,
        text_content: str = "",
        image_prompt: str = "",
        image_path: str = "",
        audio_path: str = "",
        duration_ms: int = 0,
        image_source: str = "stock",
    ) -> int:
        """Thêm 1 scene vào project."""
        cur = self.execute(
            """
            INSERT INTO scenes (
                project_id, sequence_order, text_content, image_prompt,
                image_path, audio_path, duration_ms, image_source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id, sequence_order, text_content, image_prompt,
                image_path, audio_path, duration_ms, image_source,
            ),
        )
        return int(cur.lastrowid)

    def list_scenes(self, project_id: int) -> List[Dict[str, Any]]:
        """Liệt kê scenes của project, sắp theo sequence_order."""
        rows = self.fetch_all(
            "SELECT * FROM scenes WHERE project_id = ? ORDER BY sequence_order ASC",
            (project_id,),
        )
        return [dict(r) for r in rows]

    def update_scene(self, scene_id: int, **fields: Any) -> bool:
        """Cập nhật các trường của scene."""
        ALLOWED = {
            "sequence_order", "text_content", "audio_path",
            "duration_ms", "image_prompt", "image_path", "image_source",
        }
        clean = {k: v for k, v in fields.items() if k in ALLOWED}
        if not clean:
            return False
        sets = ", ".join(f"{k} = ?" for k in clean)
        params = tuple(clean.values()) + (scene_id,)
        cur = self.execute(f"UPDATE scenes SET {sets} WHERE id = ?", params)
        return cur.rowcount > 0

    def delete_scene(self, scene_id: int) -> bool:
        """Xoá 1 scene."""
        cur = self.execute("DELETE FROM scenes WHERE id = ?", (scene_id,))
        return cur.rowcount > 0

    # ---------------------------------------------------------------------
    # publish_queue (Publisher)
    # ---------------------------------------------------------------------

    def enqueue_publish(
        self,
        platform: str,
        channel_id: str,
        video_path: str,
        title: str = "",
        description: str = "",
        tags: Optional[List[str]] = None,
        privacy_status: str = "private",
        schedule_time: Optional[str] = None,
    ) -> int:
        """Đẩy 1 video vào hàng đợi publish. schedule_time là ISO string."""
        from datetime import datetime
        if schedule_time is None:
            schedule_time = datetime.now().isoformat(timespec="seconds")
        tags_csv = ",".join(tags or [])
        cur = self.execute(
            """
            INSERT INTO publish_queue
                (platform, channel_id, video_path, title, description,
                 tags, privacy_status, schedule_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (platform, channel_id, video_path, title, description,
             tags_csv, privacy_status, schedule_time),
        )
        return int(cur.lastrowid)

    def list_publish_queue(
        self, status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Liệt kê các task trong queue."""
        if status:
            rows = self.fetch_all(
                "SELECT * FROM publish_queue WHERE status = ? "
                "ORDER BY schedule_time ASC, id ASC",
                (status,),
            )
        else:
            rows = self.fetch_all(
                "SELECT * FROM publish_queue "
                "ORDER BY schedule_time ASC, id ASC"
            )
        return [dict(r) for r in rows]

    def update_publish_task(
        self,
        task_id: int,
        status: Optional[str] = None,
        last_error: Optional[str] = None,
        result_url: Optional[str] = None,
        increment_attempts: bool = False,
    ) -> bool:
        """Cập nhật trạng thái 1 task publish."""
        sets: List[str] = []
        params: List[Any] = []
        if status is not None:
            sets.append("status = ?")
            params.append(status)
        if last_error is not None:
            sets.append("last_error = ?")
            params.append(last_error)
        if result_url is not None:
            sets.append("result_url = ?")
            params.append(result_url)
        if increment_attempts:
            sets.append("attempts = attempts + 1")
        if not sets:
            return False
        sets.append("updated_at = CURRENT_TIMESTAMP")
        params.append(task_id)
        cur = self.execute(
            f"UPDATE publish_queue SET {', '.join(sets)} WHERE id = ?",
            tuple(params),
        )
        return cur.rowcount > 0

    # ---------------------------------------------------------------------
    # Migration: projects.json → SQLite
    # ---------------------------------------------------------------------

    def migrate_legacy_projects_json(
        self, filename: str = "projects.json"
    ) -> Dict[str, int]:
        """One-shot migration: nạp projects từ legacy JSON vào bảng SQLite.

        Idempotent: chỉ thêm project có name chưa tồn tại trong DB. Trả về
        dict thống kê {migrated, skipped, scenes_added}.
        """
        legacy = self.load_projects(filename)
        stats = {"migrated": 0, "skipped": 0, "scenes_added": 0}
        if not legacy:
            return stats

        for proj in legacy:
            name = proj.get("name") or proj.get("title") or "(no-name)"
            existing = self.fetch_one(
                "SELECT id FROM projects WHERE name = ?", (name,)
            )
            if existing:
                stats["skipped"] += 1
                continue
            mode = proj.get("mode", "manual")
            if mode not in ("manual", "auto"):
                mode = "manual"
            pid = self.create_project(name=name, mode=mode)
            stats["migrated"] += 1

            # Scenes (nếu legacy có lưu)
            scenes = proj.get("scenes") or proj.get("tasks") or []
            for idx, sc in enumerate(scenes):
                self.add_scene(
                    project_id=pid,
                    sequence_order=int(sc.get("order", idx)),
                    text_content=str(sc.get("text", sc.get("script", ""))),
                    image_prompt=str(sc.get("image_prompt", "")),
                    image_path=str(sc.get("image_path", "")),
                    audio_path=str(sc.get("audio_path", "")),
                    duration_ms=int(sc.get("duration_ms", 0)),
                    image_source=sc.get("image_source", "stock"),
                )
                stats["scenes_added"] += 1

        logger.info(
            "Legacy migration done: migrated=%d skipped=%d scenes=%d",
            stats["migrated"], stats["skipped"], stats["scenes_added"],
        )
        return stats

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

    def update_task_status(self, project_index: int, task_id: int, status: str) -> bool:
        """
        Backward-compat: cập nhật status của 1 task trong JSON storage.

        Args:
            project_index: chỉ số (0-based) của project trong list `projects.json`,
                KHÔNG phải `project_id` trong SQLite.
            task_id:       giá trị trường `id` của task trong `proj["tasks"]`.
            status:        chuỗi trạng thái mới.
        """
        projects = self.load_projects()
        if 0 <= project_index < len(projects):
            proj = projects[project_index]
            for t in proj.get("tasks", []):
                if t.get("id") == task_id:
                    t["status"] = status
                    self.save_projects(projects)
                    return True
        return False
