"""
VEO SUITE V3.2 — Pro Render Workers
====================================
Các Worker cao cấp (Pro Mode) tích hợp từ voice-pro:
- AudioSeparatorWorker: Tách giọng nói và nhạc nền (Demucs)
- SpeechAlignerWorker: Khớp phụ đề từng từ (WhisperX)
"""

import os
import subprocess
import logging
from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger("VeoSuite.ProWorkers")

class AudioSeparatorWorker(QThread):
    """
    Worker sử dụng Demucs để tách Vocals và BGM.
    Yêu cầu: pip install demucs
    """
    finished_signal = pyqtSignal(bool, str, dict) # success, message, result_paths
    progress_signal = pyqtSignal(str)

    def __init__(self, input_file, output_dir):
        super().__init__()
        self.input_file = input_file
        self.output_dir = output_dir

    def run(self):
        try:
            if not os.path.exists(self.input_file):
                self.finished_signal.emit(False, "File đầu vào không tồn tại", {})
                return

            self.progress_signal.emit("🧠 Đang khởi tạo Demucs (AI Separator)...")
            
            # Sử dụng lệnh terminal để chạy demucs (tránh xung đột thư viện nếu cài local)
            # Mặc định dùng mô hình htdemucs
            cmd = [
                "demucs", 
                "--two-stems", "vocals", 
                "-o", self.output_dir, 
                self.input_file
            ]
            
            self.progress_signal.emit("⏳ Đang tách âm thanh (Có thể mất vài phút)...")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                # Demucs lưu vào folder: output_dir/htdemucs/filename/
                base_name = os.path.splitext(os.path.basename(self.input_file))[0]
                model_name = "htdemucs"
                result_dir = os.path.join(self.output_dir, model_name, base_name)
                
                paths = {
                    "vocals": os.path.join(result_dir, "vocals.wav"),
                    "no_vocals": os.path.join(result_dir, "no_vocals.wav")
                }
                
                if os.path.exists(paths["vocals"]):
                    self.finished_signal.emit(True, "Tách âm hoàn tất!", paths)
                else:
                    self.finished_signal.emit(False, "Không tìm thấy file kết quả sau khi chạy.", {})
            else:
                logger.error(f"Demucs failed: {result.stderr}")
                self.finished_signal.emit(False, f"Lỗi Demucs: {result.stderr[:200]}", {})

        except Exception as e:
            logger.error(f"AudioSeparatorWorker error: {e}")
            self.finished_signal.emit(False, f"Lỗi hệ thống: {str(e)}", {})
