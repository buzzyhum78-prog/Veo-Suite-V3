"""
VEO SUITE V3.2 — Render Service
==================================
Xử lý video production via FFmpeg:
  - Slideshow generation (ảnh + audio → video)
  - Ken Burns effect (zoom in/out/pan ngẫu nhiên)
  - Subtitle burn-in (hardcoded captions)
  - Audio duration detection
"""

import logging
import os
import random
import subprocess
from pathlib import Path

from services.config_manager import FFMPEG_PATH, FFPROBE_PATH

logger = logging.getLogger("VeoSuite.Render")

# Tối đa cho mỗi lần gọi FFmpeg — thay bằng env nếu cần render dài hơn.
import os as _os
FFMPEG_TIMEOUT = int(_os.getenv("VEO_FFMPEG_TIMEOUT", "1800"))  # 30 phút


class RenderService:
    """FFmpeg-based video renderer."""

    def __init__(self, ffmpeg_path: str = None, ffprobe_path: str = None):
        self.ffmpeg = ffmpeg_path or FFMPEG_PATH
        self.ffprobe = ffprobe_path or FFPROBE_PATH

    # =========================================================================
    # PUBLIC: Lấy thời lượng audio
    # =========================================================================

    def get_audio_duration(self, audio_path: str) -> float:
        """Lấy duration (seconds) của file audio bằng ffprobe."""
        try:
            cmd = [
                self.ffprobe, "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                audio_path,
            ]
            result = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, timeout=10
            )
            return float(result.stdout.strip())
        except Exception as e:
            logger.error(f"Cannot get audio duration: {e}")
            return 0

    # =========================================================================
    # PUBLIC: Tạo video slideshow
    # =========================================================================

    def create_video_slideshow(self, images_dir: str, audio_path: str,
                               output_path: str, resolution: str = "1920x1080"):
        """
        Dựng video từ thư mục visuals: hỗ trợ cả file video (.mp4/.mov) lẫn file ảnh (.jpg/.png).
        - File video: nối trực tiếp bằng concat filter.
        - File ảnh: áp dụng hiệu ứng Ken Burns zoom.
        Returns (success: bool, path_or_message: str).
        """
        if not os.path.exists(audio_path):
            return False, "Audio file not found"

        # Phân loại file: ảnh và video riêng biệt
        IMAGE_EXTS = ('.jpg', '.png', '.jpeg', '.webp')
        VIDEO_EXTS = ('.mp4', '.mov', '.avi', '.mkv', '.webm')
        all_files = sorted([
            os.path.join(images_dir, f) for f in os.listdir(images_dir)
            if f.lower().endswith(IMAGE_EXTS + VIDEO_EXTS)
        ])
        images = [f for f in all_files if f.lower().endswith(IMAGE_EXTS)]
        videos = [f for f in all_files if f.lower().endswith(VIDEO_EXTS)]
        
        # Nếu chỉ có video clips, dùng concat nhanh
        if videos and not images:
            return self._concat_video_clips(videos, audio_path, output_path, resolution)
        
        # Nếu chỉ có ảnh, dùng slideshow + Ken Burns
        if not all_files:
            return False, "No media files found in visuals directory"

        # Nếu không có ảnh nhưng có video lẫn lộn — xử lý bằng concat
        if not images:
            return self._concat_video_clips(videos, audio_path, output_path, resolution)

        # Calculate timing
        audio_duration = self.get_audio_duration(audio_path)
        if audio_duration == 0:
            return False, "Audio duration is 0 (corrupted file?)"

        duration_per_image = (audio_duration / len(images)) + 0.5

        # Parse resolution
        try:
            w, h = resolution.split("x")
            width, height = int(w), int(h)
        except ValueError:
            width, height = 1920, 1080

        logger.info(
            f"Rendering: {len(images)} images, "
            f"audio={audio_duration:.1f}s, "
            f"per_image={duration_per_image:.1f}s, "
            f"resolution={width}x{height}"
        )

        try:
            # Build FFmpeg filter_complex
            inputs = []
            filters = []
            concat_parts = []

            # Ken Burns effects pool
            ken_burns_effects = [
                # Zoom In Center
                "zoompan=z='min(zoom+0.0015,1.5)':d=700"
                ":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
                # Zoom Out
                "zoompan=z='if(lte(zoom,1.0),1.5,max(1.001,zoom-0.0015))':d=700"
                ":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
                # Pan Left
                "zoompan=z='min(zoom+0.001,1.2)'"
                ":x='if(lte(on,1),(iw-iw/zoom)/2,x-0.002)'"
                ":y='(ih-ih/zoom)/2':d=700",
            ]

            for i, img_path in enumerate(images):
                inputs.extend(["-loop", "1", "-t", str(duration_per_image), "-i", img_path])

                zoom = random.choice(ken_burns_effects)
                filter_chain = (
                    f"[{i}:v]"
                    f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                    f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
                    f"{zoom},"
                    f"setsar=1[v{i}]"
                )
                filters.append(filter_chain)
                concat_parts.append(f"[v{i}]")

            # Concat filter
            concat_filter = (
                f"{''.join(concat_parts)}concat=n={len(images)}:v=1:a=0,"
                f"format=yuv420p[v]"
            )
            full_filter = ";".join(filters) + ";" + concat_filter

            # Build command
            cmd = [self.ffmpeg, "-y"]
            cmd.extend(inputs)
            cmd.extend([
                "-i", audio_path,
                "-filter_complex", full_filter,
                "-map", "[v]",
                "-map", f"{len(images)}:a",
                # [VEO UPGRADE] Add 30ms fades to narration to prevent pops
                "-af", f"afade=t=in:d=0.03,afade=t=out:st={audio_duration-0.03}:d=0.03",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest",
                output_path,
            ])

            logger.debug(f"FFmpeg command: {' '.join(cmd[:20])}...")
            subprocess.run(cmd, check=True, capture_output=True, timeout=FFMPEG_TIMEOUT)

            logger.info(f"Render complete: {output_path}")
            return True, output_path

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode('utf-8', errors='replace')[-500:] if e.stderr else str(e)
            logger.error(f"FFmpeg error: {error_msg}")
            return False, f"FFmpeg Error: {error_msg}"
        except Exception as e:
            logger.error(f"Render error: {e}")
            return False, f"Render Error: {e}"

    # =========================================================================
    # PUBLIC: Add background music
    # =========================================================================

    def add_background_music(self, video_path: str, music_path: str, output_path: str, 
                             volume: float = 0.15, ducking: bool = True):
        """
        Ghép nhạc nền vào video với kỹ thuật Sidechain Compression (Ducking).
        Nhạc nền sẽ tự động giảm âm lượng khi có tiếng voice.
        
        Args:
            video_path: Video đã có voice
            music_path: File nhạc nền
            output_path: Xuất file
            volume: Âm lượng nhạc nền tối đa (0.15 = 15%)
            ducking: Nếu True, áp dụng hiệu ứng giảm âm lượng nhạc khi voice nói.
        """
        try:
            # Filter complex: 
            # [0:a] là voice, [1:a] là music
            # sidechaincompress: giảm [1:a] dựa trên cường độ của [0:a]
            if ducking:
                # threshold=0.1: mức độ nhạy, ratio=4: tỉ lệ giảm, attack=20: tốc độ giảm, release=1000: tốc độ hồi âm
                a_filter = (
                    f"[1:a]volume={volume},sidechaincompress=threshold=0.1:ratio=4:attack=20:release=1000[bg];"
                    f"[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[aout]"
                )
            else:
                a_filter = f"[1:a]volume={volume}[bg];[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[aout]"

            cmd = [
                self.ffmpeg, "-y",
                "-i", video_path,
                "-stream_loop", "-1", "-i", music_path,
                "-filter_complex", a_filter,
                "-map", "0:v", "-map", "[aout]",
                # [VEO UPGRADE] Smooth transition for mixed audio
                "-af", "afade=t=in:d=0.1,afade=t=out:d=0.1",
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k",
                output_path
            ]
            
            logger.info(f"Mixing audio (Ducking={ducking}) -> {output_path}")
            subprocess.run(cmd, check=True, capture_output=True, timeout=FFMPEG_TIMEOUT)
            return True, output_path
            
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode('utf-8', errors='replace')[-300:] if e.stderr else str(e)
            logger.error(f"Mixing error: {error_msg}")
            return False, f"Mix Error: {error_msg}"
        except Exception as e:
            return False, str(e)

    # =========================================================================
    # PUBLIC: Burn-in subtitle
    # =========================================================================

    def add_subtitles(self, video_path: str, srt_path: str, output_path: str,
                      font_name: str = "Arial", font_size: int = 18, color: str = "white"):
        """
        Burn subtitle cứng vào video với phong cách hiện đại (Premium Style).
        """
        import shutil
        import tempfile
        import time
        
        temp_dir = tempfile.gettempdir()
        safe_srt_name = f"veo_sub_{int(time.time())}.srt"
        safe_srt_path = os.path.join(temp_dir, safe_srt_name)
        
        try:
            shutil.copy2(srt_path, safe_srt_path)
        except Exception as e:
            return False, f"Subtitle copy error: {e}"

        srt_escaped = safe_srt_path.replace("\\", "/").replace(":", "\\:")

        # Premium Style: Shadow + Outline + Margin
        # PrimaryColour=&H00FFFFFF (BGR format: White)
        color_hex = "FFFFFF" if color == "white" else "00FFFF" # Vàng nếu không phải trắng
        
        style = (
            f"FontName={font_name},"
            f"FontSize={font_size},"
            f"PrimaryColour=&H00{color_hex},"
            f"OutlineColour=&H00000000,"
            f"BorderStyle=1,Outline=1,Shadow=1,MarginV=25,Alignment=2"
        )

        cmd = [
            self.ffmpeg, "-y",
            "-i", video_path,
            "-vf", f"subtitles='{srt_escaped}':force_style='{style}'",
            "-c:a", "copy",
            "-preset", "faster",
            output_path,
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=FFMPEG_TIMEOUT)
            return True, output_path
        except subprocess.CalledProcessError as e:
            return False, f"Sub Error: {e.stderr.decode('utf-8', errors='replace')[-200:]}"
        finally:
            if os.path.exists(safe_srt_path):
                os.remove(safe_srt_path)

    # =========================================================================
    # PUBLIC: Add Watermark/Logo & Signature
    # =========================================================================

    def add_branding(self, video_path: str, output_path: str, 
                     logo_path: str = None, signature: str = None):
        """
        Thêm Logo (góc trên phải) và Chữ ký (góc dưới phải) vào video.
        """
        if not logo_path and not signature:
            import shutil
            shutil.copy2(video_path, output_path)
            return True, output_path

        try:
            filters = []
            inputs = ["-i", video_path]
            
            # 1. Xử lý Logo
            if logo_path and os.path.exists(logo_path):
                inputs.extend(["-i", logo_path])
                # scale logo to 150px width, place at top-right with 20px margin
                filters.append("[1:v]scale=150:-1[logo];[0:v][logo]overlay=main_w-overlay_w-20:20[v_logo]")
                v_stream = "[v_logo]"
            else:
                v_stream = "[0:v]"

            # 2. Xử lý Signature (Text)
            if signature:
                # drawtext: bottom-right, white, shadow
                text_filter = (
                    f"drawtext=text='{signature}':fontcolor=white:fontsize=24:"
                    f"shadowcolor=black:shadowx=2:shadowy=2:"
                    f"x=w-tw-20:y=h-th-20"
                )
                filters.append(f"{v_stream}{text_filter}[v_final]")
                final_stream = "[v_final]"
            else:
                final_stream = v_stream

            cmd = [self.ffmpeg, "-y"]
            cmd.extend(inputs)
            cmd.extend([
                "-filter_complex", ";".join(filters) if filters else "copy",
                "-map", final_stream if filters else "0:v",
                "-map", "0:a",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-c:a", "copy",
                output_path
            ])

            logger.info(f"Adding branding to {video_path}...")
            subprocess.run(cmd, check=True, capture_output=True, timeout=FFMPEG_TIMEOUT)
            return True, output_path

        except Exception as e:
            logger.error(f"Branding error: {e}")
            return False, str(e)

    # =========================================================================
    # PRIVATE: Nối các video clips (khi visuals chứa toàn file .mp4)
    # =========================================================================

    def _concat_video_clips(self, video_paths: list, audio_path: str, 
                            output_path: str, resolution: str = "1920x1080") -> tuple:
        """
        Nối nhiều video clips + ghép audio mới (voice/music).
        Dùng FFmpeg filter_complex để re-encode và sync audio.
        """
        import tempfile, time
        try:
            w, h = resolution.split("x") 
            width, height = int(w), int(h)
        except ValueError:
            width, height = 1920, 1080

        # Tạo file danh sách tạm thời (Safe ASCII path)
        temp_dir = tempfile.gettempdir()
        list_file = os.path.join(temp_dir, f"veo_concat_{int(time.time())}.txt")
        
        try:
            with open(list_file, "w", encoding="utf-8") as f:
                for vp in video_paths:
                    f.write(f"file '{vp.replace(chr(92), '/')}'\n")

            # Build re-encode concat command với audio mới
            cmd = [
                self.ffmpeg, "-y",
                "-f", "concat", "-safe", "0", "-i", list_file,
                "-i", audio_path,
                "-map", "0:v:0", "-map", "1:a:0",
                "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                       f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1",
                # [VEO UPGRADE] Add crossfades between narration segments if needed
                # For now, apply global fades to the resulting audio track
                "-af", "afade=t=in:d=0.03,afade=t=out:d=0.03",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest",
                output_path
            ]

            logger.info(f"Concat {len(video_paths)} video clips -> {output_path}")
            subprocess.run(cmd, check=True, capture_output=True, timeout=FFMPEG_TIMEOUT)
            logger.info(f"Render complete (concat): {output_path}")
            return True, output_path

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode("utf-8", errors="replace")[-500:] if e.stderr else str(e)
            logger.error(f"Concat FFmpeg error: {error_msg}")
            return False, f"Concat Error: {error_msg}"
        except Exception as e:
            return False, f"Concat Exception: {e}"
        finally:
            try:
                if os.path.exists(list_file):
                    os.remove(list_file)
            except Exception: pass

    # =========================================================================
    # [NEW] AGENTIC VISIBILITY: Timeline Summary Generator
    # =========================================================================

    def generate_production_summary(self, video_path: str, output_png: str) -> bool:
        """
        Tạo ảnh tóm tắt Timeline (Filmstrip + Waveform) để AI 'nhìn' thấy kết quả.
        Tương tự logic 'timeline_view' của browser-use/video-use.
        """
        import tempfile
        temp_dir = tempfile.gettempdir()
        waveform_png = os.path.join(temp_dir, "veo_wv.png")
        filmstrip_png = os.path.join(temp_dir, "veo_fs.png")
        
        try:
            # 1. Tạo Waveform
            cmd_wv = [
                self.ffmpeg, "-y", "-i", video_path,
                "-filter_complex", "showwavespic=s=1280x200:colors=cyan|blue",
                "-frames:v", "1", waveform_png
            ]
            subprocess.run(cmd_wv, check=True, capture_output=True, timeout=FFMPEG_TIMEOUT)
            
            # 2. Tạo Filmstrip (N khung hình ghép lại)
            # Dùng tile filter để ghép 5 khung hình
            cmd_fs = [
                self.ffmpeg, "-y", "-i", video_path,
                "-vf", "select='not(mod(n,100))',scale=256:-1,tile=5x1",
                "-frames:v", "1", filmstrip_png
            ]
            subprocess.run(cmd_fs, check=True, capture_output=True, timeout=FFMPEG_TIMEOUT)
            
            # 3. Ghép Waveform và Filmstrip thành một ảnh duy nhất (Dùng vstack)
            cmd_merge = [
                self.ffmpeg, "-y",
                "-i", filmstrip_png, "-i", waveform_png,
                "-filter_complex", "[0:v]scale=1280:-1[v1];[v1][1:v]vstack=inputs=2",
                output_png
            ]
            subprocess.run(cmd_merge, check=True, capture_output=True, timeout=FFMPEG_TIMEOUT)
            
            logger.info(f"Generated production summary: {output_png}")
            return True
        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            return False
        finally:
            for p in [waveform_png, filmstrip_png]:
                if os.path.exists(p): os.remove(p)