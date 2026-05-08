"""
VEO SUITE V3.2 — Render Workers
=================================
Worker cho Editor Tab:
  - EditorRenderWorker: Render video hoàn chỉnh (slideshow + music + subtitle)
"""

import os
import logging

from PyQt6.QtCore import QThread, pyqtSignal
from services.render_service import RenderService

logger = logging.getLogger("VeoSuite.Render.Workers")


class EditorRenderWorker(QThread):
    """Worker render video đầy đủ: Slideshow + Music + Subtitle."""
    finished_signal = pyqtSignal(bool, str, str)  # success, msg, output_path
    progress_signal = pyqtSignal(str)  # Progress updates
    
    def __init__(self, render_engine, src_path, out_path, metadata=None):
        super().__init__()
        self.renderer = render_engine
        self.src_path = src_path
        self.out_path = out_path
        self.metadata = metadata or {}
        self.is_running = True
        
    def stop(self):
        self.is_running = False
        
    def run(self):
        try:
            if not self.is_running: return
            
            voice_path = os.path.join(self.src_path, "voice.mp3")
            visuals_dir = os.path.join(self.src_path, "visuals")
            music_path = os.path.join(self.src_path, "background.mp3")
            srt_path = os.path.join(self.src_path, "voice.srt")
            
            # --- ĐÓNG GÓI METADATA (Sợi chỉ đỏ) ---
            self._save_production_info()
            
            temp_base = self.out_path.replace(".mp4", "_base.mp4")
            
            # 1. Dựng hình + Tiếng
            if not self.is_running: return
            logger.info(f"Rendering slideshow: {visuals_dir}")
            self.progress_signal.emit("🎬 Đang dựng video base...")
            suc, msg = self.renderer.create_video_slideshow(visuals_dir, voice_path, temp_base)
            if not suc:
                self.finished_signal.emit(False, msg, "")
                return
            
            current_video = temp_base
            
            # 2. Nhạc nền
            if self.is_running and os.path.exists(music_path):
                self.progress_signal.emit("🎵 Đang ghép nhạc nền...")
                temp_music = self.out_path.replace(".mp4", "_music.mp4")
                suc_m, msg_m = self.renderer.add_background_music(current_video, music_path, temp_music, volume=0.15)
                if suc_m:
                    self._safe_remove(current_video)
                    current_video = temp_music
                else:
                    logger.warning(f"Background music failed: {msg_m}")
            
            # 3. Subtitle
            if self.is_running and os.path.exists(srt_path):
                self.progress_signal.emit("📝 Đang ghép subtitle...")
                temp_sub = self.out_path.replace(".mp4", "_final.mp4")
                suc_s, msg_s = self.renderer.add_subtitles(current_video, srt_path, temp_sub)
                if suc_s:
                    self._safe_remove(current_video)
                    current_video = temp_sub
                else:
                    logger.warning(f"Subtitle burn failed: {msg_s}")
            
            if not self.is_running:
                self._safe_remove(current_video)
                return

            # Rename về đích
            self._safe_remove(self.out_path)
            os.rename(current_video, self.out_path)
            
            # [NEW] Tạo ảnh Timeline Summary cho AI Director
            summary_path = self.out_path.replace(".mp4", "_summary.png")
            self.renderer.generate_production_summary(self.out_path, summary_path)
            
            logger.info(f"Render complete: {self.out_path}")
            self.finished_signal.emit(True, "Render Xong!", self.out_path)
            
        except Exception as e:
            logger.error(f"EditorRenderWorker error: {e}", exc_info=True)
            self.finished_signal.emit(False, f"Lỗi: {str(e)}", "")

    def _save_production_info(self):
        """Lưu lại toàn bộ 'Sợi chỉ đỏ' vào file info.json"""
        import json
        info_path = os.path.join(self.src_path, "production_package.json")
        try:
            with open(info_path, "w", encoding="utf-8") as f:
                json.dump(self.metadata, f, indent=4, ensure_ascii=False)
            logger.info(f"Saved production info to {info_path}")
        except Exception as e:
            logger.warning(f"Could not save production info: {e}")

    @staticmethod
    def _safe_remove(path):
        """Xóa file an toàn, bỏ qua nếu không tồn tại."""
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError as e:
            logger.warning(f"Could not remove temp file {path}: {e}")
