
import logging
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

import sys
import json
import csv
import os
import re
import random
import requests
import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QStyleOptionButton,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QStyle,
    QTabWidget, QLineEdit, QTextEdit, QProgressBar, QMessageBox,
    QFrame, QAbstractItemView, QMenu, QDialog, QFileDialog, 
    QInputDialog, QGroupBox, QApplication, QSpinBox, 
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer, QRect, QUrl, QMetaObject, Q_ARG
from PyQt6.QtGui import QColor, QBrush, QIcon, QFont, QAction, QPixmap, QStandardItemModel, QStandardItem, QCursor, QDesktopServices

# --- IMPORT AI FACTORY ---
try:
    from services.ai_factory import AIFactory
except ImportError:
    # Mockup nếu chạy độc lập
    class AIFactory:
        def __init__(self):
            # Thêm registry giả để không bị crash
            self.registry = {
                "providers": {
                    "youtube": {"api_key": "YOUR_API_KEY_HERE_1, YOUR_API_KEY_HERE_2"}
                }
            }
        def get_api_key(self, pid): return "YOUR_YOUTUBE_KEY"
        def get_gemini_response(self, prompt): return "Keyword 1, Keyword 2, Keyword 3"
        def get_worker_config(self, name): return {"provider": "google", "model": "gemini-pro"}
        def execute_custom_ai(self, provider, prompt, model): return True, "MOCK AI RESPONSE"


from modules.radar.constants import *

logger = logging.getLogger("VeoSuite.Radar.PlannerWorker")


