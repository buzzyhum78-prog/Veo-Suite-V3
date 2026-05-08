
import os
import sys
import time
import json
import random
import requests
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *
from PyQt6.QtMultimedia import *

import os
import sys
import json
import re
import datetime
import time
import threading # Để dịch không bị đơ máy
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QFrame, QSplitter, QTableWidget, QProgressDialog,
    QHeaderView, QAbstractItemView, QSpinBox, QCheckBox,
    QGroupBox, QFormLayout, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QTableWidgetItem, QTextEdit, QApplication, QScrollArea, QSizePolicy,
    QGridLayout, QInputDialog, QFileDialog, QDialog, QDialogButtonBox, QMenu, QToolButton
)
from PyQt6.QtGui import QFont, QColor, QCursor
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from deep_translator import GoogleTranslator
from services.database_manager import DatabaseManager
from services.ai_factory import AIFactory      


from modules.content.constants import *

class ScriptWriterWorker(QThread):
    # Tín hiệu trả về: (Project_Index, Task_ID, Kết quả)
    finished_signal = pyqtSignal(int, int, str) 

    # --- [CHỖ QUAN TRỌNG NHẤT: PHẢI CÓ ĐỦ 4 THAM SỐ] ---
    def __init__(self, prompt, project_index, task_id):
        super().__init__()
        self.prompt = prompt
        self.project_index = project_index
        self.task_id = task_id
        self.ai = AIFactory()
    # ----------------------------------------------------

    def run(self):
        try:
            # 1. Lấy cấu hình cho việc "Viết Kịch Bản" (script_writer)
            config = self.ai.get_worker_config("script_writer")
            if not config:
                self.finished_signal.emit(self.project_index, self.task_id, "Lỗi: Chưa cấu hình AI 'Viết Kịch Bản' trong Tab Quản Trị!")
                return

            provider = config["provider"] # VD: google, groq, openai...
            model = config["model"]       # VD: gemini-1.5-pro, llama3...

            # 2. Gọi hàm thực thi vạn năng (Tự động xoay key, tự động retry)
            # Lưu ý: Hàm execute_custom_ai đã bao gồm logic gọi Google/OpenAI cũ luôn
            success, result = self.ai.execute_custom_ai(provider, self.prompt, model, role="script_writer")

            if success:
                # [QUAN TRỌNG] Kiểm tra xem kết quả có rỗng hoặc chứa thông báo lỗi không
                result_str = str(result).strip()
                error_keywords = ["503", "exhausted", "unavailable", "overloaded", "limit reached", "error"]
                
                if not result_str or len(result_str) < 20:
                    self.finished_signal.emit(self.project_index, self.task_id, "Lỗi: AI trả về nội dung quá ngắn hoặc rỗng!")
                elif any(k in result_str.lower() for k in error_keywords) and len(result_str) < 200:
                    # Nếu nội dung ngắn mà chứa từ khóa lỗi -> Báo lỗi
                    self.finished_signal.emit(self.project_index, self.task_id, f"Error AI (System): {result_str}")
                else:
                    self.finished_signal.emit(self.project_index, self.task_id, result_str)
            else:
                self.finished_signal.emit(self.project_index, self.task_id, f"Error AI ({provider}): {result}")

        except Exception as e:
            self.finished_signal.emit(self.project_index, self.task_id, f"Critical Error: {str(e)}")

