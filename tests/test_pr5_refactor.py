"""Tests cho PR-5: account CRUD, FFmpeg builder, OpsTab refresh, audio dispatch.

Không chạm subprocess thật, không cần ffmpeg/google-api/Internet.
Smoke tests chạy được trên CI headless (``QT_QPA_PLATFORM=offscreen``).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1] / "VeoSuite_V3"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ---------------------------------------------------------------------------
# Account CRUD
# ---------------------------------------------------------------------------
def test_accounts_crud_roundtrip(tmp_path):
    from database import db_manager as dbmod

    db = dbmod.DatabaseManager(db_path=str(tmp_path / "acc.db"))

    aid = db.create_account(
        platform="youtube",
        username="keto-us-daily",
        cookies="ck=1",
        proxy="192.168.1.10:8080",
        status="money",
        notes="health niche",
    )
    assert isinstance(aid, int) and aid > 0

    rows = db.list_accounts()
    assert len(rows) == 1
    assert rows[0]["username"] == "keto-us-daily"
    assert rows[0]["status"] == "money"

    # Filter platform/status
    assert db.list_accounts(platform="youtube") and not db.list_accounts(platform="tiktok")
    assert db.list_accounts(status="money") and not db.list_accounts(status="burn")

    assert db.update_account(aid, status="burn", notes="strike-1")
    row = db.list_accounts()[0]
    assert row["status"] == "burn"
    assert row["notes"] == "strike-1"

    # field lạ → bỏ qua
    assert db.update_account(aid, foo="bar") is False

    assert db.delete_account(aid)
    assert db.list_accounts() == []


# ---------------------------------------------------------------------------
# FFmpegCommandBuilder
# ---------------------------------------------------------------------------
def test_ffmpeg_builder_basic_slideshow():
    from services.ffmpeg_builder import FFmpegPresets

    cmd = FFmpegPresets.slideshow(
        ffmpeg="ffmpeg",
        images=["a.png", "b.png"],
        audio_path="voice.mp3",
        output_path="out.mp4",
        duration_per_image=3.0,
        audio_duration=6.0,
        resolution="1280x720",
    )
    assert cmd[0] == "ffmpeg"
    assert "-y" in cmd
    assert cmd.count("-loop") == 2
    assert cmd.count("-i") == 3  # 2 ảnh + 1 audio
    assert "-c:v" in cmd and "libx264" in cmd
    assert "-pix_fmt" in cmd and "yuv420p" in cmd
    assert "-shortest" in cmd
    assert cmd[-1] == "out.mp4"


def test_ffmpeg_builder_validation_errors():
    from services.ffmpeg_builder import FFmpegCommandBuilder

    b = FFmpegCommandBuilder()
    with pytest.raises(ValueError):
        b.build()
    b.add_input("a.png", loop=True, duration=1)
    with pytest.raises(ValueError):
        b.build()  # vẫn thiếu output
    b.output("o.mp4")
    cmd = b.build()
    assert "-y" in cmd and cmd[-1] == "o.mp4"


def test_ffmpeg_builder_concat_clips_command():
    from services.ffmpeg_builder import FFmpegPresets

    cmd = FFmpegPresets.concat_clips(
        ffmpeg="ffmpeg", list_file="list.txt", audio_path="a.mp3",
        output_path="out.mp4", resolution="1920x1080",
    )
    assert "-f" in cmd and "concat" in cmd
    assert cmd[-1] == "out.mp4"


def test_ffmpeg_builder_mix_music():
    from services.ffmpeg_builder import FFmpegPresets

    cmd = FFmpegPresets.mix_background_music(
        ffmpeg="ffmpeg", video_path="v.mp4", music_path="m.mp3",
        output_path="o.mp4", volume=0.2, ducking=True,
    )
    assert "sidechaincompress" in " ".join(cmd)
    cmd2 = FFmpegPresets.mix_background_music(
        ffmpeg="ffmpeg", video_path="v.mp4", music_path="m.mp3",
        output_path="o.mp4", volume=0.2, ducking=False,
    )
    assert "sidechaincompress" not in " ".join(cmd2)


def test_ffmpeg_builder_burn_subtitle_escapes_path():
    from services.ffmpeg_builder import FFmpegPresets

    cmd = FFmpegPresets.burn_subtitle(
        ffmpeg="ffmpeg", video_path="v.mp4", srt_path="C:/a/b.srt",
        output_path="out.mp4",
    )
    joined = " ".join(cmd)
    assert "subtitles=" in joined
    assert "C\\:/a/b.srt" in joined  # ":" được escape


def test_ffmpeg_builder_resolution_fallback():
    from services.ffmpeg_builder import FFmpegPresets

    assert FFmpegPresets.parse_resolution("garbage") == (1920, 1080)
    assert FFmpegPresets.parse_resolution("1280X720") == (1280, 720)


# ---------------------------------------------------------------------------
# audio_async dispatch (no real ffmpeg)
# ---------------------------------------------------------------------------
def test_audio_dispatch_unknown_kind():
    from services.audio_async import AudioJob, execute_job

    res = execute_job(AudioJob(kind="not-a-real-kind"))
    assert res.ok is False
    assert "unknown kind" in (res.error or "")


def test_audio_dispatch_calls_handler():
    from services import audio_async

    job = audio_async.AudioJob(kind="probe", payload={"path": "/no/such.mp3"})
    res = audio_async.execute_job(job)
    # path không tồn tại → handler raise FileNotFoundError → ok=False
    assert res.ok is False
    assert "/no/such.mp3" in (res.error or "")


def test_audio_register_custom_handler():
    from services import audio_async

    @audio_async.register_handler("custom-test")
    def _h(p):
        return audio_async.AudioJobResult(job_id="", ok=True,
                                          info={"x": p.get("x", 0) * 2})

    res = audio_async.execute_job(audio_async.AudioJob(kind="custom-test", payload={"x": 21}))
    assert res.ok and res.info["x"] == 42


# ---------------------------------------------------------------------------
# OpsTab refresh — sử dụng QApplication offscreen
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def qapp():
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 not installed")
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


class _StubDB:
    """Mini DB stub trả accounts có sẵn."""

    def __init__(self, accounts):
        self._accounts = accounts

    def list_accounts(self, platform=None, status=None):
        return list(self._accounts)


def test_ops_tab_refreshes_from_db(qapp):
    from ui.widgets.ops_tab import OpsTab

    accounts = [
        {"id": 1, "platform": "youtube", "username": "ch-money",
         "status": "money", "proxy": "1.1.1.1", "notes": "n1"},
        {"id": 2, "platform": "tiktok", "username": "ch-burn",
         "status": "burn", "proxy": None, "notes": None},
        {"id": 3, "platform": "youtube", "username": "ch-warm",
         "status": "warmup", "proxy": "", "notes": ""},
    ]
    tab = OpsTab(db=_StubDB(accounts))
    # Bảng phải có 3 dòng
    assert tab.table_channels.rowCount() == 3
    # Stat cards phải hiển thị tổng/active/burn
    assert tab._card_total.text() == "3"
    assert tab._card_active.text() == "1"
    assert tab._card_alert.text() == "1"


def test_ops_tab_handles_missing_db(qapp):
    """Không truyền DB → vẫn render, bảng rỗng, không crash."""
    from ui.widgets.ops_tab import OpsTab

    tab = OpsTab(db=None)
    assert tab.table_channels.rowCount() == 0
    assert tab._card_total.text() == "0"


def test_ops_tab_handles_db_error(qapp):
    """DB.list_accounts ném exception → vẫn render, log lỗi, không crash."""
    from ui.widgets.ops_tab import OpsTab

    class BadDB:
        def list_accounts(self, **kw):
            raise RuntimeError("DB exploded")

    tab = OpsTab(db=BadDB())
    assert tab.table_channels.rowCount() == 0
