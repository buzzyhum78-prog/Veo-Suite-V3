"""
VEO SUITE V3.2 — Config Manager (Singleton)
=============================================
Quản lý tập trung mọi cấu hình hệ thống:
- Đọc biến môi trường từ .env
- Đọc/ghi settings.json (tuỳ chỉnh runtime)
- Cung cấp path constants cho toàn bộ app
- Singleton: Gọi ConfigManager() ở đâu cũng trả về cùng 1 instance
"""

import json
import logging
import os
from pathlib import Path

# Thử load .env nếu có python-dotenv
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger("VeoSuite.Config")

# ============================================================================
# ĐƯỜNG DẪN CỐ ĐỊNH (Tính từ thư mục gốc project)
# ============================================================================
# Thư mục gốc project = cha của thư mục chứa file này (services/)
ROOT_DIR = Path(__file__).parent.parent.resolve()

# Cấu hình
CONFIG_DIR = ROOT_DIR / "config"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
AI_REGISTRY_FILE = CONFIG_DIR / "ai_registry.json"

# Dữ liệu runtime
VEO_DB_DIR = ROOT_DIR / os.getenv("DATABASE_FOLDER", "VEO_DB")
OUTPUT_DIR = ROOT_DIR / os.getenv("OUTPUT_FOLDER", "VEO_DB/output_media")

# Database
DATABASE_DIR = ROOT_DIR / "database"
DATABASE_FILE = DATABASE_DIR / "veo_suite.db"

# Assets
ASSETS_DIR = ROOT_DIR / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
OVERLAYS_DIR = ASSETS_DIR / "overlays"
LOGO_PATH = ASSETS_DIR / "Logo_veo.png"

# Temp
TEMP_DIR = ROOT_DIR / "VEO_TEMP"

# Logs
LOGS_DIR = ROOT_DIR / "logs"

# FFmpeg
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg.exe")
FFPROBE_PATH = os.getenv("FFPROBE_PATH", "ffprobe.exe")

# Voice config (do Admin Tab tạo ra)
VOICE_CONFIG_FILE = VEO_DB_DIR / "voice_engine_config.json"
PROXY_CONFIG_FILE = VEO_DB_DIR / "proxy_config.json"
VPN_CONFIG_FILE = VEO_DB_DIR / "config.json"

# ============================================================================
# DEFAULT SETTINGS
# ============================================================================
DEFAULT_SETTINGS = {
    "output_folder": str(OUTPUT_DIR),
    "database_folder": str(VEO_DB_DIR),
    "app_theme": "Dark",
    "output_resolution": "1920x1080",
    "output_fps": "30",
    "app_version": "3.2.0",
}


class ConfigManager:
    """
    Singleton quản lý cấu hình hệ thống.

    Usage:
        from services.config_manager import ConfigManager
        cfg = ConfigManager()
        theme = cfg.get("app_theme", "Dark")
        cfg.set("app_theme", "Light")
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._ensure_directories()
        self._load_config()

    def _ensure_directories(self):
        """Tạo các thư mục cần thiết nếu chưa có."""
        for d in [
            CONFIG_DIR,
            VEO_DB_DIR,
            OUTPUT_DIR,
            DATABASE_DIR,
            ASSETS_DIR,
            FONTS_DIR,
            OVERLAYS_DIR,
            TEMP_DIR,
            LOGS_DIR,
        ]:
            d.mkdir(parents=True, exist_ok=True)

    def _load_config(self):
        """Tải cấu hình từ settings.json, merge với defaults."""
        if SETTINGS_FILE.exists():
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                # Merge: defaults làm nền, saved đè lên
                self.config = {**DEFAULT_SETTINGS, **saved}
            except (OSError, json.JSONDecodeError) as e:
                logger.warning(f"Settings file lỗi, dùng defaults: {e}")
                self.config = dict(DEFAULT_SETTINGS)
                self._save_config()
        else:
            self.config = dict(DEFAULT_SETTINGS)
            self._save_config()

    def _save_config(self):
        """Ghi cấu hình xuống settings.json."""
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except OSError as e:
            logger.error(f"Không thể lưu settings: {e}")

    def get(self, key: str, default=""):
        """Lấy giá trị cấu hình."""
        return self.config.get(key, default)

    def set(self, key: str, value):
        """Cập nhật và lưu cấu hình."""
        self.config[key] = value
        self._save_config()

    def reload(self):
        """Đọc lại từ file (nếu bị sửa bên ngoài)."""
        self._load_config()