# --- WORKER 1: AI THIẾT KẾ KÊNH (BẢN V3.0 - GLOBAL SCALE PERFECT) ---
class ChannelDesignerWorker(QThread):
    finished_signal = pyqtSignal(dict)
    
    def __init__(self, topic, country, platform="Youtube"):
        super().__init__()
        self.topic = topic
        self.country = country
        self.platform = platform
        self.ai = AIFactory()
        
    def run(self):
        try:
            # 1. Xác định ngôn ngữ mục tiêu (Native Language Logic)
            # Yêu cầu AI phân biệt rõ: Tên/Bio dùng tiếng bản địa, nhưng Handle/Slug dùng tiếng Anh/Latin.
            lang_instruction = (
                f"TARGET AUDIENCE LOCATION: '{self.country}'.\n"
                f"LANGUAGE RULE: All public facing text (Channel Name, Slogan, Description) MUST be in the NATIVE LANGUAGE of {self.country}. "
                f"The 'Channel Handle' must be in English/Latin characters."
            )

            # 2. Định nghĩa Luật Nền Tảng (Platform Specific Heuristics)
            # Tối ưu hóa độ dài và từ khóa cho từng nền tảng cụ thể.
            platform_rules = ""
            if "Youtube" in self.platform:
                platform_rules = """
                [PLATFORM SPECIFIC: YOUTUBE]
                - NAME: Combine [Main Keyword] + [Brand Name]. Example: 'TechFlow' or 'HorrorNight TV'.
                - BANNER: Aspect Ratio 16:9. Focus on "Safe Area" in the center. High visual impact.
                - BIO: SEO-heavy. First 2 lines are crucial. Length: 800-1000 chars.
                """
            elif "TikTok" in self.platform or "Shorts" in self.platform:
                platform_rules = """
                [PLATFORM SPECIFIC: TIKTOK/SHORTS]
                - NAME: Short, punchy, easy to remember. Max 2-3 words.
                - BANNER: Minimalist or abstract (often covered by UI).
                - BIO: Extremely short (< 80 chars). Bullet points. Focus on Personality/Hook.
                """
            elif "Facebook" in self.platform:
                platform_rules = """
                [PLATFORM SPECIFIC: FACEBOOK]
                - NAME: Professional and Trustworthy. Example: 'BrandName - [Topic]'.
                - BANNER: Community-focused imagery.
                - BIO: Welcoming tone. Focus on community building.
                """
            else:
                platform_rules = "[PLATFORM SPECIFIC: GENERAL]\n- Standard SEO practices apply. Clear branding."

            # 3. SIÊU PROMPT (The Master Brand Architect Prompt)
            prompt = f"""
            ### SYSTEM ROLE
            You are an Elite Brand Identity Architect and Visual Director suitable for Top-Tier creators. 
            Your goal is to build a cohesive, high-converting Channel Identity.

            ### INPUT CONTEXT
            - NICHE/TOPIC: {self.topic}
            - TARGET MARKET: {self.country}
            - PLATFORM: {self.platform}
            - LANGUAGE INSTRUCTIONS: {lang_instruction}

            ### PART 1: STRATEGIC RULES
            {platform_rules}

            ### PART 2: VISUAL DIRECTION (CRITICAL FOR AI IMAGE GENERATORS)
            You must define prompts for an Image Generator (like Flux/Midjourney).
            
            **LOGO PROMPT RULES:**
            - Type: Vector Graphic / Flat Icon / Esport Mascot (depending on niche).
            - Constraint: **ISOLATED ON WHITE BACKGROUND**.
            - STRICT NEGATIVE CONSTRAINT: **NO TEXT, NO LETTERS, NO WORDS, NO WATERMARKS**. The logo must be a pure visual symbol.

            **BANNER PROMPT RULES:**
            - Composition: Wide Cinematic Shot (16:9), balanced composition.
            - Style: Must match the defined Color Palette & Mood.
            - STRICT NEGATIVE CONSTRAINT: **NO TEXT, NO CHANNEL NAME, NO LOGOS**. The banner acts as a background wallpaper. Text is added via UI overlay only.

            ### PART 3: TEXT & COPYWRITING
            - **Channel Name**: Native language (unless English is common in {self.country}). Catchy, memorable.
            - **Handle**: Unique, English characters, easy to type (e.g., @BrandOfficial).
            - **Slogan**: A short tagline defining the value proposition.
            - **Description**: Natural writing, SEO keywords included, strong Call-to-Action (CTA).

            ### OUTPUT FORMAT
            Return **ONLY valid JSON** with no markdown formatting outside the JSON block.

            {{
                "channel_name": "String (Native)",
                "channel_handle": "@String (English/Latin)",
                "slogan": "String (Native)",
                "description": "String (Native - structured with line breaks)",
                "brand_identity": {{
                    "archetype": "String (e.g., Minimalist, Cyberpunk, Luxury, Rustic)",
                    "primary_color_hex": "#String",
                    "accent_color_hex": "#String",
                    "mood_keywords": "String (e.g., Trustworthy, Energetic, Dark)"
                }},
                "visual_identity": {{
                    "logo_prompt": "String (Full prompt for Image Gen: 'Vector icon of... white background...')",
                    "banner_prompt": "String (Full prompt for Image Gen: 'Wide cinematic background of... no text...')"
                }},
                "visual_style_preset": "String (e.g., 'Cinematic 4K', 'Flat Vector Illustration')"
            }}
            """
            
            # Sử dụng chung cấu hình "Viết Kịch Bản" (script_writer) vì nó cũng là tạo text
            config = self.ai.get_worker_config("script_writer")
            if not config:
                self.finished_signal.emit({})
                return

            success, res = self.ai.execute_custom_ai(config["provider"], prompt, config["model"])
            
            if success:
                match = re.search(r'(\{.*\})', str(res), re.DOTALL)
                if match:
                    self.finished_signal.emit(json.loads(match.group(1)))
                else:
                    print(f"❌ Lỗi Parse JSON Design: {res[:100]}...")
                    self.finished_signal.emit({}) # Lỗi parse
            else:
                print(f"❌ Lỗi API Design: {res}")        
                self.finished_signal.emit({}) # Lỗi API

        except Exception as e:
            print("Lỗi Channel Worker:", e)
            self.finished_signal.emit({})

