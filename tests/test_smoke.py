"""Smoke tests cho Veo-Suite-V3.

Mục tiêu:
  * Đảm bảo mọi module quan trọng compile/import OK trên Python 3.11+.
  * Đảm bảo DatabaseManager khởi tạo & thread-safe ở mức cơ bản.

Các test này KHÔNG gọi UI (PyQt6) — chỉ kiểm tra logic backend.
"""
from __future__ import annotations

import importlib
import os
import sys
import threading
from pathlib import Path

import pytest

# Đảm bảo VeoSuite_V3/ nằm trong sys.path (giống main.py)
ROOT = Path(__file__).resolve().parents[1] / "VeoSuite_V3"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Compile / import smoke
# ---------------------------------------------------------------------------
IMPORTABLE_MODULES = [
    "database.db_manager",
    "services.config_manager",
    "services.render_service",
    "services.audio_service",
    "services.voice_constants",
    "services.stock_service",
    "services.thumbnail_composer",
    "services.video_assembler",
    "modules.content.constants",
    "modules.assets_factory.prompt_templates",
]


@pytest.mark.parametrize("modname", IMPORTABLE_MODULES)
def test_module_imports(modname: str) -> None:
    """Mọi module backend trọng yếu phải import được mà không lỗi cú pháp."""
    importlib.import_module(modname)


# ---------------------------------------------------------------------------
# DatabaseManager
# ---------------------------------------------------------------------------
def test_db_manager_init_and_basic(tmp_path):
    """DatabaseManager khởi tạo trên DB tạm + chạy được câu lệnh execute()."""
    db_dir = tmp_path / "database"
    db_dir.mkdir()

    from database import db_manager as dbmod

    db = dbmod.DatabaseManager(db_path=str(db_dir / "test.db"))
    assert db is not None

    # Schema phải có ít nhất các bảng cốt lõi
    rows = db.fetch_all("SELECT name FROM sqlite_master WHERE type='table'")
    table_names = {row["name"] for row in rows}
    assert {"projects", "scenes", "settings", "accounts"}.issubset(table_names)


def test_db_manager_thread_safety(tmp_path):
    """100 thread cùng ghi/đọc — không được raise SQLite thread-error."""
    from database import db_manager as dbmod

    db_path = tmp_path / "thread.db"
    db = dbmod.DatabaseManager(db_path=str(db_path))

    db.execute("CREATE TABLE IF NOT EXISTS smoke (id INTEGER PRIMARY KEY, val TEXT)")

    errors: list[BaseException] = []

    def worker(i: int):
        try:
            db.execute("INSERT INTO smoke (val) VALUES (?)", (f"v{i}",))
            db.fetch_one("SELECT COUNT(*) FROM smoke")
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"thread errors: {errors[:3]}"

    row = db.fetch_one("SELECT COUNT(*) AS c FROM smoke")
    assert row["c"] == 100


# ---------------------------------------------------------------------------
# Misc sanity
# ---------------------------------------------------------------------------
def test_no_hardcoded_pixabay_key():
    """Đảm bảo PR-1 vẫn còn — không có Pixabay key hardcoded."""
    workers = (
        ROOT / "modules" / "assets_factory" / "workers.py"
    ).read_text(encoding="utf-8", errors="replace")
    # Pixabay free keys có dạng số-chữ dài ~30 ký tự — kiểm tra loose
    assert "PIXABAY_API_KEY" not in workers or 'os.getenv("PIXABAY_API_KEY"' in workers, (
        "Pixabay key bị hardcoded lại — vui lòng dùng env/registry."
    )


def test_no_bare_except_in_db_manager():
    """Đảm bảo PR-2 vẫn còn — db_manager.py không có bare except."""
    src = (ROOT / "database" / "db_manager.py").read_text(encoding="utf-8")
    # tách comment
    code_only = "\n".join(
        line.split("#", 1)[0]
        for line in src.splitlines()
    )
    # bare 'except:' đã bị thay bằng 'except Exception:'
    import re
    bare = re.search(r"(?<![A-Za-z0-9_])except\s*:", code_only)
    assert bare is None, "Phát hiện bare 'except:' — phải dùng 'except Exception:'"
