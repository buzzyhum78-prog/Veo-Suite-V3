"""
VEO SUITE V3 — FFmpeg Command Builder
======================================
Tập trung tất cả logic dựng command-line cho FFmpeg vào 1 chỗ thay cho việc
ghép chuỗi rải rác trong ``render_service.py``. Mục tiêu:

* Đảm bảo các flag bắt buộc (``-y``, codec, pixel_fmt, fade) không bị thiếu.
* Dễ unit-test (chỉ test cấu trúc command, không cần FFmpeg thật).
* Cho phép tab UI / scheduler / Celery worker tạo và serialize command như
  một dataclass thay vì xâu chuỗi 200 ký tự.

API có 2 lớp:

1. ``FFmpegCommandBuilder`` — class fluent dạng builder, append từng input
   và filter, gọi ``.build()`` ra ``list[str]``.
2. ``FFmpegPresets`` — các factory method dựng sẵn cho 4 use-case phổ
   biến (slideshow, concat clip, mix nhạc nền, burn subtitle).

Backward-compat: ``RenderService`` chưa bắt buộc dùng builder — file mới chỉ
là tiện ích bổ sung, sẽ được áp dụng dần ở các tab refactor sau.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field

logger = logging.getLogger("VeoSuite.FFmpegBuilder")


@dataclass
class FFmpegInput:
    """1 input clip cho FFmpeg (image, video, audio)."""

    path: str
    loop: bool = False
    duration: float | None = None  # giây — chỉ áp khi loop=True hoặc cần -t
    extra_flags: list[str] = field(default_factory=list)

    def to_args(self) -> list[str]:
        args: list[str] = []
        if self.loop:
            args.extend(["-loop", "1"])
        if self.duration is not None:
            args.extend(["-t", f"{self.duration}"])
        args.extend(self.extra_flags)
        args.extend(["-i", self.path])
        return args


@dataclass
class FFmpegCommandBuilder:
    """Builder fluent cho command FFmpeg.

    Ví dụ::

        cmd = (
            FFmpegCommandBuilder(ffmpeg="/usr/bin/ffmpeg")
            .add_input("a.png", loop=True, duration=5.0)
            .add_input("b.png", loop=True, duration=5.0)
            .add_input("voice.mp3")
            .filter_complex("[0:v][1:v]concat=n=2:v=1:a=0[v]")
            .map("[v]")
            .map("2:a")
            .vcodec("libx264", pix_fmt="yuv420p")
            .acodec("aac", bitrate="192k")
            .output("out.mp4")
            .build()
        )
    """

    ffmpeg: str = "ffmpeg"
    overwrite: bool = True
    inputs: list[FFmpegInput] = field(default_factory=list)
    _filter_complex: str | None = None
    _video_filter: str | None = None
    _audio_filter: str | None = None
    _maps: list[str] = field(default_factory=list)
    _vcodec: str | None = None
    _vextra: list[str] = field(default_factory=list)
    _pix_fmt: str | None = None
    _acodec: str | None = None
    _aextra: list[str] = field(default_factory=list)
    _shortest: bool = False
    _output: str | None = None
    _extra_pre_output: list[str] = field(default_factory=list)

    # =================================================================
    # Chainable setters
    # =================================================================

    def add_input(
        self,
        path: str,
        *,
        loop: bool = False,
        duration: float | None = None,
        extra_flags: Sequence[str] | None = None,
    ) -> FFmpegCommandBuilder:
        self.inputs.append(
            FFmpegInput(
                path=path,
                loop=loop,
                duration=duration,
                extra_flags=list(extra_flags or []),
            )
        )
        return self

    def filter_complex(self, expr: str) -> FFmpegCommandBuilder:
        self._filter_complex = expr
        return self

    def video_filter(self, expr: str) -> FFmpegCommandBuilder:
        self._video_filter = expr
        return self

    def audio_filter(self, expr: str) -> FFmpegCommandBuilder:
        self._audio_filter = expr
        return self

    def map(self, stream: str) -> FFmpegCommandBuilder:
        """Ví dụ: ``.map("[v]")`` hoặc ``.map("2:a")``."""
        self._maps.append(stream)
        return self

    def vcodec(
        self,
        codec: str,
        *,
        pix_fmt: str | None = "yuv420p",
        extra: Sequence[str] | None = None,
    ) -> FFmpegCommandBuilder:
        self._vcodec = codec
        self._pix_fmt = pix_fmt
        if extra:
            self._vextra = list(extra)
        return self

    def acodec(
        self,
        codec: str,
        *,
        bitrate: str | None = "192k",
        extra: Sequence[str] | None = None,
    ) -> FFmpegCommandBuilder:
        self._acodec = codec
        if bitrate:
            self._aextra = ["-b:a", bitrate] + list(extra or [])
        else:
            self._aextra = list(extra or [])
        return self

    def shortest(self, enable: bool = True) -> FFmpegCommandBuilder:
        self._shortest = enable
        return self

    def extra(self, *args: str) -> FFmpegCommandBuilder:
        """Thêm flag tuỳ ý ngay trước output."""
        self._extra_pre_output.extend(args)
        return self

    def output(self, path: str) -> FFmpegCommandBuilder:
        self._output = path
        return self

    # =================================================================
    # Materialize
    # =================================================================

    def build(self) -> list[str]:
        if not self._output:
            raise ValueError("FFmpegCommandBuilder: output() is required")
        if not self.inputs:
            raise ValueError("FFmpegCommandBuilder: at least one input required")

        cmd: list[str] = [self.ffmpeg]
        if self.overwrite:
            cmd.append("-y")

        for inp in self.inputs:
            cmd.extend(inp.to_args())

        if self._filter_complex:
            cmd.extend(["-filter_complex", self._filter_complex])
        if self._video_filter:
            cmd.extend(["-vf", self._video_filter])
        if self._audio_filter:
            cmd.extend(["-af", self._audio_filter])

        for m in self._maps:
            cmd.extend(["-map", m])

        if self._vcodec:
            cmd.extend(["-c:v", self._vcodec])
            if self._pix_fmt:
                cmd.extend(["-pix_fmt", self._pix_fmt])
            cmd.extend(self._vextra)
        if self._acodec:
            cmd.extend(["-c:a", self._acodec])
            cmd.extend(self._aextra)
        if self._shortest:
            cmd.append("-shortest")

        cmd.extend(self._extra_pre_output)
        cmd.append(self._output)
        logger.debug("Built ffmpeg cmd: %s", cmd[:6] + ["..."])
        return cmd


# =====================================================================
# Presets — 4 use-case phổ biến
# =====================================================================


class FFmpegPresets:
    """Factory dựng sẵn cho các pipeline render hay dùng trong VEO Suite."""

    DEFAULT_FADE = 0.03  # 30 ms — đủ để chống pop ở đầu/cuối narration

    @staticmethod
    def parse_resolution(resolution: str, default: tuple[int, int] = (1920, 1080)) -> tuple[int, int]:
        try:
            w, h = resolution.lower().split("x")
            return int(w), int(h)
        except (ValueError, AttributeError):
            logger.warning("Bad resolution '%s', falling back to %dx%d", resolution, *default)
            return default

    @classmethod
    def slideshow(
        cls,
        ffmpeg: str,
        images: Sequence[str],
        audio_path: str,
        output_path: str,
        *,
        duration_per_image: float,
        audio_duration: float,
        resolution: str = "1920x1080",
        ken_burns_filter: str | None = None,
    ) -> list[str]:
        """Dựng slideshow từ N ảnh + 1 audio.

        Đảm bảo zoompan output đúng ``resolution``: filter này mặc định trả
        ra 1280x720 nếu không có ``s=WxH``, nên ta thêm ``:s={W}x{H}`` vào
        ken-burns mặc định và thêm ``scale={W}:{H}`` cuối chain để bảo hiểm
        khi caller truyền ``ken_burns_filter`` riêng.
        """
        if not images:
            raise ValueError("slideshow: images is empty")
        width, height = cls.parse_resolution(resolution)

        kb = ken_burns_filter or (
            f"zoompan=z='min(zoom+0.0015,1.5)':d=700:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}"
        )

        builder = FFmpegCommandBuilder(ffmpeg=ffmpeg)
        for img in images:
            builder.add_input(img, loop=True, duration=duration_per_image)
        builder.add_input(audio_path)

        # filter_complex: scale+pad+kenburns mỗi ảnh, rồi concat. Thêm scale
        # cuối để chống case caller truyền custom kenburns ko set kích thước.
        per_image_chain = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
            f"{kb},scale={width}:{height},setsar=1"
        )
        per_image = [f"[{i}:v]{per_image_chain}[v{i}]" for i in range(len(images))]
        concat_inputs = "".join(f"[v{i}]" for i in range(len(images)))
        concat = f"{concat_inputs}concat=n={len(images)}:v=1:a=0,format=yuv420p[v]"
        builder.filter_complex(";".join(per_image) + ";" + concat)

        # afade in/out để tránh pop
        fade_out_start = max(0.0, audio_duration - cls.DEFAULT_FADE)
        builder.audio_filter(
            f"afade=t=in:d={cls.DEFAULT_FADE},afade=t=out:st={fade_out_start}:d={cls.DEFAULT_FADE}"
        )
        builder.map("[v]")
        builder.map(f"{len(images)}:a")
        builder.vcodec("libx264", pix_fmt="yuv420p")
        builder.acodec("aac", bitrate="192k")
        builder.shortest(True)
        builder.output(output_path)
        return builder.build()

    @classmethod
    def concat_clips(
        cls,
        ffmpeg: str,
        list_file: str,
        audio_path: str,
        output_path: str,
        *,
        resolution: str = "1920x1080",
    ) -> list[str]:
        """Concat nhiều video clip (đã liệt kê trong ``list_file``) + audio mới."""
        width, height = cls.parse_resolution(resolution)
        builder = FFmpegCommandBuilder(ffmpeg=ffmpeg)
        builder.add_input(list_file, extra_flags=["-f", "concat", "-safe", "0"])
        builder.add_input(audio_path)
        builder.map("0:v:0")
        builder.map("1:a:0")
        builder.video_filter(
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
        )
        builder.audio_filter(f"afade=t=in:d={cls.DEFAULT_FADE},afade=t=out:d={cls.DEFAULT_FADE}")
        builder.vcodec("libx264", pix_fmt="yuv420p")
        builder.acodec("aac", bitrate="192k")
        builder.shortest(True)
        builder.output(output_path)
        return builder.build()

    @classmethod
    def mix_background_music(
        cls,
        ffmpeg: str,
        video_path: str,
        music_path: str,
        output_path: str,
        *,
        volume: float = 0.15,
        ducking: bool = True,
    ) -> list[str]:
        """Ghép nhạc nền vào video, có/không sidechain ducking.

        Lưu ý kỹ thuật: FFmpeg cấm dùng ``-af`` kèm ``-filter_complex`` cho
        cùng 1 stream output. Trước đây preset này gọi cả hai (afade qua
        ``-af`` + amix qua ``-filter_complex[aout]``) khiến lệnh fail với
        ``-vf/-af/-filter and -filter_complex cannot be used together``.
        Fix: nhúng afade vào trong filter_complex luôn, không gọi
        ``audio_filter()`` nữa.
        """
        # Fade-in 0.1s ngay đầu mix; fade-out yêu cầu biết duration nên
        # ta bỏ qua ở đây (caller có thể probe video rồi tự thêm afade).
        if ducking:
            a_filter = (
                f"[1:a]volume={volume},"
                f"sidechaincompress=threshold=0.1:ratio=4:attack=20:release=1000[bg];"
                f"[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2,"
                f"afade=t=in:d=0.1[aout]"
            )
        else:
            a_filter = (
                f"[1:a]volume={volume}[bg];"
                f"[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2,"
                f"afade=t=in:d=0.1[aout]"
            )
        builder = FFmpegCommandBuilder(ffmpeg=ffmpeg)
        builder.add_input(video_path)
        builder.add_input(music_path, extra_flags=["-stream_loop", "-1"])
        builder.filter_complex(a_filter)
        builder.map("0:v")
        builder.map("[aout]")
        builder.vcodec("copy", pix_fmt=None)
        builder.acodec("aac", bitrate="192k")
        builder.output(output_path)
        return builder.build()

    @classmethod
    def burn_subtitle(
        cls,
        ffmpeg: str,
        video_path: str,
        srt_path: str,
        output_path: str,
        *,
        font_name: str = "Arial",
        font_size: int = 18,
        color: str = "white",
    ) -> list[str]:
        """Hardcode subtitle vào video."""
        # Path escape cho FFmpeg subtitles filter
        srt_escaped = srt_path.replace("\\", "/").replace(":", "\\:")
        color_hex = "FFFFFF" if color == "white" else "00FFFF"
        style = (
            f"FontName={font_name},FontSize={font_size},"
            f"PrimaryColour=&H00{color_hex},OutlineColour=&H00000000,"
            f"BorderStyle=1,Outline=1,Shadow=1,MarginV=25,Alignment=2"
        )
        builder = FFmpegCommandBuilder(ffmpeg=ffmpeg)
        builder.add_input(video_path)
        builder.video_filter(f"subtitles='{srt_escaped}':force_style='{style}'")
        builder.acodec("copy", bitrate=None)
        builder.extra("-preset", "faster")
        builder.output(output_path)
        return builder.build()


__all__ = [
    "FFmpegCommandBuilder",
    "FFmpegInput",
    "FFmpegPresets",
]
