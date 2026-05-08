"""
VEO SUITE V3 — Async-friendly audio helpers
============================================
Bọc các tác vụ xử lý audio (TTS, mix, normalize, probe) chạy trong
``QThread`` / ``QRunnable`` để UI tab không bị đứng. Tách phần "compute"
ra khỏi tab giúp test dễ hơn và mở đường refactor god-class.

Các thành phần:

* :class:`AudioJob` — dataclass mô tả 1 việc cần làm (loại + payload).
* :class:`AudioJobResult` — dataclass cho kết quả (ok/err + output_path).
* :class:`AudioWorker` — ``QObject`` chạy 1 ``AudioJob`` trong thread riêng,
  emit ``finished(AudioJobResult)``.
* :class:`AudioJobRunner` — manager nhỏ giúp queue nhiều job, giới hạn
  concurrency (mặc định = 2 — đủ để TTS + render song song).

Module được viết để có thể import & test mà KHÔNG cần PyQt6 (lazy import),
phục vụ smoke test trên CI headless.
"""

from __future__ import annotations

import contextlib
import logging
import os
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("VeoSuite.AudioAsync")

# Cho phép override timeout qua env (đã chuẩn hoá trong PR-2)
DEFAULT_TIMEOUT = int(os.environ.get("VEO_FFMPEG_TIMEOUT", "1800"))


# =====================================================================
# Pure-python primitives (test-friendly)
# =====================================================================


@dataclass
class AudioJob:
    """1 đơn vị công việc audio.

    ``kind`` quyết định worker chạy logic gì:

    * ``"probe"`` — chạy ffprobe, trả thông tin duration/bitrate.
    * ``"normalize"`` — chuẩn hoá loudness (-16 LUFS).
    * ``"mix"`` — mix narration + music với ducking nhẹ.
    * ``"trim_silence"`` — cắt khoảng lặng đầu/cuối.
    """

    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    job_id: str = ""

    def __post_init__(self) -> None:
        if not self.job_id:
            self.job_id = f"{self.kind}-{int(time.time() * 1000)}"


@dataclass
class AudioJobResult:
    """Kết quả của ``AudioJob``."""

    job_id: str
    ok: bool
    output_path: str | None = None
    info: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


# =====================================================================
# Pure-python operations (no Qt — easy to unit test)
# =====================================================================


def _which_ffmpeg() -> str:
    """Tìm binary ffmpeg trên PATH (fallback 'ffmpeg')."""
    return shutil.which("ffmpeg") or "ffmpeg"


def _which_ffprobe() -> str:
    return shutil.which("ffprobe") or "ffprobe"


