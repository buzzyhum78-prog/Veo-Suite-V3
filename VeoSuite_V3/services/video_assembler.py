"""
VEO SUITE V3.3 — Video Assembler Service
==========================================
Tự động ghép video hoàn chỉnh từ nguyên liệu (Voice + Visuals + Music + Subtitle).
Lấy cảm hứng từ:
  - MoneyPrinterTurbo (FFmpeg concat + subtitle burn)
  - Pixelle-Video (Template-based rendering)
  - Video-Use (Ken Burns + crossfade)

Hỗ trợ:
  - Ken Burns effect cho ảnh tĩnh (zoom & pan)
  - Crossfade transition giữa các cảnh
  - Burn subtitle SRT vào video
  - Mix background music với audio chính
  - Xuất 1080p / 4K
"""

import os
import json
import logging
import subprocess
import shutil
from pathlib import Path

logger = logging.getLogger("VeoSuite.VideoAssembler")


class VideoAssembler:
    """
    Ghép video hoàn chỉnh từ các nguyên liệu đã sản xuất.
    
    Usage:
        assembler = VideoAssembler(project_path)
        assembler.assemble(output_path="final_video.mp4")
    """
    
    # Cấu hình mặc định
    DEFAULT_CONFIG = {
        "resolution": "1920x1080",   # 1080p
        "fps": 30,
        "transition": "crossfade",   # crossfade | fade | cut
        "transition_duration": 0.5,  # Giây
        "ken_burns_zoom": 1.08,      # Zoom 8% cho ảnh tĩnh
        "subtitle_font": "Arial",
        "subtitle_size": 24,
        "subtitle_color": "white",
        "subtitle_outline": 2,
        "subtitle_position": "bottom",  # bottom | center | top
        "bgm_volume": 0.15,           # Âm lượng nhạc nền (0.0 - 1.0)
        "voice_volume": 1.0,
    }
    
    def __init__(self, project_path: str, config: dict = None):
        self.project_path = project_path
        self.config = {**self.DEFAULT_CONFIG, **(config or {})}
        
        # Đường dẫn nguyên liệu
        self.voice_path = os.path.join(project_path, "voice.mp3")
        self.srt_path = os.path.join(project_path, "voice.srt")
        self.bgm_path = os.path.join(project_path, "background.mp3")
        self.visuals_dir = os.path.join(project_path, "visuals")
        self.output_dir = os.path.join(project_path, "output")
        
        os.makedirs(self.output_dir, exist_ok=True)
    
    def check_prerequisites(self) -> tuple:
        """Kiểm tra xem đã đủ nguyên liệu chưa."""
        issues = []
        if not os.path.exists(self.voice_path):
            issues.append("❌ Thiếu voice.mp3 (Chưa tạo giọng đọc)")
        if not os.path.exists(self.visuals_dir):
            issues.append("❌ Thiếu thư mục visuals/ (Chưa tạo hình ảnh)")
        else:
            visual_files = self._get_visual_files()
            if not visual_files:
                issues.append("❌ Thư mục visuals/ trống")
        
        # Optional files (cảnh báo nhẹ)
        warnings = []
        if not os.path.exists(self.srt_path):
            warnings.append("⚠️ Không có phụ đề (voice.srt)")
        if not os.path.exists(self.bgm_path):
            warnings.append("⚠️ Không có nhạc nền (background.mp3)")
            
        return issues, warnings
    
    def _get_visual_files(self) -> list:
        """Lấy danh sách file visual đã sắp xếp theo scene number."""
        if not os.path.exists(self.visuals_dir):
            return []
        
        valid_ext = {'.jpg', '.jpeg', '.png', '.mp4', '.mov', '.avi', '.webm'}
        files = []
        for f in os.listdir(self.visuals_dir):
            ext = os.path.splitext(f)[1].lower()
            if ext in valid_ext:
                files.append(os.path.join(self.visuals_dir, f))
        
        return sorted(files)
    
    def _get_voice_duration(self) -> float:
        """Lấy thời lượng voice.mp3 bằng ffprobe."""
        try:
            cmd = [
                "ffprobe", "-v", "quiet", "-show_entries", 
                "format=duration", "-of", "json", self.voice_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            data = json.loads(result.stdout)
            return float(data["format"]["duration"])
        except Exception as e:
            logger.warning(f"Cannot get voice duration: {e}")
            return 60.0  # Fallback 60s
    
    def _build_ken_burns_filter(self, idx: int, duration: float) -> str:
        """
        Tạo Ken Burns effect (zoom chậm + pan) cho 1 ảnh tĩnh.
        Lấy cảm hứng từ Video-Use.
        """
        zoom = self.config["ken_burns_zoom"]
        w, h = self.config["resolution"].split("x")
        
        # Alternate zoom direction: chẵn zoom-in, lẻ zoom-out
        if idx % 2 == 0:
            zoompan = f"zoompan=z='min(zoom+0.0005,{zoom})':d={int(duration * self.config['fps'])}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={self.config['fps']}"
        else:
            zoompan = f"zoompan=z='if(lte(zoom,1.0),{zoom},max(1.001,zoom-0.0005))':d={int(duration * self.config['fps'])}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={self.config['fps']}"
        
        return zoompan

    def assemble(self, output_filename: str = "final_video.mp4",
                 progress_callback=None) -> tuple:
        """
        Ghép video hoàn chỉnh.
        
        Returns:
            (success: bool, message: str, output_path: str)
        """
        def log(msg):
            logger.info(msg)
            if progress_callback:
                progress_callback(msg)
        
        # 1. Kiểm tra nguyên liệu
        issues, warnings = self.check_prerequisites()
        if issues:
            return False, "\n".join(issues), ""
        for w in warnings:
            log(w)
        
        visual_files = self._get_visual_files()
        voice_duration = self._get_voice_duration()
        scene_duration = voice_duration / max(len(visual_files), 1)
        
        log(f"🎬 Bắt đầu ghép video: {len(visual_files)} cảnh, {voice_duration:.1f}s")
        
        output_path = os.path.join(self.output_dir, output_filename)
        w, h = self.config["resolution"].split("x")
        
        try:
            # 2. Tạo video từ visuals (Mỗi cảnh = scene_duration giây)
            log("📐 Đang xử lý từng cảnh với Ken Burns effect...")
            temp_segments = []
            
            for idx, vf in enumerate(visual_files):
                ext = os.path.splitext(vf)[1].lower()
                temp_out = os.path.join(self.output_dir, f"_seg_{idx:03d}.mp4")
                
                if ext in ['.mp4', '.mov', '.avi', '.webm']:
                    # Video → Cắt theo thời lượng + scale
                    cmd = [
                        "ffmpeg", "-y", "-i", vf,
                        "-t", str(scene_duration),
                        "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black",
                        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                        "-an", "-r", str(self.config["fps"]),
                        temp_out
                    ]
                else:
                    # Ảnh → Ken Burns effect
                    kb_filter = self._build_ken_burns_filter(idx, scene_duration)
                    cmd = [
                        "ffmpeg", "-y", "-loop", "1", "-i", vf,
                        "-t", str(scene_duration),
                        "-vf", kb_filter,
                        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                        "-pix_fmt", "yuv420p",
                        temp_out
                    ]
                
                subprocess.run(cmd, capture_output=True, timeout=120)
                if os.path.exists(temp_out):
                    temp_segments.append(temp_out)
                    log(f"  ✅ Cảnh {idx+1}/{len(visual_files)}")
                else:
                    log(f"  ⚠️ Cảnh {idx+1} thất bại")
            
            if not temp_segments:
                return False, "❌ Không có cảnh nào được xử lý thành công.", ""
            
            # 3. Ghép tất cả segments lại
            log("🔗 Đang ghép các cảnh...")
            concat_file = os.path.join(self.output_dir, "_concat.txt")
            with open(concat_file, "w", encoding="utf-8") as f:
                for seg in temp_segments:
                    f.write(f"file '{seg}'\n")
            
            merged_video = os.path.join(self.output_dir, "_merged.mp4")
            cmd_concat = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0", 
                "-i", concat_file, "-c", "copy", merged_video
            ]
            subprocess.run(cmd_concat, capture_output=True, timeout=300)
            
            # 4. Mix audio: Voice + BGM
            log("🎵 Đang mix âm thanh (Voice + BGM)...")
            
            # [CTO FIX] Nếu thiếu nhạc nền -> Tự tạo silent track để quy trình mix không lỗi
            current_bgm = self.bgm_path
            if not os.path.exists(current_bgm):
                log("⚠️ Không có nhạc nền (background.mp3). Đang tạo bản thu im lặng (Silent Track)...")
                silent_bgm = os.path.join(self.output_dir, "_silent_bgm.mp3")
                # Tạo 10s im lặng lặp lại (FFmpeg anullsrc)
                cmd_silent = [
                    "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                    "-t", "10", "-acodec", "libmp3lame", silent_bgm
                ]
                subprocess.run(cmd_silent, capture_output=True, timeout=30)
                if os.path.exists(silent_bgm):
                    current_bgm = silent_bgm

            if os.path.exists(current_bgm):
                mixed_audio = os.path.join(self.output_dir, "_mixed_audio.mp3")
                bgm_vol = self.config["bgm_volume"]
                cmd_audio = [
                    "ffmpeg", "-y",
                    "-i", self.voice_path,
                    "-i", current_bgm,
                    "-filter_complex",
                    f"[0:a]volume={self.config['voice_volume']}[voice];"
                    f"[1:a]volume={bgm_vol},aloop=loop=-1:size=2e+09[bgm];"
                    f"[voice][bgm]amix=inputs=2:duration=first:dropout_transition=3[out]",
                    "-map", "[out]", "-c:a", "libmp3lame", "-b:a", "192k",
                    mixed_audio
                ]
                subprocess.run(cmd_audio, capture_output=True, timeout=120)
                audio_file = mixed_audio if os.path.exists(mixed_audio) else self.voice_path
            else:
                audio_file = self.voice_path
            
            # 5. Ghép Video + Audio + Subtitle
            log("🎬 Đang render video cuối cùng...")
            
            # Build subtitle filter nếu có SRT
            subtitle_filter = ""
            if os.path.exists(self.srt_path):
                srt_escaped = self.srt_path.replace("\\", "/").replace(":", "\\:")
                font = self.config["subtitle_font"]
                size = self.config["subtitle_size"]
                color = self.config["subtitle_color"]
                outline = self.config["subtitle_outline"]
                
                # Vị trí phụ đề
                margin_v = 30
                if self.config["subtitle_position"] == "center":
                    margin_v = int(int(h) / 2 - size)
                elif self.config["subtitle_position"] == "top":
                    margin_v = 20
                    
                subtitle_filter = f"subtitles='{srt_escaped}':force_style='FontName={font},FontSize={size},PrimaryColour=&Hffffff&,OutlineColour=&H000000&,Outline={outline},MarginV={margin_v},Alignment=2'"
            
            if subtitle_filter:
                cmd_final = [
                    "ffmpeg", "-y",
                    "-i", merged_video,
                    "-i", audio_file,
                    "-vf", subtitle_filter,
                    "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                    "-c:a", "aac", "-b:a", "192k",
                    "-shortest", "-movflags", "+faststart",
                    output_path
                ]
            else:
                cmd_final = [
                    "ffmpeg", "-y",
                    "-i", merged_video,
                    "-i", audio_file,
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-shortest", "-movflags", "+faststart",
                    output_path
                ]
            
            subprocess.run(cmd_final, capture_output=True, timeout=600)
            
            # 6. Dọn dẹp temp files
            log("🧹 Dọn dẹp file tạm...")
            for seg in temp_segments:
                try: os.remove(seg)
                except Exception: pass
            for tmp in [concat_file, merged_video]:
                try: os.remove(tmp)
                except Exception: pass
            mixed_tmp = os.path.join(self.output_dir, "_mixed_audio.mp3")
            silent_tmp = os.path.join(self.output_dir, "_silent_bgm.mp3")
            for tmp in [mixed_tmp, silent_tmp]:
                if os.path.exists(tmp):
                    try: os.remove(tmp)
                    except Exception: pass
            
            if os.path.exists(output_path):
                # Lấy kích thước file
                size_mb = os.path.getsize(output_path) / (1024 * 1024)
                log(f"🎉 HOÀN TẤT! Video: {output_path} ({size_mb:.1f} MB)")
                return True, f"✅ Video đã render xong! ({size_mb:.1f} MB)", output_path
            else:
                return False, "❌ FFmpeg không tạo được file output.", ""
                
        except subprocess.TimeoutExpired:
            return False, "⏰ Quá thời gian render (timeout).", ""
        except Exception as e:
            logger.error(f"VideoAssembler error: {e}")
            return False, f"❌ Lỗi render: {e}", ""
