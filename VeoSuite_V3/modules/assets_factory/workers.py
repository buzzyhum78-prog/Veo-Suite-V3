"""
VEO SUITE V3.2 — Assets Factory Workers
=========================================
Các QThread worker cho Media Tab:
  - MusicSearchWorker: Tìm nhạc online
  - VoiceWorker: Tạo voice + subtitle (Edge TTS / Google / OpenAI)
  - VisualWorker: Tìm/tạo ảnh stock + AI (Director Classified)
  - BrandArtistWorker: Vẽ logo/banner (Multi-engine)
  - GenericWorker: Worker chạy task đơn giản
  - RenderVideoWorker: Render video từ materials
"""

import os
import time
import random
import shutil
import asyncio
import logging

import requests
from PyQt6.QtCore import QThread, pyqtSignal

from services.ai_factory import AIFactory
from services.render_service import RenderService
from modules.assets_factory.constants import *
from modules.assets_factory.subtitle_engine import SubtitleEngine

logger = logging.getLogger("VeoSuite.AssetsFactory.Workers")

# Voice config path
VOICE_CONFIG_FILE = "VEO_DB/voice_engine_config.json"

# Safe imports
try:
    from services.audio_service import AudioService
    AUDIO_AVAILABLE = True
except ImportError:
    AudioService = None
    AUDIO_AVAILABLE = False
    logger.warning("AudioService not available")

try:
    from services.stock_service import StockService
    STOCK_AVAILABLE = True
except ImportError:
    StockService = None
    STOCK_AVAILABLE = False
    logger.warning("StockService not available")

try:
    import edge_tts
    EDGE_AVAILABLE = True
except ImportError:
    EDGE_AVAILABLE = False
    logger.warning("edge-tts not installed. Run 'pip install edge-tts' for subtitle support.")

try:
    from google import genai
    from google.genai import types as genai_types
    GENAI_AVAILABLE = True
except ImportError:
    genai = None
    genai_types = None
    GENAI_AVAILABLE = False


# ============================================================================
# MUSIC SEARCH WORKER
# ============================================================================
class MusicSearchWorker(QThread):
    """Công nhân tìm nhạc bằng Pixabay API thay vì hardcode."""
    finished_signal = pyqtSignal(list)

    def __init__(self, query):
        super().__init__()
        self.query = query

    def run(self):
        pixabay_key = "43267597-d867c4709292c300885e3474d" # Community Key
        url = "https://pixabay.com/api/audio/"
        
        results = []
        try:
            resp = requests.get(url, params={
                "key": pixabay_key,
                "q": self.query,
                "per_page": 10
            }, timeout=10)
            
            if resp.status_code == 200:
                hits = resp.json().get("hits", [])
                for h in hits:
                    results.append({
                        "name": h.get("tags", "Unknown Track"),
                        "duration": f"{h.get('duration', 0)//60:02d}:{h.get('duration', 0)%60:02d}",
                        "url": h.get("unlocked_url") or h.get("url")
                    })
        except Exception as e:
            logger.error(f"Music search failed: {e}")
            
        if not results:
            results = [
                {"name": "Lofi Study (Fallback)", "duration": "03:20", "url": "https://cdn.pixabay.com/download/audio/2022/05/16/audio_b200b39f1c.mp3"}
            ]
            
        random.shuffle(results)
        self.finished_signal.emit(results)
        

# ============================================================================
# MUSIC AUTO WORKER (Search & Download)
# ============================================================================
class MusicAutoWorker(QThread):
    """Công nhân tự động tìm và tải nhạc nền (background.mp3)."""
    finished_signal = pyqtSignal(bool, str, str) # (success, message, file_path)

    def __init__(self, keyword, output_path):
        super().__init__()
        self.keyword = keyword
        self.output_path = output_path

    def run(self):
        try:
            if not STOCK_AVAILABLE:
                self.finished_signal.emit(False, "StockService không khả dụng", "")
                return

            stock = StockService()
            success, result = stock.download_music(self.keyword, self.output_path)
            
            if success:
                self.finished_signal.emit(True, f"✅ Đã tải nhạc: {self.keyword}", result)
            else:
                self.finished_signal.emit(False, f"❌ Lỗi tải nhạc: {result}", "")
        except Exception as e:
            logger.error(f"MusicAutoWorker error: {e}")
            self.finished_signal.emit(False, str(e), "")


