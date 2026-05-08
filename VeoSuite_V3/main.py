"""
VEO SUITE V3.2 — Main Entry Point
===================================
File: main.py
"""
import sys
import os
import time
import logging
from pathlib import Path

# Fix Unicode output trên Windows (cp1252 không hỗ trợ emoji)
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Thêm thư mục gốc vào Python path
sys.path.insert(0, str(Path(__file__).parent))

from PyQt6.QtWidgets import QApplication, QSplashScreen, QProgressBar, QLabel, QVBoxLayout, QWidget
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPixmap, QColor

# Import nội bộ
from database.db_manager import DatabaseManager
from services.config_manager import ConfigManager, LOGO_PATH, LOGS_DIR
from ui.main_window import MainWindow
from ui.styles import DARK_THEME_STYLESHEET


# ============================================================================
# LOGGING SETUP
# ============================================================================
def setup_logging():
    """Cấu hình logging cho toàn app."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOGS_DIR / "veo_suite.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(str(log_file), encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ]
    )


# ============================================================================
# MODERN SPLASH SCREEN
# ============================================================================
class ModernSplashScreen(QSplashScreen):
    def __init__(self, app_name, version, logo_path):
        pix = QPixmap(600, 350)
        pix.fill(QColor("#1e1e1e"))
        super().__init__(pix)

        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)

        # Logo
        if os.path.exists(logo_path):
            lbl_logo = QLabel()
            lbl_logo.setPixmap(
                QPixmap(str(logo_path)).scaled(
                    120, 120,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
            )
            lbl_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(lbl_logo)

        # Title
        lbl_title = QLabel(app_name)
        lbl_title.setStyleSheet(
            "color: #ffffff; font-size: 24px; font-weight: bold; font-family: 'Segoe UI';"
        )
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_title)

        # Version
        lbl_ver = QLabel(f"Version {version} — Enterprise Edition")
        lbl_ver.setStyleSheet("color: #7f8c8d; font-size: 14px; font-style: italic;")
        lbl_ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_ver)

        layout.addStretch()

        # Status
        self.lbl_status = QLabel("Initializing...")
        self.lbl_status.setStyleSheet("color: #bdc3c7; font-size: 12px;")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_status)
        layout.addSpacing(10)

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setFixedHeight(4)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet("""
            QProgressBar {
                background-color: #333;
                border-radius: 2px;
                border: none;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(
                    spread:pad, x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0d7377, stop:1 #14ffec
                );
                border-radius: 2px;
            }
        """)
        layout.addWidget(self.progress)

    def update_status(self, msg, percent):
        """Cập nhật trạng thái loading."""
        self.lbl_status.setText(msg)
        self.progress.setValue(percent)
        QApplication.processEvents()

    def fade_out(self):
        """Hiệu ứng Fade Out mượt."""
        self.anim = QPropertyAnimation(self, b"windowOpacity")
        self.anim.setDuration(800)
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self.anim.finished.connect(self.close)
        self.anim.start()


# ============================================================================
# STARTUP CHECKS
# ============================================================================
def check_dependencies() -> bool:
    """Kiểm tra thư viện bắt buộc."""
    try:
        import PyQt6
        import sqlite3
        return True
    except ImportError:
        return False


def initialize_database() -> DatabaseManager:
    """Khởi tạo database."""
    try:
        db = DatabaseManager()
        return db
    except Exception as e:
        logging.getLogger("VeoSuite").critical(f"Database init failed: {e}")
        sys.exit(1)


def create_application() -> QApplication:
    """Tạo QApplication."""
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("VEO SUITE")
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_THEME_STYLESHEET)
    return app


# ============================================================================
# MAIN
# ============================================================================
def main() -> int:
    # 0. Logging
    setup_logging()
    logger = logging.getLogger("VeoSuite")
    logger.info("=== VEO SUITE V3.2 Starting ===")

    # 1. Config (tạo thư mục, load .env)
    ConfigManager()

    # 2. App + Splash
    app = create_application()
    splash = ModernSplashScreen("VEO SUITE", "3.2.0", str(LOGO_PATH))
    splash.show()

    # 3. Loading steps
    splash.update_status("Checking system requirements...", 10)
    time.sleep(0.2)

    if not check_dependencies():
        logger.critical("Missing dependencies!")
        return 1

    splash.update_status("Loading core modules...", 30)
    time.sleep(0.2)

    splash.update_status("Connecting to Database...", 50)
    db = initialize_database()

    splash.update_status("Verifying integrity...", 75)
    time.sleep(0.3)

    splash.update_status("Preparing User Interface...", 90)
    time.sleep(0.2)

    try:
        main_window = MainWindow()
        splash.update_status("Ready to launch!", 100)
        time.sleep(0.2)

        main_window.show()
        splash.fade_out()

        logger.info("App launched successfully")
        return app.exec()

    except Exception as e:
        logger.critical(f"Launch failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())