def _run(cmd: list[str], *, timeout: int = DEFAULT_TIMEOUT) -> subprocess.CompletedProcess:
    """Chạy subprocess với timeout chuẩn hoá."""
    logger.debug("Run: %s", cmd[:5] + ["..."])
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def probe_audio(path: str) -> dict[str, Any]:
    """Trả {duration, sample_rate, bit_rate, channels} qua ffprobe."""
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    cmd = [
        _which_ffprobe(),
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type,sample_rate,channels,bit_rate:format=duration,bit_rate",
        "-of",
        "default=noprint_wrappers=1:nokey=0",
        path,
    ]
    proc = _run(cmd, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {proc.stderr.strip()}")
    info: dict[str, Any] = {}
    for line in proc.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            info[k.strip()] = v.strip()
    if "duration" in info:
        with contextlib.suppress(ValueError):
            info["duration"] = float(info["duration"])
    return info


def normalize_loudness(
    src: str,
    dst: str,
    *,
    target_lufs: float = -16.0,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """One-pass loudnorm tới ``target_lufs``."""
    if not os.path.exists(src):
        raise FileNotFoundError(src)
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        _which_ffmpeg(),
        "-y",
        "-i",
        src,
        "-af",
        f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11",
        "-ar",
        "44100",
        dst,
    ]
    proc = _run(cmd, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"normalize failed: {proc.stderr.strip()[:300]}")
    return dst


def trim_silence(
    src: str,
    dst: str,
    *,
    threshold_db: float = -50.0,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Cắt khoảng lặng > ``threshold_db`` ở đầu/cuối."""
    if not os.path.exists(src):
        raise FileNotFoundError(src)
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    af = (
        f"silenceremove=start_periods=1:start_silence=0.05:start_threshold={threshold_db}dB,"
        f"areverse,"
        f"silenceremove=start_periods=1:start_silence=0.05:start_threshold={threshold_db}dB,"
        f"areverse"
    )
    cmd = [_which_ffmpeg(), "-y", "-i", src, "-af", af, dst]
    proc = _run(cmd, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"trim_silence failed: {proc.stderr.strip()[:300]}")
    return dst


def mix_narration_with_music(
    narration: str,
    music: str,
    dst: str,
    *,
    music_volume: float = 0.15,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Mix narration + music nền (ducking nhẹ)."""
    for p in (narration, music):
        if not os.path.exists(p):
            raise FileNotFoundError(p)
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    a_filter = (
        f"[1:a]volume={music_volume},"
        f"sidechaincompress=threshold=0.1:ratio=4:attack=20:release=1000[bg];"
        f"[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    )
    cmd = [
        _which_ffmpeg(),
        "-y",
        "-i",
        narration,
        "-stream_loop",
        "-1",
        "-i",
        music,
        "-filter_complex",
        a_filter,
        "-map",
        "[aout]",
        "-shortest",
        dst,
    ]
    proc = _run(cmd, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"mix failed: {proc.stderr.strip()[:300]}")
    return dst


# =====================================================================
# Dispatch
# =====================================================================


_HANDLERS: dict[str, Callable[[dict[str, Any]], AudioJobResult]] = {}


def register_handler(
    kind: str,
) -> Callable[[Callable[[dict[str, Any]], AudioJobResult]], Callable[[dict[str, Any]], AudioJobResult]]:
    """Decorator để mở rộng kind tuỳ ý từ plugin."""

    def deco(fn: Callable[[dict[str, Any]], AudioJobResult]) -> Callable[[dict[str, Any]], AudioJobResult]:
        _HANDLERS[kind] = fn
        return fn

    return deco


def _handle_probe(p: dict[str, Any]) -> AudioJobResult:
    info = probe_audio(p["path"])
    return AudioJobResult(job_id="", ok=True, info=info, output_path=p["path"])


def _handle_normalize(p: dict[str, Any]) -> AudioJobResult:
    out = normalize_loudness(p["src"], p["dst"], target_lufs=p.get("target_lufs", -16.0))
    return AudioJobResult(job_id="", ok=True, output_path=out)


def _handle_trim(p: dict[str, Any]) -> AudioJobResult:
    out = trim_silence(p["src"], p["dst"], threshold_db=p.get("threshold_db", -50.0))
    return AudioJobResult(job_id="", ok=True, output_path=out)


def _handle_mix(p: dict[str, Any]) -> AudioJobResult:
    out = mix_narration_with_music(
        p["narration"], p["music"], p["dst"], music_volume=p.get("music_volume", 0.15)
    )
    return AudioJobResult(job_id="", ok=True, output_path=out)


_HANDLERS.update(
    {
        "probe": _handle_probe,
        "normalize": _handle_normalize,
        "trim_silence": _handle_trim,
        "mix": _handle_mix,
    }
)


def execute_job(job: AudioJob) -> AudioJobResult:
    """Chạy đồng bộ (dùng cho test). Worker async sẽ gọi hàm này từ thread."""
    handler = _HANDLERS.get(job.kind)
    if handler is None:
        return AudioJobResult(job_id=job.job_id, ok=False, error=f"unknown kind: {job.kind}")
    try:
        result = handler(job.payload)
        result.job_id = job.job_id
        return result
    except Exception as e:  # noqa: BLE001 — boundary của worker
        logger.exception("Audio job %s failed: %s", job.job_id, e)
        return AudioJobResult(job_id=job.job_id, ok=False, error=str(e))


# =====================================================================
# Qt wrapper — chỉ tạo class khi PyQt6 có sẵn
# =====================================================================


def _build_qt_classes():  # pragma: no cover — chỉ chạy khi có Qt
    try:
        from PyQt6.QtCore import (
            QObject,
            QRunnable,
            QThreadPool,
            pyqtSignal,
            pyqtSlot,
        )
    except Exception:  # pragma: no cover
        return None, None

    class _Signals(QObject):
        finished = pyqtSignal(object)  # AudioJobResult
        progress = pyqtSignal(str, float)  # job_id, ratio

    class AudioWorker(QRunnable):
        """Chạy 1 ``AudioJob`` trong ``QThreadPool``."""

        def __init__(self, job: AudioJob) -> None:
            super().__init__()
            self.job = job
            self.signals = _Signals()

        @pyqtSlot()
        def run(self) -> None:  # type: ignore[override]
            self.signals.progress.emit(self.job.job_id, 0.0)
            result = execute_job(self.job)
            self.signals.progress.emit(self.job.job_id, 1.0)
            self.signals.finished.emit(result)

    class AudioJobRunner(QObject):
        """Submit & track nhiều ``AudioJob`` qua ``QThreadPool`` chung."""

        finished = pyqtSignal(object)
        progress = pyqtSignal(str, float)

        def __init__(self, max_concurrent: int = 2) -> None:
            super().__init__()
            self._pool = QThreadPool.globalInstance()
            self._pool.setMaxThreadCount(max_concurrent)

        def submit(self, job: AudioJob) -> None:
            worker = AudioWorker(job)
            worker.signals.finished.connect(self.finished.emit)
            worker.signals.progress.connect(self.progress.emit)
            self._pool.start(worker)

        def wait(self, msec: int = -1) -> bool:
            return self._pool.waitForDone(msec)

    return AudioWorker, AudioJobRunner


AudioWorker, AudioJobRunner = _build_qt_classes() or (None, None)


__all__ = [
    "AudioJob",
    "AudioJobResult",
    "AudioJobRunner",
    "AudioWorker",
    "execute_job",
    "mix_narration_with_music",
    "normalize_loudness",
    "probe_audio",
    "register_handler",
    "trim_silence",
]
