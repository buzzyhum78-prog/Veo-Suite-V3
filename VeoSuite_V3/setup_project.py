"""
VEO SUITE V3.2 — Project Structure Initializer
================================================
Tự động khởi tạo cấu trúc thư mục cho dự án.
Chạy 1 lần khi setup project mới: python setup_project.py

LƯU Ý: Database logic nằm ở database/db_manager.py (KHÔNG trùng lặp ở đây).
"""

import sys
from pathlib import Path

# Fix Windows Unicode
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass


# Cấu trúc thư mục chuẩn
FOLDER_STRUCTURE = [
    "assets/fonts",
    "assets/overlays/Stickers",
    "assets/overlays/VFX",
    "assets/overlays/Arrows",
    "assets/overlays/Badges",
    "config",
    "database",
    "logs",
    "modules/radar",
    "modules/content",
    "modules/assets_factory",
    "modules/render",
    "modules/publisher",
    "modules/ops",
    "services",
    "ui/widgets",
    "utils",
    "VEO_DB",
    "VEO_TEMP",
]

# Các thư mục cần __init__.py
PYTHON_PACKAGES = [
    "modules/radar",
    "modules/content",
    "modules/assets_factory",
    "modules/render",
    "modules/publisher",
    "modules/ops",
    "services",
    "ui",
    "ui/widgets",
    "utils",
]


def create_structure(base_path: str = ".") -> bool:
    """Tạo cấu trúc thư mục cho dự án."""
    try:
        base = Path(base_path)

        for folder in FOLDER_STRUCTURE:
            folder_path = base / folder
            folder_path.mkdir(parents=True, exist_ok=True)
            print(f"  ✓ {folder}/")

        for pkg in PYTHON_PACKAGES:
            init_file = base / pkg / "__init__.py"
            if not init_file.exists():
                init_file.write_text(f'"""{pkg} module"""\n', encoding="utf-8")

        print(f"\n✓ Hoàn tất khởi tạo cấu trúc dự án tại: {base.absolute()}")
        return True

    except Exception as e:
        print(f"✗ Lỗi khi tạo cấu trúc: {repr(e)}")
        return False


def initialize_project() -> None:
    """Hàm chính: Khởi tạo thư mục + kiểm tra database."""
    print("=" * 60)
    print("VEO SUITE V3.2 — PROJECT INITIALIZATION")
    print("=" * 60)
    print()

    # Bước 1: Cấu trúc thư mục
    print("[1/2] Đang tạo cấu trúc thư mục...")
    if not create_structure():
        print("✗ Không thể tạo cấu trúc thư mục!")
        return

    print()

    # Bước 2: Kiểm tra Database
    print("[2/2] Đang kiểm tra database...")
    try:
        from database.db_manager import DatabaseManager
        db = DatabaseManager()
        if db.check_db_integrity():
            stats = db.get_stats()
            print(f"  ✓ Database OK — {stats}")
        else:
            print("  ✗ Database integrity check failed!")
        db.close()
    except Exception as e:
        print(f"  ✗ Lỗi database: {e}")

    print()
    print("=" * 60)
    print("✓ KHỞI TẠO HOÀN TẤT")
    print("  Chạy app: python main.py")
    print("=" * 60)


if __name__ == "__main__":
    initialize_project()