# --- WORKER 2: AI BÀO KEY (STRATEGIC EXPANSION V2) ---
class IdeaExpansionWorker(QThread):
    finished_signal = pyqtSignal(list)
    def __init__(self, topic, country, root_keyword, quantity, duration_str=""):
        super().__init__()
        self.topic = topic
        self.country = country
        self.root_keyword = root_keyword
        self.quantity = int(quantity)
        self.duration_str = duration_str
        self.ai = AIFactory()

    def run(self):
        try:
            # 1. Lấy cấu hình cho việc "Tìm Trends/Bào Key" (researcher)
            config = self.ai.get_worker_config("researcher")
            if not config:
                print("❌ Lỗi Bào Key: Chưa cấu hình 'Chuyên viên phân tích' trong Admin!")
                self.finished_signal.emit([]) 
                return
            
            time_rule = ""
            if "1 giờ" in self.duration_str.lower() or "1 hour" in self.duration_str.lower():
                time_rule = "CONSTRAINT: Video length is 1 Hour. Titles MUST NOT say '2 Hours' or '10 Hours'."

            # PROMPT BÀO KEY "ĂN TIỀN"
            prompt = f"""
            ROLE: YouTube Growth Hacker & SEO Strategist.
            TASK: Scale the Winning Keyword "{self.root_keyword}" into {self.quantity} NEW 'Money-Making' Video Ideas.
            
            CONTEXT:
            - Niche: {self.topic}
            - Audience Country: {self.country} (OUTPUT MUST BE IN NATIVE LANGUAGE)

            {time_rule}

            CRITICAL CRITERIA (THE 'MONEY' FORMULA):
            1. HIGH CTR TITLES: Use formats like "VS", "Top X", "The Truth About", "Stop Doing This", "How I...".
            2. SEO RETENTION: The title must act as a Long-tail Keyword.
            3. CONTENT GAP: Don't just copy the root key. Find related sub-topics (e.g. if key is 'Hamster', expand to 'Hamster Food', 'Hamster Cage', 'Hamster Mistakes').
            4. NO DUPLICATES: Each idea must be distinct.
            5. PSYCHOLOGICAL TRIGGERS: Use 'Negativity Bias' (e.g., "Don't do this", "Stop"), 'Authority' (e.g., "Experts say"), or 'Specific Numbers' (e.g., "7 Rules").
            
            OUTPUT FORMAT:
            Just the raw list of clickable titles, one per line. No numbering, no quotes, no intros.
            """
            
            result_tuple = self.ai.execute_custom_ai(config["provider"], prompt, config["model"])
            
            # Kiểm tra xem nó có trả về đúng 2 giá trị không
            if not result_tuple or len(result_tuple) != 2:
                print(f"❌ Lỗi Critical: Hàm AI trả về dữ liệu sai định dạng: {result_tuple}")
                self.finished_signal.emit([])
                return

            # Nếu ổn thì mới unpack (bung lụa)
            success, res = result_tuple 
            # --------------------------------------
            
            if success:
                titles = []
                res_str = str(res).strip()
                # Kiểm tra lỗi giả (False success)
                error_keywords = ["503", "exhausted", "unavailable", "limit reached"]
                if any(k in res_str.lower() for k in error_keywords) and len(res_str) < 200:
                    print(f"❌ Lỗi AI (Detected in result): {res_str}")
                    self.finished_signal.emit([])
                    return

                # Xử lý kết quả trả về: Tách dòng, lọc rác
                for line in res_str.split('\n'):
                    clean = line.strip().strip('"').strip("'").strip('-').strip('*')
                    # Lọc dòng trống hoặc dòng quá ngắn
                    if len(clean) > 5 and not clean.lower().startswith("here are"): 
                        titles.append(clean)
                
                if not titles:
                    print("❌ Lỗi: AI không trả về ý tưởng nào hợp lệ.")
                    self.finished_signal.emit([])
                else:
                    self.finished_signal.emit(titles[:self.quantity])
            else:
                print(f"❌ Lỗi AI: {res}")
                self.finished_signal.emit([])

        except Exception as e: 
            print(f"❌ Lỗi Crash Worker: {e}")
            self.finished_signal.emit([])

