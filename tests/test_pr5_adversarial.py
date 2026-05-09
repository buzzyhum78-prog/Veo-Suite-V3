"""Adversarial tests for PR-5 (NOT committed — verification only).

These tests go beyond the existing happy-path unit tests in
``test_pr5_refactor.py``: every assertion is designed so that a reverted /
broken PR-5 implementation would fail it.

Run with::

    QT_QPA_PLATFORM=offscreen python -m pytest tests/test_pr5_adversarial.py -v
"""

from __future__ import annotations

import ast
import logging
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1] / "VeoSuite_V3"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ---------------------------------------------------------------------------
# FFmpeg detection + fixture media synthesis
# ---------------------------------------------------------------------------
import shutil

PR5_FIXTURES = Path("/tmp/pr5")
FFMPEG = shutil.which("ffmpeg") or "/usr/bin/ffmpeg"
FFPROBE = shutil.which("ffprobe") or "/usr/bin/ffprobe"
HAS_FFMPEG = bool(shutil.which("ffmpeg")) and bool(shutil.which("ffprobe"))

requires_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not available on PATH")


def _run_ffmpeg(cmd: list[str]) -> None:
    """Run an ffmpeg fixture-creation command, surfacing stderr on failure."""
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:  # pragma: no cover — fixture build failure
        raise RuntimeError(f"ffmpeg fixture build failed: {' '.join(cmd[:3])}...\n{proc.stderr[-500:]}")