# ============================================================================
# VOICE WORKER (Edge TTS + Google + OpenAI)
# ============================================================================
class VoiceWorker(QThread): 
    finished_signal = pyqtSignal(bool, str, str)  # (success, message, file_path)
    log_signal = pyqtSignal(str)

    def __init__(self, text, output_path, meta_data):
        super().__init__()
        self.text = text
        self.output_path = output_path
        self.meta_data = meta_data
        self.is_running = True
        self.ai = AIFactory()

    def stop(self):
        self.is_running = False

    def run(self):
        self.is_running = True
        try:
            config = self.ai.get_worker_config("voice_actor") 
            provider = self.meta_data.get("provider_override", "edge")
            if provider == "auto":
                provider = config.get("provider", "edge") if config else "edge"

            os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
            srt_path = self.output_path.replace(".mp3", ".srt")
            success = False
            msg = ""

            if provider == "edge":
                if not EDGE_AVAILABLE:
                    self.finished_signal.emit(False, "Thiếu thư viện edge-tts. Chạy 'pip install edge-tts'", "")
                    return

                self.log_signal.emit("🚀 Edge TTS: Đang tạo Audio + Sub...")
                voice = self.meta_data.get("voice_id", "vi-VN-HoaiMyNeural") 
                rate = self.meta_data.get("rate", "+0%")
                pitch = self.meta_data.get("pitch", "+0Hz")
                
                try:
                    # Clean text to avoid edge-tts issues
                    safe_text = self.text.replace('"', '').replace("'", "")
                    if len(safe_text) < 2:
                        raise Exception("Nội dung text quá ngắn để tạo voice.")

                    asyncio.run(self._run_edge_native(safe_text, voice, rate, pitch, self.output_path, srt_path))
                    
                    if os.path.exists(self.output_path) and os.path.getsize(self.output_path) > 0:
                        success = True
                        msg = "✅ Xong (MP3 + SRT)"
                        if not os.path.exists(srt_path) or os.path.getsize(srt_path) == 0:
                             self._generate_srt_heuristic(safe_text, srt_path)
                             msg += " (Sub Fallback)"
                    else:
                        raise Exception("File MP3 tạo ra bị lỗi hoặc rỗng.")
                except Exception as e:
                    logger.error(f"Edge TTS error: {e}")
                    self.finished_signal.emit(False, f"Lỗi Edge TTS: {str(e)}", "")
                    return
            else:
                self.log_signal.emit(f"🎙️ Đang gọi API: {provider}...")
                if not AUDIO_AVAILABLE:
                    self.finished_signal.emit(False, "AudioService không khả dụng", "")
                    return
                srv = AudioService()
                success, msg = srv.create_audio(self.text, self.output_path, self.meta_data)
                if success:
                    self._generate_srt_heuristic(self.text, srt_path)
                    msg += " + Sub (Auto-Estimate)"

            # [VEO UPGRADE] Auto-format to High-Impact Subtitles
            if success and os.path.exists(srt_path):
                try:
                    engine = SubtitleEngine()
                    engine.create_premium_srt(srt_path, srt_path)
                    msg += " 🔥 [Premium Sub]"
                except Exception as e:
                    logger.warning(f"Failed to upgrade subtitles: {e}")

            self.finished_signal.emit(success, msg, self.output_path)
        except Exception as e:
            logger.error(f"VoiceWorker error: {e}", exc_info=True)
            self.finished_signal.emit(False, f"Lỗi: {str(e)}", "")

    async def _run_edge_native(self, text, voice, rate, pitch, audio_file, srt_file):
        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        submaker = edge_tts.SubMaker()
        with open(audio_file, "wb") as file:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio": file.write(chunk["data"])
                elif chunk["type"] == "WordBoundary": submaker.feed(chunk)
        with open(srt_file, "w", encoding="utf-8") as file:
            try:
                if hasattr(submaker, 'generate_subs'): file.write(submaker.generate_subs())
                elif hasattr(submaker, 'get_subs'): file.write(submaker.get_subs())
            except: pass

    def _generate_srt_heuristic(self, text, srt_path):
        try:
            sentences = [s.strip() for s in text.replace('.', '.|').split('|') if s.strip()]
            char_per_sec = 15 
            srt_content = ""
            current_time = 0.0
            for i, sen in enumerate(sentences):
                duration = max(1.5, len(sen) / char_per_sec)
                start, end = current_time, current_time + duration
                def fmt(t):
                    return f"{int(t//3600):02}:{int((t%3600)//60):02}:{int(t%60):02},{int((t%1)*1000):03}"
                srt_content += f"{i+1}\n{fmt(start)} --> {fmt(end)}\n{sen}\n\n"
                current_time = end
            with open(srt_path, "w", encoding="utf-8") as f: f.write(srt_content)
        except: pass