# [CLASS MỚI] AI KIẾN TRÚC SƯ (THIẾT KẾ KÊNH)
class ChannelDesignWorker(QThread):
    finished = pyqtSignal(dict) # Trả về {name, bio, logo_prompt...}
    
    def __init__(self, topic, country):
        super().__init__()
        self.topic = topic
        self.country = country
        self.ai = AIFactory() # Gọi AIFactory
        
    def run(self):
        # Prompt xin thiết kế kênh
        prompt = (
            f"ROLE: Professional Brand Designer for YouTube.\n"
            f"TASK: Create a channel identity for Topic: '{self.topic}' targeting Market: '{self.country}'.\n"
            f"OUTPUT JSON ONLY:\n"
            f"{{\n"
            f'  "channel_name": "Unique, Catchy Name (Native Language)",\n'
            f'  "channel_handle": "@ShortHandle",\n'
            f'  "channel_bio": "SEO optimized description (Native Language, max 150 chars)",\n'
            f'  "logo_prompt": "Detailed AI prompt to generate a minimal, iconic logo",\n'
            f'  "banner_prompt": "Detailed AI prompt for channel banner"\n'
            f"}}"
        )
        
        # Lấy cấu hình từ Quản trị
        config = self.ai.get_worker_config("brand_artist")
        if not config:
            provider, model = "google", "gemini-3.1-flash"
        else:
            provider, model = config["provider"], config["model"]
            
        success, response = self.ai.execute_custom_ai(provider, prompt, model)
        
        if success:
            try:
                import json
                import re
                # Lọc JSON
                match = re.search(r'(\{.*\})', str(response), re.DOTALL)
                if match:
                    data = json.loads(match.group(1))
                    self.finished.emit(data)
            except:
                pass

