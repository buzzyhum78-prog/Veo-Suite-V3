"""
VEO SUITE V3.2 — Diagnostic Tool (Bác Sĩ VEO)
=================================================
Chạy: python bac_si_veo.py
Kiểm tra nhanh mọi thành phần của hệ thống.
"""

import sys
import os

# Fix encoding
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

print("=" * 50)
print("🚑 BÁC SĨ VEO ĐANG KHÁM BỆNH...")
print("=" * 50)


def check_step(step_name, func):
    print(f"👉 {step_name}...", end=" ")
    try:
        func()
        print("✅ OK")
        return True
    except Exception as e:
        print(f"❌ LỖI: {e}")
        return False


# --- CÁC BƯỚC KIỂM TRA ---

def check_python():
    ver = sys.version.split()[0]
    print(f"(Python {ver})", end=" ")
    assert int(ver.split(".")[0]) >= 3, "Cần Python 3+"


def check_core_libs():
    import PyQt6.QtWidgets
    import sqlite3
    import requests
    import PIL


def check_edge_tts():
    import edge_tts


def check_files():
    required = [
        "main.py",
        "ui/main_window.py",
        "ui/widgets/media_tab.py",
        "ui/widgets/radar_tab.py",
        "ui/widgets/content_tab.py",
        "ui/widgets/editor_tab.py",
        "services/ai_factory.py",
        "services/audio_service.py",
        "services/config_manager.py",
        "database/db_manager.py",
    ]
    missing = [f for f in required if not os.path.exists(f)]
    if missing:
        raise FileNotFoundError(f"Thiếu: {', '.join(missing)}")


def check_database():
    from database.db_manager import DatabaseManager
    db = DatabaseManager()
    assert db.check_db_integrity(), "Database integrity check failed!"
    stats = db.get_stats()
    print(f"(Projects: {stats['total_projects']}, Size: {stats['db_size_mb']}MB)", end=" ")
    db.close()


def check_config():
    from services.config_manager import ConfigManager, ROOT_DIR, LOGO_PATH
    cfg = ConfigManager()
    theme = cfg.get("app_theme", "Dark")
    print(f"(Theme: {theme}, Root: {ROOT_DIR})", end=" ")


def check_ai_factory():
    from services.ai_factory import AIFactory
    ai = AIFactory()
    providers = list(ai.registry.get("providers", {}).keys())
    print(f"({len(providers)} providers)", end=" ")


def check_media_tab():
    from ui.widgets.media_tab import MediaTab
    print("(Import OK)", end=" ")


# --- CHẠY CHẨN ĐOÁN ---
print()
results = []
results.append(check_step("Phiên bản Python", check_python))
results.append(check_step("File hệ thống", check_files))

print("\n--- THƯ VIỆN ---")
results.append(check_step("Core (PyQt6, requests, Pillow)", check_core_libs))
results.append(check_step("Edge TTS", check_edge_tts))

print("\n--- SERVICES ---")
results.append(check_step("Config Manager", check_config))
results.append(check_step("Database", check_database))
results.append(check_step("AI Factory", check_ai_factory))

print("\n--- GIAO DIỆN ---")
results.append(check_step("Import MediaTab", check_media_tab))

# --- KẾT LUẬN ---
print("\n" + "=" * 50)
passed = sum(results)
total = len(results)
if passed == total:
    print(f"✅ TẤT CẢ {total}/{total} BƯỚC ĐỀU OK!")
    print("🎉 Hệ thống khoẻ mạnh. Chạy: python main.py")
else:
    print(f"⚠️ {passed}/{total} bước OK — {total - passed} bước LỖI")
    print("Kiểm tra lỗi ở trên và khắc phục trước khi chạy main.py")

print("=" * 50)
input("\nBấm Enter để thoát...")