# ============================================================================
# VISUAL WORKER (Director Classified: Stock vs AI)
# ============================================================================
class VisualWorker(QThread):
    finished_signal = pyqtSignal(bool, str, str)
    progress_signal = pyqtSignal(str) 
    scene_finished_signal = pyqtSignal(int)

    def __init__(self, scenes_file_path, output_folder, ai_ratio=20):
        super().__init__()
        self.scenes_path = scenes_file_path
        self.output_folder = output_folder
        self.ai_ratio = ai_ratio
        self.is_running = True
        self.ai = AIFactory()
        self.pexels_key = self.ai.get_api_key("pexels")

    def stop(self):
        self.is_running = False

    def run(self):
        self.is_running = True
        orient = getattr(self, 'orientation', 'landscape')
        target_style = getattr(self, 'style_config', 'Cinematic, Realistic, 4K')
        
        try:
            with open(self.scenes_path, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f.readlines() if l.strip()]
        except Exception as e:
            self.finished_signal.emit(False, f"Lỗi đọc file: {e}", "")
            return

        if not lines:
            self.finished_signal.emit(False, "File scenes rỗng!", "")
            return

        # [AUTO DETECT STYLE] — Dùng STYLE_CATALOG 20 phong cách
        if target_style == "Auto Detect":
            self.progress_signal.emit("🤖 AI đang phân tích Kịch bản để chọn Phong Cách...")
            try:
                from modules.assets_factory.prompt_templates import get_style_for_ai_detect, get_all_style_names
                detected = get_style_for_ai_detect(' '.join(lines[:3]))
                target_style = detected
                self.progress_signal.emit(f"✨ AI đã chọn phong cách: {target_style}")
            except Exception as e:
                target_style = "Cinematic"
                self.progress_signal.emit(f"⚠️ Fallback → Cinematic (Lỗi: {e})")
        
        # Lấy prompt prefix cho phong cách đã chọn
        style_prompt_prefix = ""
        try:
            from modules.assets_factory.prompt_templates import get_prompt_prefix
            style_prompt_prefix = get_prompt_prefix(target_style)
        except:
            style_prompt_prefix = target_style  # Fallback dùng tên style thô

        if not STOCK_AVAILABLE:
            self.finished_signal.emit(False, "Thiếu thư viện StockService", "")
            return
            
        try:
            stock_engine = StockService(self.pexels_key) 
        except Exception as e:
            self.finished_signal.emit(False, f"Lỗi Stock: {e}", "")
            return
        
        save_dir = os.path.join(self.output_folder, "visuals")
        os.makedirs(save_dir, exist_ok=True)

        try:
            self.progress_signal.emit(f"🚀 [Xưởng Media] Tự động hóa {len(lines)} cảnh...")
            count_success = 0
            
            for i, line in enumerate(lines):
                if not self.is_running: return
                scene_num = i + 1
                self.progress_signal.emit(f"🎬 Cảnh {scene_num}: Director đang phân loại...")
                
                # --- AI Director ---
                director_prompt = f"Phân loại cảnh: '{line}'. Trả về JSON: {{'type': 'stock'|'ai_image', 'keywords': 'en keywords', 'prompt': 'ai prompt'}}"
                success_ai, res_ai = self.ai.execute_custom_ai("google", director_prompt, "gemini-2.0-flash", role="visual_director")
                
                # Fallback to Pollinations (Free) if Gemini fails
                if not success_ai:
                    success_ai, res_ai = self.ai.execute_custom_ai("pollinations_text", director_prompt, role="visual_director")

                scene_type, search_query, ai_prompt = "stock", line, line
                if success_ai:
                    try:
                        import json, re
                        match = re.search(r'(\{.*\})', str(res_ai), re.DOTALL)
                        if match:
                            # Fix common JSON formatting issues from free LLMs
                            json_str = match.group(1).replace("'", '"')
                            data = json.loads(json_str)
                            scene_type = data.get("type", "stock")
                            search_query = data.get("keywords", line)
                            ai_prompt = data.get("prompt", line)
                    except: pass

                # Ghi đè scene_type dựa trên cấu hình người dùng
                if self.ai_ratio == 100:
                    scene_type = "ai_image"
                elif self.ai_ratio == 0:
                    scene_type = "stock"

                tech_tag = "unknown"
                success, final_path = False, ""
                
                # 1. Stock
                if scene_type == "stock":
                    self.progress_signal.emit(f"🎥 Cảnh {scene_num}: Tìm Stock cho '{search_query}'...")
                    # Thử Pexels trước, sau đó Pixabay (StockService handles this)
                    res, temp_path = stock_engine.download_visual(search_query, save_dir, orient, "video")
                    if res: 
                        success, final_path = True, temp_path
                        # Giả định StockService trả về path có tên provider hoặc ta tự gán
                        tech_tag = "stock_auto" 
                        if "pexels" in temp_path.lower(): tech_tag = "stock_pexels"
                        elif "pixabay" in temp_path.lower(): tech_tag = "stock_pixabay"
                    else: 
                        scene_type = "ai_image"

                # 2. AI Image
                if not success and scene_type == "ai_image":
                    self.progress_signal.emit(f"🎨 Cảnh {scene_num}: AI đang vẽ (Pollinations)...")
                    tech_tag = "ai_pollinations"
                    save_path = os.path.join(save_dir, f"temp_scene_{scene_num:02d}_AI.jpg")
                    full_p = f"{ai_prompt}, {style_prompt_prefix} --ar {'9:16' if orient=='portrait' else '16:9'}"
                    # Retry loop for Pollinations (Free AI often has transient errors)
                    for attempt in range(3):
                        try:
                            url = f"https://image.pollinations.ai/prompt/{requests.utils.quote(full_p)}?width=1920&height=1080&nologo=true"
                            r = requests.get(url, timeout=40)
                            if r.status_code == 200:
                                with open(save_path, "wb") as f: f.write(r.content)
                                success, final_path = True, save_path
                                break
                            elif r.status_code == 429:
                                self.progress_signal.emit(f"⏳ Đang bị giới hạn (429), chờ 5s (Lần {attempt+1})...")
                                time.sleep(5)
                        except Exception as e:
                            self.progress_signal.emit(f"⚠️ Thử lại {attempt+1}/3: {e}")
                            time.sleep(2)

                if success:
                    count_success += 1
                    ext = os.path.splitext(final_path)[1]
                    # Format mới: scene_01_tech_tag.ext
                    off_path = os.path.join(save_dir, f"scene_{scene_num:02d}_{tech_tag}{ext}")
                    
                    # Dọn dẹp các file cũ cùng scene index nhưng khác tech tag
                    for f in os.listdir(save_dir):
                        if f.startswith(f"scene_{scene_num:02d}_") and f != os.path.basename(off_path):
                            try: os.remove(os.path.join(save_dir, f))
                            except: pass

                    if os.path.exists(off_path): os.remove(off_path)
                    os.rename(final_path, off_path)
                    
                    # Phát tín hiệu báo cảnh này đã xong để UI update live
                    self.scene_finished_signal.emit(scene_num)
                else:
                    self.progress_signal.emit(f"⚠️ Cảnh {scene_num}: Không tìm được tư liệu.")
                time.sleep(0.5)

            self.finished_signal.emit(True, f"✅ Hoàn tất: {count_success}/{len(lines)} cảnh.", "")
        except Exception as e:
            logger.error(f"VisualWorker error: {e}")
            self.finished_signal.emit(False, f"Lỗi: {e}", "")