# --- WORKER 3: KỸ SƯ ÂM THANH (AUDIO GENERATOR) ---
class AudioGenWorker(QThread):
    finished_signal = pyqtSignal(int, int, str) # project_idx, task_id, path_file
    
    def __init__(self, text, project_idx, task_id):
        super().__init__()
        self.text = text
        self.project_idx = project_idx
        self.task_id = task_id
        
    def run(self):
        try:
            # 1. Đọc cấu hình từ file JSON (Do Admin Tab tạo ra)
            config_path = "VEO_DB/voice_engine_config.json"
            if not os.path.exists(config_path):
                self.finished_signal.emit(self.project_idx, self.task_id, "Lỗi: Chưa cấu hình Voice bên Admin!")
                return
                
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            
            # 2. Định tuyến (Router): Chọn Engine nào?
            # Ưu tiên theo thứ tự: OpenAI > Google > Custom > Edge (Fallback)
            engine_used = "Unknown"
            
            # Sử dụng AudioService thống nhất
            try:
                from services.audio_service import AudioService
                audio_svc = AudioService()
                
                # Chuyển đổi cấu hình từ file sang format meta_data mà AudioService cần
                meta_data = {
                    "provider": "openai" if config.get("openai_enable") else ("google" if config.get("google_enable") else "edge"),
                    "voice_id": "alloy" if config.get("openai_enable") else ("vi-VN-Standard-A" if config.get("google_enable") else "vi-VN-HoaiMyNeural"),
                }
                
                if config.get("openai_enable"):
                    engine_used = "OpenAI TTS"
                    success, msg = audio_svc.create_audio(self.text, self.output_file, meta_data)
                    if success:
                        self.finished_signal.emit(self.project_idx, self.task_id, f"✅ Đã tạo Voice ({engine_used})")
                        return
                        
                elif config.get("google_enable"):
                    engine_used = "Google Cloud TTS"
                    success, msg = audio_svc.create_audio(self.text, self.output_file, meta_data)
                    if success:
                        self.finished_signal.emit(self.project_idx, self.task_id, f"✅ Đã tạo Voice ({engine_used})")
                        return
            except Exception as e:
                pass # Rơi xuống Fallback Edge TTS bên dưới nếu AudioService lỗi
                
            # Mặc định dùng Edge TTS (Free Fallback)
            engine_used = "Edge TTS (Free)"
            import asyncio
            import edge_tts
            
            # Hàm chạy async cho Edge
            async def run_edge():
                communicate = edge_tts.Communicate(self.text, "vi-VN-HoaiMyNeural") # Mặc định giọng nữ Việt
                # Lưu tạm vào file
                out_path = f"VEO_DB/temp_audio_{self.task_id}.mp3"
                await communicate.save(out_path)
                return out_path
            
            # Chạy loop
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                path = loop.run_until_complete(run_edge())
                audio_data = path
            except Exception as e:
                self.finished_signal.emit(self.project_idx, self.task_id, f"Lỗi Edge TTS: {e}")
                return

            # 3. Trả kết quả
            if audio_data:
                self.finished_signal.emit(self.project_idx, self.task_id, f"✅ Đã tạo Voice ({engine_used}): {audio_data}")
            else:
                self.finished_signal.emit(self.project_idx, self.task_id, "Lỗi: Không tạo được Audio (Chưa cài thư viện?)")
                
        except Exception as e:
            self.finished_signal.emit(self.project_idx, self.task_id, f"Crash Audio Worker: {e}")

