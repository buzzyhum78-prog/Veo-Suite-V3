"""
VEO SUITE V3.2 — Main Entry Point
===================================
File: main.py
"""

import logging
import os
import sys
from pathlib import Path

# Fix Unicode output trên Windows (cp1252 không hỗ trợ emoji)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Thêm thư mục gốc vào Python path
sys.path.insert(0, str(Path(__file__).parent))

# Import nội bộ
from database.db_manager import DatabaseManager
from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QApplication, QLabel, QProgressBar, QSplashScreen, QVBoxLayout
from services.config_manager import LOGO_PATH, LOGS_DIR, ConfigManager
from ui.main_window import MainWindow
from ui.styles import DARK_THEME_STYLESHEET


# ============================================================================
# LOGGING SETUP
# ============================================================================
def setup_logging():
    """Cấu hình logging cho toàn app với rotating file (10 MB × 5 file)."""
    from logging.handlers import RotatingFileHandler

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOGS_DIR / "veo_suite.log"

    fmt = logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        str(log_file),
        maxBytes=10 * 1024 * 1024,  # 10 MB / file
        backupCount=5,  # giữ 5 file cũ
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # Tránh tích luỹ handler khi setup_logging được gọi lại
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)


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
                    120, 120, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
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
    from importlib.util import find_spec

    return all(find_spec(mod) is not None for mod in ("PyQt6", "sqlite3"))


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
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
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

    # 2. App + Splash (non-blocking — splash steps run via QTimer
    #    instead of time.sleep() so the GUI thread stays responsive).
    app = create_application()
    splash = ModernSplashScreen("VEO SUITE", "3.2.0", str(LOGO_PATH))
    splash.show()

    if not check_dependencies():
        logger.critical("Missing dependencies!")
        return 1

    state: dict = {"db": None, "main_window": None, "exit_code": 0}

    # Mỗi step là (label, percent, action) — action có thể là None.
    steps = [
        ("Checking system requirements...", 10, None),
        ("Loading core modules...", 30, None),
        ("Connecting to Database...", 50, lambda: state.update(db=initialize_database())),
        ("Verifying integrity...", 75, None),
        ("Preparing User Interface...", 90, lambda: state.update(main_window=MainWindow())),
        ("Ready to launch!", 100, None),
    ]

    step_iter = iter(steps)

    def run_next_step() -> None:
        try:
            label, pct, action = next(step_iter)
        except StopIteration:
            # Tất cả steps xong → show window + fade splash.
            try:
                window = state["main_window"]
                if window is None:
                    raise RuntimeError("MainWindow was not initialized")
                window.show()
                splash.fade_out()
                logger.info("App launched successfully")
            except Exception as exc:
                logger.critical("Launch failed: %s", exc, exc_info=True)
                state["exit_code"] = 1
                app.quit()
            return

        splash.update_status(label, pct)
        if action is not None:
            try:
                action()
            except Exception as exc:
                logger.critical("Splash step '%s' failed: %s", label, exc, exc_info=True)
                state["exit_code"] = 1
                app.quit()
                return

        # 200ms giữa các step — non-blocking (không chặn event loop).
        QTimer.singleShot(200, run_next_step)

    QTimer.singleShot(0, run_next_step)

    rc = app.exec()
    return state["exit_code"] or rc


if __name__ == "__main__":
    sys.exit(main())