class QuickPlannerWorker(QThread):
    finished = pyqtSignal(list) # Trả về list các dict thông tin kênh
    
    def __init__(self, niche, countries, spy_dna=None):
        super().__init__()
        self.niche = niche
        self.countries = countries # List tên nước
        self.spy_dna = spy_dna or {} # Dữ liệu từ Tab Spy (Style, Key, Tone...)
        self.ai = AIFactory()
        
    def run(self):
        # 1. Lấy cấu hình từ Admin (Dynamic Configuration)
        # Tên mã nhiệm vụ: "branding_expert"
        config = self.ai.get_worker_config("branding_expert")
        provider = config.get("provider", "google") if config else "google"
        model = config.get("model", "default") if config else "default"

        # [LOGIC DI TRUYỀN] Trích xuất DNA từ video gốc
        inherited_style = self.spy_dna.get("visual_style", "Clean & Professional")
        root_key = self.spy_dna.get("root_keyword", self.niche)

        # In log để debug
        logger.info(f"🤖 Planner đang dùng AI: {provider} ({model})")
        logger.info(f"🧬 DNA kế thừa: Style='{inherited_style}' | Key='{root_key}'")
        
        # [NÂNG CẤP 1] LANGUAGE MAP (Định nghĩa chính xác hệ chữ viết)
        # Giúp AI không bị nhầm giữa Tiếng Trung (Giản thể/Phồn thể) hay Tiếng Ấn (Hindi/Anh)
        LANGUAGE_MAP = {
            # --- TIER 1: KHO BÁU TỶ ĐÔ (RPM $10 - $35+) ---
            "Hoa Kỳ": "English (US)",
            "Úc": "English (AU)",
            "Thụy Sĩ": "German (Deutsch) or French (Français)",
            "Anh Quốc": "English (UK)", "Anh": "English (UK)", # Mapping cả 2 tên cho chắc
            "Canada": "English (CA)",
            "Na Uy": "Norwegian (Norsk)",
            "New Zealand": "English (NZ)",

            # --- TIER 2: CHÂU ÂU THỊNH VƯỢNG (RPM $6 - $18) ---
            "Đức": "German (Deutsch)",
            "Hà Lan": "Dutch (Nederlands)",
            "Thụy Điển": "Swedish (Svenska)",
            "Đan Mạch": "Danish (Dansk)",
            "Phần Lan": "Finnish (Suomi)",
            "Pháp": "French (Français)",
            "Ireland": "English (Ireland)",
            "Áo": "German (Austrian German)",
            "Bỉ": "French (Français) or Dutch (Nederlands)",

            # --- TIER 3: CHÂU Á RỒNG HỔ & DẦU MỎ (RPM $4 - $12) ---
            "Qatar": "Arabic (العربية)",
            "UAE": "Arabic (العربية)", "Các Tiểu vương quốc Ả Rập Thống nhất": "Arabic (العربية)",
            "Singapore": "English (Singapore)",
            "Nhật Bản": "Japanese (日本語 - Natural)",
            "Hàn Quốc": "Korean (한국어)",
            "Israel": "Hebrew (עברית)",
            "Ả Rập Xê Út": "Arabic (العربية)",
            "Hồng Kông": "Traditional Chinese (繁體中文 - HK usage)",
            "Đài Loan": "Traditional Chinese (繁體中文 - Taiwan usage)",
            "Kuwait": "Arabic (العربية)",
            "Trung Quốc": "Simplified Chinese (简体中文)", # Giữ lại từ list cũ dù không có trong RPM list

            # --- TIER 4: NAM ÂU & ĐÔNG ÂU (RPM $2 - $8) ---
            "Tây Ban Nha": "Spanish (Español)",
            "Ý": "Italian (Italiano)",
            "Bồ Đào Nha": "Portuguese (Português)",
            "Ba Lan": "Polish (Polski)",
            "Séc": "Czech (Čeština)", "Cộng hòa Séc": "Czech (Čeština)",
            "Hy Lạp": "Greek (Ελληνικά)",
            "Hungary": "Hungarian (Magyar)",
            "Nga": "Russian (Русский)",
            "Thổ Nhĩ Kỳ": "Turkish (Türkçe)",

            # --- TIER 5: MỸ LATIN & NAM Á (RPM $1 - $5) ---
            "Brazil": "Portuguese (Português - Brazil)",
            "Mexico": "Spanish (Español - Mexico)",
            "Argentina": "Spanish (Español - Argentina)",
            "Chile": "Spanish (Español - Chile)",
            "Ấn Độ": "Hindi (हिन्दी) or English (India)",
            "Nam Phi": "English (South Africa)",

            # --- TIER 6: ĐÔNG NAM Á (VOLUME LỚN, RPM THẤP <$3) ---
            "Việt Nam": "Vietnamese (Tiếng Việt)",
            "Indonesia": "Indonesian (Bahasa Indonesia)",
            "Philippines": "English (Philippines) or Tagalog",
            "Thái Lan": "Thai (ไทย)",
            "Malaysia": "Malay (Bahasa Melayu)",
            "Pakistan": "Urdu (اردو)",
            "Bangladesh": "Bengali (বাংলা)",
            "Lào": "Lao (ລາວ)",
            "Campuchia": "Khmer (ខ្មែរ)",

            # --- TIER 7: CÁC NƯỚC KHÁC (HỖ TRỢ FULL) ---
            "Iran": "Persian (Farsi - فارسی)",
            "Iraq": "Arabic (العربية)",
            "Ai Cập": "Arabic (العربية)",
            "Nigeria": "English (Nigeria)",
            "Ukraine": "Ukrainian (Українська)",
            "Ả Rập": "Arabic (العربية)" # General mapping
        }

        # Tạo chỉ dẫn "Vibe" cho AI
        style_instruction = (
            f"VISUAL DNA INHERITANCE:\n"
            f"- Original Video Style: '{inherited_style}'\n"
            f"- Core Keyword: '{root_key}'\n"
            f"- REQUIRED: The new channel branding (Logo, Banner, Thumbnails) MUST align with this visual style to maintain the 'Viral Vibe'."
        )

        results = []
        # Chạy vòng lặp (hoặc batch prompt nếu muốn nhanh)
        for country in self.countries:
            # Lấy ngôn ngữ đích danh, nếu không có thì fallback về tên nước
            target_lang_script = LANGUAGE_MAP.get(country, f"Native Language of {country}")

            # [NÂNG CẤP] Prompt Kỷ luật ngôn ngữ & Định dạng
            prompt = (
                f"ROLE: Senior YouTube Brand Architect & Visual Director (Scale & Automation Specialist).\n"
                f"TASK: Create a COMPLETE, MONETIZATION-SAFE Brand Package for a Faceless Channel in '{country}'.\n"
                f"NICHE: {self.niche}\n"
                f"CONTEXT & VISUAL DNA: {style_instruction}\n"
                f"\n"
                f"--- 1. STRICT LANGUAGE PROTOCOL (CRITICAL) ---\n"
                f"Target Audience Script: {target_lang_script} (Native Language of '{country}')\n"
                f"- Channel NAME & BIO: MUST be in {target_lang_script} (Local SEO & Authority).\n"
                f"- Handle & Image Prompts: MUST be in English/Latin characters (Global Standard/AI Compatibility).\n"
                f"\n"
                f"--- 2. BIO & SEO STRATEGY (SCORE 10/10) ---\n"
                f"Construct the Bio in {target_lang_script} following this EXACT structure:\n"
                f"1. HOOK: A strong Value Proposition sentence.\n"
                f"2. CONTENT: Brief summary of what viewers will see.\n"
                f"3. KEYWORD: Naturally embed the translated version of '{root_key}'.\n"
                f"4. CTA: A clear call to action (e.g., 'Subscribe for daily videos!').\n"
                f"5. HASHTAGS: Add 3-5 relevant hashtags at the VERY END (e.g. #shorts #{root_key}).\n"
                f"\n"
                f"--- 3. ANTI-COLLISION & NAMING RULES (AVOID DUPLICATES) ---\n"
                f"- NAME STRATEGY: Evocative, Catchy & Authority-building. Avoid generic single words.\n"
                f"- HANDLE STRATEGY: MUST be Unique. To ensure availability, use this format: @[Keyword]_[CountryCode]_Official or @[Brand]_[Topic]_TV.\n"
                f"  (Example: Instead of '@RainRelax', use '@RainRelax_VN_Official' or '@DeepSleep_Japan_TV').\n"
                f"- SAFETY: STRICTLY avoid copyrighted terms, famous brand names, or misleading claims.\n"
                f"\n"
                f"--- 4. VISUAL IDENTITY GUIDELINES (AI GENERATION) ---\n"
                f"- General Style: Clean, modern, high contrast, strictly adhering to '{inherited_style}'.\n"
                f"- Logo Prompt: **Vector Graphic, Flat Design, White Background, Minimalist**. Abstract symbol or Mascot. **CRITICAL: NO TEXT, NO LETTERS inside the image (add '--no text' at end)**. Optimized for small mobile screens.\n"
                f"- Banner Prompt: **High Contrast, Professional, Clean**. Matches color palette. **CRITICAL: NO TEXT (add '--no text' at end)**.\n"
                f"- Thumbnail Prompt: Describe a viral, high-CTR composition consistent with '{inherited_style}'.\n"
                f"\n"
                f"--- 5. REPLICATION RISK ASSESSMENT ---\n"
                f"- Evaluate if this niche is safe to clone/automate in '{country}'.\n"
                f"- High Risk = Requires specific face/talent or highly localized vlog.\n"
                f"- Low/Medium Risk = Faceless, ASMR, Facts, Animation, Generic Stock footage.\n"
                f"\n"
                f"--- OUTPUT FORMAT (STRICT JSON WRAPPED IN TAGS) ---\n"
                f"Output ONLY the JSON object between <JSON_START> and <JSON_END> tags.\n"
                f"No markdown blocks (```json), no intro text.\n"
                f"\n"
                f"<JSON_START>\n"
                f"{{\n"
                f'  "name": "Native Channel Name (e.g. 🌧️ Mưa Chill)",\n'
                f'  "handle": "@Unique_English_Handle_Official",\n'
                f'  "bio": "Hook... Content... Keywords... CTA... #hashtags",\n'
                f'  "native_target_keyword": "THE_MONEY_KEYWORD_IN_NATIVE_LANG",\n'
                f'  "logo_prompt": "Detailed ENGLISH prompt: Vector Graphic, Flat Design... (Style: {inherited_style}, No Text)",\n'
                f'  "banner_prompt": "Detailed ENGLISH prompt: High Contrast... (Style: {inherited_style}, No Text)",\n'
                f'  "thumb_prompt": "High quality ENGLISH prompt for a viral thumbnail template (Style: {inherited_style})",\n'
                f'  "replication_risk": "Low" | "Medium" | "High",\n'
                f'  "clone_distance": "Close" | "Moderate" | "Far"\n'
                f"}}\n"
                f"<JSON_END>"
            )
            # Gọi AI theo cấu hình đã lấy
            success, resp = self.ai.execute_custom_ai(provider, prompt, model)
            
            # Dữ liệu mặc định phòng khi lỗi
            data = {
                "country": country, 
                "name": f"{self.niche} {country}", 
                "handle": "@new_channel", 
                "bio": "New Faceless Channel", 
                "native_target_keyword": root_key, # Fallback nếu lỗi
                "logo_prompt": f"Logo for {self.niche}, {inherited_style} style", 
                "banner_prompt": f"Banner for {self.niche}, {inherited_style} style",
                "thumb_prompt": f"Thumbnail for {self.niche}, {inherited_style} style",
                "replication_risk": "Unknown",
                "clone_distance": "Moderate" # Default an toàn
            }
            if success:
                try:
                    import json, re
                    # [NÂNG CẤP 3] Parse JSON bằng thẻ Tag (An toàn tuyệt đối)
                    # Tìm nội dung nằm giữa <JSON_START> và <JSON_END>
                    match = re.search(r'<JSON_START>(.*?)<JSON_END>', str(resp), re.DOTALL)
                    if match: 
                        json_str = match.group(1).strip()
                        parsed = json.loads(json_str)
                        data.update(parsed)
                    else:
                        # Fallback: Thử tìm json thuần nếu AI quên tag (hiếm)
                        match_fallback = re.search(r'(\{.*\})', str(resp), re.DOTALL)
                        if match_fallback:
                            data.update(json.loads(match_fallback.group(1)))
                except Exception as e: 
                    logger.info(f"Lỗi parse JSON Planner: {e}")
            
            results.append(data)
            
        self.finished.emit(results)

# --- WORKER: TÌNH BÁO VIÊN (LẤY METADATA THẬT TỪ YOUTUBE) ---
