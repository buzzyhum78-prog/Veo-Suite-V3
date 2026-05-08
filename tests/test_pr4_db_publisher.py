"""Tests cho PR-4: native SQLite CRUD, JSON migration, publish_queue + scheduler.

Không chạm UI/PyQt6, không cần Internet.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1] / "VeoSuite_V3"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Native CRUD
# ---------------------------------------------------------------------------
def test_project_scene_crud(tmp_path):
    from database import db_manager as dbmod

    db = dbmod.DatabaseManager(db_path=str(tmp_path / "crud.db"))

    pid = db.create_project("My First Project", mode="auto")
    assert isinstance(pid, int) and pid > 0

    proj = db.get_project(pid)
    assert proj is not None
    assert proj["name"] == "My First Project"
    assert proj["mode"] == "auto"
    assert proj["status"] == "draft"

    s1 = db.add_scene(pid, sequence_order=0, text_content="Hello",
                      image_prompt="a cat", duration_ms=3000)
    s2 = db.add_scene(pid, sequence_order=1, text_content="World")
    assert s1 != s2

    scenes = db.list_scenes(pid)
    assert len(scenes) == 2
    assert scenes[0]["text_content"] == "Hello"
    assert scenes[1]["sequence_order"] == 1

    assert db.update_scene(s1, text_content="Hi", duration_ms=5000)
    sc = db.fetch_one("SELECT * FROM scenes WHERE id = ?", (s1,))
    assert sc["text_content"] == "Hi"
    assert sc["duration_ms"] == 5000

    assert db.update_project(pid, status="rendering")
    assert db.get_project(pid)["status"] == "rendering"

    # Bỏ qua trường lạ
    assert db.update_project(pid, foo="bar") is False

    assert db.delete_scene(s2)
    assert len(db.list_scenes(pid)) == 1

    # Cascade
    assert db.delete_project(pid)
    assert db.get_project(pid) is None
    assert db.list_scenes(pid) == []


# ---------------------------------------------------------------------------
# Legacy migration
# ---------------------------------------------------------------------------
def test_legacy_projects_json_migration(tmp_path):
    from database import db_manager as dbmod

    db = dbmod.DatabaseManager(db_path=str(tmp_path / "mig.db"))

    # Bịa file projects.json kiểu cũ vào VEO_DB
    veo_db = Path(db.db_folder)
    veo_db.mkdir(parents=True, exist_ok=True)
    legacy = [
        {
            "name": "Old Project A",
            "mode": "manual",
            "scenes": [
                {"order": 0, "text": "scene1", "image_prompt": "p1", "duration_ms": 1000},
                {"order": 1, "text": "scene2", "image_prompt": "p2", "duration_ms": 2000},
            ],
        },
        {
            "name": "Old Project B",
            "mode": "garbage_value",  # phải fallback về 'manual'
            "tasks": [],
        },
    ]
    (veo_db / "projects.json").write_text(json.dumps(legacy), encoding="utf-8")

    stats = db.migrate_legacy_projects_json("projects.json")
    assert stats == {"migrated": 2, "skipped": 0, "scenes_added": 2}

    projects = db.list_projects()
    names = {p["name"] for p in projects}
    assert names == {"Old Project A", "Old Project B"}
    proj_b = next(p for p in projects if p["name"] == "Old Project B")
    assert proj_b["mode"] == "manual"   # đã sanitize

    # Idempotent
    stats2 = db.migrate_legacy_projects_json("projects.json")
    assert stats2 == {"migrated": 0, "skipped": 2, "scenes_added": 0}


# ---------------------------------------------------------------------------
# Publish queue + scheduler
# ---------------------------------------------------------------------------
def test_publish_queue_crud(tmp_path):
    from database import db_manager as dbmod

    db = dbmod.DatabaseManager(db_path=str(tmp_path / "q.db"))

    tid = db.enqueue_publish(
        platform="youtube", channel_id="ch1",
        video_path="/tmp/test.mp4",
        title="hello", description="d", tags=["a", "b"],
    )
    assert tid > 0

    rows = db.list_publish_queue()
    assert len(rows) == 1
    row = rows[0]
    assert row["platform"] == "youtube"
    assert row["status"] == "pending"
    assert row["tags"] == "a,b"

    assert db.update_publish_task(tid, status="running")
    assert db.list_publish_queue(status="running")[0]["id"] == tid

    assert db.update_publish_task(
        tid, status="done", result_url="https://yt/x",
        increment_attempts=True,
    )
    done = db.list_publish_queue(status="done")[0]
    assert done["result_url"] == "https://yt/x"
    assert done["attempts"] == 1


def test_scheduler_dispatches_to_uploader(tmp_path):
    from database import db_manager as dbmod
    from modules.publisher.scheduler import PublishScheduler

    db = dbmod.DatabaseManager(db_path=str(tmp_path / "sched.db"))

    # Tạo file giả để uploader nhận video_path tồn tại nếu cần (không bắt buộc)
    fake_video = tmp_path / "v.mp4"
    fake_video.write_bytes(b"fake")

    fake_uploader = MagicMock()
    fake_uploader.upload_video.return_value = (True, "https://yt/abc")

    scheduler = PublishScheduler(
        db_manager=db,
        uploaders={"youtube": fake_uploader},
        poll_seconds=1,
    )

    # Lên lịch quá khứ → tick xử lý ngay
    tid = scheduler.add_to_queue(
        platform="youtube", channel_id="ch1",
        video_path=str(fake_video), title="t", description="d",
        tags=["x"], schedule_time="2000-01-01T00:00:00",
    )

    scheduler._tick()  # gọi trực tiếp, không cần thread

    fake_uploader.upload_video.assert_called_once()
    rows = db.list_publish_queue()
    assert rows[0]["status"] == "done"
    assert rows[0]["result_url"] == "https://yt/abc"
    assert rows[0]["attempts"] == 1
    assert rows[0]["id"] == tid


def test_scheduler_retries_on_failure(tmp_path):
    from database import db_manager as dbmod
    from modules.publisher.scheduler import MAX_ATTEMPTS, PublishScheduler

    db = dbmod.DatabaseManager(db_path=str(tmp_path / "retry.db"))

    fake_uploader = MagicMock()
    fake_uploader.upload_video.return_value = (False, "boom")

    scheduler = PublishScheduler(
        db_manager=db, uploaders={"youtube": fake_uploader}, poll_seconds=1,
    )

    scheduler.add_to_queue(
        platform="youtube", channel_id="ch1",
        video_path="/tmp/x.mp4", title="t",
        schedule_time="2000-01-01T00:00:00",
    )

    # Tick MAX_ATTEMPTS lần — task phải chuyển sang 'failed'
    for _ in range(MAX_ATTEMPTS):
        scheduler._tick()

    rows = db.list_publish_queue()
    assert rows[0]["status"] == "failed"
    assert rows[0]["attempts"] == MAX_ATTEMPTS
    assert "boom" in (rows[0]["last_error"] or "")


def test_scheduler_unknown_platform(tmp_path):
    from database import db_manager as dbmod
    from modules.publisher.scheduler import PublishScheduler

    db = dbmod.DatabaseManager(db_path=str(tmp_path / "unk.db"))
    scheduler = PublishScheduler(db_manager=db, uploaders={}, poll_seconds=1)
    scheduler.add_to_queue(
        platform="tiktok", channel_id="ch", video_path="/tmp/x.mp4",
        schedule_time="2000-01-01T00:00:00",
    )
    scheduler._tick()
    row = db.list_publish_queue()[0]
    assert row["status"] == "failed"
    assert "No uploader" in (row["last_error"] or "")


# ---------------------------------------------------------------------------
# YouTubeUploader (mock mode — google-api có thể chưa cài)
# ---------------------------------------------------------------------------
def test_youtube_uploader_mock_mode(tmp_path):
    from modules.publisher.youtube_uploader import YouTubeUploader

    up = YouTubeUploader(token_dir=str(tmp_path), mock=True)
    assert up.mock is True

    # Auth (mock) phải pass
    assert up.authenticate_channel("ch1", client_secret_path="/non/existent.json")

    # Upload với file không tồn tại → fail
    ok, msg = up.upload_video("ch1", "/no/such/video.mp4", "t")
    assert ok is False
    assert "not found" in msg.lower() or "not found" in msg

    # Upload với file thật giả (any file) → mock trả URL
    f = tmp_path / "f.mp4"
    f.write_bytes(b"x")
    ok, msg = up.upload_video("ch1", str(f), "t", description="d", tags=["a"])
    assert ok is True
    assert msg.startswith("https://youtube.com/")


@pytest.mark.skipif(
    "modules.publisher.youtube_uploader" not in sys.modules
    and not Path(ROOT, "modules/publisher/youtube_uploader.py").exists(),
    reason="youtube_uploader missing",
)
def test_youtube_uploader_unauthenticated_fails():
    from modules.publisher.youtube_uploader import YouTubeUploader

    up = YouTubeUploader(mock=True)
    # Chưa authenticate → không upload được
    ok, msg = up.upload_video("nope", "/tmp/x.mp4", "t")
    assert ok is False
    # vẫn báo file not found trước (priority cao hơn auth check theo thứ tự code)
    assert "not found" in msg.lower() or "authenticate" in msg.lower()