# ============================================================================
# BRAND ARTIST WORKER (Multi-Engine)
# ============================================================================
class BrandArtistWorker(QThread):
    finished_signal = pyqtSignal(bool, str, str, str)

    def __init__(self, prompt, img_type, output_folder):
        super().__init__()
        self.prompt, self.img_type, self.output_folder = prompt, img_type, output_folder
        self.ai = AIFactory()

    def run(self):
        try:
            os.makedirs(self.output_folder, exist_ok=True)
            save_path = os.path.join(self.output_folder, f"{self.img_type}.jpg")
            config = self.ai.get_worker_config("brand_artist")
            provider = config.get("provider", "pollinations") if config else "pollinations"
            
            # Pollinations as default free
            url = f"https://image.pollinations.ai/prompt/{requests.utils.quote(self.prompt)}?nologo=true"
            r = requests.get(url, timeout=40)
            if r.status_code == 200:
                with open(save_path, "wb") as f: f.write(r.content)
                self.finished_signal.emit(True, f"✅ Đã vẽ xong bằng {provider}", self.img_type, save_path)
            else:
                self.finished_signal.emit(False, "❌ Vẽ thất bại", self.img_type, "")
        except Exception as e:
            self.finished_signal.emit(False, f"Lỗi: {e}", self.img_type, "")


