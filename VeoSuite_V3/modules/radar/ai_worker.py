
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

class RadarAIWorker(QThread):
    """Xử lý gọi Gemini AI để sinh từ khóa hoặc phân tích"""
    finished = pyqtSignal(object, str) # data, type
    error = pyqtSignal(str)
    log_signal = pyqtSignal(str) # [MỚI] Thêm signal log để bắn tin

    def __init__(self, mode, data):
        super().__init__()
        self.mode = mode # 'keywords', 'analysis', 'remix'
        self.data = data
        self.ai = AIFactory()
        self.backup_data_list = [] # Để khôi phục khi lỡ xóa

    def run(self):
        import re
        import json
        import time

        try:
            if self.mode == 'keywords':
                self._run_idea_hunter() # <--- SỬA: Gọi đúng hàm này
            elif self.mode == 'analysis':
                # [LOGIC PHÂN TÍCH]
                # Ưu tiên dùng cấu hình chuyên biệt 'researcher', nếu không có thì dùng 'script_writer'
                config = self.ai.get_worker_config("researcher") or self.ai.get_worker_config("script_writer")

                provider = config.get("provider", "google") if config else "google"
                model = config.get("model", "default") if config else "default"
                
                # --- A. BÓC TÁCH & LÀM SẠCH DỮ LIỆU (DATA CLEANING) ---
                
                # 1. XỬ LÝ MÔ TẢ (DESCRIPTION CLEANER - FINAL BOSS VERSION)
                # Mục tiêu: Làm sạch Meta Block để AI không bị nhiễu bởi Link/Social
                raw_desc = self.data.get('description', '') or ""
                lines = raw_desc.split('\n')
                clean_lines = []
                
                # --- TỪ ĐIỂN RÁC ĐA QUỐC GIA (GLOBAL JUNK FILTER V7.2) ---
                junk_markers = [
                    # === TIER 1 & GLOBAL (En/De/Fr) ===
                    # English (US, UK, AU, CA, NZ) - [UPDATED]
                    "watch next", "related video", "playlist", "music by", 
                    "follow me", "social", "connect", "gear", "equipment", 
                    "camera", "copyright", "contact", "subscribe", "don't click",
                    "instagram", "facebook", "twitter", "tiktok", "discord", "telegram",
                    "merch", "business", "inquiries", "music in this video", "my setup",
                    "thanks for watching", "click here", "support", "patreon", "paypal",
                    "donate", "affiliate", "link in bio", "buy here",
                    # Soft CTA (Tương tác)
                    "let me know", "comment below", "leave a comment", "thoughts?", 
                    "video ideas", "any questions", "drop a like", "thumbs up",
                    
                    # German (DE, CH, AT)
                    "abonnieren", "folgen", "musik", "kontakt", "ausrüstung", 
                    "impressum", "urheberrecht", "werbung", "kamera", "mein equipment",
                    "nächstes video", "kanal", "unterstützen", 
                    "kommentieren", "daumen hoch", "deine meinung", # Comment/Like/Opinion
                    
                    # French (FR, CH, BE)
                    "abonnez-vous", "suivez-nous", "musique", "contact", "matériel", 
                    "droits d'auteur", "lien", "chaine", "réseaux sociaux", "soutenir",
                    "regarder ensuite", "équipement", 
                    "commentaire", "pouce bleu", "dites-moi", # Comment/Like/Tell me

                    # === TIER 2: CHÂU ÂU (Nl/Scandinavia) ===
                    # Dutch (NL, BE)
                    "abonneer", "volgen", "muziek", "apparatuur", "klik hier", 
                    "reactie", "laat weten", # Comment/Let know
                    
                    # Nordic (SE, NO, DK, FI)
                    "prenumerera", "följ", "musik", "utrustning", "länk", "kommentera", # Sweden
                    "abonner", "følg", "musikk", "kamera", "kommentar", # Norway/Denmark
                    "tilaa", "seuraa", "musiikki", "linkki", "kommentti", # Finland

                    # === TIER 3: CHÂU Á & TRUNG ĐÔNG (Ja/Ko/Zh/Ar/He) ===
                    # Japanese (JP)
                    "チャンネル登録", "高評価", "ツイッター", "インスタ", "フォロー", 
                    "関連動画", "おすすめ", "お問い合わせ", "使用機材", "音楽", "リンク",
                    "コメント", "感想", # Comment/Thoughts
                    
                    # Korean (KR)
                    "구독", "좋아요", "알림", "팔로우", "인스타그램", "문의", 
                    "사용 장비", "배경음악", "영상 링크", "이메일", "보러가기",
                    "댓글", "의견", # Comment/Opinion
                    
                    # Chinese (TW/HK - Traditional)
                    "訂閱", "關注", "點贊", "聯繫", "播放列表", "推薦視頻", 
                    "攝影器材", "音樂", "合作", "鏈接", "追蹤",
                    "評論", "留言", "告訴我", # Comment/Message/Tell me
                    
                    # Arabic (QA, AE, SA, KW, IQ, EG)
                    "اشترك", "تابعني", "تواصل", "موسيقى", "رابط", "فيديو", 
                    "انستقرام", "للدعاية", "إعجاب", "تعليق", "رأيكم", # Subscribe/Like/Comment/Opinion
                    
                    # Hebrew (IL)
                    "הירשמו", "עקבו", "מוזיקה", "יצירת קשר", "קישור", "מצלמה", 
                    "תגובה", "לייק", # Comment/Like

                    # === TIER 4: NAM & ĐÔNG ÂU (Es/It/Pt/Ru/Tr/Pl) ===
                    # Spanish (ES, MX, AR, CL)
                    "suscríbete", "sigueme", "redes sociales", "contacto", 
                    "música", "cámara", "video anterior", "donaciones", "enlace",
                    "comentario", "dale like", "qué opinas", # Comment/Like/Opinion
                    
                    # Italian (IT)
                    "iscriviti", "seguimi", "musica", "contatti", "attrezzatura", "link",
                    "commenta", "mi piace", "fammi sapere", # Comment/Like/Let me know
                    
                    # Portuguese (PT, BR)
                    "inscreva-se", "siga", "música", "contato", "equipamento", "apoie",
                    "comente", "deixe seu like", "sua opinião", # Comment/Like/Opinion
                    
                    # Russian (RU, UA - Common)
                    "подписаться", "музыка", "контакты", "ссылка", "плейлист", 
                    "камера", "подпишись", "инстаграм", "по вопросам",
                    "комментарий", "лайк", "напишите", # Comment/Like/Write
                    
                    # Turkish (TR)
                    "abone ol", "takip et", "müzik", "iletişim", "ekipman", "link",
                    "yorum", "beğen", # Comment/Like
                    
                    # Polish/Czech/Hungarian
                    "subskrybuj", "obserwuj", "kontakt", "komentarz", # PL
                    "odebírat", "sledovat", "hudba", "komentář", # CZ
                    "iratkozz fel", "kövess", "zene", "komment", # HU

                    # === TIER 5 & 6: NAM Á & ĐÔNG NAM Á (Hi/Vi/Id/Th/Ms) ===
                    # Vietnamese (VN) - [UPDATED]
                    "đăng ký", "theo dõi", "kết nối", "liên hệ", "bản quyền", 
                    "xem thêm", "ủng hộ", "cảm ơn", "nhạc trong video", 
                    "fanpage", "thiết bị", "quảng cáo", "hợp tác", "nhóm",
                    # Soft CTA (Tương tác)
                    "cho mình biết", "bình luận", "ý kiến", "câu hỏi", "xuống phía dưới",
                    "shop", "etsy", "store", "mua hàng", "shopee", "lazada",
                    "like video", "bấm like",
                    
                    # Hindi (IN)
                    "सब्सक्राइब", "संगीत", "संपर्क", "लिंक", "फॉलो", 
                    "कमेंट", "लाइक", "विचार", # Comment/Like/Thoughts
                    
                    # Indonesian/Malay (ID, MY)
                    "langganan", "ikuti", "musik", "muzik", "hubungi", "peralatan",
                    "klik di sini", "tonton", "video terkait", 
                    "komentar", "pendapat", # Comment/Opinion
                    
                    # Thai (TH)
                    "กดติดตาม", "เพลง", "ติดต่อ", "ลิ้งค์", "อุปกรณ์", "ติดตามเรา", 
                    "คอมเมนต์", "ความคิดเห็น", # Comment/Opinion
                    
                    # Lao (LA)
                    "ຕິດຕາມ", "ເພງ", "ຕິດຕໍ່", "ລິ້ງ", "ຂອບໃຈ", 
                    "ຄອມເມັ້ນ", "ຄວາມຄິດເຫັນ", # Comment/Opinion
                    
                    # Khmer (KH)
                    "ចុះឈ្មោះ", "តាមដាន", "តន្ត្រី", "ទំនាក់ទំនង", 
                    "មតិ", "យោបល់", # Comment/Opinion

                    # === TIER 7: KHÁC (Fa/Uk) ===
                    # Persian (IR)
                    "مشترک شوید", "دنبال کنید", "موزیک", "تماس", "لینک", 
                    "نظر", "کامنت", # Comment/Opinion
                    
                    # Ukrainian (UA - Specific)
                    "підписатися", "музика", "контакти", "посилання", "коментар"
                ]
                # Regex diệt ký tự hình học/dòng kẻ lạ (Block Elements, Geometric Shapes, Dingbats)
                # \u2500-\u257F: Box Drawing (─ │ ┌ ┐)
                # \u2580-\u259F: Block Elements (█ ▓ ▒ ░)
                # \u25A0-\u25FF: Geometric Shapes (■ ▲ ► ▼)
                # \u2600-\u26FF: Misc Symbols (★ ☂ ☎)
                # \u2700-\u27BF: Dingbats (✓ ➔ ➜)
                symbol_pattern = r'[\u2500-\u257F\u2580-\u259F\u25A0-\u25FF\u2600-\u26FF\u2700-\u27BF]+'
                # --- VÒNG LẶP LỌC SÂU (PIPELINE CHUẨN 100%) ---
                N = len(lines)
                i = 0
                while i < N:
                    line_str = lines[i]
                    line_clean = re.sub(symbol_pattern, '', line_str).strip()
                    # Nếu tẩy xong mà dòng thành rỗng -> Vứt
                    if not line_clean: 
                        i += 1; continue
                    
                    line_lower = line_clean.lower()
                    
                    # 1. Bỏ qua dòng trống
                    if not line_clean: 
                        i += 1; continue
                    
                    # 2. [MÁY CHÉM 1] Dòng chứa Link -> Xóa ngay lập tức
                    if "http://" in line_clean or "https://" in line_clean or "www." in line_clean:
                        i += 1; continue
                    
                    # 3. [MÁY CHÉM 2] Dòng kẻ phân cách (Visual Separator) -> Xóa
                    if re.match(r'^[-=_*~—–]+$', line_clean):
                        i += 1; continue

                    # 4. [MÁY CHÉM 3 - TỔ HỢP] Diệt Hashtag (#) & Handle (@) & Tag Cloud
                    # A. Bắt Handle (@user) ở đầu dòng
                    if line_clean.startswith("@") or line_clean.startswith("- @") or line_clean.startswith("• @"):
                        i += 1; continue
                    
                    # B. Bắt Hashtag ở đầu dòng (Fix lỗi khoảng trắng)
                    if line_clean.startswith("#"):
                        i += 1; continue
                    
                    # Diệt dòng chứa email (kể cả khi không có http)
                    if "@" in line_clean and ("mail" in line_lower or ".com" in line_lower):
                        i += 1; continue

                    # C. [TUYỆT CHIÊU] Diệt "Đám mây Hashtag" (Tag Cloud)
                    if line_str.count("#") >= 2:
                        i += 1; continue

                    # D. Diệt dòng chỉ chứa toàn hashtag (Dù chỉ 1 cái)
                    temp_line = re.sub(r'#\w+', '', line_clean).strip()
                    if len(temp_line) < 2 and "#" in line_clean:
                         i += 1; continue

                    # 5. [MÁY CHÉM 4] Từ khóa rác (Footer/Call to Action)
                    if any(marker in line_lower for marker in junk_markers):
                        i += 1; continue
                    
                    # 6. [MÁY CHÉM 5] Dòng chứa dấu gạch đứng (Đặc trưng tiêu đề nhúng)
                    if "|" in line_clean:
                        i += 1; continue

                    # 7. [MÁY CHÉM 6 - CAO CẤP] Look-Ahead (Tiêu đề mồ côi)
                    words = line_clean.split()
                    if len(words) < 15 and not line_clean.endswith(('.', '!', '?', '"', '”', ')')):
                        is_next_link = False
                        if i + 1 < N:
                            next_line = lines[i+1]
                            if "http://" in next_line or "https://" in next_line or "www." in next_line:
                                is_next_link = True
                        
                        if is_next_link:
                            i += 1; continue # Xóa dòng này vì nó là tiêu đề của link sau
                        
                        # Check Title Case (Viết hoa > 50%)
                        upper_words = sum(1 for w in words if w[0].isupper())
                        if len(words) > 0 and (upper_words / len(words) > 0.5):
                            i += 1; continue

                    # 8. [MÁY CHÉM 7] Dòng quá ngắn vô nghĩa
                    if len(line_clean) < 3: 
                         i += 1; continue

                    # --- CHỐT HẠ: Sống sót -> Được giữ lại ---
                    clean_lines.append(line_clean)
                    i += 1
                
                # Cắt ngắn 2000 ký tự (Đủ cho AI hiểu Context mà không tốn Token)
                desc_final = "\n".join(clean_lines)[:2000]
                
                # 2. XỬ LÝ TRANSCRIPT (Sanitize cho f-string)
                transcript_text = self.data.get('transcript', '')
                if not transcript_text: 
                    transcript_text = "(Video này không có lời thoại/phụ đề. Hãy phân tích dựa trên Metadata)"
                
                # [FIX QUAN TRỌNG] Thay thế { và } thành {{ }} để không bị lỗi f-string
                transcript_block = transcript_text[:25000].replace("{", "{{").replace("}", "}}")
                
                # 3. ĐÓNG GÓI METADATA (Cũng phải sanitize)
                title_safe = self.data.get('title', 'Unknown').replace("{", "{{").replace("}", "}}")
                channel_safe = self.data.get('channel_name', 'Unknown').replace("{", "{{").replace("}", "}}")
                desc_safe = desc_final.replace("{", "{{").replace("}", "}}")

                meta_block = f"""
                VIDEO TITLE: {self.data.get('title', 'Unknown')}
                CHANNEL: {self.data.get('channel_name', 'Unknown')}
                VIEWS: {self.data.get('views', 0)}
                PUBLISHED: {self.data.get('upload_date', '')}
                DESCRIPTION (Summary):
                {desc_final}
                """

                # 2. Tạo khối Transcript (Nội dung cốt lõi - DNA)
                transcript_text = self.data.get('transcript', '')
                if not transcript_text: 
                    transcript_text = "(Video này không có lời thoại/phụ đề. Hãy phân tích dựa trên Metadata)"
                
                # Cắt bớt nếu quá dài để tránh lỗi Token (25k ký tự là an toàn cho Gemini/GPT)
                transcript_block = transcript_text[:25000]

                # --- SIÊU PROMPT V6.1: KỶ LUẬT THÉP (TÍCH HỢP MỌI QUY ĐỊNH) ---
                prompt = f"""
                    ROLE: You are a WORLD-CLASS YOUTUBE STRATEGIST (Top 1%).
                    OBJECTIVE: Reverse-engineer the success formula of this video for REPLICATION.

                    === SOURCE 1: METADATA (Context & Packaging) ===
                    {meta_block}

                    === SOURCE 2: TRANSCRIPT (The Actual Content DNA) ===
                    {transcript_block}
                    
                    === CRITICAL INSTRUCTIONS & CONSTRAINTS (VIOLATION = FAILURE) ===
                    1. STRICT DATA BOUNDARY: Analyze based strictly on the Metadata/Transcript above. Do not hallucinate video content/footage.
                    2. IGNORE TAGS: Focus purely on Semantic SEO & Psychology (Hook, Pacing, Retention).
                    3. HUMAN READABLE: Sections 1 and 2 must be plain text for a scriptwriter. NO CODE BLOCKS for these sections.
                    4. DEEP ANALYSIS: Don't just summarize. Reverse-engineer the PSYCHOLOGY (Why it worked).
                    5. NO MARKDOWN IN SECTION 3: Return RAW JSON strictly for the final section.
                    6. BE CONCISE: Direct and actionable insights only.
                    7. FORMATTING: Use the separator "|||SEPARATOR|||" exactly as requested to split sections.

                    === OUTPUT FORMAT (STRICTLY FOLLOW) ===

                    |||SEPARATOR|||

                    --- SECTION 1: THE SKELETON (ENGLISH - FOR SCRIPTWRITER) ---
                    [A. REVERSE ENGINEERED STRUCTURE]
                    - Format Archetype: Select ONE ONLY (Listicle / Storytelling / Commentary / ASMR / Tutorial). If ambiguous, output "Hybrid/Unclear".
                    - Pacing Strategy: (Fast/Retention-Hacking OR Slow/Deep-Dive?)
                    - ACTUAL HOOK (VERBATIM): Quote the EXACT words/sounds of the first 0-15s from SOURCE 2. DO NOT PARAPHRASE.
                    - PSYCHOLOGICAL HOOK: Select MAX 2 triggers (Curiosity / Fear / Greed / Validation). Why did the hook above work?
                    - STRUCTURE BREAKDOWN:
                      * Intro: [The Promise/Stake]
                      * Body: [Key Beats/Pattern Interrupts]
                      * Climax: [The Peak Moment]
                      * Outro: [CTA/Loop Strategy]

                    [B1. VISUAL PACING ANALYSIS]
                    - Average Shot Duration: (Fast <3s / Medium 5s / Slow >10s)?
                    - Visual Style: (Stock Footage / Animation / Real Person / Screen Rec)?  

                    [B2. REPLICATION BLUEPRINT]
                    - ELEMENTS TO COPY: (Structure, Pacing, Tone, Editing Style)
                    - ELEMENTS TO AVOID: (Specific names, Personal stories, Trademarked terms)

                    |||SEPARATOR|||

                    --- SECTION 2: GIẢI MÃ CHIẾN THUẬT (VIETNAMESE - CHI TIẾT) ---
                    (Giải thích cho Creator người Việt hiểu cách làm video này)
                    1. Loại hình & Định dạng: (Video này thuộc thể loại gì? Tại sao nó giữ chân người xem tốt?)
                    2. Chiến thuật Nhịp độ: (Nhanh hay chậm? Phù hợp với ai?)
                    3. Phân tích Mồi câu (Hook): (Tại sao 15 giây đầu lại thành công? Đánh vào tâm lý gì?)
                    4. Bài học Clone (QUAN TRỌNG): (Nếu tôi muốn làm video tương tự, tôi PHẢI bắt chước cái gì và TRÁNH cái gì để an toàn?)

                    |||SEPARATOR|||

                    {{
                        "root_keyword": "THE_MONEY_KEYWORD (The specific search term that drove views to this video, max 4 words. Optimize for High Search Volume, Extract the main topic AND TRANSLATE IT TO ENGLISH. Must be English)",
                        "content_intent": "Storytelling/Narrative" | "Educational/Facts" | "Relaxation/ASMR" | "Motivation/Inspiration" | "Tutorial/How-to" | "News/Trend Analysis",
                        "visual_style": "Stock Footage & Documentary" | "2D/3D/Whiteboard Animation" | "Screen Recording & Coding" | "Gaming & Gameplay" | "Cinematic & B-Roll" | "Typography & Kinetic Text" | "POV/Hand-Only (DIY/Review)",
                        "audience_level": "Beginner" | "General" | "Expert",
                        "is_evergreen": true,
                        "estimated_editing_effort": "Low" | "Medium" | "High",
                        "replication_risk": "Low" | "Medium" | "High"
                    }}
                """

                self.log_signal.emit(f"🧬 Đang giải mã DNA (Song ngữ) bằng {provider.upper()}...")
                success, response = self.ai.execute_custom_ai(provider, prompt, model)
                
                if success:
                    # Tách response thành 2 phần
                    full_text = str(response)
                    en_part = ""
                    vi_part = ""
                    meta_data = {
                        "root_keyword": "Unknown", 
                        "visual_style": "Default",
                        "replication_risk": "Medium"
                    }

                    # --- SMART PARSING: TÌM THEO TỪ KHÓA CHỨ KHÔNG THEO THỨ TỰ ---
                    if "|||SEPARATOR|||" in full_text:
                        parts = full_text.split("|||SEPARATOR|||")
                        
                        for p in parts:
                            p_clean = p.strip()
                            if not p_clean: continue
                            
                            # 1. Nhận diện Section 1 (Tiếng Anh)
                            if "SECTION 1" in p_clean or "THE SKELETON" in p_clean:
                                en_part = p_clean
                            
                            # 2. Nhận diện Section 2 (Tiếng Việt)
                            elif "SECTION 2" in p_clean or "CHIẾN THUẬT" in p_clean:
                                vi_part = p_clean
                            
                            # 3. Nhận diện JSON (Có dấu ngoặc nhọn) -> Lấy meta_data
                            elif "{" in p_clean and "}" in p_clean:
                                try:
                                    import re, json
                                    # Dùng Regex bắt chính xác cục JSON nằm giữa { và }
                                    match = re.search(r'(\{.*\})', p_clean, re.DOTALL)
                                    if match:
                                        json_str = match.group(1)
                                        # Parse thành Dictionary Python
                                        meta_data = json.loads(json_str)
                                except Exception as e:
                                    print(f"⚠️ Lỗi Parse JSON: {e}")

                    # Fallback: Nếu AI quên separator (Hiếm gặp với prompt V6.1)
                    if not en_part and len(parts) > 1: en_part = parts[0]
                    if not vi_part and len(parts) > 2: vi_part = parts[1]

                    # Gửi đủ 3 món về: Tiếng Anh, Tiếng Việt, và Metadata (JSON)
                    self.finished.emit({'en': en_part, 'vi': vi_part, 'meta': meta_data}, 'analysis')
                else:
                    self.error.emit(f"Lỗi phân tích: {response}")

                # [THÊM NHÁNH MỚI NÀY VÀO]
            elif self.mode == 'remix':
                # [LOGIC REMIX - NÂNG CẤP V3.0: NARRATIVE POV & HOOK LOOPS]
                
                # 1. Validate Input (Quan trọng)
                analysis_text = self.data.get('analysis', '')
                if not analysis_text or not analysis_text.strip():
                    self.error.emit("❌ Lỗi: Không tìm thấy dữ liệu phân tích. Vui lòng chạy Phân Tích trước!")
                    return
                
                # 2. Lấy Config & Context
                config = self.ai.get_worker_config("script_writer") 
                provider = config.get("provider", "google") if config else "google"
                model = config.get("model", "default") if config else "default"
                
                ref_url = self.data.get('url', 'N/A') # Lấy URL gốc để làm reference
                
                # 2. Tạo Prompt phân tích
                video_url_or_info = self.data.get('info', '')
                prompt = (
                    f"REFERENCE SOURCE: {ref_url}\n"
                    f"INPUT VIRAL DNA (SKELETON):\n{analysis_text}\n"
                    f"------------------------------\n"
                    f"ROLE: World-Class YouTube Scriptwriter & Policy Auditor (Creative Mode).\n"
                    f"TASK: Write ONE high-quality, engaging script based on the DNA above.\n"
                    f"\n"
                    f"--- PART 1: PRE-FLIGHT CHECK (CRITICAL) ---\n"
                    f"0. SANITY CHECK: Before writing, evaluate if this DNA is suitable for remixing. "
                    f"If the DNA is too specific to the original video's footage (that cannot be replicated with Stock/AI), explicitly state how you will ADAPT it to be safe.\n"
                    f"\n"
                    f"--- PART 2: WRITING RULES ---\n"
                    f"CRITICAL SAFETY RULES (ANTI-CLONE & ANTI-REUSED):\n"
                    f"1. STRUCTURE: You MUST follow the exact Hook, Pacing, and Logic of the input skeleton.\n"
                    f"2. CONTENT SWAP: You MUST completely rewrite all examples, anecdotes, and dialogue. Do NOT use the original text.\n"
                    f"3. VALUE ADD: Add at least one NEW insight or perspective that was not in the original.\n"
                    f"4. TONE: High Energy, Retention-Focused, Natural (Native Speaker level).\n"
                    f"5. SELF-CHECK: Verify that this script does NOT look like a translation of the original. It must stand alone as a unique creation.\n"
                    f"\n"
                    f"--- PART 3: SCRIPT OUTPUT ---\n"
                    f"TITLE OPTION 1: ...\n"
                    f"TITLE OPTION 2: ...\n"
                    f"\n"
                    f"[SCENE 1 - HOOK] (0:00-0:10)\n"
                    f"Visual: (Describe specific imagery)\n"
                    f"Audio: (Script...)\n"
                    f"\n"
                    f"[SCENE 2 - BODY]\n"
                    f"...\n"
                    f"\n"
                    f"--- PART 4: POST-FLIGHT RISK REVIEW ---\n"
                    f"6. RISK FLAG: Flag any part of your new script that might be considered 'borderline reused content' or 'low monetization value', and explain why it is safe.\n"
                    f"\n"
                    f"Start the Sanity Check and Script writing now:"
                )

                self.log_signal.emit(f"✍️ Đang viết lại kịch bản bằng {provider.upper()}...")

                # 3. Gọi AI
                success, response = self.ai.execute_custom_ai(provider, prompt, model)
                
                if success:
                    self.finished.emit(str(response), 'remix')
                else:
                    self.error.emit(f"Lỗi viết script: {response}")        

            elif self.mode == 'batch_remix':
                # [LOGIC NHÂN BẢN HÀNG LOẠT]
                config = self.ai.get_worker_config("script_writer")
                provider = config.get("provider", "google") if config else "google"
                model = config.get("model", "default") if config else "default"
                
                # Lấy dữ liệu đầu vào
                skeleton = self.data.get('skeleton', '')
                target_niches = self.data.get('niches', []) # List các chủ đề chọn
                target_langs = self.data.get('langs', [])   # List ngôn ngữ
                quantity = self.data.get('quantity', 3) # [MỚI] Lấy số lượng
                
                if not skeleton:
                    self.error.emit("Chưa có DNA mẫu! Hãy chạy Bước 1 trước.")
                    return
                
                # Tạo Prompt Batch
                # Ta yêu cầu AI lặp qua từng chủ đề và điền vào form
                niche_str = ", ".join(target_niches)
                lang_str = ", ".join(target_langs)
                
                prompt = (
                    f"INPUT VIRAL DNA (SKELETON):\n{skeleton}\n"
                    f"----------------------------------\n"
                    f"TASK: MASS PRODUCTION (SAFE LOCALIZATION MODE).\n"
                    f"Generate {quantity} UNIQUE SCRIPTS based on the DNA above.\n"
                    f"Based on the DNA above, generate NEW scripts for:\n"
                    f"TOPICS: {niche_str}\n"
                    f"TARGET LANGUAGES: {lang_str}\n"
                    f"\n"
                    f"CRITICAL INSTRUCTIONS (SAFETY GUARDRAILS):\n"
                    f"1. KEEP THE DNA: You MUST follow the exact Hook structure, Pacing, and Logic of the input skeleton.\n"
                    f"2. CHANGE THE CONTENT: Completely rewrite examples, stories, and dialogue. The new script must NOT resemble the original content textually.\n"
                    f"3. LOCALIZE: Use cultural references, idioms, and tone appropriate for the TARGET LANGUAGE (Natural Native Speaker flow).\n"
                    f"4. ABSTRACT THE LOGIC (ANTI-REUSED): If the skeleton relies on a specific event from the source, GENERALIZE the logic first before applying it to the new topic. Avoid semantic cloning.\n"
                    f"5. DYNAMIC TONE: Adapt the script tone to the Niche. (e.g. Horror = Scary/Slow; Tech = Fast/Excited; Relax = Calm/Soft). Do NOT use 'High Energy' for relaxing topics.\n"
                    f"6. SELF-CHECK: Before outputting, verify that the new script does NOT reference specific names, dates, or phrasing from the original source. It must add unique value.\n"
                    f"\n"
                    f"--- OUTPUT FORMAT ---\n"
                    f"=== TOPIC: [Topic Name] | LANGUAGE: [Lang] ===\n"
                    f"TITLE: [Clickable Viral Title in Native Lang]\n"
                    f"[SCENE 1 - HOOK]\n"
                    f"Visual: (Describe stock footage/AI image specific to this Topic)\n"
                    f"Audio: (Native Voiceover Script)\n"
                    f"...\n"
                    f"============================================\n"
                    f"\n"
                    f"Start generating {quantity} scripts now:"
                )
                
                self.log_signal.emit(f"🏭 Đang nhân bản và bản địa hóa ({len(target_niches)} kịch bản) trên {provider}...")
                
                success, response = self.ai.execute_custom_ai(provider, prompt, model)
                
                if success:
                    self.finished.emit(str(response), 'batch_remix')
                else:
                    self.error.emit(f"Lỗi Batch: {response}")

        except Exception as e:
            self.error.emit(str(e))

    def _run_idea_hunter(self):
        # 1. LẤY LỆNH TRỰC TIẾP
        final_prompt = self.data.get('prompt_target', '').strip()
        
        if not final_prompt:
            self.error.emit("❌ Lỗi: Ô nhập liệu Prompt đang trống!")
            return

        config = self.ai.get_worker_config("researcher") 
        provider = config.get("provider", "google") if config else "google"
        model = config.get("model", "default") if config else "default"
        
        self.log_signal.emit(f"🚀 Đang gửi lệnh cho {provider.upper()} ({model})...")

        try:
            success, response = self.ai.execute_custom_ai(provider, final_prompt, model)
            
            if success:
                parsed_data = []
                lines = str(response).strip().split('\n')
                import re 
                
                # --- TỪ ĐIỂN HIỂN THỊ (Map từ Mã -> Tên đầy đủ) ---
                # Đây là cái giúp bảng hiện đẹp (VD: NO -> 🇳🇴 Na Uy)
                # Tôi lấy đúng theo danh sách Input của bạn để nó khớp 100%
                DISPLAY_MAP = {
                    "US": "🇺🇸 Hoa Kỳ", "AU": "🇦🇺 Úc", "CH": "🇨🇭 Thụy Sĩ", "GB": "🇬🇧 Anh", "UK": "🇬🇧 Anh", 
                    "CA": "🇨🇦 Canada", "NO": "🇳🇴 Na Uy", "NZ": "🇳🇿 New Zealand",
                    "DE": "🇩🇪 Đức", "NL": "🇳🇱 Hà Lan", "SE": "🇸🇪 Thụy Điển", "DK": "🇩🇰 Đan Mạch", 
                    "FI": "🇫🇮 Phần Lan", "FR": "🇫🇷 Pháp", "IE": "🇮🇪 Ireland", "AT": "🇦🇹 Áo", "BE": "🇧🇪 Bỉ",
                    "QA": "🇶🇦 Qatar", "AE": "🇦🇪 UAE", "SG": "🇸🇬 Singapore", "JP": "🇯🇵 Nhật Bản", 
                    "KR": "🇰🇷 Hàn Quốc", "IL": "🇮🇱 Israel", "SA": "🇸🇦 Ả Rập", "HK": "🇭🇰 Hồng Kông", 
                    "TW": "🇹🇼 Đài Loan", "KW": "🇰🇼 Kuwait",
                    "ES": "🇪🇸 T.Ban Nha", "IT": "🇮🇹 Ý", "PT": "🇵🇹 Bồ Đào Nha", "PL": "🇵🇱 Ba Lan", 
                    "CZ": "🇨🇿 Séc", "GR": "🇬🇷 Hy Lạp", "HU": "🇭🇺 Hungary", "RU": "🇷🇺 Nga", "TR": "🇹🇷 Thổ Nhĩ Kỳ",
                    "BR": "🇧🇷 Brazil", "MX": "🇲🇽 Mexico", "AR": "🇦🇷 Argentina", "CL": "🇨🇱 Chile", 
                    "IN": "🇮🇳 Ấn Độ", "ZA": "🇿🇦 Nam Phi",
                    "VN": "🇻🇳 Việt Nam", "ID": "🇮🇩 Indo", "PH": "🇵🇭 Phil", "TH": "🇹🇭 Thái Lan", 
                    "MY": "🇲🇾 Malay", "PK": "🇵🇰 Pakistan", "BD": "🇧🇩 Bangladesh", "LA": "🇱🇦 Lào", "KH": "🇰🇭 Campuchia",
                    "IR": "🇮🇷 Iran", "IQ": "🇮🇶 Iraq", "EG": "🇪🇬 Ai Cập", "NG": "🇳🇬 Nigeria", "UA": "🇺🇦 Ukraine"
                }
                for line in lines:
                    line = line.strip()
                    if not line or "|" not in line: continue
                    
                    parts = [p.strip() for p in line.split('|')]
                    
                    # --- THUẬT TOÁN NHẶT MÃ [CODE] ---
                    # Tìm chuỗi nào có dạng [XX] (2 ký tự in hoa trong ngoặc)
                    detected_code = "US" # Mặc định
                    
                    for p in parts:
                        match = re.search(r"\[([A-Z]{2})\]", p.upper())
                        if match:
                            code = match.group(1)
                            # Kiểm tra xem mã này có trong từ điển của mình không
                            if code in DISPLAY_MAP:
                                detected_code = code # Lấy mã trần (VD: NO)
                                break

                    # Mapping dữ liệu
                    raw_niche = ""
                    raw_kw = ""
                    mean_kw = ""
                    title = ""
                    title_mean = ""

                    if len(parts) >= 6:
                        raw_niche = parts[0]
                        # parts[1] thường là country, ta bỏ qua vì đã nhặt ở trên
                        raw_kw = parts[2]
                        mean_kw = parts[3]
                        title = parts[4]
                        title_mean = parts[5]
                        
                        # Fix lỗi 7 cột (Competition)
                        if len(parts) >= 7 and len(parts[4]) < 15 and any(x in parts[4] for x in ["Low", "Med", "High"]):
                             title = parts[5]
                             title_mean = parts[6]

                    elif len(parts) == 5: # Fallback
                        # Nếu cột đầu là [CODE] -> Thiếu Niche
                        if "[" in parts[0] and "]" in parts[0]:
                             raw_niche = self.data.get('topic', 'General')
                             raw_kw = parts[1]
                             mean_kw = parts[2]
                             title = parts[3]
                             title_mean = parts[4]
                        else: # Cột đầu là Niche -> Thiếu Country
                             raw_niche = parts[0]
                             raw_kw = parts[1] 
                             mean_kw = parts[2]
                             title = parts[3]
                             title_mean = parts[4]
                    else: continue 

                    # Cleaning
                    clean_niche = raw_niche.replace("[","").replace("]","").strip()
                    clean_keyword = re.sub(r'(?i)^(?:\[?[a-z]{2}\]?[:\s\-]+)', '', raw_kw).strip()

                    # Đóng gói
                    parsed_data.append({
                        "topic": clean_niche,
                        "country": detected_code, 
                        "keyword": clean_keyword,
                        "meaning": mean_kw,
                        "title": title,
                        "title_meaning": title_mean
                    })

                if not parsed_data:
                    self.error.emit("AI trả dữ liệu lỗi format. Vui lòng thử lại!")
                else:
                    self.finished.emit(parsed_data, 'keywords')
            else:
                self.error.emit(f"Lỗi AI: {response}")
                
        except Exception as e:
            self.error.emit(f"Lỗi xử lý: {str(e)}")