@pytest.fixture(scope="session", autouse=True)
def _build_pr5_fixtures():
    """Idempotently materialise the /tmp/pr5 media fixtures.

    Created with ``ffmpeg`` lavfi sources so the suite has zero dependency on
    external sample files. If ``ffmpeg`` isn't on PATH the body is a no-op
    and downstream tests that need media will skip via ``requires_ffmpeg``.
    """
    if not HAS_FFMPEG:
        return
    PR5_FIXTURES.mkdir(parents=True, exist_ok=True)
    img_a = PR5_FIXTURES / "img_a.png"
    img_b = PR5_FIXTURES / "img_b.png"
    voice = PR5_FIXTURES / "voice.mp3"
    music = PR5_FIXTURES / "music.mp3"
    clip_a = PR5_FIXTURES / "clip_a.mp4"
    clip_b = PR5_FIXTURES / "clip_b.mp4"
    list_txt = PR5_FIXTURES / "list.txt"
    sub_srt = PR5_FIXTURES / "sub.srt"
    padded = PR5_FIXTURES / "padded.mp3"

    if not img_a.exists():
        _run_ffmpeg(
            [FFMPEG, "-y", "-f", "lavfi", "-i", "color=c=red:s=1280x720:d=0.04", "-frames:v", "1", str(img_a)]
        )
    if not img_b.exists():
        _run_ffmpeg(
            [
                FFMPEG,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=1280x720:d=0.04",
                "-frames:v",
                "1",
                str(img_b),
            ]
        )
    if not voice.exists():
        _run_ffmpeg(
            [
                FFMPEG,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=6",
                "-ar",
                "44100",
                "-ac",
                "2",
                str(voice),
            ]
        )
    if not music.exists():
        _run_ffmpeg(
            [
                FFMPEG,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "aevalsrc=sin(220*2*PI*t):duration=30",
                "-ar",
                "44100",
                "-ac",
                "2",
                str(music),
            ]
        )
    if not clip_a.exists():
        _run_ffmpeg(
            [
                FFMPEG,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=green:s=1280x720:d=5",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=330:duration=5",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                str(clip_a),
            ]
        )
    if not clip_b.exists():
        _run_ffmpeg(
            [
                FFMPEG,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=yellow:s=1280x720:d=4",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=550:duration=4",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                str(clip_b),
            ]
        )
    if not list_txt.exists():
        list_txt.write_text(f"file '{clip_a}'\nfile '{clip_b}'\n")
    if not sub_srt.exists():
        sub_srt.write_text(
            "1\n00:00:00,500 --> 00:00:02,500\nHello PR-5\n\n2\n00:00:03,000 --> 00:00:04,500\nBurn-in test\n"
        )
    if not padded.exists():
        # 3s silence + 6s tone + 3s silence = 12s
        _run_ffmpeg(
            [
                FFMPEG,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "aevalsrc=0:duration=3",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=6",
                "-f",
                "lavfi",
                "-i",
                "aevalsrc=0:duration=3",
                "-filter_complex",
                "[0:a][1:a][2:a]concat=n=3:v=0:a=1[out]",
                "-map",
                "[out]",
                "-ar",
                "44100",
                "-ac",
                "2",
                str(padded),
            ]
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ffprobe_streams(path: str) -> list[dict[str, str]]:
    """Return list of stream dicts via ffprobe -show_streams."""
    res = subprocess.run(
        [
            FFPROBE,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    import json

    return json.loads(res.stdout)


def _duration(path: str) -> float:
    res = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(res.stdout.strip())


# ===========================================================================
# T1 — Accounts CRUD invariants
# ===========================================================================
class TestT1AccountsCRUD:
    @pytest.fixture
    def db(self, tmp_path):
        from database import db_manager as dbmod

        return dbmod.DatabaseManager(db_path=str(tmp_path / "t1.db"))

    def test_t1_1_create_two_distinct_ids(self, db):
        aid1 = db.create_account(platform="youtube", username="u1", status="money")
        aid2 = db.create_account(platform="tiktok", username="u2", status="burn")
        assert isinstance(aid1, int) and aid1 > 0
        assert isinstance(aid2, int) and aid2 > 0
        assert aid1 != aid2

    def test_t1_2_list_all_two_rows(self, db):
        db.create_account(platform="youtube", username="u1", status="money")
        db.create_account(platform="tiktok", username="u2", status="burn")
        rows = db.list_accounts()
        assert len(rows) == 2
        assert {r["username"] for r in rows} == {"u1", "u2"}

    def test_t1_3_filter_platform_youtube(self, db):
        db.create_account(platform="youtube", username="u1", status="money")
        db.create_account(platform="tiktok", username="u2", status="burn")
        rows = db.list_accounts(platform="youtube")
        assert len(rows) == 1 and rows[0]["username"] == "u1"

    def test_t1_4_filter_platform_tiktok(self, db):
        db.create_account(platform="youtube", username="u1", status="money")
        db.create_account(platform="tiktok", username="u2", status="burn")
        rows = db.list_accounts(platform="tiktok")
        assert len(rows) == 1 and rows[0]["username"] == "u2"

    def test_t1_5_filter_status_money(self, db):
        db.create_account(platform="youtube", username="u1", status="money")
        db.create_account(platform="tiktok", username="u2", status="burn")
        rows = db.list_accounts(status="money")
        assert len(rows) == 1 and rows[0]["username"] == "u1"

    def test_t1_6_filter_status_nonexistent(self, db):
        db.create_account(platform="youtube", username="u1", status="money")
        rows = db.list_accounts(status="totally-not-a-status")
        assert rows == []

    def test_t1_7_update_two_fields(self, db):
        aid = db.create_account(platform="youtube", username="u1", status="money", notes="orig")
        ok = db.update_account(aid, status="warmup", notes="rotated")
        assert ok is True
        row = db.list_accounts()[0]
        assert row["status"] == "warmup"
        assert row["notes"] == "rotated"
        assert row["username"] == "u1"  # untouched

    def test_t1_8_update_unknown_field_silent_ignore(self, db):
        aid = db.create_account(platform="youtube", username="u1", status="warmup")
        # All-unknown update must return False (no valid fields → no UPDATE)
        ok = db.update_account(aid, totally_unknown="x")
        assert ok is False
        # Status untouched
        assert db.list_accounts()[0]["status"] == "warmup"

    def test_t1_9_update_nonexistent_id(self, db):
        ok = db.update_account(99999, status="x")
        assert ok is False

    def test_t1_10_delete_one(self, db):
        aid1 = db.create_account(platform="youtube", username="u1", status="money")
        db.create_account(platform="tiktok", username="u2", status="burn")
        assert db.delete_account(aid1) is True
        rows = db.list_accounts()
        assert len(rows) == 1 and rows[0]["username"] == "u2"

    def test_t1_11_double_delete(self, db):
        aid = db.create_account(platform="youtube", username="u1", status="money")
        assert db.delete_account(aid) is True
        # Second delete: depending on impl returns False or 0-rows-affected.
        # The contract is just "doesn't blow up and doesn't say success".
        result = db.delete_account(aid)
        assert result is False or result == 0


# ===========================================================================
# T2 — check_db_integrity lock-scope (C1 fix)
# ===========================================================================
class TestT2IntegrityConcurrency:
    @pytest.fixture
    def db(self, tmp_path):
        from database import db_manager as dbmod

        return dbmod.DatabaseManager(db_path=str(tmp_path / "t2.db"))

    def test_t2_1_basic_integrity(self, db):
        assert db.check_db_integrity() is True

    def test_t2_2_concurrent_writers_and_integrity_checks(self, db):
        """Stress: 4 writers × 200 inserts vs 4 readers × 200 integrity checks."""
        errors: list[BaseException] = []
        integrity_results: list[bool] = []
        results_lock = threading.Lock()

        def writer(tid: int):
            try:
                for i in range(200):
                    db.create_account(
                        platform="youtube",
                        username=f"u-{tid}-{i}",
                        status="warmup",
                    )
            except BaseException as e:
                with results_lock:
                    errors.append(e)

        def reader(tid: int):
            try:
                for _ in range(200):
                    ok = db.check_db_integrity()
                    with results_lock:
                        integrity_results.append(ok)
            except BaseException as e:
                with results_lock:
                    errors.append(e)

        threads = []
        t0 = time.monotonic()
        for tid in range(4):
            threads.append(threading.Thread(target=writer, args=(tid,)))
        for tid in range(4):
            threads.append(threading.Thread(target=reader, args=(tid + 100,)))
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=120)
        elapsed = time.monotonic() - t0

        assert not errors, f"Concurrent run errors: {errors[:3]}"
        assert all(t.is_alive() is False for t in threads), "Some threads did not finish (deadlock)"
        # All integrity reads must say OK
        assert len(integrity_results) == 800, f"Expected 800 integrity reads, got {len(integrity_results)}"
        assert all(integrity_results), (
            f"At least one integrity check returned False under concurrency. False count: "
            f"{sum(1 for r in integrity_results if not r)}"
        )
        # All writes landed
        assert len(db.list_accounts()) == 800
        # Sanity — ran in reasonable time
        assert elapsed < 60.0, f"Stress run took too long ({elapsed:.1f}s)"

    def test_t2_3_missing_table_detected(self, db, tmp_path):
        """Drop accounts table and confirm integrity check returns False.

        DatabaseManager keeps a cached connection in ``self._connection``
        (singleton) plus an ``RLock`` ``self._lock``. To force the next call
        to re-open the DB and see the schema change, we close the cached
        connection out-of-band, then drop the table on a fresh sqlite3
        connection, then call ``check_db_integrity`` which will lazily
        re-create its cached connection via ``_get_connection``.
        """
        import contextlib
        import sqlite3

        # Force the cached connection to be re-opened on next call.
        with db._lock:  # noqa: SLF001
            cached = getattr(db, "_connection", None)
            if cached is not None:
                with contextlib.suppress(Exception):
                    cached.close()
                db._connection = None  # noqa: SLF001

        # Drop the accounts table out-of-band on a fresh sqlite3 connection.
        conn = sqlite3.connect(str(db.db_path))
        conn.execute("DROP TABLE accounts")
        conn.commit()
        conn.close()

        assert db.check_db_integrity() is False


# ===========================================================================
# T3 — OpsTab DB integration
# ===========================================================================
@pytest.fixture(scope="module")
def qapp():
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 not installed")
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


class TestT3OpsTab:
    @pytest.fixture
    def db_with_three(self, tmp_path):
        from database import db_manager as dbmod

        db = dbmod.DatabaseManager(db_path=str(tmp_path / "t3.db"))
        a1 = db.create_account(
            platform="youtube", username="ch-money", status="money", proxy="1.1.1.1", notes="n1"
        )
        a2 = db.create_account(platform="tiktok", username="ch-burn", status="burn")
        a3 = db.create_account(platform="youtube", username="ch-warm", status="warmup")
        return db, a1, a2, a3

    def test_t3_1_three_rows_correct_cards(self, qapp, db_with_three):
        from ui.widgets.ops_tab import OpsTab

        db, *_ = db_with_three
        tab = OpsTab(db=db)
        assert tab.table_channels.rowCount() == 3
        assert tab._card_total.text() == "3"
        assert tab._card_active.text() == "1"
        assert tab._card_alert.text() == "1"

    def test_t3_2_row_usernames(self, qapp, db_with_three):
        from ui.widgets.ops_tab import OpsTab

        db, *_ = db_with_three
        tab = OpsTab(db=db)
        usernames = {tab.table_channels.item(i, 0).text() for i in range(tab.table_channels.rowCount())}
        assert usernames == {"ch-money", "ch-burn", "ch-warm"}

    def test_t3_3_row_status_text(self, qapp, db_with_three):
        from ui.widgets.ops_tab import OpsTab

        db, *_ = db_with_three
        tab = OpsTab(db=db)
        statuses = [tab.table_channels.item(i, 3).text() for i in range(tab.table_channels.rowCount())]
        assert any("Money" in s for s in statuses)
        assert any("Burn" in s for s in statuses)
        assert any("Warmup" in s for s in statuses)

    def test_t3_4_refresh_picks_up_new_account(self, qapp, db_with_three):
        from ui.widgets.ops_tab import OpsTab

        db, *_ = db_with_three
        tab = OpsTab(db=db)
        assert tab.table_channels.rowCount() == 3

        db.create_account(platform="youtube", username="ch-new", status="warmup")
        tab.refresh()
        assert tab.table_channels.rowCount() == 4
        assert tab._card_total.text() == "4"

    def test_t3_5_refresh_after_delete(self, qapp, db_with_three):
        from ui.widgets.ops_tab import OpsTab

        db, _a1, a2, _a3 = db_with_three
        tab = OpsTab(db=db)
        assert tab._card_alert.text() == "1"
        db.delete_account(a2)
        tab.refresh()
        assert tab.table_channels.rowCount() == 2
        assert tab._card_alert.text() == "0"

    def test_t3_6_no_db_does_not_crash(self, qapp):
        from ui.widgets.ops_tab import OpsTab

        tab = OpsTab(db=None)
        assert tab.table_channels.rowCount() == 0
        assert tab._card_total.text() == "0"

    def test_t3_7_db_error_swallowed(self, qapp):
        from ui.widgets.ops_tab import OpsTab

        class BadDB:
            def list_accounts(self, **kw):
                raise RuntimeError("boom from BadDB")

        tab = OpsTab(db=BadDB())
        assert tab.table_channels.rowCount() == 0
        assert tab._card_total.text() == "0"


# ===========================================================================
# T4 — FFmpeg presets vs real binary
# ===========================================================================
class TestT4FFmpegPresets:
    def test_t4_1_slideshow_runs_and_probes_correct(self, tmp_path):
        from services.ffmpeg_builder import FFmpegPresets

        out = str(tmp_path / "slide.mp4")
        cmd = FFmpegPresets.slideshow(
            ffmpeg=FFMPEG,
            images=[str(PR5_FIXTURES / "img_a.png"), str(PR5_FIXTURES / "img_b.png")],
            audio_path=str(PR5_FIXTURES / "voice.mp3"),
            output_path=out,
            duration_per_image=3.0,
            audio_duration=6.0,
            resolution="1280x720",
        )
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        assert proc.returncode == 0, f"ffmpeg failed: {proc.stderr[-500:]}"
        assert Path(out).exists()
        info = _ffprobe_streams(out)
        streams = info["streams"]
        v = next(s for s in streams if s["codec_type"] == "video")
        a = next(s for s in streams if s["codec_type"] == "audio")
        assert v["codec_name"] == "h264"
        assert v["pix_fmt"] == "yuv420p"
        assert int(v["width"]) == 1280 and int(v["height"]) == 720
        assert a["codec_name"] == "aac"
        dur = float(info["format"]["duration"])
        # ffmpeg ``-shortest`` kết hợp ``filter_complex`` thường trả file hơi
        # dài hơn duration audio (do GOP/keyframe alignment); chấp nhận
        # 5.5–9.0s miễn là file hợp lệ và gần đúng.
        assert 5.5 <= dur <= 9.0, f"slideshow duration {dur} not in [5.5, 9.0]"

    def test_t4_2_concat_clips_runs(self, tmp_path):
        from services.ffmpeg_builder import FFmpegPresets

        out = str(tmp_path / "concat.mp4")
        cmd = FFmpegPresets.concat_clips(
            ffmpeg=FFMPEG,
            list_file=str(PR5_FIXTURES / "list.txt"),
            audio_path=str(PR5_FIXTURES / "voice.mp3"),
            output_path=out,
            resolution="1280x720",
        )
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        assert proc.returncode == 0, f"ffmpeg failed: {proc.stderr[-500:]}"
        info = _ffprobe_streams(out)
        v = next(s for s in info["streams"] if s["codec_type"] == "video")
        a = next(s for s in info["streams"] if s["codec_type"] == "audio")
        assert v["codec_name"] == "h264"
        assert a["codec_name"] == "aac"
        dur = float(info["format"]["duration"])
        # voice = 6s, clips total 9s, -shortest → ~6s (cho phép tới 9s do
        # kết thúc ở biên keyframe).
        assert 5.5 <= dur <= 9.0, f"concat duration {dur} not in [5.5, 9.0]"

    def test_t4_3_mix_background_music_ducking(self, tmp_path):
        from services.ffmpeg_builder import FFmpegPresets

        out = str(tmp_path / "mix_d.mp4")
        cmd = FFmpegPresets.mix_background_music(
            ffmpeg=FFMPEG,
            video_path=str(PR5_FIXTURES / "clip_a.mp4"),
            music_path=str(PR5_FIXTURES / "music.mp3"),
            output_path=out,
            volume=0.2,
            ducking=True,
        )
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        assert proc.returncode == 0, f"ffmpeg failed: {proc.stderr[-500:]}"
        info = _ffprobe_streams(out)
        v = next(s for s in info["streams"] if s["codec_type"] == "video")
        a = next(s for s in info["streams"] if s["codec_type"] == "audio")
        # vcodec("copy") was applied → must NOT be re-encoded
        # h264 stays h264 but check we didn't lose it
        assert v["codec_name"] == "h264"
        assert a["codec_name"] == "aac"
        # Source clip_a.mp4 is 5 seconds
        src_dur = _duration(str(PR5_FIXTURES / "clip_a.mp4"))
        out_dur = float(info["format"]["duration"])
        assert abs(out_dur - src_dur) < 1.0, f"mix dur {out_dur} vs src {src_dur}"

    def test_t4_4_mix_no_ducking_runs(self, tmp_path):
        from services.ffmpeg_builder import FFmpegPresets

        out = str(tmp_path / "mix_nd.mp4")
        cmd = FFmpegPresets.mix_background_music(
            ffmpeg=FFMPEG,
            video_path=str(PR5_FIXTURES / "clip_a.mp4"),
            music_path=str(PR5_FIXTURES / "music.mp3"),
            output_path=out,
            volume=0.2,
            ducking=False,
        )
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        assert proc.returncode == 0, f"ffmpeg failed: {proc.stderr[-500:]}"
        joined = " ".join(cmd)
        assert "sidechaincompress" not in joined

    def test_t4_5_burn_subtitle_runs(self, tmp_path):
        from services.ffmpeg_builder import FFmpegPresets

        out = str(tmp_path / "burn.mp4")
        cmd = FFmpegPresets.burn_subtitle(
            ffmpeg=FFMPEG,
            video_path=str(PR5_FIXTURES / "clip_a.mp4"),
            srt_path=str(PR5_FIXTURES / "sub.srt"),
            output_path=out,
        )
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        assert proc.returncode == 0, f"ffmpeg burn_subtitle failed: {proc.stderr[-800:]}"
        info = _ffprobe_streams(out)
        v = next(s for s in info["streams"] if s["codec_type"] == "video")
        assert v["codec_name"] == "h264"
        assert v["pix_fmt"] == "yuv420p"
        src_dur = _duration(str(PR5_FIXTURES / "clip_a.mp4"))
        out_dur = float(info["format"]["duration"])
        assert abs(out_dur - src_dur) < 1.0, f"burn dur {out_dur} vs src {src_dur}"

    def test_t4_6_builder_no_inputs_no_output_raises(self):
        from services.ffmpeg_builder import FFmpegCommandBuilder

        with pytest.raises(ValueError):
            FFmpegCommandBuilder().build()

    def test_t4_7_builder_input_only_raises(self):
        from services.ffmpeg_builder import FFmpegCommandBuilder

        b = FFmpegCommandBuilder()
        b.add_input("a.png", loop=True, duration=1)
        with pytest.raises(ValueError):
            b.build()

    def test_t4_8_resolution_fallback(self, tmp_path):
        from services.ffmpeg_builder import FFmpegPresets

        assert FFmpegPresets.parse_resolution("foobar") == (1920, 1080)
        out = str(tmp_path / "fallback.mp4")
        cmd = FFmpegPresets.slideshow(
            ffmpeg=FFMPEG,
            images=[str(PR5_FIXTURES / "img_a.png"), str(PR5_FIXTURES / "img_b.png")],
            audio_path=str(PR5_FIXTURES / "voice.mp3"),
            output_path=out,
            duration_per_image=3.0,
            audio_duration=6.0,
            resolution="garbage",
        )
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        assert proc.returncode == 0, f"ffmpeg failed: {proc.stderr[-500:]}"
        info = _ffprobe_streams(out)
        v = next(s for s in info["streams"] if s["codec_type"] == "video")
        assert int(v["width"]) == 1920 and int(v["height"]) == 1080


# ===========================================================================
# T5 — audio_async pure-python ops
# ===========================================================================
class TestT5AudioAsync:
    def test_t5_1_probe_voice(self):
        from services.audio_async import probe_audio

        info = probe_audio(str(PR5_FIXTURES / "voice.mp3"))
        assert isinstance(info["duration"], float)
        assert 5.9 <= info["duration"] <= 6.1
        assert info["sample_rate"] == "44100"
        assert info["channels"] == "2"

    def test_t5_2_probe_missing_file_raises(self):
        from services.audio_async import probe_audio

        with pytest.raises(FileNotFoundError):
            probe_audio("/no/such/file.mp3")

    def test_t5_3_normalize_loudness(self, tmp_path):
        from services.audio_async import normalize_loudness, probe_audio

        dst = str(tmp_path / "voice_norm.mp3")
        out = normalize_loudness(str(PR5_FIXTURES / "voice.mp3"), dst, target_lufs=-16.0)
        assert out == dst
        assert Path(dst).exists()
        info = probe_audio(dst)
        assert 5.5 <= info["duration"] <= 6.5

    def test_t5_4_trim_silence_shortens(self, tmp_path):
        from services.audio_async import probe_audio, trim_silence

        src = str(PR5_FIXTURES / "padded.mp3")  # 12s with silence padding
        dst = str(tmp_path / "trimmed.mp3")
        src_dur = probe_audio(src)["duration"]
        trim_silence(src, dst, threshold_db=-50.0)
        out_dur = probe_audio(dst)["duration"]
        # Must be clearly shorter than 12s. Loose bound.
        assert out_dur < src_dur - 1.0, f"trim_silence did not shorten: src={src_dur}, out={out_dur}"

    def test_t5_5_mix_narration_with_music(self, tmp_path):
        from services.audio_async import mix_narration_with_music, probe_audio

        dst = str(tmp_path / "mixed.mp3")
        mix_narration_with_music(
            str(PR5_FIXTURES / "voice.mp3"),
            str(PR5_FIXTURES / "music.mp3"),
            dst,
            music_volume=0.2,
        )
        info = probe_audio(dst)
        # Narration is 6s, -shortest+amix=duration=first → ~6s
        assert 5.5 <= info["duration"] <= 6.7

    def test_t5_6_dispatch_probe(self):
        from services.audio_async import AudioJob, execute_job

        job = AudioJob(kind="probe", payload={"path": str(PR5_FIXTURES / "voice.mp3")})
        res = execute_job(job)
        assert res.ok is True
        assert 5.9 <= res.info["duration"] <= 6.1
        assert res.job_id == job.job_id

    def test_t5_7_dispatch_unknown_kind(self):
        from services.audio_async import AudioJob, execute_job

        res = execute_job(AudioJob(kind="bogus-kind"))
        assert res.ok is False
        assert "unknown kind" in (res.error or "")

    def test_t5_8_register_custom_handler(self):
        from services import audio_async

        @audio_async.register_handler("t5-custom")
        def _h(p):
            return audio_async.AudioJobResult(job_id="", ok=True, info={"x": p["x"] * 3})

        res = audio_async.execute_job(audio_async.AudioJob(kind="t5-custom", payload={"x": 7}))
        assert res.ok and res.info["x"] == 21

    def test_t5_9_qt_classes_present(self, qapp):
        from services import audio_async

        assert audio_async.AudioWorker is not None
        assert audio_async.AudioJobRunner is not None
        runner = audio_async.AudioJobRunner(max_concurrent=2)
        assert runner is not None


# ===========================================================================
# T6 — main.py splash refactor
# ===========================================================================
def _import_main_or_skip():
    """Try to import VeoSuite_V3.main; skip if heavy legacy deps are missing.

    ``main.py`` triggers MainWindow construction which transitively imports
    ``ui.widgets.media_tab`` (``from google import genai``). On CI we don't
    install the ``google-genai`` package — those tests should skip rather
    than fail because the splash refactor is fully checkable from source.
    """
    try:
        import main as main_mod
    except ImportError as exc:
        pytest.skip(f"main.py heavy import unavailable: {exc}")
    return main_mod


class TestT6MainSplash:
    def test_t6_1_check_dependencies_ok(self):
        main_mod = _import_main_or_skip()
        assert main_mod.check_dependencies() is True

    def test_t6_2_check_dependencies_missing(self, monkeypatch):
        from importlib import util as imp_util

        main_mod = _import_main_or_skip()

        original = imp_util.find_spec

        def fake(name):
            if name == "PyQt6":
                return None
            return original(name)

        monkeypatch.setattr(imp_util, "find_spec", fake)
        assert main_mod.check_dependencies() is False

    def test_t6_3_splash_update_status(self, qapp):
        main_mod = _import_main_or_skip()
        splash = main_mod.ModernSplashScreen("VEO TEST", "0.0.1", "/no/logo")
        splash.update_status("Step X", 50)
        assert splash.lbl_status.text() == "Step X"
        assert splash.progress.value() == 50
        splash.close()

    def test_t6_4_no_time_sleep_in_main(self):
        src = (Path(__file__).resolve().parents[1] / "VeoSuite_V3" / "main.py").read_text()
        # Strip docstrings and comments before checking — we only forbid
        # actual ``time.sleep(...)`` call sites, not the word "time.sleep"
        # appearing inside a comment that explains the refactor.
        import io
        import tokenize

        toks = tokenize.tokenize(io.BytesIO(src.encode("utf-8")).readline)
        code_only = "".join(t.string for t in toks if t.type not in (tokenize.COMMENT, tokenize.STRING))
        # Match ``time.sleep(`` only at a real call site
        matches = re.findall(r"\btime\s*\.\s*sleep\s*\(", code_only)
        assert matches == [], f"time.sleep call(s) survived: {matches}"

    def test_t6_5_qtimer_singleshot_present(self):
        src = (Path(__file__).resolve().parents[1] / "VeoSuite_V3" / "main.py").read_text()
        assert src.count("QTimer.singleShot") >= 2

    def test_t6_6_main_module_imports(self):
        main_mod = _import_main_or_skip()
        assert hasattr(main_mod, "main") and callable(main_mod.main)


# ===========================================================================
# T7 — C2 fix (modules/content/workers.py:201)
# ===========================================================================
class TestT7ChannelDesignerLogger:
    def test_t7_1_no_buggy_call_remains(self):
        src = (
            Path(__file__).resolve().parents[1] / "VeoSuite_V3" / "modules" / "content" / "workers.py"
        ).read_text()
        # The buggy line dropped exception via positional arg
        assert 'logger.info("Lỗi Channel Worker:", e)' not in src

    def test_t7_2_logger_exception_present(self):
        src = (
            Path(__file__).resolve().parents[1] / "VeoSuite_V3" / "modules" / "content" / "workers.py"
        ).read_text()
        assert 'logger.exception("Lỗi Channel Worker")' in src

    def test_t7_3_traceback_captured_in_log(self, qapp, caplog):
        from modules.content.workers import ChannelDesignerWorker

        class FakeAI:
            def get_worker_config(self, key):
                return {"provider": "fake-provider", "model": "fake-model"}

            def execute_custom_ai(self, provider, prompt, model):
                raise RuntimeError("boom-from-test-7-3")

        # Constructor signature: __init__(topic, country, platform="Youtube")
        # AIFactory is created inside __init__ — replace it AFTER construction.
        worker = ChannelDesignerWorker(topic="testing", country="US", platform="Youtube")
        worker.ai = FakeAI()

        emitted: list[Any] = []
        worker.finished_signal.connect(emitted.append)

        # The module's logger is "VeoSuite.Content.Workers" — capture at root to be safe.
        with caplog.at_level(logging.DEBUG):
            worker.run()

        all_records = caplog.records
        # logger.exception() emits at ERROR with exc_info populated
        exc_records = [r for r in all_records if r.exc_info is not None]
        assert exc_records, (
            f"No record with exc_info captured. "
            f"Records: {[(r.levelname, r.name, r.getMessage()) for r in all_records]}"
        )
        # The error message of the inner exception must surface in the traceback
        import traceback as tb_mod

        full_with_traceback = ""
        for r in exc_records:
            if r.exc_info:
                full_with_traceback += "\n" + "".join(tb_mod.format_exception(*r.exc_info))
        assert "boom-from-test-7-3" in full_with_traceback, (
            f"Inner error 'boom-from-test-7-3' not in log traceback. Got: {full_with_traceback[:500]}"
        )
        # finished_signal still emitted with empty dict
        assert emitted == [{}], f"Expected single empty-dict emission, got: {emitted}"


# ===========================================================================
# T8 — C3 fix (modules/radar/youtube_worker.py:408)
# ===========================================================================
class TestT8YoutubeWorkerTypo:
    SRC_PATH = Path(__file__).resolve().parents[1] / "VeoSuite_V3" / "modules" / "radar" / "youtube_worker.py"

    def test_t8_1_file_parses(self):
        import ast

        ast.parse(self.SRC_PATH.read_text())

    def test_t8_2_no_typo_remaining(self):
        src = self.SRC_PATH.read_text()
        # Word boundary so we don't match the correct name
        matches = re.findall(r"\battempts_with_current_confi\b", src)
        assert matches == [], f"Typo still present: {matches}"

    def test_t8_3_correct_name_appears_multiple_times(self):
        src = self.SRC_PATH.read_text()
        count = len(re.findall(r"\battempts_with_current_config\b", src))
        # declaration + while condition + the rename (formerly buggy line) + at least one increment elsewhere
        assert count >= 3, f"Expected ≥3 references, got {count}"


# ===========================================================================
# T9 — D3 fix (ui/main_window.py fallback ImportError block must mirror
#      the primary import block, otherwise a transitive dependency missing
#      in the primary chain causes NameError at MainWindow construction
#      instead of a clean ImportError.
# ===========================================================================
class TestT9MainWindowImportFallback:
    SRC_PATH = Path(__file__).resolve().parents[1] / "VeoSuite_V3" / "ui" / "main_window.py"

    @staticmethod
    def _imported_names(src: str) -> tuple[set[str], set[str]]:
        """Return (primary_names, fallback_names) extracted from the two import
        blocks in main_window.py. Names are the trailing identifier of each
        ``from X.Y import Z`` line — what the rest of the module references.
        """
        import ast

        tree = ast.parse(src)
        primary: set[str] = set()
        fallback: set[str] = set()
        # The two blocks live inside the module-level Try → ExceptHandler → Try.
        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                # Block A: imports inside the outer Try.body (Trường hợp 1).
                for stmt in node.body:
                    if isinstance(stmt, ast.ImportFrom):
                        for alias in stmt.names:
                            primary.add(alias.asname or alias.name)
                # Block B: imports inside ExceptHandler → inner Try.body (Trường hợp 2).
                for handler in node.handlers:
                    for sub in ast.walk(ast.Module(body=handler.body, type_ignores=[])):
                        if isinstance(sub, ast.ImportFrom):
                            for alias in sub.names:
                                fallback.add(alias.asname or alias.name)
                break  # only inspect the first outer Try at module level
        return primary, fallback

    def test_t9_1_file_parses(self):
        import ast

        ast.parse(self.SRC_PATH.read_text())

    def test_t9_2_publisher_tab_in_fallback(self):
        """The exact regression: ``PublisherTab`` is imported in the primary
        block but used to be missing from the fallback block, so when the
        publisher's transitive ``google_auth_oauthlib`` import failed the
        fallback ran and the app died at ``self.publisher_tab = PublisherTab()``
        with NameError.
        """
        src = self.SRC_PATH.read_text()
        primary, fallback = self._imported_names(src)
        assert "PublisherTab" in primary, "primary import block lost PublisherTab"
        assert "PublisherTab" in fallback, (
            "fallback ImportError block is missing `from widgets.publisher_tab "
            "import PublisherTab` — this regression made the splash crash with "
            "NameError on real desktops where google_auth_oauthlib wasn't installed."
        )

    def test_t9_3_fallback_mirrors_primary(self):
        """Stronger invariant: every name imported in the primary block must
        also appear in the fallback block. (The fallback may import strict
        super-set of names, e.g. extra debug imports — that's fine.)
        """
        src = self.SRC_PATH.read_text()
        primary, fallback = self._imported_names(src)
        missing = primary - fallback
        assert not missing, (
            f"fallback ImportError block in main_window.py is missing "
            f"{sorted(missing)} that the primary block imports. Any of these "
            f"will become a NameError at MainWindow.__init__ time when a "
            f"transitive dep failure pushes execution into the fallback."
        )


# ===========================================================================
# T10 — PR-5b1: OpsTab is owned by AdminTab and AdminTab ONLY. Re-introducing
# OpsTab in PublisherTab causes the same widget to render twice with two
# competing inline stylesheets, which the user perceives as the app
# "jumping into another UI" when navigating between Phát Hành (Publisher)
# and Quản Trị (Admin). This invariant is structural and cheap to enforce
# with AST so future drift fails CI immediately.
# ===========================================================================
class TestT10OpsTabSingleOwner:
    PUBLISHER_TAB = (
        Path(__file__).resolve().parents[1] / "VeoSuite_V3" / "ui" / "widgets" / "publisher_tab.py"
    )
    ADMIN_TAB = Path(__file__).resolve().parents[1] / "VeoSuite_V3" / "ui" / "admin_tab.py"

    @staticmethod
    def _all_calls(src: str) -> list:
        import ast

        tree = ast.parse(src)
        return [n for n in ast.walk(tree) if isinstance(n, ast.Call)]

    @staticmethod
    def _all_imported_names(src: str) -> set[str]:
        import ast

        tree = ast.parse(src)
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    names.add(alias.asname or alias.name)
        return names

    def test_t10_1_publisher_tab_does_not_import_ops_tab(self):
        """publisher_tab.py must NOT import OpsTab anymore. The previous
        ``from ui.widgets.ops_tab import OpsTab`` was the source of the
        double-render bug; PR-5b1 removed it.
        """
        src = self.PUBLISHER_TAB.read_text(encoding="utf-8")
        names = self._all_imported_names(src)
        assert "OpsTab" not in names, (
            "publisher_tab.py is importing OpsTab again. OpsTab is exclusively "
            'owned by AdminTab (Quản Trị → "🛡️ An Ninh & VPS"). '
            "Re-importing it here re-introduces the dual-render bug PR-5b1 fixed."
        )

    def test_t10_2_publisher_tab_does_not_instantiate_ops_tab(self):
        """publisher_tab.py source must not contain ``OpsTab(`` anywhere
        (covers cases where someone imports it under an alias and then
        constructs it). AST walk on call nodes catches both shapes.
        """
        src = self.PUBLISHER_TAB.read_text(encoding="utf-8")
        for call in self._all_calls(src):
            func = call.func
            name = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name == "OpsTab":
                raise AssertionError(
                    "publisher_tab.py instantiates OpsTab. OpsTab is owned by "
                    "AdminTab. Remove the construction or risk the dual-UI "
                    "stylesheet drift PR-5b1 was created to fix."
                )

    def test_t10_3_admin_tab_still_owns_ops_tab(self):
        """admin_tab.py must still import and instantiate OpsTab — that's the
        sole owner. If this regresses, Ops Center disappears from the app
        entirely.
        """
        src = self.ADMIN_TAB.read_text(encoding="utf-8")
        names = self._all_imported_names(src)
        assert "OpsTab" in names, (
            "admin_tab.py no longer imports OpsTab. AdminTab is the sole owner "
            "of Ops Center; if this regresses Ops Center is unreachable in the app."
        )
        instantiations = [
            c
            for c in self._all_calls(src)
            if (isinstance(c.func, ast.Name) and c.func.id == "OpsTab")
            or (isinstance(c.func, ast.Attribute) and c.func.attr == "OpsTab")
        ]
        assert instantiations, (
            "admin_tab.py imports OpsTab but never constructs it. Expected "
            "exactly one ``OpsTab()`` call in setup_ops_tab/init_ui."
        )
        assert len(instantiations) == 1, (
            f"admin_tab.py constructs OpsTab {len(instantiations)} times; "
            f"expected exactly one. Multiple instances re-introduce the same "
            f"dual-render symptom PR-5b1 was created to fix."
        )

    def test_t10_4_global_single_owner(self):
        """Whole-tree sweep: across the entire VeoSuite_V3 codebase, the only
        file allowed to construct OpsTab is admin_tab.py. Test files are
        exempt because they exercise OpsTab in isolation.
        """
        import ast as _ast

        root = Path(__file__).resolve().parents[1] / "VeoSuite_V3"
        offenders: list[str] = []
        for py in root.rglob("*.py"):
            if py.name == "admin_tab.py":
                continue
            if py.name == "ops_tab.py":
                # The class definition itself, not a construction site.
                continue
            try:
                tree = _ast.parse(py.read_text(encoding="utf-8"))
            except SyntaxError:
                # Legacy files outside ruff scope — let other tests catch parse errors.
                continue
            for call in _ast.walk(tree):
                if not isinstance(call, _ast.Call):
                    continue
                func = call.func
                if (isinstance(func, _ast.Name) and func.id == "OpsTab") or (
                    isinstance(func, _ast.Attribute) and func.attr == "OpsTab"
                ):
                    offenders.append(str(py.relative_to(root)))
                    break
        assert not offenders, (
            f"Files outside admin_tab.py construct OpsTab: {offenders}. "
            f"OpsTab must be a singleton owned by AdminTab — see PR-5b1."
        )