# ============================================================================
# RENDER VIDEO WORKER
# ============================================================================
class RenderVideoWorker(QThread):
    finished_signal = pyqtSignal(bool, str, str)
    progress_signal = pyqtSignal(str)
    
    def __init__(self, src_path, output_path):
        super().__init__()
        self.src_path, self.output_path = src_path, output_path
        self.renderer = RenderService()
        
    def run(self):
        try:
            voice_path = os.path.join(self.src_path, "voice.mp3")
            visuals_dir = os.path.join(self.src_path, "visuals")
            
            self.progress_signal.emit("🎬 Đang render video...")
            success, result = self.renderer.create_video_slideshow(visuals_dir, voice_path, self.output_path)
            
            if success:
                # 2. Ghép Subtitle nếu có
                srt_path = os.path.join(self.src_path, "voice.srt")
                if os.path.exists(srt_path):
                    self.progress_signal.emit("📝 Ghép subtitle...")
                    tmp = self.output_path.replace(".mp4", "_sub.mp4")
                    if self.renderer.add_subtitles(self.output_path, srt_path, tmp)[0]:
                        shutil.move(tmp, self.output_path)

                # 3. Chèn Branding (Logo & Chữ ký)
                # Thử tìm logo trong Brand_Assets (thư mục cha của bài)
                parent = os.path.dirname(self.src_path) # Thư mục con (Shorts/Long)
                grand_parent = os.path.dirname(parent) # Thư mục Key_Vua
                great_grand = os.path.dirname(grand_parent) # Thư mục Topic
                
                logo_path = os.path.join(great_grand, "Brand_Assets", "logo.jpg")
                sig_file = os.path.join(great_grand, "Brand_Assets", "signature.txt")
                signature = None
                if os.path.exists(sig_file):
                    try:
                        with open(sig_file, "r", encoding="utf-8") as f: signature = f.read().strip()
                    except: pass
                
                if os.path.exists(logo_path) or signature:
                    self.progress_signal.emit("🎨 Đang chèn Branding (Logo/Chữ ký)...")
                    tmp_brand = self.output_path.replace(".mp4", "_branded.mp4")
                    if self.renderer.add_branding(self.output_path, tmp_brand, 
                                                 logo_path if os.path.exists(logo_path) else None, 
                                                 signature)[0]:
                        shutil.move(tmp_brand, self.output_path)

                self.finished_signal.emit(True, "✅ Hoàn tất!", self.output_path)
            else:
                self.finished_signal.emit(False, f"Lỗi: {result}", "")
        except Exception as e:
            self.finished_signal.emit(False, f"Lỗi: {e}", "")

class GenericWorker(QThread):
    finished_signal = pyqtSignal(object)  # Emit bất kỳ kết quả nào
    
    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self._func = func
        self._args = args
        self._kwargs = kwargs
    
    def run(self):
        try:
            result = self._func(*self._args, **self._kwargs)
            self.finished_signal.emit(result)
        except Exception as e:
            logger.error(f"GenericWorker error: {e}")
            self.finished_signal.emit((False, str(e), ""))

class AvatarWorker(QThread):
    finished_signal = pyqtSignal(bool, str, str)
    def __init__(self, t, i, o): super().__init__(); self.t, self.i, self.o = t, i, o
    def run(self): time.sleep(2); self.finished_signal.emit(False, "Tính năng Avatar đang nâng cấp.", "")


# ============================================================================
# THUMBNAIL AI WORKER (Lấy cảm hứng từ yt_thumbnail_creator)
# ============================================================================
class ThumbnailAIWorker(QThread):
    """
    Worker chạy pipeline AI Thumbnail trong background thread.
    Pipeline: AI Director → Generate Assets → rembg → Composite → Output
    """
    finished_signal = pyqtSignal(bool, str, str)  # (success, message, output_path)
    progress_signal = pyqtSignal(str)  # Log messages

    def __init__(self, topic: str, output_path: str, title_override: str = None,
                 brand_color: str = "#FF0000", country: str = "US"):
        super().__init__()
        self.topic = topic
        self.output_path = output_path
        self.title_override = title_override
        self.brand_color = brand_color
        self.country = country

    def run(self):
        try:
            from services.thumbnail_composer import ThumbnailComposer
            composer = ThumbnailComposer()
            
            success, result = composer.create_ai_thumbnail(
                topic=self.topic,
                output_path=self.output_path,
                title_override=self.title_override,
                brand_color=self.brand_color,
                country=self.country,
                progress_callback=lambda msg: self.progress_signal.emit(msg)
            )
            
            self.finished_signal.emit(success, result if not success else "✅ AI Thumbnail hoàn tất!", 
                                      self.output_path if success else "")
        except Exception as e:
            logger.error(f"ThumbnailAIWorker error: {e}")
            self.finished_signal.emit(False, f"❌ Lỗi: {e}", "")