# --- WORKER 4: NHÀ SÁNG TẠO TIÊU ĐỀ (BATCH TITLE GENERATOR) ---
class BatchTitleGeneratorWorker(QThread):
    finished_signal = pyqtSignal(list) # Trả về danh sách tiêu đề mới

    def __init__(self, key_vua, quantity, country, topic, duration_label=""):
        super().__init__()
        self.key_vua = key_vua
        self.quantity = quantity
        self.country = country
        self.topic = topic
        self.duration_label = duration_label # Lưu lại để dùng trong prompt
        self.ai = AIFactory()

    def run(self):
        try:
            config = self.ai.get_worker_config("script_writer")
            if not config:
                self.finished_signal.emit([])
                return
            
            # ==================================================================
            # 🛡️ LOGIC KIỂM SOÁT SỰ THẬT CHO TIÊU ĐỀ (TRUTH GUARD)
            # ==================================================================
            topic_lower = self.topic.lower()
            truth_rule = "CREATIVITY LEVEL: HIGH. You can use metaphors, exaggeration, and curiosity gaps." # Mặc định (Giải trí/Nhạc)
            
            # Danh sách các chủ đề "Nhạy cảm" cần sự thật
            strict_topics = [
                "news", "tin tức", "sự thật", "fact", "tài chính", "finance", 
                "crypto", "sức khỏe", "health", "y tế", "medicine", "bệnh", 
                "lịch sử", "history", "war", "chiến tranh", "khoa học", "science"
            ]

            if any(k in topic_lower for k in strict_topics):
                truth_rule = (
                    "⚠️ TRUTH CONSTRAINT: STRICT.\n"
                    "1. Titles MUST BE FACTUALLY ACCURATE. Do not invent events or dates.\n"
                    "2. Do NOT use fake 'Breaking News' for historical events.\n"
                    "3. Do NOT make false medical/financial promises (e.g., 'Cure Cancer', 'Get Rich Overnight')."
                )

            # [LOGIC MỚI] XỬ LÝ RÀNG BUỘC THỜI GIAN
            time_constraint = ""
            if self.duration_label:
                # Nếu tiêu đề có chữ "1 Giờ" hoặc "Loop", ép AI viết đúng
                if "1 giờ" in self.duration_label.lower() or "1 hour" in self.duration_label.lower():
                    time_constraint = "TIME RULE: The video is exactly '1 Hour'. DO NOT write '2 Hours', '10 Hours' or 'All Night'. Write '1 Hour' or '60 Minutes'."
                elif "phút" in self.duration_label.lower() or "minutes" in self.duration_label.lower():
                     time_constraint = f"TIME RULE: The video is short ({self.duration_label}). DO NOT write 'Hours' or 'Long Loop'."

            # [NÂNG CẤP] PROMPT TITLE MASTER V4.0 (INTENT LOCKED)
            prompt = f"""
                ROLE: World-Class YouTube Strategist, SEO Specialist, and Linguistics Expert.
                TASK: Generate {self.quantity} VIRAL & SEO-OPTIMIZED video titles for the keyword: "{self.key_vua}".
                        
                --- INPUT CONTEXT ---
                1. NICHE: {self.topic}
                2. KEYWORD (KEY VUA): "{self.key_vua}"
                3. TARGET MARKET: {self.country} (OUTPUT MUST BE 100% NATIVE LANGUAGE OF THIS REGION)
                4. CONTENT DURATION: {self.duration_label}

                {truth_rule}

                --- CRITICAL RULES FOR HIGH CTR ---
                1. HYBRID INTENT STRATEGY:
                - [Search]: Keyword "{self.key_vua}" must be at the BEGINNING. Focus on solution/benefit.
                - [Browse]: Focus on Curiosity/Shock/Story. Keyword can be implied or at the end. Goal is High CTR.
                
                2. LOCALIZATION (EXTREMELY IMPORTANT):
                - Use natural spoken grammar of {self.country}. NO "Google Translate" feeling.
                - If mentioning money, use LOCAL CURRENCY of {self.country} (e.g. Vietnam=VND/Triệu, US=$, Japan=¥). DO NOT default to USD.
                - Keep proper nouns (iPhone, AI, ChatGPT, Vlog) in English if locals naturally use them.
                
                3. DURATION & ACCURACY (NEW & STRICT):
                - {time_constraint}
                - ACCURACY: Do not exaggerate time commitments. If the video is a "1 Hour Loop", say it. If it's a "5-minute tutorial", use words like "Fast", "Quick", "In 5 Mins".
                - DO NOT LIE: The title must reflect the actual content length implied by "{self.duration_label}".
                
                4. MOBILE OPTIMIZATION & PSYCHOLOGY:
                - Keep titles under 60 characters where possible.
                - Use power words appropriate for the language (Secret, Mistake, Fast, Only X Minutes).

                5. PSYCHOLOGICAL TRIGGERS:
                - Use power words: Secret, Mistake, Don't, Stop, Exposed, Fast, Only X Minutes.
                - Use brackets for context: (Tutorial), (2025), (Revealed).
                
                6. FORMATTING (STRICT):
                - Append [Search] or [Browse] tag at the end of each line.
                - NO numbering, NO quotes, NO introductory text.
                - One title per line.
                - NO preamble or postscript (e.g. do NOT write "Here are the titles").
                - JUST THE RAW LIST.
                
                --- EXAMPLE OUTPUT PATTERN ---
                Passive Income for Beginners: How to make $100/day from home [Search]
                Du lịch Đà Lạt tự túc: Cầm 2 triệu ăn chơi tẹt ga (Đừng mắc bẫy cò mồi) [Browse]
                iPhone 16 Pro レビュー: 買う前に絶対見てください (15万円の価値あり?) [Browse]
                أفضل 5 مشاريع مربحة في السعودية برأس مال 1000 ريال [Search]
                Best 5G Phone Under ₹15000 in India (Don't Buy Wrong!) [Search]

                INPUT KEYWORD: "{self.key_vua}"
                IMPORTANT: If the Niche is "Relax/Music/ASMR", titles must be search-focused (SEO). If Niche is "News/Drama", titles must be Clickbait-focused.
                """
            
            success, res = self.ai.execute_custom_ai(config["provider"], prompt, config["model"])
            # --- [DEBUG] IN KẾT QUẢ THÔ RA ĐỂ KIỂM TRA ---
            print(f"\n[{self.country}] RAW RESPONSE:\n{str(res)[:200]}...\n")

            titles = []
            if success:
                res_str = str(res).strip()
                # Kiểm tra lỗi giả
                error_keywords = ["503", "exhausted", "unavailable", "limit reached"]
                if any(k in res_str.lower() for k in error_keywords) and len(res_str) < 200:
                    print(f"❌ Lỗi AI ({self.country}) (Detected in result): {res_str}")
                    self.finished_signal.emit([])
                    return

                lines = res_str.split('\n')
                for line in lines:
                    # 1. Dọn dẹp rác (Dấu ngoặc kép, gạch đầu dòng, số thứ tự)
                    # Regex: Xóa số đầu dòng (1. ), dấu -, *, "
                    import re
                    clean = re.sub(r'^[\d-]+\.\s*', '', line.strip()) # Xóa "1. ", "2. "
                    clean = line.strip().strip('"').strip("'").strip('-').strip('*')
                    
                    # -----------------------------------------------------------
                    # [CẬP NHẬT] BỘ LỌC RÁC THÔNG MINH (SMART FILTER V2)
                    # -----------------------------------------------------------
                    is_trash = False
                    low_line = clean.lower()
                    
                    # Danh sách các từ mở đầu thừa thãi (thường gặp khi AI nói tiếng Anh)
                    bad_starts = ("here", "sure", "certainly", "okay", "i have", "below", "please", "note")
                    
                    # Rule 1: Quá ngắn -> Rác
                    if len(clean) < 5: is_trash = True
                    
                    # Rule 2: Bắt đầu bằng từ thừa -> Rác
                    if low_line.startswith(bad_starts): is_trash = True
                    
                    # Rule 3: [QUAN TRỌNG] Kết thúc bằng dấu hai chấm (:) -> Rác
                    # (Áp dụng cho mọi ngôn ngữ: "Danh sách là:", "Here is:", "List:")
                    if low_line.endswith(":"): is_trash = True 
                    
                    if not is_trash:
                        # Logic tự động vá lỗi Tag (nếu AI quên hoặc bị lỗi RTL)
                        if "[" not in clean and "]" not in clean:
                            clean += " [Browse]" 
                        
                        titles.append(clean)
                    # -----------------------------------------------------------
            
                self.finished_signal.emit(titles[:self.quantity])
            else:
                print(f"❌ Lỗi AI ({self.country}): {res}")
                self.finished_signal.emit([])
        except Exception as e:
            print(f"Lỗi Title Gen: {e}")
            self.finished_signal.emit([])

# --- WORKER 5: THỢ DỊCH TOOLTIP (HOVER TRANSLATOR) ---
class TooltipTranslationWorker(QThread):
    # Trả về: (Widget Object, Text Tiếng Việt)
    finished_signal = pyqtSignal(object, str)

    def __init__(self, widget, text_source):
        super().__init__()
        self.widget = widget
        self.text_source = text_source

    def run(self):
        try:
            if not self.text_source: return
            
            # Cắt ngắn nếu quá dài để dịch nhanh
            text_to_trans = self.text_source[:1000]
            
            from deep_translator import GoogleTranslator
            translator = GoogleTranslator(source='auto', target='vi')
            res = translator.translate(text_to_trans)
            
            if res:
                # Format đẹp: Gốc ở trên, Việt ở dưới
                final_tooltip = f"{self.text_source}\n\n🇻🇳 DỊCH: {res}"
                self.finished_signal.emit(self.widget, final_tooltip)
                
        except Exception as e:
            pass # Lỗi thì thôi, giữ nguyên tooltip gốc