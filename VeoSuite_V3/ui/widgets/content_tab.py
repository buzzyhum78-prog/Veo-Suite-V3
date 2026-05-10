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

from ui.style_kit import apply_kind, apply_accent  # PR-5e: dynamic-property style helpers

from modules.content.constants import *
from modules.content.ui_components import *
from modules.content.workers import *

# PR-5b: pure helpers extracted from this file. Behaviour preserved verbatim;
# tests live in tests/test_pr5b_content_refactor.py::TestTcontent*.
from modules.content.file_naming import sanitize_filename as _pure_sanitize_filename
from modules.content.json_extractor import (
    extract_json_from_text as _pure_extract_json_from_text,
)
from modules.content.safety_filter import (
    apply_safety_filter as _pure_apply_safety_filter,
)
from modules.content.safety_filter import (
    process_voice_and_sfx as _pure_process_voice_and_sfx,
)
from modules.content.topic_classifier import (
    DEFAULT_TONE as _PURE_DEFAULT_TONE,
)
from modules.content.topic_classifier import (
    classify_duration_and_visual as _pure_classify_duration_and_visual,
)
from modules.content.topic_classifier import (
    classify_tone_by_topic as _pure_classify_tone_by_topic,
)

class ContentTab(QWidget):
    update_vn_signal = pyqtSignal(str)
    log_signal = pyqtSignal(str) # <--- [MỚI] Thêm dòng này để bắn tin ra ngoài 

    def __init__(self):
        super().__init__()
        
        # --- KHỞI TẠO DATABASE ---
        self.db = DatabaseManager() 
        self.projects = self.db.load_projects() # <--- LOAD DỮ LIỆU CŨ LÊN NGAY LẬP TỨC
        self.active_workers = {}
        self.current_project_index = -1
        
        self._build_ui()
        self._apply_style()
        
        # Vẽ lại list ngay khi mở app (nếu có dữ liệu cũ)
        self.refresh_project_list()
        
        self.list_projects.itemClicked.connect(self.on_project_selected_from_list)
        self.update_vn_signal.connect(self.box_vn.text_edit.setText)

    # [HÀM MỚI] QUÉT TOÀN BỘ DỰ ÁN ĐỂ VIẾT LẠI TIÊU ĐỀ (GLOBAL REWRITE)
    def auto_rewrite_titles_GLOBAL(self):
        # 1. Quét TẤT CẢ các dự án thay vì chỉ 1 cái
        groups = {}
        total_pending = 0
        
        for proj in self.projects:
            tasks = proj.get("tasks", [])
            for t in tasks:
                # Điều kiện: Trạng thái chờ VÀ Tiêu đề vẫn y nguyên Key Vua (chưa sửa)
                # strip() để xóa khoảng trắng thừa tránh so sánh sai
                if t["status"] == "Chờ viết" and t["title"].strip() == t["key_vua"].strip():
                    k = t["key_vua"]
                    c = t["country"]
                    topic = t["topic"]
                    
                    # Tạo ID nhóm: (Key, Country, Topic)
                    # Gom các bài cùng Key/Nước lại để xử lý 1 lần cho tiết kiệm API
                    group_id = (k, c, topic)

                    if group_id not in groups: groups[group_id] = []
                    groups[group_id].append(t)
                    total_pending += 1
        
        if not groups:
            self.log_system("⚠️ Không tìm thấy bài nào cần viết lại tiêu đề trên toàn hệ thống.")
            return

        # 2. Đưa vào Hàng Đợi (Queue)
        self.rewrite_queue = [] # Reset hàng đợi
        for (key, country, topic), task_list in groups.items():
            self.rewrite_queue.append({
                "key": key,
                "country": country,
                "topic": topic,
                "tasks": task_list, # Tham chiếu trực tiếp đến object trong list
                "qty": len(task_list)
            })

        count_groups = len(self.rewrite_queue)
        self.log_system(f"🚀 GLOBAL SCAN: Tìm thấy {count_groups} nhóm ({total_pending} bài) trên TẤT CẢ các kênh.")
        
        # 3. Kích hoạt xử lý tuần tự
        self.process_next_rewrite_group()

    # [HÀM MỚI] XỬ LÝ TUẦN TỰ TỪNG NHÓM (Process Queue)
    def process_next_rewrite_group(self):
        # Nếu hàng đợi hết -> Xong
        if not hasattr(self, 'rewrite_queue') or not self.rewrite_queue:
            self.log_system("✅ HOÀN TẤT: Đã viết lại tiêu đề cho tất cả các nhóm!")
            QMessageBox.information(self, "Xong", "Đã tối ưu xong toàn bộ tiêu đề!")
            return

        # Lấy nhóm đầu tiên ra (Pop)
        current_job = self.rewrite_queue.pop(0)
        
        key = current_job["key"]
        qty = current_job["qty"]
        country = current_job["country"]
        topic = current_job["topic"]
        
        self.log_system(f"⚡ [QUEUE] Đang xử lý nhóm: {country} | Key: '{key}' ({qty} bài)...")
        # [MỚI] Lấy duration từ bài đầu tiên trong nhóm để làm chuẩn
        first_task = current_job["tasks"][0]
        # Lấy duration từ UI hoặc từ config mặc định của Topic đó
        # Ở đây ta tạm truyền rỗng hoặc string mặc định nếu không lấy được từ UI
        # Nhưng tốt nhất là ngài sửa dòng gọi Worker như sau:

        # Gọi Worker
        self.current_rewrite_worker = BatchTitleGeneratorWorker(key, qty, country, topic, duration_label="Auto Length")
        
        # Kết nối tín hiệu: Khi xong nhóm này -> Gọi hàm xử lý kết quả -> Sau đó TỰ GỌI LẠI hàm này để làm nhóm tiếp
        # Dùng lambda để truyền task_list vào
        self.current_rewrite_worker.finished_signal.connect(
            lambda titles, tasks=current_job["tasks"]: self.on_rewrite_group_finished(titles, tasks)
        )
        
        self.current_rewrite_worker.start()

    # [HÀM MỚI] XỬ LÝ KẾT QUẢ VÀ KÍCH HOẠT TIẾP THEO
    def on_rewrite_group_finished(self, new_titles, task_list):
        if new_titles:
            # Cập nhật vào DB
            for i, task in enumerate(task_list):
                if i < len(new_titles):
                    raw_title = new_titles[i]

                    # --- [LOGIC MỚI] XỬ LÝ TAG BẤT CHẤP VỊ TRÍ ---
                    clean_title = raw_title
                    intent = "Viral/Normal" # Mặc định

                    if "[Search]" in raw_title:
                        clean_title = raw_title.replace("[Search]", "").strip()
                        intent = "SEO/Search"
                    elif "[Browse]" in raw_title:
                        clean_title = raw_title.replace("[Browse]", "").strip()
                        intent = "Viral/Browse"
                    
                    # Xử lý dọn dẹp dấu thừa lần cuối (cho chắc)
                    clean_title = clean_title.strip(" .-_*")

                    task["title"] = clean_title
                    task["_temp_intent"] = intent # Lưu tạm để hiện tooltip
            
            self.db.save_projects(self.projects)
            self.refresh_task_table()
            self.log_system(f"✅ Đã cập nhật xong nhóm hiện tại ({len(new_titles)} tiêu đề).")
        else:
            self.log_system("⚠️ Nhóm này AI trả về rỗng. (Check Console đen để xem lỗi chi tiết).")

        # --- QUAN TRỌNG: NGHỈ 2 GIÂY RỒI LÀM NHÓM TIẾP THEO ---
        # (Delay để Google không chặn API)
        QTimer.singleShot(2000, self.process_next_rewrite_group)

    # Hàm Callback để áp dụng tiêu đề mới
    def apply_new_titles(self, new_titles, task_list):
        if not new_titles: return
        
        # Gán tiêu đề mới cho từng task
        for i, task in enumerate(task_list):
            if i < len(new_titles):
                raw_title = new_titles[i]
                
                # --- [XỬ LÝ CẮT ĐUÔI THÔNG MINH] ---
                clean_title = raw_title
                intent_type = "Normal" # Mặc định
                
                if "[Search]" in raw_title:
                    clean_title = raw_title.replace("[Search]", "").strip()
                    intent_type = "🔍 SEO/Search"
                elif "[Browse]" in raw_title:
                    clean_title = raw_title.replace("[Browse]", "").strip()
                    intent_type = "🚀 Viral/Browse"
                
                # Gán tiêu đề SẠCH vào
                task["title"] = clean_title
                
                # Lưu loại chiến thuật vào visual_style hoặc một chỗ nào đó để CEO nhớ (Tùy chọn)
                # Hoặc chỉ cần hiện Tooltip
                # Ở đây tôi tạm gán vào biến tạm để hiển thị tooltip trong bảng
                task["_temp_intent"] = intent_type 

        self.db.save_projects(self.projects)
        self.refresh_task_table()
        self.log_system(f"✅ AUTO-TITLE: Đã cập nhật & làm sạch {len(new_titles)} tiêu đề!")

    # [HÀM MỚI] TỰ ĐỘNG TẠO PROMPT RIÊNG CHO TỪNG BÀI
    def generate_dynamic_prompt(self, task):
        # 1. Lấy thông tin từ Task & Giao diện
        topic = self.cb_topic.currentText().strip()
        raw_country = self.cb_country.currentText().strip()
        print(f"DEBUG GỬI AI: Country={raw_country} | Topic={topic}")
        platform = (
            self.cb_platform.currentText()
            if hasattr(self, "cb_platform")
            else task.get("platform", "Youtube")
        )
        duration_str = self.cb_duration.currentText()

        # ==================================================================
        # 🟢 LOGIC MỚI: XÁC ĐỊNH CHỦ ĐỀ CHÍNH (CONTENT FOCUS)
        # ==================================================================
        current_title = task.get("title", "").strip()
        key_vua = task.get("key_vua", "").strip()
        
        # Mặc định lấy Key Vua làm chủ đề
        main_subject = key_vua
        has_locked_title = False
        # Nếu đã có Tiêu đề (Khác Key Vua) -> ÉP AI VIẾT THEO TIÊU ĐỀ
        if current_title and current_title != key_vua:
            has_locked_title = True
            main_subject = current_title # <--- QUAN TRỌNG: Chủ đề chính giờ là Tiêu đề
            print(f"🎯 LOCKED SUBJECT: {main_subject}")

        # ------------------------------------------------------------------
        # 1. Lấy Skeleton (nếu có) - Đây là di sản từ Tab 3
        spy_skeleton = task.get("spy_skeleton", "")
        if not spy_skeleton: spy_skeleton = "No specific skeleton. Use standard viral structure."

        thumb_url = task.get("thumbnail_url", "")
        vis_source = self.cb_visual_source.currentText()

        # 2. Lấy Visual Style (Ưu tiên Style bài riêng -> Style Kênh -> Mặc định)
        # Lấy từ giao diện HQ để đảm bảo cập nhật mới nhất
        vis_style = "Cinematic, High Quality"
        if hasattr(self, 'txt_visual_style'):
            vis_style = self.txt_visual_style.toPlainText()
        # Nếu task có style riêng (do import) thì đè lên
        if task.get("visual_style_override"):
            vis_style = task.get("visual_style_override")
        if not vis_style: vis_style = "Cinematic, Realistic, 4K"
        
        # Custom Instruction (Check kiểu dữ liệu widget)
        custom_note = ""
        if hasattr(self, 'txt_custom_instruction'):
            # Thử lấy text theo cả 2 cách để tránh lỗi crash
            widget = self.txt_custom_instruction
            try:
                custom_note = widget.toPlainText().strip()
            except AttributeError:
                custom_note = widget.text().strip()

        # --- [A] XỬ LÝ TONE GIỌNG ---
        ui_tone = self.cb_tone.currentText()
        topic_lower = topic.lower()
        # 1. Khởi tạo giá trị mặc định (Lấy từ giao diện nếu không trúng Preset)
        final_duration = duration_str 
        final_vis_source = vis_source
        is_silent_mode = False
        tone = "Professional/Neutral"
        
        # 2. Áp dụng Luật chơi (Preset)
        # --- NHÓM 1: AMBIENT / MUSIC / SLEEP ---
        if any(x in topic_lower for x in ["rain", "music", "lofi", "sleep", "asmr", "meditation", "mưa", "thiền", "ngủ", "nhạc", "ambient", "study", "piano", "noise", "yoga", "focus", "snow", "winter", "tuyết", "fire", "lửa", "ocean", "water", "biển"]):
            print(f"🎹 ÁP DỤNG PRESET: MUSIC/AMBIENT")
            is_silent_mode = True
            final_duration = "1 Hour Loop"          # <--- Tự động set 1 tiếng
            final_vis_source = "100% Stock Footage" # <--- Nhạc dùng Stock
            vis_style = "Cozy, Photorealistic, 4K, Aesthetic, Soft Lighting"
            tone = "Healing/Relaxing"

        # --- NHÓM 2: HISTORY / MYSTERY ---
        elif any(x in topic_lower for x in ["lịch sử", "history", "war", "chiến tranh", "bí ẩn", "mystery", "vụ án"]):
            print(f"📜 ÁP DỤNG PRESET: HISTORY")
            is_silent_mode = False
            final_duration = "10-15 Minutes"        # <--- Lịch sử dài vừa phải
            final_vis_source = "80% AI Generated + 20% Stock"
            vis_style = "Epic, Vintage, Documentary Style, Detailed, 8K"
            tone = "Documentary/Epic/Serious"

        # --- NHÓM 3: HORROR / CREEPY ---
        elif any(x in topic_lower for x in ["ma", "kinh dị", "horror", "scary", "ghost", "creepy"]):
            print(f"👻 ÁP DỤNG PRESET: HORROR")
            is_silent_mode = False
            final_duration = "8-10 Minutes"
            final_vis_source = "100% AI Generated"
            vis_style = "Dark, Gloomy, High Contrast, Foggy, Unreal Engine 5"
            tone = "Horror/Creepy/Suspenseful"

        # --- NHÓM 4: KIDS / FAIRY TALES ---
        elif any(x in topic_lower for x in ["kid", "bé", "truyện cổ tích", "fairy", "cartoon", "hoạt hình"]):
            print(f"🧸 ÁP DỤNG PRESET: KIDS")
            is_silent_mode = False
            final_duration = "5-8 Minutes"
            final_vis_source = "100% AI Generated"
            vis_style = "3D Pixar Style, Cute, Bright Colors, Soft"
            tone = "Gentle/Bedtime Story"

        # --- MẶC ĐỊNH (Theo UI) ---
        else:
            # Nếu user chọn Tone trên UI, dùng Tone đó. Nếu Auto, để mặc định Professional.
            if "Auto" not in ui_tone: tone = ui_tone

        # ==================================================================
        # [B] MAPPING NGÔN NGỮ TOÀN CẦU (FULL TIER 1 -> TIER 7)
        # ==================================================================
        # Logic: Key là từ khóa nhận diện (Mã nước, Tên nước, hoặc Mã ngữ).
        # Value là (Tên Tiếng Anh của Ngôn ngữ, Câu chào mẫu).
        
        lang_map = {
            # --- NHÓM TIẾNG ANH (ENGLISH - High RPM & Global) ---
            # Tier 1: US, AU, UK, CA, NZ | Tier 2: IE | Tier 3: SG, UAE(En) | Tier 5: ZA, IN(En) | Tier 6: PH | Tier 7: NG
            "Hoa Kỳ": ("English", "Welcome back..."), "Mỹ": ("English", "Welcome back..."), "US": ("English", "Welcome back..."),
            "Anh": ("English", "Welcome back..."), "UK": ("English", "Welcome back..."), "GB": ("English", "Welcome back..."),
            "Úc": ("English", "G'day mate..."), "Australia": ("English", "G'day mate..."), "AU": ("English", "G'day mate..."),
            "Canada": ("English", "Welcome back..."), "CA": ("English", "Welcome back..."),
            "New Zealand": ("English", "Welcome back..."), "NZ": ("English", "Welcome back..."),
            "Ireland": ("English", "Welcome back..."), "IE": ("English", "Welcome back..."),
            "Singapore": ("English", "Welcome back..."), "SG": ("English", "Welcome back..."),
            "Philippines": ("English", "Welcome back..."), "PH": ("English", "Welcome back..."),
            "Nam Phi": ("English", "Welcome back..."), "ZA": ("English", "Welcome back..."),
            "Nigeria": ("English", "Welcome back..."), "NG": ("English", "Welcome back..."),
            "(En)": ("English", "Welcome back..."), # Catch-all cho mọi nước dùng (En)

            # --- NHÓM TIẾNG VIỆT (VIETNAMESE) ---
            "Việt Nam": ("Vietnamese", "Xin chào..."), "VN": ("Vietnamese", "Xin chào..."), "(Vi)": ("Vietnamese", "Xin chào..."),

            # --- NHÓM TIẾNG ĐỨC (GERMAN) ---
            # Tier 1: Thụy Sĩ (De) | Tier 2: Đức, Áo
            "Đức": ("German", "Hallo..."), "DE": ("German", "Hallo..."), 
            "Áo": ("German", "Hallo..."), "AT": ("German", "Hallo..."),
            "Thụy Sĩ": ("German", "Grüezi..."), "CH": ("German", "Grüezi..."), # Ưu tiên Đức cho Thụy Sĩ vì RPM cao nhất
            "(De)": ("German", "Hallo..."),

            # --- NHÓM TIẾNG PHÁP (FRENCH) ---
            # Tier 2: Pháp, Bỉ (Fr)
            "Pháp": ("French", "Bonjour..."), "FR": ("French", "Bonjour..."), 
            "Bỉ": ("French", "Bonjour..."), "BE": ("French", "Bonjour..."),
            "(Fr)": ("French", "Bonjour..."),

            # --- NHÓM TIẾNG TÂY BAN NHA (SPANISH) ---
            # Tier 4: TBN | Tier 5: Mexico, Argentina, Chile
            "Tây Ban Nha": ("Spanish", "Hola..."), "ES": ("Spanish", "Hola..."), 
            "Mexico": ("Spanish", "Hola..."), "MX": ("Spanish", "Hola..."),
            "Argentina": ("Spanish", "Hola..."), "AR": ("Spanish", "Hola..."),
            "Chile": ("Spanish", "Hola..."), "CL": ("Spanish", "Hola..."),
            "(Es)": ("Spanish", "Hola..."),

            # --- NHÓM TIẾNG BỒ ĐÀO NHA (PORTUGUESE) ---
            # Tier 4: Bồ Đào Nha | Tier 5: Brazil
            "Bồ Đào Nha": ("Portuguese", "Olá..."), "PT": ("Portuguese", "Olá..."),
            "Brazil": ("Portuguese", "Olá..."), "BR": ("Portuguese", "Olá..."),
            "(Pt)": ("Portuguese", "Olá..."),

            # --- NHÓM TIẾNG Ả RẬP (ARABIC) ---
            # Tier 3: Qatar, UAE, Saudi, Kuwait | Tier 7: Iraq, Ai Cập
            "Qatar": ("Arabic", "مرحباً (Marhaban)..."), "QA": ("Arabic", "مرحباً (Marhaban)..."),
            "UAE": ("Arabic", "مرحباً (Marhaban)..."), "AE": ("Arabic", "مرحباً (Marhaban)..."),
            "Ả Rập": ("Arabic", "مرحباً (Marhaban)..."), "SA": ("Arabic", "مرحباً (Marhaban)..."),
            "Kuwait": ("Arabic", "مرحباً (Marhaban)..."), "KW": ("Arabic", "مرحباً (Marhaban)..."),
            "Iraq": ("Arabic", "مرحباً (Marhaban)..."), "IQ": ("Arabic", "مرحباً (Marhaban)..."),
            "Ai Cập": ("Arabic", "مرحباً (Marhaban)..."), "EG": ("Arabic", "مرحباً (Marhaban)..."),
            "(Ar)": ("Arabic", "مرحباً (Marhaban)..."),

            # --- NHÓM CHÂU Á (ASIA - SPECIFIC) ---
            "Nhật Bản": ("Japanese", "こんにちは (Konnichiwa)..."), "JP": ("Japanese", "こんにちは (Konnichiwa)..."), "(Ja)": ("Japanese", "こんにちは (Konnichiwa)..."),
            "Hàn Quốc": ("Korean", "안녕하세요 (Annyeonghaseyo)..."), "KR": ("Korean", "안녕하세요 (Annyeonghaseyo)..."), "(Ko)": ("Korean", "안녕하세요 (Annyeonghaseyo)..."),
            "Trung Quốc": ("Chinese (Mandarin)", "大家好 (Dàjiā hǎo)..."), "CN": ("Chinese (Mandarin)", "大家好 (Dàjiā hǎo)..."), "(Zh)": ("Chinese (Mandarin)", "大家好 (Dàjiā hǎo)..."),
            "Đài Loan": ("Chinese (Mandarin)", "大家好 (Dàjiā hǎo)..."), "TW": ("Chinese (Mandarin)", "大家好 (Dàjiā hǎo)..."),
            "Hồng Kông": ("Chinese (Cantonese)", "你好 (Nei hou)..."), "HK": ("Chinese (Cantonese)", "你好 (Nei hou)..."),
            "Ấn Độ": ("Hindi", "नमस्ते (Namaste)..."), "IN": ("Hindi", "नमस्ते (Namaste)..."), "(Hi)": ("Hindi", "नमस्ते (Namaste)..."),
            "Thái Lan": ("Thai", "สวัสดี (Sawasdee)..."), "TH": ("Thai", "สวัสดี (Sawasdee)..."), "(Th)": ("Thai", "สวัสดี (Sawasdee)..."),
            "Lào": ("Lao", "ສະບາຍດີ (Sabaidee)..."), "LA": ("Lao", "ສະບາຍດີ (Sabaidee)..."), "(Lo)": ("Lao", "ສະບາຍດີ (Sabaidee)..."),
            "Campuchia": ("Khmer", "សួស្តី (Suostei)..."), "KH": ("Khmer", "សួស្តី (Suostei)..."), "(Km)": ("Khmer", "សួស្តី (Suostei)..."),
            "Indonesia": ("Indonesian", "Halo..."), "ID": ("Indonesian", "Halo..."), "(Id)": ("Indonesian", "Halo..."),
            "Malaysia": ("Malay", "Halo..."), "MY": ("Malay", "Halo..."), "(Ms)": ("Malay", "Halo..."),
            "Pakistan": ("Urdu", "السلام علیکم (Assalam)..."), "PK": ("Urdu", "السلام علیکم (Assalam)..."), "(Ur)": ("Urdu", "السلام علیکم (Assalam)..."),
            "Bangladesh": ("Bengali", "হ্যালো (Hyālō)..."), "BD": ("Bengali", "হ্যালো (Hyālō)..."), "(Bn)": ("Bengali", "হ্যালো (Hyālō)..."),

            # --- NHÓM BẮC ÂU (NORDIC) ---
            "Thụy Điển": ("Swedish", "Hej..."), "SE": ("Swedish", "Hej..."), "(Sv)": ("Swedish", "Hej..."),
            "Na Uy": ("Norwegian", "Hei..."), "NO": ("Norwegian", "Hei..."), "(No)": ("Norwegian", "Hei..."),
            "Đan Mạch": ("Danish", "Hej..."), "DK": ("Danish", "Hej..."), "(Da)": ("Danish", "Hej..."),
            "Phần Lan": ("Finnish", "Hei..."), "FI": ("Finnish", "Hei..."), "(Fi)": ("Finnish", "Hei..."),
            "Hà Lan": ("Dutch", "Hallo..."), "NL": ("Dutch", "Hallo..."), "(Nl)": ("Dutch", "Hallo..."),

            # --- NHÓM NAM/ĐÔNG ÂU & KHÁC ---
            "Ý": ("Italian", "Ciao..."), "Italy": ("Italian", "Ciao..."), "IT": ("Italian", "Ciao..."), "(It)": ("Italian", "Ciao..."),
            "Nga": ("Russian", "Привет (Privet)..."), "RU": ("Russian", "Привет (Privet)..."), "(Ru)": ("Russian", "Привет (Privet)..."),
            "Ukraine": ("Ukrainian", "Привіт (Pryvit)..."), "UA": ("Ukrainian", "Привіт (Pryvit)..."), "(Uk)": ("Ukrainian", "Привіт (Pryvit)..."),
            "Ba Lan": ("Polish", "Cześć..."), "PL": ("Polish", "Cześć..."), "(Pl)": ("Polish", "Cześć..."),
            "Séc": ("Czech", "Ahoj..."), "CZ": ("Czech", "Ahoj..."), "(Cs)": ("Czech", "Ahoj..."),
            "Hy Lạp": ("Greek", "Γεια (Yia)..."), "GR": ("Greek", "Γεια (Yia)..."), "(El)": ("Greek", "Γεια (Yia)..."),
            "Hungary": ("Hungarian", "Szia..."), "HU": ("Hungarian", "Szia..."), "(Hu)": ("Hungarian", "Szia..."),
            "Thổ Nhĩ Kỳ": ("Turkish", "Merhaba..."), "TR": ("Turkish", "Merhaba..."), "(Tr)": ("Turkish", "Merhaba..."),
            "Israel": ("Hebrew", "שלום (Shalom)..."), "IL": ("Hebrew", "שלום (Shalom)..."), "(He)": ("Hebrew", "שלום (Shalom)..."),
            "Iran": ("Persian", "سلام (Salam)..."), "IR": ("Persian", "سلام (Salam)..."), "(Fa)": ("Persian", "سلام (Salam)..."),
        }

        target_language = "English"
        sample_text = "Hello..."
        # Logic tìm kiếm trong Map
        for key, val in lang_map.items():
            if key in raw_country or f"({key})" in raw_country:
                target_language, sample_text = val
                break
        # DEBUG kiểm tra xem nhận đúng nước chưa
        print(f"🌍 Detected Country: {raw_country} -> Lang: {target_language}")
        
        # ==================================================================
        # [NEW] BỘ LỌC SỰ THẬT (TRUTH FILTER - CHỐNG BỊA ĐẶT)
        # ==================================================================
        truth_instruction = "CREATIVE FREEDOM ALLOWED. Focus on engagement and emotion." # Mặc định (Giải trí/Nhạc)
        
        # Nhóm 1: BẮT BUỘC SỰ THẬT 100% (History, News, Finance, Science, Health)
        # Các chủ đề này nếu AI bịa (Hallucination) -> Youtube quét "Misleading" -> Chết kênh.
        strict_facts_keywords = [
            "lịch sử", "history", "war", "chiến tranh", "ancient", "cổ đại",
            "tin tức", "news", "sự thật", "fact", "top 10",
            "tài chính", "finance", "crypto", "tiền", "business",
            "khoa học", "science", "technology", "công nghệ",
            "sức khỏe", "health", "y tế", "medicine", "bệnh",
            "vụ án", "crime", "sát nhân", "biography", "tiểu sử"
        ]
        
        # Nhóm 2: NỬA THỰC NỬA HƯ (Mystery, Space)
        semi_facts_keywords = ["bí ẩn", "mystery", "vũ trụ", "space", "alien", "người ngoài hành tinh", "tâm linh", "thần thoại"]

        if any(k in topic_lower for k in strict_facts_keywords):
            print(f"⚖️ TRUTH MODE: STRICT (Sự thật 100%) cho '{topic_lower}'")
            truth_instruction = (
                "⚠️ STRICTLY FACTUAL MODE (NON-FICTION):\n"
                "1. Content must be based on REAL historical events, verified news, or scientific data.\n"
                "2. NO HALLUCINATIONS. Do not invent names, dates, or events.\n"
                "3. If information is uncertain, explicitly state it as a 'theory' or 'legend'.\n"
                "4. Accuracy is more important than drama."
            )
        elif any(k in topic_lower for k in semi_facts_keywords):
            print(f"⚖️ TRUTH MODE: SEMI (Huyền bí) cho '{topic_lower}'")
            truth_instruction = (
                "⚖️ SEMI-FACTUAL MODE:\n"
                "Clearly distinguish between proven facts (Science) and unproven theories (Mystery/Speculation).\n"
                "Do not present rumors as absolute truth."
            )

        # ==================================================================
        # 🟢 [C] PHÂN LOẠI CHẾ ĐỘ: KỂ CHUYỆN (NARRATIVE) vs KHÔNG LỜI (SILENT)
        # ==================================================================
        is_silent_mode = False
        
        # Danh sách chủ đề TUYỆT ĐỐI KHÔNG CẦN GIỌNG ĐỌC
        if any(x in topic_lower for x in ["rain", "music", "lofi", "sleep", "asmr", "meditation", "mưa", "thiền", "ngủ", "nhạc", "ambient", "study", "piano", "noise", "yoga", "focus"]):
            is_silent_mode = True

        # --- [D] ÉP ĐỘ DÀI (HARDCORE MODE – NÂNG CẤP) ---
        word_count_guide = "approx 150 words"
        body_instruction = ""
        output_structure = {}
        ssml_guide = ""
        fd_lower = str(final_duration).lower()
        
        if is_silent_mode:
            # === 🎵 CHẾ ĐỘ 1: PURE SOUND (KHÔNG LỜI - CHỈ ÂM THANH 3 TẦNG) ===
            print("🌊 DETECTED: Silent/Music Mode (Bỏ qua Voice)")
            
            word_count_guide = "0 WORDS (NO VOICE AT ALL)"
            
            # Chỉ đạo AI tập trung vào ÂM THANH 3 LỚP
            body_instruction = (
                "MODE: PURE AMBIENT/ASMR (NO VOICE).\n"
                "1. SCRIPT: DO NOT WRITE ANY VOICE SCRIPT. The video must be 100% audio experience.\n"
                "2. AUDIO RECIPE (CRITICAL): You must act as a Sound Engineer and define 3 LAYERS of sound:\n"
                "   - Layer 1 (Base): Constant atmosphere (Rain, Wind, Ocean, Forest, Brown Noise). MUST BE IN ENGLISH for search engine.\n"
                "   - Layer 2 (Musical): Soft, slow instrumental pad (Piano, Flute, Singing Bowl) or Frequency (432Hz). NO DRUMS. MUST BE IN ENGLISH.\n"
                "   - Layer 3 (Accent): Random details to add realism (Distant Thunder, Crickets, Fire crackle). MUST BE IN ENGLISH.\n"
                "CRITICAL: The 'audio_engineer_recipe' values MUST be in ENGLISH regardless of the target language.\n"
                "3. VISUAL: Describe a perfect seamless loop scene."
            )
            
            # Cấu trúc JSON đặc biệt: Bỏ 'audio_director', dùng 'audio_engineer_recipe'
            output_structure = {  
                "project_meta": {"mode": "SILENT_AMBIENT"},
                "seo_core": {"main_keyword": key_vua , "seo_score_target": 95},            
                "marketing_kit": {
                    "title_primary": f"Viral Title (MANDATORY: Include '{key_vua}' AND Frequency Keywords like: 432Hz, 528Hz, 963Hz, Alpha Waves, Binaural Beats, Delta for Sleep, Rain Sounds)",
                    "description": "SEO optimized description (3 lines, includes keywords). Mention benefits: Sleep, Focus, Healing.",
                    "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
                    "thumbnail_text": "Short, Punchy Text for Cover (Max 5 words)",
                    "thumbnail_prompt": f"High-quality prompt describing a {vis_style} cover image..."
                },
                "audio_engineer_recipe": { 
                    "layer_1_ambience_search": "Keywords for constant background - English Keywords Only (e.g. 'Heavy Rain on Window')",
                    "layer_2_music_search": "Keywords for musical pad - English Keywords Only (e.g. 'Sad Piano Slow', '432Hz Drone Pad')",
                    "layer_3_sfx_search": "Keywords for random details - English Keywords Only (e.g. 'Distant Thunder', 'Wind Chimes')",
                    "voice_model": "None (Silent)"
                },
                "script_board": [
                    {
                        "scene_id": 1,
                        "role": "INFINITE_LOOP",
                        "estimated_duration": final_duration,
                        "voice_text": "(NO VOICE - AUDIO LAYERS PLAYING ONLY)", # <--- Ép AI trả về dòng này
                        "visual_prompt": f"({vis_style})Perfect seamless loop of rain falling against the glass, warm light inside...",
                        "note": "This scene repeats until the end of video."
                    }
                ]
            }

        else:
            # === 📖 CHẾ ĐỘ 2: NARRATIVE (KỂ CHUYỆN BÌNH THƯỜNG - GIỮ NGUYÊN) ===
            # Logic cũ: Tính số từ dựa trên phút
            if "3 phút" in duration_str:
                word_count_guide = "approx 450 words"
                body_instruction = "WRITE_DETAILED_CONTENT_MIN_400_WORDS"
            elif "5 phút" in duration_str:
                word_count_guide = "approx 800 words"
                body_instruction = "WRITE_VERY_DETAILED_CONTENT_MIN_700_WORDS"
            elif "10 phút" in duration_str:
                word_count_guide = "approx 1500 words"
                body_instruction = "WRITE_EXTREMELY_DEEP_CONTENT_MIN_1500_WORDS_NO_SUMMARY"
            elif "15+" in duration_str:
                word_count_guide = "approx 2500 words"
                body_instruction = "WRITE_DOCUMENTARY_STYLE_CONTENT_MIN_2500_WORDS"
            elif "20+" in duration_str:
                word_count_guide = "over 3000 words"
                body_instruction = "WRITE_FULL_LENGTH_DOCUMENTARY_MIN_3000_WORDS_NO_SUMMARY" 
            
        # Cấu trúc JSON chuẩn cho kể chuyện
            output_structure = {
                "project_meta": {"mode": "NARRATIVE"},
                "seo_core": {"main_keyword": key_vua , "seo_score_target": 95},
                "marketing_kit": {
                    "title_primary": "Viral Title (Uses LOCKED_TITLE if provided, else create best one)",
                    "description": "SEO optimized description (3 lines, includes keywords)",
                    "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
                    "thumbnail_text": "Short, Punchy Text for Cover (Max 5 words)",
                    "thumbnail_prompt": f"High-quality prompt describing a {vis_style} cover image..."
                },
                "audio_director": {
                    "music_mood": "Keywords for background music (e.g., 'Suspenseful, Lo-fi, Epic')",
                    "voice_intonation": "Specific instruction for the Voiceover Artist, Professional/Deep/Engaging"
               },
                "script_board": [
                    {
                        "scene_id": 1,
                        "role": "THE_HOOK",
                        "emotional_goal": "SHOCK / CURIOSITY",
                        "estimated_duration": "00:00 - 00:XX",
                        "visual_prompt": f"({vis_style}) Detailed English description with CAMERA MOVEMENT...",
                        "voice_text": f"FULL {target_language.upper()} Hook here (Must relate to '{main_subject}'). Start immediately, NO generic greeting."
                    },
                    {
                        "scene_id": 2,
                        "role": "BODY",
                        "estimated_duration": "...",
                        "visual_prompt": "...",
                        "voice_text": "Detailed content body..."
                    },
                    {
                        "scene_id": "N",
                        "role": "CONCLUSION/CTA",
                        "estimated_duration": "...",
                        "visual_prompt": "...",
                        "voice_text": "Conclusion and Call to Action..."
                    }
                ]
            }
        
        # --- [NÂNG CẤP] THÊM HƯỚNG DẪN CẢM XÚC (SSML SHORTCODES) ---
        ssml_guide = ""
        if not is_silent_mode:
            ssml_guide = (
                "AUDIO SPEECH OPTIMIZATION (CRITICAL FOR NATURAL TTS):\n"
                "The script must be formatted as raw text specifically for AI Voice reading. Follow these rules strictly:\n"
                " 1. PACING & BREATHING: Use ellipses '...' for natural pauses or hesitations. Use Double Line Breaks for distinct transitions between ideas.\n"
                " 2. EMPHASIS: Use CAPS LOCK for specific words that require strong vocal stress or urgency.\n"
                " 3. TEXT NORMALIZATION: Convert all numbers, currencies, dates, and symbols into full spoken words to prevent TTS errors.\n"
                "    - Numbers: Write 'one thousand' instead of '1000'.\n"
                "    - Dates/Ordinals: Write 'the first' instead of '1st', 'twenty twenty-five' instead of '2025'.\n"
                "    - Currencies/Symbols: Write 'ten percent' instead of '10%', 'fifty dollars' instead of '$50'.\n"
                " 4. CLEAN TEXT ONLY: ABSOLUTELY NO non-spoken tags. Do not use [pause], [music], [laughter], or (sfx).\n"
                "    - BAD: 'Hello [pause] world.'\n"
                "    - GOOD: 'Hello... world.'"
            )

        # --- [C] ÉP NGÔN NGỮ + TONE ---
        force_lang_instruction = (
            f"CRITICAL: INPUT topic is '{topic}', topic may be Vietnamese, BUT YOU MUST WRITE THE FINAL SCRIPT IN [{target_language.upper()}]. "
            f"Language Reference: '{sample_text}'. "
            f"TONE OF VOICE MUST BE: [{tone.upper()}]. "
            f"DO NOT TRANSLATE BACK TO VIETNAMESE."
        )

        ratio_instruction = "80% Stock + 20% AI"
        if "100% AI" in vis_source:
            ratio_instruction = "100% AI Generated"
        elif "100% Stock" in vis_source:
            ratio_instruction = "100% Stock Footage"

        # --- [E] PROMPT JSON (CLONE vs CREATE) ---
        # Biến chứa hướng dẫn cốt lõi
        core_instruction = ""

        if spy_skeleton:
            # === CHẾ ĐỘ 1: CLONE/REMIX (Dựa trên Spy Skeleton) ===
            print("🧬 DETECTED SPY SKELETON: Chuyển sang chế độ Remix cấu trúc.")
            core_instruction = f"""
            Task Mode: STRUCTURE CLONING (REMIX).
            INPUT SKELETON (DNA):
            {spy_skeleton}
            -------------------------
            INSTRUCTION: 
            1. You MUST follow the exact 'Hook -> Retention -> Payoff' structure of the INPUT SKELETON.
            2. BUT you must CHANGE the content/topic to fit: "{topic}".
            3. Do NOT copy the original text word-for-word. Adapt the LOGIC, apply it to the new topic.
            """
        else:
            # === CHẾ ĐỘ 2: SÁNG TẠO MỚI (Như cũ) ===
            print("✨ NO SKELETON: Chế độ sáng tạo tự do.")
            core_instruction = f"""
            Task Mode: CREATIVE WRITING FROM SCRATCH.
            Create a high-retention script optimized for {platform}.
            Structure: Explosive Hook (0-5s) -> Value-packed Body -> Strong CTA.
            """
        
        # --- [F] PROMPT JSON FINAL ---
        prompt_json = {
            # [1. ĐỊNH DANH VÀ VAI TRÒ]
            "ROLE": f"World-Class Content Director & Native {target_language} Storyteller (Specializing in Retention Psychology)",
            "OUTPUT_LANGUAGE_RULE": f"DETECT language from AUDIENCE '{raw_country}'. MUST write Script/Voiceover in that language.",
            "REFERENCE_THUMBNAIL": thumb_url if thumb_url else "None",
            "VISUAL_TASK": "If REFERENCE_THUMBNAIL is provided, analyze its style.",

            # [2. DỮ LIỆU ĐẦU VÀO - Gom nhóm gọn gàng]
            "INPUT_CONTEXT": {
                "CORE_INSTRUCTION": core_instruction,
                "CONTENT_FOCUS": main_subject,  
                "SEO_KEYWORD": key_vua,    
                "Topic": topic,
                "Audience_Language": target_language,
                "Audience_Persona": raw_country,
                "Platform": f"{platform} (Fast-paced, dopamine-driven)" if platform in ["TikTok", "Shorts"] else f"{platform} (Search-driven, value-heavy)",
                "Main_Keyword": task.get("key_vua", ""),
                "Target_Duration": f"{duration_str} (Target: {word_count_guide} words- DO NOT EXCEED)",
                "LOCKED_TITLE": current_title if has_locked_title else "None"
            },

            # [3. QUY TẮC CỐT LÕI - Sáp nhập các rule rời rạc vào đây]
            "STRATEGIC_MANDATES": {
                "0_LANGUAGE_ENFORCEMENT": force_lang_instruction,
                "1_TONE_AND_STYLE": (
                    f"Maintain a [{tone.upper()}] persona. Ref Style: '{sample_text}'. "
                    f"MUST WRITE IN SPOKEN {target_language.upper()}. "
                    "Use short sentences. No academic fluff like 'In conclusion'. "
                    "Use transitions like 'But wait', 'Here is the secret'."
                ),
                "2_ANTI_LAZY_MODE": (
                    f"CRITICAL: Target duration is {duration_str}. "
                    "DO NOT SUMMARIZE. Write the FULL verbatim script for every scene. "
                    "NO placeholders. NO empty strings."
                ),
                "3_NATURAL_PACING": (
                    "DO NOT use filler words like 'Umm', 'Ahh', 'Hmm' explicitly. "
                    "INSTEAD, use ellipsis (...) and dashes (-) to create natural pauses and hesitation. "
                    "Example: 'It's not just big... it's huge.' instead of 'It's umm big'."
                ),
                "4_RETENTION_MECHANICS": (
                    "Every 45-60s, insert a 'Pattern Interrupt' "
                    "(a controversial statement, a sudden question, or a weird visual change) "
                    "to reset viewer dopamine."
                ),
                "5_TRUTH_CONSTRAINT": truth_instruction,
                "6_EMOTIONAL_ARC": "Ensure the script moves through emotions: Curiosity -> Tension -> Relief -> Satisfaction.",
                "7_VISUAL_STORYTELLING": "Visual prompts must describe ACTION and CAMERA MOVEMENT (Zoom, Pan), not just static images.",
                "8_AUDIO_TECH": ssml_guide,  # Giữ lại hướng dẫn SSML của bạn
                #"9_SEO_INTEGRATION": f"Naturally weave the keyword '{task.get('key_vua', '')}' into the first 15s and the CTA."
            },

            # [4. CẤU TRÚC VIRAL - Xương sống nội dung]
            "VIRAL_DNA_SKELETON": {
                "Instruction": "Strictly follow this narrative arc:",
                "DNA_Content": spy_skeleton if spy_skeleton else "Use standard viral structure."
            },

            "VISUAL_CONTROLLER": {
                "Settings": {
                    "Art_Style": vis_style,
                    "Ratio": ratio_instruction,
                    "Camera_Work": "Dynamic (Zoom in, Pan left, Rack focus)",
                    "Character_Consistency": "Define 'character_profile' if using AI."
                },
                "Master_Instruction": (
                    "CRITICAL LANGUAGE RULE:\n"
                    "1. 'visual_prompt': MUST BE IN ENGLISH (for Stock/AI search), strictly following the '{vis_style}' style. Ratio: {ratio_instruction}.\n"
                    f"2. 'voice_text': MUST BE IN {target_language.upper()} (Native for audience).\n"
                    "Do NOT mix them. Do NOT translate visual prompts to native language."
                )
            },

            # [6. CEO NOTE - Chỉ đạo riêng]
            "CEO_SPECIAL_ORDER": custom_note,
            "SEO_MANDATES": {
                "keyword_insertion": "Main keyword MUST appear in Title, Description, and Script.",
                "hook_rule": "First 3 seconds must be shocking/engaging."
            },
            "CINEMATIC_INSTRUCTIONS": {
                "sfx": "Suggest Sound Effects (SFX) for every scene.",
                "highlights": "List 1-3 keywords to highlight in subtitles.",
                "pacing": "Average shot length 4–6 seconds."
            },

            # [7. CẤU TRÚC ĐẦU RA BẮT BUỘC]
            "MANDATORY_OUTPUT_JSON_STRUCTURE": output_structure
        }

        return json.dumps(prompt_json, indent=2, ensure_ascii=False)
    
    # --- [HÀM 1] GHI NHẬT KÝ ---
    def log_system(self, message):
        
        time_str = datetime.datetime.now().strftime("%H:%M:%S")
        full_msg = f"[{time_str}] [Tab 4] {message}"
        
        # 1. Bắn tín hiệu ra Main Window
        self.log_signal.emit(full_msg)
        
        # 2. In ra màn hình đen (để debug nếu cần)
        print(full_msg)
        #self.txt_system_log.append(f"[{time_str}] {message}")
        # Tự động cuộn xuống dưới cùng
        #self.txt_system_log.verticalScrollBar().setValue(self.txt_system_log.verticalScrollBar().maximum())

    # [CẬP NHẬT] HỦY TÁC VỤ (KHẨN CẤP & TRIỆT ĐỂ)

    # [HÀM MỚI] GẮN DỊCH VÀO TOOLTIP (HOVER LÀ THẤY VIỆT HÓA)
    def attach_translate_tooltip(self, widget, text):
        if not text: return
        
        # 1. Set Tooltip mặc định là text gốc (để xem ngay được)
        widget.setToolTip(f"{text}\n\n(⏳ Đang dịch tiếng Việt...)")
        
        # 2. Gọi thợ dịch chạy ngầm
        worker = TooltipTranslationWorker(widget, text)
        
        # Khi dịch xong -> Update lại Tooltip của widget đó
        worker.finished_signal.connect(lambda w, t: w.setToolTip(t))
        
        # Giữ tham chiếu để không bị Python xóa giữa chừng
        if not hasattr(self, 'tooltip_workers'): self.tooltip_workers = []
        self.tooltip_workers.append(worker)
        
        worker.start()

    def stop_selected_worker(self):
        # 1. Dựng cờ STOP để chặn các task đang xếp hàng (Queue)
        self.stop_requested = True
        
        # 2. Hủy các task đang chạy (Active Workers)
        killed_count = 0
        
        if hasattr(self, 'active_workers'):
            # Copy keys ra list để tránh lỗi "dictionary changed size during iteration"
            active_keys = list(self.active_workers.keys())
            
            for key in active_keys:
                # Chỉ hủy các worker thuộc dự án hiện tại
                if key.startswith(f"{self.current_project_index}_"):
                    worker = self.active_workers[key]
                    try:
                        worker.finished_signal.disconnect() # Ngắt kết nối để không báo Xong ảo
                        worker.terminate() # Giết tiến trình
                        worker.wait()      # Chờ chết hẳn
                    except: pass
                    
                    del self.active_workers[key]
                    
                    # Update UI thành "Đã dừng"
                    task_id = int(key.split('_')[1])
                    row_idx = self.find_row_by_task_id(task_id)
                    if row_idx != -1:
                        self.table_tasks.setItem(row_idx, 2, QTableWidgetItem("⛔ Đã dừng"))
                    
                    killed_count += 1

        self.log_system(f"🛑 STOP: Đã dựng cờ Hủy. Đã diệt {killed_count} tiến trình đang chạy.")
        QMessageBox.information(self, "Đã Hủy", "Đã kích hoạt phanh khẩn cấp!\n- Các bài đang chạy đã dừng.\n- Các bài xếp hàng sẽ bị hủy lệnh.")

    # [THAY THẾ HÀM import_json_file CŨ]
    def import_json_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Chọn file Keyword (.json)", "", "JSON Files (*.json);;All Files (*)")
        if not file_path: return

        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                content = f.read().strip()
                if not content: return
                data = json.loads(content)
            
            if not isinstance(data, list):
                QMessageBox.warning(self, "Lỗi Format", "File JSON phải bắt đầu bằng dấu ngoặc vuông []")
                return

            count_new = 0
            count_skip = 0
            
            for item in data:
                # 1. Lấy thông tin
                t = item.get("topic", "General")
                c = item.get("country", "Global")
                p = item.get("platform", "Multi")
                k = item.get("key_vua", "Imported Key").strip() # Xóa khoảng trắng thừa
                thumb = item.get("thumbnail_url", "")
                
                # 2. Định tuyến vào Dự án
                idx = self._find_or_create_project(t, c, p)
                current_tasks = self.projects[idx]["tasks"]
                
                # --- [MỚI] KIỂM TRA TRÙNG LẶP ---
                is_duplicate = False
                for existing_task in current_tasks:
                    if existing_task["key_vua"].strip() == k:
                        is_duplicate = True
                        break
                
                if is_duplicate:
                    count_skip += 1
                    continue # Bỏ qua, sang vòng lặp kế tiếp
                # -------------------------------

                # 3. Nếu không trùng thì thêm mới
                new_task = {
                    "id": len(current_tasks) + 1,
                    "key_vua": k,
                    "topic": t, "country": c, "platform": p,
                    "thumbnail_url": thumb,
                    "status": "Chờ viết", "script_content": "", "visual_content": ""
                }
                current_tasks.append(new_task)
                count_new += 1
                
                # Update con trỏ
                self.current_project_index = idx
            
            # 4. Lưu và Vẽ lại
            self.db.save_projects(self.projects)
            self.refresh_project_list()
            self.list_projects.setCurrentRow(self.current_project_index)
            self.refresh_task_table()
            
            self.log_system(f"📂 IMPORT: Đã nhập {count_new} key mới từ file (Bỏ qua {count_skip} trùng).")

            # Thông báo chi tiết hơn
            msg = f"Đã xử lý xong!\n\n✅ Thêm mới: {count_new} bài\n⏭️ Bỏ qua (Trùng): {count_skip} bài"
            QMessageBox.information(self, "Kết quả Nhập liệu", msg)

        except Exception as e:
            self.log_system(f"❌ LỖI IMPORT: {str(e)}")
            QMessageBox.critical(self, "Lỗi Đọc File", str(e))
    def load_sample_data_from_json(self):
        try:
            # Đường dẫn tương đối
            file_path = os.path.join("VEO_DB", "input_samples", "Vidu_Keyword.json")
            
            if not os.path.exists(file_path):
                # Nếu chưa có thư mục thì tạo mẫu luôn cho tiện test
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                sample_data = [
                    {"id": 101, "key_vua": "Bí ẩn Bermuda", "topic": "👽 Bí ẩn", "country": "VN", "platform": "Youtube", "status": "Chờ viết"}
                ]
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(sample_data, f, ensure_ascii=False, indent=2)
            
            # Đọc file
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Nạp vào RAM và Bảng
            self.all_tasks = data
            self.refresh_task_table() # Hàm này ngài đã có ở code cũ, nó sẽ vẽ lại bảng
            QMessageBox.information(self, "OK", f"Đã nạp {len(data)} nhiệm vụ mẫu!")
            
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Không đọc được file mẫu:\n{e}")

    # [CẬP NHẬT HÀM NÀY TRONG ContentTab]
    def add_new_project_dialog(self):
        # Gọi hộp thoại chọn chuẩn (Class vừa tạo ở Bước 1)
        dialog = NewProjectDialog(self)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Lấy dữ liệu chuẩn từ hộp thoại
            platform, country, topic = dialog.get_data()
            
            # Gọi bộ não định tuyến (nó sẽ tự lo việc tạo mới hay gộp)
            idx = self._find_or_create_project(topic, country, platform)
            
            # Focus vào dự án đó
            self.list_projects.setCurrentRow(idx)
            self.on_project_selected_from_list(None)
            
            QMessageBox.information(self, "Thành công", f"Đã thiết lập kênh:\n{self.projects[idx]['name']}")
    
            # [HÀM MỚI] TÌM DÒNG CHUẨN XÁC THEO ID
    def find_row_by_task_id(self, target_id):
        for r in range(self.table_tasks.rowCount()):
            try:
                item = self.table_tasks.item(r, 0) # Cột 0 là ID
                # So sánh ID trong bảng với ID cần tìm
                if item and int(item.text().strip()) == target_id:
                    return r # Trả về số dòng chính xác
            except: continue
        return -1

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # --- HEADER ---
        header = QHBoxLayout()
        lbl = QLabel("📝 CONTENT FACTORY (TRUNG TÂM SẢN XUẤT)")
        lbl.setObjectName("sectionTitleLabel")  # PR-5e: was inline 18px/bold/#00e6e6
        
        # [MỚI] Nút Khôi phục (Undo)
        btn_restore = QPushButton("↩️ KHÔI PHỤC (UNDO)")
        btn_restore.setToolTip("Quay lại trạng thái trước khi Xóa/Dọn dẹp gần nhất")
        apply_kind(btn_restore, "ai_magic")  # PR-5e: was inline #8e44ad
        btn_restore.clicked.connect(self.restore_last_backup) # Hàm này sẽ viết ở dưới

        btn_refresh = QPushButton("🔄 NẠP LẠI DATA")
        apply_kind(btn_refresh, "info")  # PR-5e: was inline #34495e
        btn_refresh.setToolTip("Click nếu bạn vừa xóa file database thủ công")
        btn_refresh.clicked.connect(self.hard_reload_data)

        btn_new = QPushButton("+ DỰ ÁN MỚI")
        apply_kind(btn_new, "success")  # PR-5e: was inline #27ae60
        btn_new.clicked.connect(self.add_new_project_dialog)

        header.addWidget(lbl); header.addStretch()
        header.addWidget(btn_restore)
        header.addWidget(btn_refresh); header.addWidget(btn_new)
        layout.addLayout(header)

        # --- SPLITTER CHIA 3 CỘT ---
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # ==================================================
        # CỘT 1: QUẢN LÝ DỰ ÁN (PROJECTS)
        # ==================================================
        panel_1 = QFrame(); l1 = QVBoxLayout(panel_1)
        l1.addWidget(QLabel("📂 QUẢN LÝ KÊNH"))
        
        self.list_projects = QListWidget()
        self.list_projects.itemClicked.connect(self.on_project_selected_from_list)
        self.list_projects.setStyleSheet("border: none; background: #252526;")
        self.list_projects.setWordWrap(True)
        self.list_projects.setSpacing(4)
        self.list_projects.setTextElideMode(Qt.TextElideMode.ElideNone)
        
        self.list_projects.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_projects.customContextMenuRequested.connect(self.show_project_context_menu)
        
        panel_1.setFixedWidth(250)
        l1.addWidget(self.list_projects)

        # ==================================================
        # CỘT 2: DANH SÁCH VIDEO & BỘ CHỈ HUY (TASKS & HQ)
        # ==================================================
        panel_2 = QFrame()
        l2_main = QVBoxLayout(panel_2); l2_main.setContentsMargins(0,0,0,0)
        panel_2.setFixedWidth(750)
        
        # Tạo Splitter Dọc
        splitter_v = QSplitter(Qt.Orientation.Vertical)
        splitter_v.setHandleWidth(8) 
        # Style cho tay cầm dễ nhìn hơn (màu xám nhạt khi rê chuột)
        splitter_v.setStyleSheet("""
            QSplitter::handle { background: #2d2d30; border: 1px solid #3e3e42; }
            QSplitter::handle:hover { background: #007acc; }
        """)

        # --- PHẦN 1: DANH SÁCH VIDEO (TABLE) ---
        container_table = QWidget()
        lt = QVBoxLayout(container_table); lt.setContentsMargins(0,0,0,0)
        lt.addWidget(QLabel("📋 DANH SÁCH VIDEO (TASKS)"))
        
        self.table_tasks = QTableWidget(0, 3)
        self.table_tasks.setHorizontalHeaderLabels(["ID", "Key Vua/Tiêu đề", "Trạng thái"])
        self.table_tasks.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_tasks.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_tasks.setWordWrap(True)
        self.table_tasks.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_tasks.verticalHeader().setVisible(False)
        self.table_tasks.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_tasks.setStyleSheet("border: none;")
        self.table_tasks.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_tasks.customContextMenuRequested.connect(self.show_task_context_menu)
        self.table_tasks.itemClicked.connect(self.on_task_selected)
        
        lt.addWidget(self.table_tasks)
        
        # [QUAN TRỌNG] Thiết lập chiều cao tối thiểu để không bị kéo mất
        container_table.setMinimumHeight(150) 
        splitter_v.addWidget(container_table)

        # --- PHẦN 2: BỘ CHỈ HUY KÊNH (HQ) ---
        self.channel_panel = self._create_channel_hq()
        container_hq = QWidget(); lhq = QVBoxLayout(container_hq); lhq.setContentsMargins(0,0,0,0)
        lhq.addWidget(self.channel_panel)
        
        # [QUAN TRỌNG] Chiều cao tối thiểu cho HQ
        container_hq.setMinimumHeight(300)
        container_hq.setMaximumHeight(300)
        splitter_v.addWidget(container_hq)

        # --- PHẦN 3: BẢNG ĐIỀU KHIỂN (CONTROL) ---
        control_panel = self._create_control_panel()
        container_ctrl = QWidget(); lctrl = QVBoxLayout(container_ctrl); lctrl.setContentsMargins(0,0,0,0)
        lctrl.addWidget(control_panel)
        
        # [QUAN TRỌNG] Chiều cao tối thiểu cho Control
        container_ctrl.setMinimumHeight(320)
        container_ctrl.setMaximumHeight(320)
        splitter_v.addWidget(container_ctrl)

        # --- CẤU HÌNH SPLITTER ---
        # Không cho phép kéo "tắt" (Collapsible = False)
        splitter_v.setCollapsible(0, False)
        splitter_v.setCollapsible(1, False)
        splitter_v.setCollapsible(2, False)

        # 2. Thiết lập kích thước tối thiểu (Min Size) để không bị bóp nghẹt
        # Quan trọng: Phải set MinHeight cho Widget con bên trong splitter
        #container_table.setMinimumHeight(150) # Bảng video luôn cao ít nhất 150px
        #container_hq.setMinimumHeight(220)    # HQ luôn cao ít nhất 220px
        #container_ctrl.setMinimumHeight(280)  # Control luôn cao ít nhất 280px

        # Tỷ lệ mặc định (Bảng to nhất)
        splitter_v.setStretchFactor(0, 4)
        splitter_v.setStretchFactor(1, 6)
        splitter_v.setStretchFactor(2, 3)

        l2_main.addWidget(splitter_v)
        l2 = l2_main

        # ==================================================
        # CỘT 3: KHÔNG GIAN BIÊN TẬP (EDITOR)
        # ==================================================
        panel_3 = QFrame(); l3 = QVBoxLayout(panel_3); l3.setContentsMargins(0,0,0,0)
        
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setObjectName("contentEditorScroll")  # PR-5e: was inline border:none + bg #2d2d30
        scroll_content = QWidget(); self.scroll_layout = QVBoxLayout(scroll_content)
        self.scroll_layout.setSpacing(15); self.scroll_layout.setContentsMargins(10, 10, 10, 10)
        
        # 1. KỊCH BẢN
        grp_script = QGroupBox("📜 KỊCH BẢN & LỜI THOẠI")
        apply_accent(grp_script, "amber")  # PR-5e: was inline #f1c40f border
        ls = QVBoxLayout(grp_script); ls.setSpacing(10)
        
        self.box_script_board = self._create_input_box("KỊCH BẢN PHÂN CẢNH (SCENES JSON)", "Dữ liệu cấu trúc...", 120)
        ls.addWidget(self.box_script_board)

        h_voice = QHBoxLayout()
        self.box_target = self._create_input_box("LỜI BÌNH (VOICEOVER)", "Lời đọc chính...", 120)
        self.box_vn = self._create_input_box("BẢN DỊCH VIỆT", "Tham khảo...", 120)
        h_voice.addWidget(self.box_target); h_voice.addWidget(self.box_vn)
        ls.addLayout(h_voice)
        self.scroll_layout.addWidget(grp_script)

        # 2. METADATA
        grp_meta = QGroupBox("🚀 SEO & AUTO-UPLOAD")
        apply_accent(grp_meta, "red")  # PR-5e: was inline #e74c3c border
        lm = QVBoxLayout(grp_meta); lm.setSpacing(10)
        
        self.box_title = self._create_input_box("TIÊU ĐỀ (TITLE)", "Tiêu đề video...", 50)
        lm.addWidget(self.box_title)
        
        hm = QHBoxLayout()
        self.box_desc = self._create_input_box("MÔ TẢ (DESCRIPTION)", "Nội dung mô tả...", 100)
        self.box_tags = self._create_input_box("THẺ (TAGS)", "tag1, tag2, tag3...", 100)
        hm.addWidget(self.box_desc, stretch=2); hm.addWidget(self.box_tags, stretch=1)
        lm.addLayout(hm)
        self.scroll_layout.addWidget(grp_meta)

        # 3. VISUALS & MUSIC
        grp_vis = QGroupBox("🎨 VISUALS & MUSIC")
        apply_accent(grp_vis, "emerald")  # PR-5e: was inline #2ecc71 border
        lv = QVBoxLayout(grp_vis); lv.setSpacing(10)
        
        self.box_visual = self._create_input_box("PROMPT VẼ THUMBNAIL / ẢNH", "Prompt cho AI vẽ...", 70)
        lv.addWidget(self.box_visual)
        
        vm = QHBoxLayout()
        self.box_thumb_text = self._create_input_box("TEXT TRÊN THUMBNAIL", "Text overlay...", 50)
        self.box_music = self._create_input_box("TỪ KHÓA TÌM NHẠC (YOUTUBE LIB)", "VD: Cinematic Sad Piano...", 50)
        vm.addWidget(self.box_thumb_text); vm.addWidget(self.box_music)
        lv.addLayout(vm)
        self.scroll_layout.addWidget(grp_vis)

        scroll.setWidget(scroll_content)
        l3.addWidget(scroll)

        # 4. ACTION BAR (NÚT LƯU ĐẸP)
        action_bar = QFrame()
        action_bar.setObjectName("contentActionBar")  # PR-5e: was inline bg #252526 + border-top
        action_layout = QHBoxLayout(action_bar)
        action_layout.setContentsMargins(10, 10, 10, 10); action_layout.setSpacing(10)

        btn_style = "QPushButton { border: none; border-radius: 4px; padding: 0 15px; font-weight: bold; font-size: 13px; height: 40px; }"
        
        btn_save = QPushButton("💾 LƯU BÀI NÀY")
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.setMinimumHeight(40)  # was baked into btn_style
        apply_kind(btn_save, "warning")  # PR-5e: was inline #e67e22
        btn_save.clicked.connect(self.on_save_media)

        btn_save_batch = QPushButton("📦 LƯU TẤT CẢ (ĐÃ XONG)")
        btn_save_batch.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save_batch.setMinimumHeight(40)
        apply_kind(btn_save_batch, "success")  # PR-5e: was inline #27ae60
        btn_save_batch.clicked.connect(self.on_save_media_batch)

        action_layout.addWidget(btn_save, stretch=1)
        action_layout.addWidget(btn_save_batch, stretch=1)
        l3.addWidget(action_bar)

        # GỘP VÀO SPLITTER
        self.splitter.addWidget(panel_1)
        self.splitter.addWidget(panel_2)
        self.splitter.addWidget(panel_3)
        
        # Tỷ lệ: 1 (List) : 3 (Tasks) : 5 (Editor)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 3)
        self.splitter.setStretchFactor(2, 5)
        
        layout.addWidget(self.splitter)
        
        # Init Data
        self.refresh_task_table()
        QTimer.singleShot(100, self.update_prompt_preview)

    # [HÀM MỚI] TẠO ĐIỂM KHÔI PHỤC (SNAPSHOT)
    def create_backup(self):
        try:
            # Lưu trạng thái hiện tại ra file backup
            self.db.save_projects(self.projects, filename="projects_backup.json")
            print("🛡️ Auto-Backup: Đã tạo điểm khôi phục.")
        except Exception as e:
            print(f"Lỗi Backup: {e}")

    # [HÀM MỚI] KHÔI PHỤC DỮ LIỆU TỪ BACKUP
    def restore_last_backup(self):
        backup_path = os.path.join(self.db.db_folder, "projects_backup.json")
        if not os.path.exists(backup_path):
            QMessageBox.warning(self, "Không thể khôi phục", "Chưa có hành động xóa nào để khôi phục (Hoặc file backup không tồn tại).")
            return

        confirm = QMessageBox.question(self, "Xác nhận Khôi phục", 
                                       "Bạn có chắc muốn quay lại trạng thái trước khi Xóa/Dọn dẹp gần nhất?\n(Những thay đổi sau đó sẽ bị mất).",
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if confirm == QMessageBox.StandardButton.No: return

        try:
            # 1. Load file backup
            with open(backup_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # 2. Ghi đè vào file chính
            self.db.save_projects(data)
            
            # 3. Nạp lại RAM
            self.projects = data
            self.refresh_project_list()
            self.table_tasks.setRowCount(0)
            self.refresh_task_table()
            
            QMessageBox.information(self, "Thành công", "✅ Đã khôi phục dữ liệu thành công!")
            
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Khôi phục thất bại: {e}")

    def _create_text_area(self, placeholder, height):
        # 1. Tạo vật chứa (Container)
        container = QWidget()
        l = QVBoxLayout(container)
        l.setContentsMargins(0,0,0,0)
        l.setSpacing(2)
        
        # 2. Tạo Toolbar (Nút Copy)
        tb = QFrame()
        tb.setStyleSheet("background: #444; border-radius: 2px;")
        ltb = QHBoxLayout(tb)
        ltb.setContentsMargins(5,2,5,2)
        ltb.addStretch()
        
        btn_copy = QPushButton("📋 Copy")
        btn_copy.setFixedSize(50, 20)
        btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copy.setStyleSheet("border: none; color: white; font-size: 15px;")
        ltb.addWidget(btn_copy)
        
        # 3. Tạo ô nhập liệu (TextEdit)
        txt = QTextEdit()
        txt.setPlaceholderText(placeholder)
        if height: 
            txt.setMinimumHeight(height)
            # Giới hạn chiều cao tối đa nếu ô nhỏ, để scroll hoạt động tốt
            txt.setMaximumHeight(height if height < 150 else 16777215)
        
        # 4. Kết nối nút copy
        btn_copy.clicked.connect(lambda: QApplication.clipboard().setText(txt.toPlainText()))

        # 5. Đóng gói vào Container
        l.addWidget(tb)
        l.addWidget(txt)
        
        # --- QUAN TRỌNG: GÁN TEXT EDIT VÀO CONTAINER ĐỂ DÙNG SAU ---
        container.text_edit = txt 
        
        # --- QUAN TRỌNG: TRẢ VỀ CONTAINER (CHA) ĐỂ NÓ KHÔNG BỊ XÓA ---
        return container

    def _apply_style(self):
        # Style chung cho toàn bộ tab
        self.setStyleSheet("""
            QWidget { background-color: #121212; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; }
            
            /* Style cho List và Table */
            QListWidget, QTableWidget { background: #1e1e1e; border: 1px solid #333; border-radius: 4px; }
            QListWidget::item, QTableWidget::item { padding: 8px; }
            QListWidget::item:selected, QTableWidget::item:selected { background: #007acc; color: white; }
            
            /* Style cho các ô nhập liệu */
            QTextEdit, QLineEdit, QComboBox { background: #252526; border: 1px solid #444; border-radius: 3px; padding: 5px; color: #eee; }
            QComboBox::drop-down { border: none; }
            
            /* --- [QUAN TRỌNG] SỬA LỖI TIÊU ĐỀ BỊ KHUẤT --- */
            QGroupBox { margin-top: 15px; font-size: 12px; }
            QGroupBox::title { 
                subcontrol-origin: margin; left: 10px; padding: 0 5px 5px 5px; /* Thêm padding dưới để không bị cắt chữ */
            }
        """)

    def copy_to_clipboard(self, text):
        QApplication.clipboard().setText(text)
        QMessageBox.information(self, "Đã Copy", "Đã copy nội dung vào bộ nhớ tạm!")

    # --- GIỮ NGUYÊN LOGIC CŨ ---
    def add_project_item(self, name, info):
        item = QListWidgetItem(f"{name}\n   └─ {info}")
        item.setFont(QFont("Segoe UI", 11))
        self.list_projects.addItem(item)
    
    def on_project_selected(self, item):
        project_name = item.text().split("\n")[0]
        self.lbl_current_project.setText(f"Dự án: {project_name}")
        self.refresh_task_table(project_name)

    # [CẬP NHẬT] Vẽ lại List Kênh với Đèn Báo Hiệu (Traffic Lights)
    def refresh_project_list(self):
        # Lưu lại vị trí đang chọn để không bị nhảy khi refresh
        current_row = self.list_projects.currentRow()        
        self.list_projects.clear()
        
        for p in self.projects:
            tasks = p.get("tasks", [])
            total = len(tasks)
            
            # 1. Thống kê chỉ số (Metrics)
            c_green = 0 # Xanh: Xong, Ready
            c_yellow = 0 # Đang viết / Đang chạy
            c_red = 0   # Đỏ: Chờ, Lỗi, Đang viết
            
            for t in tasks:
                st = t.get("status", "")
                # Các trạng thái coi là "An toàn/Xong"
                if "Hoàn thành" in st or "Xong" in st or "Ready" in st or "Sẵn sàng" in st:
                    c_green += 1
                elif "Đang" in st or "Writing" in st:
                    c_yellow += 1
                else:
                    c_red += 1
            
            # Tạo chuỗi tín hiệu: 🔴2 🟡1 🟢5
            # 2. Tạo chuỗi tín hiệu (Visual Signal)
            signal_str = ""
            if total == 0:
                signal_str = "⚪ (Trống)"
            else:
                # Logic hiển thị thông minh:
                # Luôn hiện cả 2 số để Ngài nắm được tỉ lệ hoàn thành
                if c_red > 0:    signal_str += f"🔴{c_red} "
                if c_yellow > 0: signal_str += f"🟡{c_yellow} "
                if c_green > 0:  signal_str += f"🟢{c_green} "
                
                # Nếu kênh đã xong 100% -> Thêm dấu tích cho sướng mắt
                if c_red == 0 and c_green > 0:
                    signal_str += "✅ FULL"

            # 3. Hiển thị lên UI
            # Dòng 1: Tên kênh
            # Dòng 2: Tín hiệu đèn
            display_text = f"📂 {p['name']}\n   └─ {signal_str}"
            
            item = QListWidgetItem(display_text)
            item.setFont(QFont("Segoe UI", 10))
            
            # Tooltip để di chuột vào xem chi tiết nếu tên quá dài
            item.setToolTip(f"Kênh: {p['name']}\nTổng: {total}\nChưa làm: {c_red}\nĐang làm: {c_yellow}\nĐã xong: {c_green}")
            self.list_projects.addItem(item)
            
        # Khôi phục vị trí chọn cũ (để trải nghiệm mượt mà)
        if current_row >= 0 and current_row < self.list_projects.count():
            self.list_projects.setCurrentRow(current_row)
        elif self.current_project_index >= 0 and self.current_project_index < self.list_projects.count():
            self.list_projects.setCurrentRow(self.current_project_index)

    # Hàm xử lý khi bấm vào List bên trái

    # 1. Tự động điền Info kênh vào ô (CẬP NHẬT HIỂN THỊ BRANDING)
    def update_channel_ui(self):
        if self.current_project_index < 0: return
        proj = self.projects[self.current_project_index]
        profile = proj.get("channel_profile", {})
                
        # Lấy thông tin Visual & Brand
        visuals = profile.get("visual_identity", {})
        brand = profile.get("brand_identity", {})

        # --- BƯỚC 1: KHAI BÁO BIẾN (Lấy dữ liệu ra đĩa trước) ---
        name = profile.get("channel_name", "")
        handle = profile.get("channel_handle", "")
        desc = profile.get("description", "")
        
        logo_info = visuals.get("logo_prompt", "")
        banner = visuals.get("banner_prompt", "")
        style = profile.get("visual_style_preset", "")

        # --- BƯỚC 2: XỬ LÝ HIỂN THỊ (Logic gộp text) ---
        # Riêng ô Logo, ta hiển thị thêm thông tin Brand nếu có (cho thợ design đọc)
        display_logo = logo_info
        if brand:
             display_logo += f"\n[BRAND SYSTEM]\n🎨 Colors: {brand.get('color_palette', '')}\n🎭 Mood: {brand.get('mood', '')}\n🏛️ Style: {brand.get('archetype', '')}"

        # --- BƯỚC 3: ĐIỀN VÀO GIAO DIỆN (Set Text) ---
        self.txt_logo_prompt.setText(display_logo)
        self.txt_banner_prompt.setText(banner)
        self.txt_visual_style.setText(style)
        self.txt_channel_name.setText(name)
        self.txt_channel_handle.setText(handle)
        self.txt_channel_desc.setText(desc)

        # --- BƯỚC 4: KÍCH HOẠT DỊCH TOOLTIP ---
        # Lưu ý: Truyền biến gốc (logo_info) để dịch cho chuẩn, thay vì truyền cái display_logo dài ngoằng
        self.attach_translate_tooltip(self.txt_channel_name, name)
        self.attach_translate_tooltip(self.txt_channel_desc, desc)
        self.attach_translate_tooltip(self.txt_logo_prompt, logo_info) 
        self.attach_translate_tooltip(self.txt_banner_prompt, banner)
        self.attach_translate_tooltip(self.txt_visual_style, style)

    # [HÀM MỚI] XÓA TRẮNG TOÀN BỘ GIAO DIỆN (RESET UI)
    def reset_ui_to_blank(self):
        # 1. Xóa Bộ Chỉ Huy (HQ)
        self.txt_channel_name.clear()
        self.txt_channel_handle.clear()
        self.txt_channel_desc.clear()
        self.txt_logo_prompt.clear()
        self.txt_banner_prompt.clear()
        self.txt_visual_style.clear()
        self.txt_skeleton_preview.clear()
        self.txt_key_vua_strategy.clear()
        
        # 2. Xóa Bảng Video
        self.table_tasks.setRowCount(0)
        
        # 3. Xóa Editor (Bên phải)
        self.distribute_data_to_boxes("") 
        
        # 4. Reset các ComboBox về mặc định (nếu cần)
        self.cb_topic.setCurrentIndex(0)

    # [FIX] ĐỒNG BỘ GIAO DIỆN KHI CHỌN DỰ ÁN
    def on_project_selected_from_list(self, item):
        # 1. Cập nhật Index hiện tại
        self.current_project_index = self.list_projects.currentRow()
        
        # 2. Làm mới bảng Video và UI Branding
        self.refresh_task_table()
        self.update_channel_ui()

        # 3. [QUAN TRỌNG] ĐỒNG BỘ CONTROL PANEL THEO DỰ ÁN
        # Để Prompt Preview hiển thị đúng thông tin của dự án này
        if self.current_project_index >= 0:
            proj = self.projects[self.current_project_index]
            
            # Tạm khóa tín hiệu để không bị giật
            self.cb_topic.blockSignals(True)
            self.cb_country.blockSignals(True)
            self.cb_platform.blockSignals(True)

            try:
                # A. Sync Topic
                topic = proj.get("topic", "General")
                # Tìm gần đúng
                t_idx = self.cb_topic.findText(topic, Qt.MatchFlag.MatchContains)
                if t_idx >= 0: self.cb_topic.setCurrentIndex(t_idx)

                # B. Sync Platform
                platform = proj.get("platform", "Youtube")
                p_idx = self.cb_platform.findText(platform, Qt.MatchFlag.MatchContains)
                if p_idx >= 0: self.cb_platform.setCurrentIndex(p_idx)

                # C. Sync Country (Logic thông minh tìm theo Code)
                raw_country = proj.get("country", "Global")
                c_idx = -1
                
                # C1. Thử tìm theo mã trong ngoặc (VD: (US))
                import re
                match = re.search(r'\(([A-Za-z]{2})\)', raw_country)
                if match:
                    code = match.group(1).upper()
                    # Quét combobox tìm dòng chứa code đó
                    for i in range(self.cb_country.count()):
                        if f"({code})" in self.cb_country.itemText(i):
                            c_idx = i; break
                
                # C2. Nếu không thấy, tìm theo tên
                if c_idx == -1:
                    clean_name = raw_country.split('~')[0].strip()
                    c_idx = self.cb_country.findText(clean_name, Qt.MatchFlag.MatchContains)

                if c_idx >= 0: self.cb_country.setCurrentIndex(c_idx)

            except Exception as e:
                print(f"Lỗi đồng bộ UI Project: {e}")

            # Mở lại tín hiệu
            self.cb_topic.blockSignals(False)
            self.cb_country.blockSignals(False)
            self.cb_platform.blockSignals(False)

            # 4. [FIX CHÍNH] KÍCH HOẠT TẠO PROMPT PREVIEW NGAY LẬP TỨC
            # Tự động chọn Tone và Độ dài phù hợp luôn
            self.auto_select_tone_by_topic() 
            self.auto_select_duration()
            
            # Gọi hàm vẽ lại JSON Preview
            self.update_prompt_preview()

    # 3. Hàm gọi Worker thiết kế kênh (Manual & Auto)
    def auto_generate_channel_info_manual(self):
        if self.current_project_index < 0: 
            QMessageBox.warning(self, "Chưa chọn kênh", "Vui lòng chọn 1 dự án bên trái!")
            return
        
        # Kiểm tra xem đã có thông tin chưa
        proj = self.projects[self.current_project_index]
        profile = proj.get("channel_profile", {})
        existing_name = profile.get("channel_name", "")
        
        if existing_name:
            confirm = QMessageBox.question(
                self, 
                "Xác nhận thiết kế lại", 
                f"Kênh này đã có tên: '{existing_name}'\n\nNgài có chắc muốn AI xóa cũ và thiết kế lại từ đầu không?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if confirm == QMessageBox.StandardButton.No: return

        self.start_channel_design_worker(self.current_project_index)

    # [HÀM DUY NHẤT] KÍCH HOẠT THIẾT KẾ KÊNH (AUTO DESIGN)
    def start_channel_design_worker(self, idx):
        # 1. Lấy dữ liệu dự án
        proj = self.projects[idx]
        topic = proj.get("topic", "General")
        country = proj.get("country", "Global")
        p_platform = proj.get("platform", "Youtube")
        
        # 2. Gọi Worker (Đúng tên Class và tham số)
        self.design_worker = ChannelDesignerWorker(topic, country, p_platform)
        
        # 3. Hàm xử lý kết quả
        def on_done(data):
            if not data:
                if self.current_project_index == idx:
                    QMessageBox.warning(self, "Lỗi", "AI không trả về kết quả thiết kế. Vui lòng thử lại!")
                return

            # A. Cập nhật vào RAM & Database
            if "channel_profile" not in self.projects[idx]:
                self.projects[idx]["channel_profile"] = {}
                
            # Merge dữ liệu mới vào dữ liệu cũ (để không mất Visual Style nếu có)
            self.projects[idx]["channel_profile"].update(data)
            
            # Lưu Database
            self.db.save_projects(self.projects)
            
            # B. Lưu ra File cứng (Cho Tool Media dùng sau này)
            try:
                p_plat = self._sanitize_filename(p_platform)
                p_coun = self._sanitize_filename(country.split('~')[0])
                p_top = self._sanitize_filename(topic)
                
                # Tạo đường dẫn gốc của Kênh
                channel_path = os.path.join("VEO_DB", p_plat, p_coun, p_top)
                if not os.path.exists(channel_path): os.makedirs(channel_path)
                
                # Ghi file JSON
                with open(os.path.join(channel_path, "channel_profile.json"), "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"Lỗi lưu file channel: {e}")

            # C. Update Giao diện (Nếu đang xem dự án này)
            if self.current_project_index == idx:
                self.update_channel_ui() # Cập nhật các ô input
                self.log_system(f"✨ BRANDING: Hoàn tất thiết kế cho '{data.get('channel_name')}'")
                
                # Chỉ hiện popup nếu Tab đang mở (để không làm phiền nếu chạy ngầm)
                if self.isVisible():
                    QMessageBox.information(self, "Xong", "✨ Đã thiết kế xong bộ nhận diện kênh!\n(Dữ liệu đã được lưu).")

        # Kết nối tín hiệu
        self.design_worker.finished_signal.connect(on_done)
        self.design_worker.start()
        
        # Thông báo bắt đầu
        if self.isVisible():
            self.log_system(f"🎨 AUTO-DESIGN: Đang bắt đầu thiết kế kênh '{topic}'...")

    # 4. Hàm BÀO KEY (Idea Expansion) - [NÂNG CẤP: KẾ THỪA DNA]
    def run_idea_expansion(self):
        if self.current_project_index < 0: return
        
        # 1. Xác định bài gốc (Source Task)
        current_row = self.table_tasks.currentRow()
        tasks = self.projects[self.current_project_index]["tasks"]
        source_task = None
        
        # Lấy bài đang chọn làm bài mẫu
        if current_row >= 0:
            try:
                task_id = int(self.table_tasks.item(current_row, 0).text())
                source_task = next((t for t in tasks if t["id"] == task_id), None)
            except: pass
            
        # Nếu không chọn bài nào, lấy bài đầu tiên làm mẫu (Fallback)
        if not source_task and tasks:
            source_task = tasks[0]
            
        if not source_task:
            QMessageBox.warning(self, "Thiếu Key", "Vui lòng chọn 1 bài có Key Vua để bào!")
            return
            
        root_key = source_task.get("key_vua", "")
        if not root_key:
            QMessageBox.warning(self, "Lỗi", "Bài gốc không có Key Vua!")
            return

        # 2. Hỏi xác nhận
        qty = self.spin_scale_qty.value()
        confirm = QMessageBox.question(self, "Bào Key", 
                                     f"AI sẽ tạo {qty} ý tưởng mới từ key: '{root_key}'\n\n"
                                     f"🧬 Kế thừa DNA: {len(source_task.get('spy_skeleton', '')) > 0}\n"
                                     f"🎨 Kế thừa Style: {source_task.get('visual_style_override', 'Mặc định')}\n\n"
                                     f"Triển khai ngay?", 
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if confirm == QMessageBox.StandardButton.No: return

        # 3. Gọi Worker tạo tiêu đề
        proj = self.projects[self.current_project_index]
        # Lấy duration từ ComboBox hiện tại
        current_dur = self.cb_duration.currentText()
        self.idea_worker = IdeaExpansionWorker(proj["topic"], proj["country"], root_key, qty, current_dur)
        
        self.table_tasks.setEnabled(False) # Khóa bảng tạm thời
        
        # Hàm xử lý khi có Key mới về
        def on_ideas_ready(titles):
            self.table_tasks.setEnabled(True)
            if not titles:
                QMessageBox.warning(self, "Lỗi", "AI không trả về ý tưởng nào.")
                return
            
            count_add = 0
            for t in titles:
                if not t: continue
                
                # --- [LOGIC QUAN TRỌNG NHẤT: DI TRUYỀN GEN] ---
                new_task = {
                    "id": len(tasks) + 1,
                    "key_vua": t, # Key mới do AI nghĩ ra
                    "title": t,   # Tạm lấy Key làm Tiêu đề luôn (sau này sửa sau)
                    "topic": proj["topic"],
                    "country": proj["country"],
                    "platform": proj["platform"],
                    "status": "Chờ viết",
                    "script_content": "",
                    
                    # === [COPY GEN TỪ BÀI MẸ] ===
                    # 1. Copy Kịch bản khung (DNA)
                    "spy_skeleton": source_task.get("spy_skeleton", ""),
                    
                    # 2. Copy Phong cách hình ảnh
                    "visual_style_override": source_task.get("visual_style_override", ""),
                    
                    # 3. Copy Prompt Thumb (nếu có)
                    "visual_content_prompt": source_task.get("visual_content_prompt", ""),
                    
                    # 4. Copy Link Thumb gốc (để tham khảo style)
                    "thumbnail_url": source_task.get("thumbnail_url", "")
                }
                # ---------------------------------------------

                tasks.append(new_task)
                count_add += 1
                
            self.db.save_projects(self.projects)
            self.refresh_task_table()
            
            # Thông báo kết quả
            QMessageBox.information(self, "Thành công", 
                                    f"✅ Đã nhân bản {count_add} video mới!\n"
                                    f"🧬 Đã kế thừa DNA & Visual Style từ bài gốc.")

        self.idea_worker.finished_signal.connect(on_ideas_ready)
        self.idea_worker.start()

    # Hàm vẽ lại Bảng bên phải (Cột 2)
    # [THAY THẾ HÀM refresh_task_table CŨ]
    def refresh_task_table(self):
        self.table_tasks.setRowCount(0)
        
        # Nếu chưa chọn dự án hoặc danh sách rỗng -> Dừng
        if self.current_project_index < 0 or self.current_project_index >= len(self.projects): 
            return

        current_tasks = self.projects[self.current_project_index]["tasks"]
        
        for i, task in enumerate(current_tasks):
            self.table_tasks.insertRow(i)
            
            # Cột ID: Căn giữa cho đẹp
            item_id = QTableWidgetItem(str(task["id"]))
            item_id.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table_tasks.setItem(i, 0, item_id)
            
            # Cột Key Vua
            # Cột Key Vua / Tiêu đề
            # Logic: Ưu tiên hiện Tiêu đề (nếu AI đã viết), nếu chưa thì hiện Key Vua
            display_text = task.get("title") if task.get("title") else task.get("key_vua")
            
            # Tạo Item
            item_text = QTableWidgetItem(str(display_text))
            
            # Nếu là Tiêu đề mới (khác Key vua) -> Tô màu cam nhạt cho dễ nhận biết
            if task.get("title") and task.get("title") != task.get("key_vua"):
                item_text.setForeground(QColor("#ff9f43")) # Màu cam
                # [MỚI] Hiển thị Chiến thuật trong Tooltip
                intent = task.get("_temp_intent", "Unknown Strategy")
                item_text.setToolTip(f"Chiến thuật: {intent}\nKey gốc: {task.get('key_vua')}")

            self.table_tasks.setItem(i, 1, item_text)
            
            # --- [FIX QUAN TRỌNG] KIỂM TRA WORKER ĐANG CHẠY NGẦM ---
            # Tạo khóa worker để kiểm tra xem bài này có đang được AI viết không
            worker_key = f"{self.current_project_index}_{task['id']}"
            is_running_background = hasattr(self, 'active_workers') and worker_key in self.active_workers

            # Cột Trạng thái (Tô màu & Icon)
            st = str(task["status"])
            item_status = QTableWidgetItem(st)

            if is_running_background:
                # Nếu đang chạy ngầm -> Ưu tiên hiện Đang viết (Bất chấp DB lưu gì)
                item_status.setText("⏳ Đang chạy ngầm...")
                item_status.setForeground(QColor("#3498db")) # Màu xanh dương
            else:
                if "Chờ viết" in st:
                    item_status.setText("🔴 Chờ viết")
                    item_status.setForeground(QColor("#e74c3c")) # Đỏ
                elif "Đang" in st:
                    item_status.setText("🟡 Đang viết...")
                    item_status.setForeground(QColor("#f1c40f")) # Vàng
                elif "Hoàn thành" in st or "Xong" in st:
                    item_status.setText("🟢 Hoàn thành")
                    item_status.setForeground(QColor("#2ecc71")) # Xanh lá
                elif "Text Thô" in st:
                    item_status.setText("⚠️ Text Thô (Check)")
                    item_status.setForeground(QColor("#d35400")) # Cam đậm
            
            # Căn giữa trạng thái
            item_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table_tasks.setItem(i, 2, item_status)

    def on_task_selected(self, item):
        row = item.row()
        try:
            # 1. Lấy bài viết đang chọn
            task_id = int(self.table_tasks.item(row, 0).text())
            tasks = self.projects[self.current_project_index]["tasks"]
            t = next((x for x in tasks if x["id"] == task_id), None)
            
            if t:
                # --- A. ĐỒNG BỘ GIAO DIỆN (SYNC UI) ---
                # Chặn tín hiệu để điền dữ liệu cho êm, tránh trigger các hàm auto không mong muốn khi đang set data
                self.cb_topic.blockSignals(True)
                self.cb_country.blockSignals(True)
                self.cb_platform.blockSignals(True)
                
                # [MỚI] Hiển thị Key Vua
                key_val = t.get("key_vua", "")
                self.txt_key_vua_strategy.setText(key_val)
                self.attach_translate_tooltip(self.txt_key_vua_strategy, key_val) # <--- THÊM DÒNG NÀY
                
                # 1. Xử lý Topic
                raw_topic = t.get("topic", "")
                idx_topic = self.cb_topic.findText(raw_topic, Qt.MatchFlag.MatchContains)
                
                # Nếu tìm không thấy (do lệch tiếng Anh/Việt), ta dùng "Chiêu cuối": Map thủ công
                if idx_topic == -1:
                    topic_map = {
                        "Mystery": "Bí ẩn", "Horror": "Ma", "Ghost": "Ma", 
                        "Kids": "Kids", "Funny": "Funny", "Pet": "Thú cưng",
                        "Crypto": "Crypto", "Finance": "Tài chính",
                        "Fact": "Sự thật", "News": "Sự thật",
                        "History": "Lịch sử", "War": "Chiến tranh"
                    }
                    for key, val in topic_map.items():
                        if key in raw_topic:
                            idx_topic = self.cb_topic.findText(val, Qt.MatchFlag.MatchContains)
                            break
                
                if idx_topic >= 0: self.cb_topic.setCurrentIndex(idx_topic)
                
                # 2. XỬ LÝ COUNTRY (QUỐC GIA) - LOGIC TÌM MÃ CODE (V2.0)
                raw_country = t.get("country", "")
                
                # Bước 1: Thử tách mã code trong ngoặc đơn. 
                # Ví dụ: Input là "Nga (Ru) ~$0.8..." -> Lấy được chữ "RU"
                # Ví dụ: Input là "Sing (Sg)..." -> Lấy được chữ "SG"
                import re
                match = re.search(r'\(([A-Za-z]{2})\)', raw_country)
                target_code = match.group(1).upper() if match else ""
                
                # Nếu không có ngoặc, nhưng chuỗi chỉ có 2 ký tự (VD: "US") -> Lấy luôn
                if not target_code and len(raw_country.strip()) == 2:
                    target_code = raw_country.strip().upper()

                idx_country = -1
                
                # Bước 2: Quét danh sách ComboBox để tìm dòng nào chứa mã đó
                # Cách này chính xác 100%, không bao giờ nhầm Nga (Ru) sang Singapore (Sg)
                if target_code:
                    for i in range(self.cb_country.count()):
                        item_text = self.cb_country.itemText(i)
                        # Tìm mã "(Ru)" trong dòng text của ComboBox
                        if f"({target_code})" in item_text:
                            idx_country = i
                            break
                
                # Bước 3: Nếu không tìm thấy theo Code, mới tìm theo tên text (Fallback)
                if idx_country == -1:
                    clean_name = raw_country.split('~')[0].strip()
                    idx_country = self.cb_country.findText(clean_name, Qt.MatchFlag.MatchContains)

                # Set giá trị nếu tìm thấy
                if idx_country >= 0: 
                    self.cb_country.setCurrentIndex(idx_country)
                else:
                    pass
                
                # 3. Xử lý Platform
                idx_plat = self.cb_platform.findText(t.get("platform", ""), Qt.MatchFlag.MatchContains)
                if idx_plat >= 0: self.cb_platform.setCurrentIndex(idx_plat)
                
                # Mở lại tín hiệu sau khi đã set xong dữ liệu cơ bản
                self.cb_topic.blockSignals(False)
                self.cb_country.blockSignals(False)
                self.cb_platform.blockSignals(False)

                # --- B. KÍCH HOẠT CHỌN TONE & DURATION TỰ ĐỘNG ---
                # Gọi các hàm này SAU khi blockSignals(False) để chúng hoạt động bình thường
                
                # 1. Tự chọn Tone theo Topic
                self.auto_select_tone_by_topic()
                
                # 2. Tự chọn Duration theo Platform & Topic
                # Hàm này sẽ check Platform hiện tại (đã được set ở trên) và Topic để quyết định độ dài
                self.auto_select_duration() 

                # --- [CẬP NHẬT] ĐỔ SKELETON VÀO Ô MỚI TRONG HQ ---
            skeleton_text = t.get("spy_skeleton", "")
            if skeleton_text:
                self.txt_skeleton_preview.setText(skeleton_text)
                self.txt_skeleton_preview.setToolTip(skeleton_text) 
            else:
                self.txt_skeleton_preview.setText("(Bài này không có dữ liệu Spy)")
            
            # --- [CẬP NHẬT] ĐỔ VISUAL STYLE VÀO Ô BÊN CẠNH ---
            # Ưu tiên lấy Style riêng của bài (nếu có), không thì lấy của Kênh
            vis_style_task = t.get("visual_style_override", "")
            if vis_style_task:
                self.txt_visual_style.setText(vis_style_task)
            else:
                # Nếu bài không có style riêng, lấy style chung của kênh
                proj = self.projects[self.current_project_index]
                profile = proj.get("channel_profile", {})
                self.txt_visual_style.setText(profile.get("visual_style_preset", ""))
                
                # --- C. HIỂN THỊ NỘI DUNG ---
                content = t.get("script_content", "")
                # Debug để kiểm tra
                # print(f"DEBUG: Chọn bài ID {task_id}. Độ dài content: {len(content)}")
                
                if content:
                    self.distribute_data_to_boxes(content)
                else:
                    # Nếu bài chưa có nội dung -> Xóa trắng các ô cũ đi (tránh nhầm với bài trước)
                    self.distribute_data_to_boxes("")
                
                # Cập nhật Prompt Preview lần cuối cùng với tất cả dữ liệu mới
                self.update_prompt_preview()
            
            # =========================================================
            # 🆘 [FIX CHÍNH] ĐỔ DỮ LIỆU ĐÃ LƯU RA CÁC Ô EDITOR
            # =========================================================
            # Lấy nội dung kịch bản đã lưu trong DB
            saved_content = t.get("script_content", "")
            
            if saved_content:
                # Nếu có nội dung -> Gọi hàm phân phối để điền vào các ô Title, Body, Prompt...
                self.distribute_data_to_boxes(saved_content)
            else:
                # Nếu chưa có (bài mới) -> Xóa trắng các ô để không bị nhầm với bài cũ
                self.distribute_data_to_boxes("") 
            # =========================================================

        except Exception as e:
            print(f"Lỗi chọn bài: {e}")

    def update_prompt_preview(self):
        if not hasattr(self, 'txt_custom_instruction'): 
            return
        # Lấy dữ liệu thực tế từ giao diện
        current_tone = self.cb_tone.currentText()
        current_country = self.cb_country.currentText().split('~')[0].strip() # Lấy Quốc gia
        current_topic = self.cb_topic.currentText()     # Lấy Chủ đề
        current_platform = self.cb_platform.currentText()
        current_duration = self.cb_duration.currentText()

        vis_style = "Cinematic, High Quality" # Mặc định
        if hasattr(self, 'txt_visual_style'):
            vis_style = self.txt_visual_style.toPlainText()
            if not vis_style: vis_style = "Cinematic, Realistic, 4K"

        vis_source = self.cb_visual_source.currentText()
        custom_note = self.txt_custom_instruction.text()
        current_thumb_url = ""
        current_key_vua = "" # [MỚI] Lấy Key Vua
        topic_lower = current_topic.lower()
        fact_instruction = "Creative Freedom allowed. Focus on engagement and emotion." # Mặc định cho giải trí
        
        # Nhóm cần sự thật tuyệt đối
        if any(x in topic_lower for x in ["lịch sử", "history", "chiến tranh", "war", "tin tức", "news", "sự thật", "fact", "tài chính", "finance", "khoa học", "science", "biography", "tiểu sử"]):
            fact_instruction = (
                "⚠️ STRICTLY FACTUAL MODE: Content must be based on REAL historical events/verified news. "
                "NO Hallucinations. Dates, Names, and Locations must be 100% accurate. "
                "If information is uncertain, state it as a 'legend' or 'theory'."
            )
        # Nhóm tâm linh/bí ẩn (Nửa thực nửa hư)
        elif any(x in topic_lower for x in ["bí ẩn", "mystery", "tâm linh", "vũ trụ", "alien"]):
            fact_instruction = "Mix of Facts and Theories. Clearly distinguish between proven science and mysterious speculation."
        # ----------------------------------------------------

        ratio_instruction = "80% Stock Footage (Realistic) + 20% AI Generated (Abstract)" # Mặc định
        if "100% AI" in vis_source: ratio_instruction = "100% AI Generated Images (No Stock)"
        elif "100% Stock" in vis_source: ratio_instruction = "100% Stock Footage (No AI)"
        elif "50%" in vis_source: ratio_instruction = "50% Stock + 50% AI"

        # --- [ĐOẠN CODE MỚI BẮT ĐẦU TỪ ĐÂY] ---
        # 1. KIỂM TRA CHẾ ĐỘ SILENT (NHẠC/THIỀN)
        is_silent_mode = False
        # Check theo từ khóa Topic
        if any(x in topic_lower for x in ["nhạc", "music", "lofi", "rain", "mưa", "thiền", "meditation", "sleep", "asmr", "yoga", "study", "piano", "noise", "yoga", "focus", "snow", "winter", "tuyết", "fire", "lửa", "ocean", "water", "biển"]):
            is_silent_mode = True
        # Check theo Độ dài (Nếu chọn 1 Giờ/Loop)
        if "loop" in current_duration.lower() or "1 giờ" in current_duration.lower() or "1 hour" in current_duration.lower():
            is_silent_mode = True

        # 2. TẠO CẤU TRÚC JSON ĐẦU RA (OUTPUT STRUCTURE)
        output_structure = {}
        
        if is_silent_mode:
            # === CẤU TRÚC A: NHẠC/THIỀN (KHÔNG LỜI) ===
            output_structure = {
                "project_meta": {"mode": "SILENT_AMBIENT"},
                "seo_core": {"main_keyword": "..." , "seo_score_target": 95},
                "marketing_kit": {
                    "title_primary": "Viral Title (MANDATORY: Include 'Frequency Keywords' like: 432Hz, 528Hz, Rain Sound, ASMR)",
                    "description": "SEO description focusing on benefits (Sleep, Focus, Relax).",
                    "tags": [],
                    "thumbnail_prompt": f"High-quality prompt describing a {vis_style} cover image..."
                },
                "audio_engineer_recipe": { 
                    "layer_1_ambience": "Constant background (Rain, Wind, White Noise)",
                    "layer_2_music": "Musical pad (Piano, Flute, Drone) or Frequency",
                    "layer_3_sfx": "Occasional accents (Thunder, Birds)",
                    "voice_model": "None (Silent)"
                },
                "script_board": [
                    {
                        "scene_id": 1,
                        "role": "INFINITE_LOOP",
                        "estimated_duration": "1 Hour Loop",
                        "voice_text": "(NO VOICE - AUDIO LAYERS PLAYING ONLY)", 
                        "visual_prompt": f"({vis_style}) Seamless loop scene...",
                        "note": "Repeat this visual loop until the end."
                    }
                ]
            }
        else:
            # === CẤU TRÚC B: KỂ CHUYỆN (BÌNH THƯỜNG) ===
            output_structure = {
                "project_meta": {"mode": "NARRATIVE"},
                "seo_core": {"main_keyword": "..." , "seo_score_target": 95},
                "marketing_kit": {
                    "title_primary": "Viral Title (Clickbait but Accurate)",
                    "title_vietnamese": "Vietnamese translation of title",
                    "description": "SEO optimized description (3 lines).",
                    "tags": [],
                    "thumbnail_text": "Short text on cover",
                    "thumbnail_prompt": "..."
                },
                "audio_director": {
                    "music_keywords": "Background music keywords (English)",
                    "voice_model": f"{current_tone} Voice Style",
                    "sfx_instructions": "General SFX mood"
                },
                "script_board": [
                    {
                        "scene_id": 1,
                        "role": "HOOK",
                        "voice_text": "Hook content...",
                        "subtitle_highlight": ["KEYWORD"],
                        "visual_type": "STOCK | AI_GEN",
                        "visual_prompt": "...",
                        "duration_est": 5
                    },
                    {
                        "scene_id": 2,
                        "role": "BODY",
                        "voice_text": "Main content...",
                        "visual_prompt": "..."
                    }
                ]
            }
        # --- [KẾT THÚC ĐOẠN CODE MỚI] ---

        if self.current_project_index >= 0:
             current_row = self.table_tasks.currentRow()
             if current_row >= 0:
                 # Lấy task từ ID (để chắc ăn)
                 task_id = int(self.table_tasks.item(current_row, 0).text())
                 tasks = self.projects[self.current_project_index]["tasks"]
                 task = next((t for t in tasks if t["id"] == task_id), None)
                 if task:
                     current_thumb_url = task.get("thumbnail_url", "")
                     current_key_vua = task.get("key_vua", "")

        # PROMPT CHUẨN PLATINUM (JSON SẠCH)
        prompt_json = {
            "ROLE": "Professional Video Director & SEO Expert",
            "OUTPUT_LANGUAGE_RULE": f"DETECT language from AUDIENCE '{current_country}'. MUST write Script/Voiceover in that language (e.g., 'US'->English, 'VN'->Vietnamese).",
            "REFERENCE_THUMBNAIL": current_thumb_url if current_thumb_url else "None (Create from scratch)",
            "VISUAL_TASK": "If REFERENCE_THUMBNAIL is provided, analyze its style/color/composition and write a similar 'thumbnail_prompt' in marketing_kit.",

            "AUDIENCE": current_country,  # <--- ĐIỀN QUỐC GIA VÀO ĐÂY
            "TOPIC": current_topic,       # <--- ĐIỀN CHỦ ĐỀ VÀO ĐÂY
            "TRUTH_CONSTRAINT": fact_instruction,
            "PLATFORM": current_platform, # <--- ĐIỀN NỀN TẢNG VÀO ĐÂY
            "KEY_VUA_FOCUS": current_key_vua,
            "DURATION_TARGET": current_duration, # <--- ĐIỀN ĐỘ DÀI VIDEO VÀO ĐÂY
            
            "STYLE_GUIDE": {
                "TONE_OF_VOICE": current_tone,
                "VISUAL_ART_STYLE": vis_style, # <--- AI biết phải vẽ style gì
            },       
            "CEO_NOTE": custom_note,
            "SEO_MANDATES": {
                "keyword_insertion": "Main keyword MUST appear in Title, Description, and 3 times in Script.",
                "hook_rule": "First 3 seconds must be shocking/engaging."
            },
            "VISUAL_RULES": {
                "ratio": ratio_instruction, # <--- AI sẽ tuân thủ tỷ lệ này
                "style": vis_style,
                "character_consistency": "Define 'character_profile' if using AI."
            },
            "CINEMATIC_INSTRUCTIONS": {
                "sfx": "Suggest Sound Effects (SFX) for every scene.",
                "highlights": "List 1-3 keywords to highlight in subtitles.",
                "pacing": "Average shot length 4–6 seconds."
            }, 
            "MANDATORY_OUTPUT_JSON_STRUCTURE": output_structure
        }
        
        # Đổ dữ liệu vào ô Text Box (Màu xanh neon cho ngầu)
        formatted_json = json.dumps(prompt_json, indent=2, ensure_ascii=False)
        self.txt_prompt_preview.setText(formatted_json)
    # --- DÁN HÀM NÀY VÀO TRONG CLASS ContentTab (Ví dụ: Dán vào cuối file) ---

    def _create_input_box(self, title, placeholder, height):
        container = QWidget()
        l = QVBoxLayout(container); l.setContentsMargins(0,0,0,0); l.setSpacing(0)
        
        # Toolbar
        tb = QFrame(); tb.setStyleSheet("background: #333; border-top-left-radius: 3px; border-top-right-radius: 3px; border-bottom: 1px solid #444;")
        tb.setFixedHeight(30)
        ltb = QHBoxLayout(tb); ltb.setContentsMargins(10,0,5,0)
        
        # --- [QUAN TRỌNG: THÊM TIÊU ĐỀ VÀO ĐÂY] ---
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("font-weight: bold; color: #ddd; font-size: 12px;")
        ltb.addWidget(lbl_title)
        # ------------------------------------------
        
        ltb.addStretch()
        
        btn_copy = QToolButton()
        btn_copy.setText("📋 COPY")
        btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        # Set kích thước cứng để không bị co
        btn_copy.setFixedSize(60, 22)
        btn_copy.setStyleSheet("""
            QToolButton { 
                background: #555; color: white; 
                border: 1px solid #666; border-radius: 3px; 
                font-weight: bold; font-size: 9px;
            }
            QToolButton:hover { background: #666; }
            QToolButton:pressed { background: #444; }
        """)
        ltb.addWidget(btn_copy)
        
        # 2. Ô nhập liệu (TextEdit)
        txt = QTextEdit(); txt.setPlaceholderText(placeholder)
        txt.setStyleSheet("""
            QTextEdit { background: #1e1e1e; border: 1px solid #444; border-top: none; 
                        border-bottom-left-radius: 4px; border-bottom-right-radius: 4px; color: #eee; padding: 5px; }
        """)
        if height: txt.setMinimumHeight(height)
        
        # Logic nút Copy
        btn_copy.clicked.connect(lambda: QApplication.clipboard().setText(txt.toPlainText()))
        
        # Đóng gói
        l.addWidget(tb); l.addWidget(txt)
        
        container.text_edit = txt # Gán tham chiếu để dùng sau
        return container
    
    def _create_channel_hq(self):
        """Tạo khu vực quản lý thông tin Kênh và Bào Key (PHIÊN BẢN PRO)"""
        group = QGroupBox("📢 BỘ CHỈ HUY KÊNH (CHANNEL HQ - SEO OPTIMIZED)")
        apply_accent(group, "cyan")  # PR-5e: was inline #00e6e6 border
        layout = QVBoxLayout(group)
        layout.setSpacing(5)
        layout.setContentsMargins(5, 10, 5, 5)
        
        # 1. Thông tin định danh (Hàng 1)
        h1 = QHBoxLayout()
        self.txt_channel_name = QLineEdit(); self.txt_channel_name.setPlaceholderText("Tên Kênh (Chứa Key Vua)...")
        self.txt_channel_handle = QLineEdit(); self.txt_channel_handle.setPlaceholderText("@Handle_Chuan_SEO...")
        h1.addWidget(QLabel("Tên Kênh:")); h1.addWidget(self.txt_channel_name, stretch=4)
        h1.addWidget(QLabel("Handle:")); h1.addWidget(self.txt_channel_handle, stretch=3)
        layout.addLayout(h1)
        
        # 2. Mô tả (Hàng 2 - To hơn để chứa nhiều text)
        h2 = QHBoxLayout()
        #h2.setSpacing(2)
        self.txt_channel_desc = QTextEdit()
        self.txt_channel_desc.setPlaceholderText("Mô tả kênh (Bio/About) tối ưu từ khóa...")
        self.txt_channel_desc.setFixedHeight(50)
        h2.addWidget(QLabel("Mô tả:"))
        h2.addWidget(self.txt_channel_desc)
        layout.addLayout(h2)

        # 3. Visual Identity (Hàng 3 - Tách đôi Logo/Banner)
        h3 = QHBoxLayout()
        
        # Ô Logo
        v_logo = QVBoxLayout(); v_logo.setSpacing(2)
        v_logo.addWidget(QLabel("🎨 Prompt Logo (1:1):"))
        self.txt_logo_prompt = QTextEdit(); self.txt_logo_prompt.setFixedHeight(40)
        self.txt_logo_prompt.setPlaceholderText("Prompt vẽ Logo...")
        v_logo.addWidget(self.txt_logo_prompt)
        
        # Ô Banner
        v_banner = QVBoxLayout(); v_banner.setSpacing(2)
        v_banner.addWidget(QLabel("🖼️ Prompt Banner (Cover):"))
        self.txt_banner_prompt = QTextEdit(); self.txt_banner_prompt.setFixedHeight(40)
        self.txt_banner_prompt.setPlaceholderText("Prompt vẽ Bìa/Banner...")
        v_banner.addWidget(self.txt_banner_prompt)
        
        h3.addLayout(v_logo, stretch=1)
        h3.addLayout(v_banner, stretch=1)
        layout.addLayout(h3)

        # --- [MỚI] 4. STYLE & DNA (Hàng 4: Visual Style + Skeleton View) ---
        h4 = QHBoxLayout()

        # Cột Trái: Visual Style (Label trên, Text dưới)
        v_style = QVBoxLayout()
        v_style.setSpacing(2) # Khoảng cách giữa Label và Ô nhập nhỏ lại
        v_style.addWidget(QLabel("📸 Visual Style (Hình ảnh):")) # Label nằm trên

        self.txt_visual_style = QTextEdit()
        self.txt_visual_style.setFixedHeight(40)
        self.txt_visual_style.setPlaceholderText("VD: Cinematic 4K, Cyberpunk, Anime Style, Bright & Colorful...")
        self.txt_visual_style.setStyleSheet("background: #222; color: #00ffea; border: 1px solid #444;")        
        v_style.addWidget(self.txt_visual_style)
        #layout.addLayout(v_style)
        
        # Cột Phải: Skeleton DNA (Cấu trúc Spy) (Label trên, Text dưới)
        v_skel = QVBoxLayout(); v_skel.setSpacing(2)
        lbl_skel = QLabel("🧬 DNA Gốc (Skeleton Spy):")
        lbl_skel.setToolTip("Cấu trúc phân tích được từ Video Spy (Section 1). Dùng để tham khảo khi viết bài.")
        v_skel.addWidget(lbl_skel)

        self.txt_skeleton_preview = QTextEdit()
        self.txt_skeleton_preview.setFixedHeight(40)
        self.txt_skeleton_preview.setPlaceholderText("Chưa có dữ liệu Spy (Skeleton)...")
        # Màu chữ xanh lá nhạt matrix, nền tối
        self.txt_skeleton_preview.setStyleSheet("color: #aaffaa; font-family: Consolas; font-size: 10px; background: #1a1a1a; border: 1px solid #444;")
        self.txt_skeleton_preview.setReadOnly(True)
        v_skel.addWidget(self.txt_skeleton_preview)

        h4.addLayout(v_style)
        h4.addLayout(v_skel)
        #h4.addLayout(v_style, stretch=1)
        #h4.addLayout(v_skel, stretch=1)
        layout.addLayout(h4)

        # 5. Toolbar Chiến Lược
        h_tools = QHBoxLayout()
        h_tools.setContentsMargins(0, 5, 0, 0) # Cách bên trên 5px
        
        # 2. Định nghĩa Style cho Nút nhỏ (Height 28px)
        btn_style_compact = """
            QPushButton { 
                height: 20px; 
                font-size: 11px; 
                font-weight: bold; 
                padding: 0 10px;
                border-radius: 3px;
            }
        """

        # Nút Lưu Cấu Hình (MỚI)
        btn_save_config = QPushButton("💾 LƯU KÊNH")
        apply_kind(btn_save_config, "success")  # PR-5e: was inline #27ae60
        btn_save_config.clicked.connect(self.save_channel_config) # Kết nối hàm lưu

        btn_regen_info = QPushButton("✨ Thiết Kế Kênh")
        apply_kind(btn_regen_info, "info")  # PR-5e: was inline #34495e
        btn_regen_info.clicked.connect(self.auto_generate_channel_info_manual)

         # Thêm vào đầu tiên
        h_tools.addWidget(btn_save_config) # Thêm nút lưu
        h_tools.addWidget(btn_regen_info)
        h_tools.addStretch()

        # [MỚI] Thêm Label "Key:" màu vàng
        lbl_key = QLabel("🔑 Key:")
        lbl_key.setStyleSheet("font-weight: bold; color: #f1c40f; font-size: 11px;")
        h_tools.addWidget(lbl_key)

        # [MỚI] Ô Hiển thị Key Vua Chiến Lược (Read Only)
        # Đặt ngay đầu hàng nút để CEO dễ đối chiếu
        self.txt_key_vua_strategy = QLineEdit()
        self.txt_key_vua_strategy.setPlaceholderText("Nhập Key gốc để bào...")
        #self.txt_key_vua_strategy.setReadOnly(True
        self.txt_key_vua_strategy.setFixedWidth(180) # Gọn gàng
        self.txt_key_vua_strategy.setToolTip("Nhập từ khóa gốc vào đây -> Bấm '➕ BÀO KEY' để AI đẻ ra ý tưởng.")
        self.txt_key_vua_strategy.setStyleSheet("background: #2c3e50; color: #f1c40f; font-weight: bold; border: 1px solid #555; height: 24px;")
        h_tools.addWidget(self.txt_key_vua_strategy)

        h_tools.addWidget(QLabel("SL:"))

        self.spin_scale_qty = QSpinBox(); self.spin_scale_qty.setRange(1, 40); self.spin_scale_qty.setValue(1)
        self.spin_scale_qty.setSuffix(" video")
        self.spin_scale_qty.setFixedHeight(28)
        self.spin_scale_qty.setFixedWidth(70)
        self.spin_scale_qty.setStyleSheet("background: #333; color: white;")
        h_tools.addWidget(self.spin_scale_qty)

        btn_scale = QPushButton("➕ BÀO KEY")
        apply_kind(btn_scale, "ai_magic")  # PR-5e: was inline #8e44ad
        btn_scale.clicked.connect(self.run_idea_expansion)
        h_tools.addWidget(btn_scale)

        layout.addLayout(h_tools)
        
        # Sự kiện: Khi gõ text xong (Enter hoặc click ra ngoài) -> Tự dịch vào Tooltip
        self.txt_key_vua_strategy.editingFinished.connect(
            lambda: self.attach_translate_tooltip(self.txt_key_vua_strategy, self.txt_key_vua_strategy.text())
        )

        return group
    
    # [HÀM MỚI] LƯU THÔNG TIN KÊNH TỪ GIAO DIỆN VÀO DATABASE
    def save_channel_config(self):
        if self.current_project_index < 0:
            QMessageBox.warning(self, "Lỗi", "Chưa chọn dự án nào!")
            return

        # 1. Lấy dữ liệu từ UI
        name = self.txt_channel_name.text()
        handle = self.txt_channel_handle.text()
        desc = self.txt_channel_desc.toPlainText()
        logo = self.txt_logo_prompt.toPlainText()
        banner = self.txt_banner_prompt.toPlainText()
        style = self.txt_visual_style.toPlainText() # Lấy Style ảnh

        # 2. Cập nhật vào biến projects
        proj = self.projects[self.current_project_index]
        if "channel_profile" not in proj: proj["channel_profile"] = {}
        
        profile = proj["channel_profile"]
        profile["channel_name"] = name
        profile["channel_handle"] = handle
        profile["description"] = desc
        profile["visual_identity"] = {
            "logo_prompt": logo,
            "banner_prompt": banner
        }
        # Lưu Visual Style Preset
        profile["visual_style_preset"] = style

        # 3. Ghi xuống ổ cứng
        self.db.save_projects(self.projects)
        QMessageBox.information(self, "Đã lưu", "✅ Cập nhật thông tin kênh thành công!")

    def _create_control_panel(self):
        """Hàm tạo bảng điều khiển (Model, List, Tone, Prompt) để nhét vào Cột 2"""
        container = QFrame()
        container.setObjectName("controlContainer")  # PR-5e: was inline bg #252526 + border-top
        layout = QVBoxLayout(container)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        grid = QGridLayout(); grid.setSpacing(5)

        # Hàng 0: Model | Tone
        grid.addWidget(QLabel("Model:"), 0, 0)
        self.cb_model = QComboBox(); self.cb_model.addItems(["Gemini 2.5 Flash", "Gemini 1.5 Pro", "GPT-4o"])
        grid.addWidget(self.cb_model, 0, 1)
        
        grid.addWidget(QLabel("Tone (Văn):"), 0, 2)
        self.cb_tone = QComboBox(); self.cb_tone.addItems(TONES_DATA)
        self.cb_tone.currentIndexChanged.connect(self.update_prompt_preview)
        grid.addWidget(self.cb_tone, 0, 3)

        # Hàng 1: Target | Topic
        grid.addWidget(QLabel("Target:"), 1, 0)
        self.cb_country = QComboBox(); self.cb_country.addItems(COUNTRIES_DATA)
        self.cb_country.currentIndexChanged.connect(self.update_prompt_preview)
        grid.addWidget(self.cb_country, 1, 1)
        
        grid.addWidget(QLabel("Topic:"), 1, 2)
        self.cb_topic = QComboBox(); self.cb_topic.addItems(TOPICS_DATA)
        # Kết nối logic tự động
        # self.cb_topic.currentTextChanged.connect(self.auto_select_tone_by_topic)
        self.cb_topic.currentTextChanged.connect(self.auto_select_duration)
        self.cb_topic.currentIndexChanged.connect(self.update_prompt_preview)
        grid.addWidget(self.cb_topic, 1, 3)

        # Hàng 2: Platform | Duration
        grid.addWidget(QLabel("Platform:"), 2, 0)
        self.cb_platform = QComboBox(); self.cb_platform.addItems(PLATFORMS_DATA)
        # Kết nối logic tự động
        self.cb_platform.currentTextChanged.connect(self.auto_select_duration)
        self.cb_platform.currentIndexChanged.connect(self.update_prompt_preview)
        grid.addWidget(self.cb_platform, 2, 1)

        grid.addWidget(QLabel("Độ dài:"), 2, 2)
        self.cb_duration = QComboBox(); self.cb_duration.addItems(DURATIONS_DATA)
        self.cb_duration.currentIndexChanged.connect(self.update_prompt_preview)
        grid.addWidget(self.cb_duration, 2, 3)

        # --- [MỚI] Hàng 3: Visual Style | Custom Note ---
        # grid.addWidget(QLabel("Visual Style:"), 3, 0)
        # self.cb_visual_style = QComboBox()
        # self.cb_visual_style.addItems(VISUAL_STYLES_DATA)
        # self.cb_visual_style.currentIndexChanged.connect(self.update_prompt_preview)
        # grid.addWidget(self.cb_visual_style, 3, 1)

        # Cột 2: Source (MỚI)
        grid.addWidget(QLabel("Nguồn Ảnh:"), 3, 0)
        self.cb_visual_source = QComboBox()
        self.cb_visual_source.addItems(VISUAL_SOURCE_DATA)
        self.cb_visual_source.currentIndexChanged.connect(self.update_prompt_preview)
        grid.addWidget(self.cb_visual_source, 3, 1)

        grid.addWidget(QLabel("Ghi chú AI:"), 3, 2)
        self.txt_custom_instruction = QLineEdit()
        self.txt_custom_instruction.setPlaceholderText("VD: Đừng dùng từ sáo rỗng...")
        self.txt_custom_instruction.textChanged.connect(self.update_prompt_preview)
        grid.addWidget(self.txt_custom_instruction, 3, 3)
        
        layout.addLayout(grid)

        # --- B. GIỜ MỚI ĐƯỢC NỐI DÂY LOGIC (VÌ LÚC NÀY cb_topic ĐÃ CÓ) ---
        self.cb_topic.currentTextChanged.connect(self.auto_select_tone_by_topic)
        # ---------------------------------------------------------------

        # 2. Ô Prompt Preview
        lbl_prompt = QLabel("👁️ LIVE PROMPT (JSON Preview):")
        lbl_prompt.setStyleSheet("color: #aaa; font-size: 10px; margin-top: 5px;")
        layout.addWidget(lbl_prompt)

        self.txt_prompt_preview = QTextEdit()
        self.txt_prompt_preview.setPlaceholderText("Prompt JSON...")
        self.txt_prompt_preview.setMaximumHeight(60)
        self.txt_prompt_preview.setStyleSheet("color: #00ffcc; font-family: Consolas; font-size: 10px; background: #1e1e1e; border: 1px solid #333;")
        layout.addWidget(self.txt_prompt_preview)

        # Nút Reset
        btn_reset = QPushButton("♻ Cập nhật Prompt theo cấu hình trên")
        apply_kind(btn_reset, "muted")  # PR-5e: was inline #333/#ccc
        def manual_update_prompt():
            self.update_prompt_preview()
            QMessageBox.information(self, "Đã cập nhật", "✅ Đã làm mới Prompt theo cấu hình hiện tại!")

        btn_reset.clicked.connect(manual_update_prompt)
        layout.addWidget(btn_reset)

        action_box = QHBoxLayout()
        # [MỚI] NÚT NẠP FILE DATA
        btn_import = QPushButton("📂 Nhập Key")
        apply_kind(btn_import, "info")  # PR-5e: was inline #34495e
        btn_import.clicked.connect(self.import_json_file)

        # --- [THÊM NÚT NÀY] ---
        btn_cleanup = QPushButton("🧹 Dọn dẹp")
        btn_cleanup.setToolTip("Xóa bài trùng, bài rác, làm tươi danh sách")
        apply_kind(btn_cleanup, "warning")  # PR-5e: was inline #d35400
        btn_cleanup.clicked.connect(self.cleanup_current_project) # Nối vào hàm dọn dẹp
        # ----------------------

        # Nút 1: Viết bài đang chọn
        btn_write_one = QPushButton("✍ Viết bài này")
        apply_kind(btn_write_one, "primary")  # PR-5e: was inline #2980b9
        btn_write_one.clicked.connect(self.run_ai_writer_single)
        
        # Nút 2: VIẾT HÀNG LOẠT (WRITE ALL) - Ngôi sao sáng
        btn_write_all = QPushButton("⚡ VIẾT ALL (AUTO)")
        apply_kind(btn_write_all, "ai_magic")  # PR-5e: was inline #8e44ad
        btn_write_all.clicked.connect(self.run_ai_writer_batch)
        
        # [MỚI] NÚT HỦY (STOP) - Mặc định ẩn hoặc xám, khi chạy mới sáng
        self.btn_stop = QPushButton("🛑 HỦY TÁC VỤ")
        apply_kind(self.btn_stop, "danger")  # PR-5e: was inline #c0392b
        self.btn_stop.clicked.connect(self.stop_selected_worker) # Hàm hủy bên dưới

        action_box.addWidget(btn_import)
        action_box.addWidget(btn_cleanup)
        action_box.addWidget(btn_write_one)
        action_box.addWidget(btn_write_all)
        action_box.addWidget(self.btn_stop)
        
        layout.addLayout(action_box)
        
        return container
    # --- [HÀM 1: TỰ ĐỘNG CHỌN TONE DỰA VÀO CHỦ ĐỀ] ---
    # PR-5b: keyword tables lifted to modules/content/topic_classifier.py.
    # The Qt glue here is unchanged: pick a label via the pure classifier,
    # fuzzy-match it against the items already populated in cb_tone, then
    # apply with blockSignals + refresh the prompt preview.
    def auto_select_tone_by_topic(self):
        """Logic tự động chọn Tone (V13 - FULL SYNC)"""
        topic = self.cb_topic.currentText()

        # Decoration rows like "--- Format ---" leave the selection alone.
        if "---" in topic.lower():
            return

        target_tone = _pure_classify_tone_by_topic(topic)

        # Set Tone trên giao diện
        self.cb_tone.blockSignals(True)
        idx = -1

        # Tìm gần đúng (Fuzzy match)
        for i in range(self.cb_tone.count()):
            clean_target = target_tone.split("(")[0].strip()
            clean_item = self.cb_tone.itemText(i).split("(")[0].strip()
            if clean_target in clean_item:
                idx = i
                break

        if idx >= 0:
            self.cb_tone.setCurrentIndex(idx)
        else:
            self.cb_tone.setCurrentIndex(0)

        self.cb_tone.blockSignals(False)
        self.update_prompt_preview()
        
    # [HÀM ĐÃ NÂNG CẤP TOÀN DIỆN] TỰ ĐỘNG CHỌN ĐỘ DÀI & NGUỒN ẢNH CHUẨN ĐẠO DIỄN
    # PR-5b: keyword tables + Facebook clamp lifted to
    # modules/content/topic_classifier.py. Qt glue stays: block signals,
    # apply the indices the classifier returned (still bounded by combo
    # box sizes), refresh the prompt preview.
    def auto_select_duration(self):
        platform = self.cb_platform.currentText()
        topic = self.cb_topic.currentText()

        target_idx, target_vis_idx = _pure_classify_duration_and_visual(
            platform, topic
        )

        # THỰC THI (Block signals để tránh lỗi lặp vô tận)
        self.cb_duration.blockSignals(True)
        self.cb_visual_source.blockSignals(True)

        # Apply Độ dài (vẫn bounded theo cb_duration.count())
        if target_idx < self.cb_duration.count():
            self.cb_duration.setCurrentIndex(target_idx)

        # Apply Nguồn ảnh (vẫn bounded theo cb_visual_source.count())
        if target_vis_idx < self.cb_visual_source.count():
            self.cb_visual_source.setCurrentIndex(target_vis_idx)

        self.cb_duration.blockSignals(False)
        self.cb_visual_source.blockSignals(False)

        # Cập nhật Prompt Preview ngay lập tức để User thấy sự thay đổi
        self.update_prompt_preview()

    # --- [HÀM MỚI] ĐỊNH TUYẾN DỰ ÁN THÔNG MINH ---
    # [CẬP NHẬT HÀM NÀY TRONG ContentTab]
    def _find_or_create_project(self, topic, country, platform):
        t = topic.strip()
        c = country.split("~")[0].strip()
        p_raw = platform.strip()
        
        # --- LOGIC GỘP KÊNH YOUTUBE ---
        # Nếu là Youtube Long hay Shorts -> Đều quy về dự án mẹ là "Youtube"
        if "Youtube" in p_raw:
            p_project = "Youtube" 
        else:
            p_project = p_raw
            
        # Tên định danh dự án (Signature)
        project_name = f"{p_project} - {c} ({t})"
        # ------------------------------
        
        # Quét xem đã có chưa
        for i, proj in enumerate(self.projects):
            if proj["name"] == project_name:
                return i 
        
        # Chưa có -> Tạo mới
        new_proj = {
            "name": project_name,
            "topic": t, 
            "country": c, 
            "platform": p_project, 
            "tasks": [] 
        }
        self.projects.append(new_proj)
        self.refresh_project_list()

        self.db.save_projects(self.projects)
        
        return len(self.projects) - 1
        
    # [CẬP NHẬT] Nhận Data từ Radar -> Tự động tạo Hồ Sơ Kênh
   # [CẬP NHẬT] Nhận Data -> Tự động tạo Tiêu đề Viral
    def receive_data_from_radar(self, data_package):
        data_list = []
        if isinstance(data_package, list): data_list = data_package
        elif isinstance(data_package, dict): data_list = [data_package]
        else: return

        count_new = 0
        target_idx = -1 

        for item in data_list:
            # 1. Bóc tách dữ liệu từ Radar
            t = item.get("topic", "General")
            c = item.get("country", "Global")
            p = item.get("platform", "Multi")
            k = item.get("key_vua", "Untitled").strip()
            thumb = item.get("thumbnail_url", "")
            skeleton = item.get("skeleton", "") 
            vis_style = item.get("visual_style", "")
            vis_prompt_from_radar = item.get("initial_visual_prompt", "")
            
            # 2. Định tuyến (Routing)
            idx = self._find_or_create_project(t, c, p)
            target_idx = idx
            
            # 3. Update Branding (Nếu có)
            branding = item.get("branding_info", {})
            proj = self.projects[idx]
            if "channel_profile" not in proj: proj["channel_profile"] = {}
            
            if branding:
                if branding.get("channel_name"): 
                    proj["channel_profile"]["channel_name"] = branding.get("channel_name")
                if branding.get("channel_handle"):
                    proj["channel_profile"]["channel_handle"] = branding.get("channel_handle")
                if branding.get("description"):
                    proj["channel_profile"]["description"] = branding.get("description")
                
                vis_id = branding.get("visual_identity", {})
                if vis_id:
                    if "visual_identity" not in proj["channel_profile"]:
                        proj["channel_profile"]["visual_identity"] = {}
                    proj["channel_profile"]["visual_identity"].update(vis_id)
            
            if vis_style:
                 proj["channel_profile"]["visual_style_preset"] = vis_style
            
            # ---------------------------------------------------------
            # [MỚI] LOGIC THÊM BÀI VÀO DANH SÁCH (TASK QUEUE)
            # ---------------------------------------------------------
            current_tasks = self.projects[idx]["tasks"]
            
            # Hàm thêm bài (Định nghĩa ngay tại đây để dùng biến cục bộ)
            # Lưu ý: Hàm này dùng để tạo task với tiêu đề tạm, sau đó AI sẽ sửa sau
            def add_single_task_to_project(title_text):
                # --- [FIX LOGIC ID] Dùng Max ID để tránh trùng lặp khi đã xóa bài cũ ---
                if current_tasks:
                    # Tìm số ID lớn nhất hiện có và cộng thêm 1
                    new_id = max(t["id"] for t in current_tasks) + 1
                else:
                    # Nếu danh sách rỗng thì bắt đầu từ 1
                    new_id = 1
                
                # Vòng lặp check trùng này vẫn giữ để an toàn tuyệt đối (Double check)
                while any(tk["id"] == new_id for tk in current_tasks):
                    new_id += 1

                new_task = {
                    "id": new_id,
                    "key_vua": k,          # Giữ Key gốc để tham chiếu (trong Bộ chỉ huy)
                    "title": title_text,   # Tiêu đề hiển thị (Ban đầu là Key Vua)
                    "topic": t, "country": c, "platform": p,
                    "thumbnail_url": thumb,
                    "status": "Chờ viết", "script_content": "",
                    "spy_skeleton": skeleton,
                    "visual_style_override": vis_style,
                    "visual_content_prompt": vis_prompt_from_radar
                }
                current_tasks.append(new_task)
                # Vì biến count_new là biến của hàm cha, muốn sửa phải dùng nonlocal
                # Nhưng ở đây ta đang trong vòng lặp của hàm cha, nên cộng thẳng được nếu không dùng hàm con
                return 1

            # Thực hiện thêm 1 bài (Do bên Radar đã nhân bản gói tin rồi, nên ở đây mỗi item là 1 bài)
            # Ta tạm thời lấy Key Vua làm Tiêu đề. 
            # Lát nữa hàm auto_rewrite_titles_for_project sẽ chạy ngầm để sửa lại.
            added = add_single_task_to_project(k)
            count_new += added

        # ---------------------------------------------------------
        # 4. KẾT THÚC & LƯU
        # ---------------------------------------------------------
        if count_new > 0:
            self.db.save_projects(self.projects)
            self.refresh_project_list()
            
            if target_idx >= 0:
                self.list_projects.setCurrentRow(target_idx)
                self.on_project_selected_from_list(None)

                # [KÍCH HOẠT] TỰ ĐỘNG VIẾT LẠI TIÊU ĐỀ CHO CÁC BÀI VỪA THÊM
                # (Hàm này sẽ tìm các bài có tiêu đề trùng Key Vua và sửa lại)
                if hasattr(self, 'auto_rewrite_titles_GLOBAL'):
                    self.auto_rewrite_titles_GLOBAL()
            
                # [AUTO TRIGGER] Thiết kế kênh nếu mới tinh
                proj_data = self.projects[target_idx]
                prof = proj_data.get("channel_profile", {})
                if not prof and hasattr(self, 'api_key_cache') and self.api_key_cache:
                     self.log_system(f"🎨 AUTO-DESIGN: Đang tự động thiết kế kênh '{proj_data['name']}'...")
                     self.start_channel_design_worker(target_idx)

            QMessageBox.information(self, "Thành công", f"✅ Đã nhập {count_new} video.\n(AI đang tự động viết lại tiêu đề cho hấp dẫn...)")
        
        else:
            QMessageBox.warning(self, "Không có dữ liệu", "Không nhập được bài nào.")        
    
    def run_ai_writer_single(self):
        # 1. Lấy dòng đang chọn bằng chuột (để biết người dùng muốn viết bài nào)
        current_row = self.table_tasks.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "Chưa chọn", "Vui lòng chọn 1 dòng để viết!")
            return
            
        try:
            # 2. Lấy ID thật từ dòng đó (Cột 0 chứa ID)
            task_id_item = self.table_tasks.item(current_row, 0)
            if not task_id_item: return
            task_id = int(task_id_item.text())
            
            # Lấy data từ bộ nhớ
            tasks = self.projects[self.current_project_index]["tasks"]
            target_task = next((t for t in tasks if t["id"] == task_id), None)
        except: return
        
        # --- [SỬA KHÓA QUẢN LÝ WORKER] ---
        worker_key = f"{self.current_project_index}_{task_id}"

        if hasattr(self, 'active_workers') and worker_key in self.active_workers:
            QMessageBox.warning(self, "Từ từ", "Bài này đang chạy rồi!")
            return

        # Check trạng thái cũ
        if target_task and ("Hoàn thành" in target_task.get("status", "") or "Xong" in target_task.get("status", "")):
            confirm = QMessageBox.question(self, "Cảnh báo", "Bài này ĐÃ XONG. Viết lại không?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if confirm == QMessageBox.StandardButton.No: return
        
        # --- [ĐOẠN MỚI: KHÔNG CẦN HỎI KEY NỮA] ---
        # Lấy Prompt và Chạy luôn
        prompt = self.txt_prompt_preview.toPlainText()
        # CƠ CHẾ AN TOÀN: Nếu ô Preview bị trống (do quên bấm update), thì mới tự tạo lại
        if not prompt or len(prompt) < 10:
            print("⚠️ Prompt Preview trống, đang tự tạo mới từ cấu hình...")
            prompt = self.generate_dynamic_prompt(target_task)
            self.txt_prompt_preview.setText(prompt) # Điền lại cho bạn thấy
        
        # --- [QUAN TRỌNG: UPDATE UI ĐÚNG DÒNG TUYỆT ĐỐI] ---
        # Dùng hàm tìm dòng mới để update trạng thái chính xác
        real_row = self.find_row_by_task_id(task_id)
        if real_row != -1:
            # Cột trạng thái là cột số 2 (0: ID, 1: Key, 2: Trạng thái)
            self.table_tasks.setItem(real_row, 2, QTableWidgetItem("⏳ Đang viết...")) 
        # ======================
        
        # Debug nhẹ để an tâm
        print(f"🚀 GỬI LỆNH (Nguồn: Preview Box): {prompt[:100]}...")
        
        # Gọi Worker
        worker = ScriptWriterWorker(prompt, self.current_project_index, task_id)
        
        worker.finished_signal.connect(self.on_ai_finished)

        if not hasattr(self, 'active_workers'): self.active_workers = {}
        self.active_workers[worker_key] = worker
        worker.start()
        self.log_system(f"🚀 START: Viết bài ID {task_id} (Dùng cấu hình Quản Trị)")

    # --- [TÍNH NĂNG MỚI] MENU CHUỘT PHẢI CHO DỰ ÁN ---
    def show_project_context_menu(self, pos):
        item = self.list_projects.itemAt(pos)
        if not item: return
        
        menu = QMenu()
        # [MỚI] Action Viết lại tiêu đề
        action_rewrite_titles = menu.addAction("♻️ Auto-Rewrite: Viết lại tiêu đề (Các bài chờ)")
        menu.addSeparator()
        action_edit = menu.addAction("✏️ Chỉnh sửa Cấu hình Dự án") # Đổi tên cho sang
        action_delete = menu.addAction("🗑️ Xóa Dự án này")
        
        action = menu.exec(self.list_projects.mapToGlobal(pos))
        
        row = self.list_projects.row(item)
        target_project = self.projects[row]

        # --- XỬ LÝ VIẾT LẠI TIÊU ĐỀ ---
        if action == action_rewrite_titles:
            confirm = QMessageBox.question(
                self, "Xác nhận", 
                "AI sẽ viết lại tiêu đề cho TẤT CẢ các bài đang ở trạng thái 'Chờ viết' trong kênh này.\n\nTiếp tục?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if confirm == QMessageBox.StandardButton.Yes:
                # Gọi hàm auto rewrite chúng ta đã viết trước đó
                # Hàm này đã có logic gom nhóm theo Key Vua rồi
                self.auto_rewrite_titles_for_project(row)
                QMessageBox.information(self, "Đã kích hoạt", "🚀 AI đang chạy ngầm để viết lại tiêu đề...\n(Theo dõi Console bên dưới)")

        # --- XÓA DỰ ÁN (LOGIC HỢP NHẤT & LÀM SẠCH UI) ---
        elif action == action_delete:
            tasks_count = len(target_project.get("tasks", []))
            should_delete = False # Cờ kiểm soát: Có được xóa hay không?

            # 1. QUY TRÌNH HỎI (CONFIRMATION FLOW)
            if tasks_count == 0:
                # Trường hợp nhẹ: Kênh trống -> Hỏi Yes/No thường
                ans = QMessageBox.question(self, "Xóa Kênh", f"Xóa kênh trống '{target_project['name']}'?", 
                                           QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if ans == QMessageBox.StandardButton.Yes: should_delete = True
            else:
                # Trường hợp nặng: Có dữ liệu -> Cảnh báo ĐỎ
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Icon.Warning)
                msg.setWindowTitle("⚠️ CẢNH BÁO XÓA DỮ LIỆU")
                msg.setText(f"Kênh '{target_project['name']}' đang chứa {tasks_count} video!")
                msg.setInformativeText("Hành động này sẽ xóa vĩnh viễn cấu hình kênh và toàn bộ danh sách video bên trong.\n\nBạn có chắc chắn muốn xóa?")
                msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                msg.setDefaultButton(QMessageBox.StandardButton.No)
                msg.setStyleSheet("QPushButton[text='&Yes'] { background: #c0392b; color: white; font-weight: bold; }")
                
                if msg.exec() == QMessageBox.StandardButton.Yes: should_delete = True

            # 2. THỰC HIỆN XÓA (EXECUTION)
            if should_delete:
                # A. Backup trước khi xóa (An toàn là bạn)
                self.create_backup() 
                
                # B. Xóa dữ liệu trong RAM và Ổ cứng
                del self.projects[row]
                self.db.save_projects(self.projects)
                
                # C. Cập nhật Giao diện (QUAN TRỌNG NHẤT)
                self.refresh_project_list() # Vẽ lại danh sách bên trái
                
                if not self.projects:
                    # TÌNH HUỐNG 1: Xóa hết sạch sành sanh -> Reset trắng bảng
                    self.current_project_index = -1
                    self.reset_ui_to_blank() # <--- Gọi hàm làm sạch ngài vừa thêm
                else:
                    # TÌNH HUỐNG 2: Vẫn còn kênh khác -> Tự động nhảy sang kênh liền kề
                    # (Để người dùng không bị hụt hẫng nhìn vào khoảng không)
                    new_idx = max(0, row - 1)
                    self.list_projects.setCurrentRow(new_idx)
                    self.on_project_selected_from_list(None) # Load dữ liệu kênh đó lên
                
                # D. Thông báo
                QMessageBox.information(self, "Đã xóa", "Đã xóa kênh thành công!\n(Dữ liệu cũ đã được Backup).")

        # --- SỬA DỰ ÁN (DÙNG DROPDOWN CHUẨN) ---
        elif action == action_edit:
            # Gọi lại hộp thoại chọn chuẩn
            dialog = NewProjectDialog(self)
            dialog.setWindowTitle("Chỉnh sửa thông tin Dự án")
            
            # Pre-fill (Điền sẵn) thông tin cũ vào hộp thoại
            # (Lưu ý: Phải tìm text trong combobox để set index)
            dialog.cb_platform.setCurrentText(target_project.get("platform", ""))
            
            # Quốc gia cũ có thể dính tên tiền tệ, ta tìm tương đối
            old_country = target_project.get("country", "")
            idx_c = dialog.cb_country.findText(old_country.split("~")[0].strip(), Qt.MatchFlag.MatchContains)
            if idx_c >= 0: dialog.cb_country.setCurrentIndex(idx_c)
            
            dialog.cb_topic.setCurrentText(target_project.get("topic", ""))
            
            # Hiện bảng lên cho chọn lại
            if dialog.exec() == QDialog.DialogCode.Accepted:
                new_platform, new_country, new_topic = dialog.get_data()
                
                # Logic gộp Youtube (như lúc tạo mới)
                p_project = "Youtube" if "Youtube" in new_platform else new_platform
                
                # Tạo tên mới chuẩn format
                new_name = f"{p_project} - {new_country.split('~')[0].strip()} ({new_topic})"
                
                # Cập nhật dữ liệu
                target_project["name"] = new_name
                target_project["topic"] = new_topic
                target_project["country"] = new_country
                target_project["platform"] = p_project # Lưu cái gốc
                
                self.db.save_projects(self.projects)
                self.refresh_project_list()
                QMessageBox.information(self, "Xong", f"Đã cập nhật dự án thành:\n{new_name}")

    # --- [TÍNH NĂNG MỚI] MENU CHUỘT PHẢI CHO VIDEO (TASK) ---
    def show_task_context_menu(self, pos):
        item = self.table_tasks.itemAt(pos)
        if not item: return
        
        menu = QMenu()
        # [MỚI] Thêm dòng này
        action_translate = menu.addAction("🇻🇳 Dịch Tiêu Đề (Gắn vào Tooltip)")
        action_regen_title = menu.addAction("♻️ AI Viết Lại Tiêu Đề (Re-Generate)") # [MỚI]
        action_edit = menu.addAction("✏️ Sửa Key Vua")
        action_delete = menu.addAction("🗑️ Xóa Video này")
        
        action = menu.exec(self.table_tasks.mapToGlobal(pos))
        
        if self.current_project_index < 0: return
        current_tasks = self.projects[self.current_project_index]["tasks"]
        row = item.row()
        
        # Lấy ID task để xóa cho chuẩn
        task_id = int(self.table_tasks.item(row, 0).text())
        
        # [MỚI] Xử lý khi bấm nút Dịch
        if action == action_translate:
            # Lấy text tiêu đề (Cột 1)
            title_item = self.table_tasks.item(row, 1)
            title_text = title_item.text()
            
            # Gọi hàm dịch Tooltip cho ô này
            self.attach_translate_tooltip(title_item, title_text) # QTableWidgetItem cũng dùng được setToolTip
            
            # Thông báo nhẹ
            self.log_system(f"Đang dịch tiêu đề ID {task_id}...")

        elif action == action_delete:
            confirm = QMessageBox.question(self, "Xóa", "Xóa video này khỏi danh sách?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if confirm == QMessageBox.StandardButton.Yes:
                # Xóa task trong list
                for i, t in enumerate(current_tasks):
                    if t["id"] == task_id:
                        del current_tasks[i]
                        break
                
                self.db.save_projects(self.projects)
                self.refresh_task_table()
                self.refresh_project_list()

        elif action == action_edit:
            # Tìm task
            target_task = next((t for t in current_tasks if t["id"] == task_id), None)
            if target_task:
                new_key, ok = QInputDialog.getText(self, "Sửa Key", "Nhập Key Vua mới:", text=target_task["key_vua"])
                if ok and new_key:
                    target_task["key_vua"] = new_key
                    self.db.save_projects(self.projects)
                    self.refresh_task_table()
                    self.refresh_project_list()

        # [LOGIC MỚI] XỬ LÝ VIẾT LẠI TIÊU ĐỀ
        if action == action_regen_title:
            target_task = next((t for t in current_tasks if t["id"] == task_id), None)
            if target_task:
                # Gọi lại Worker tạo tiêu đề (Số lượng = 1)
                key = target_task["key_vua"]
                country = target_task["country"]
                topic = target_task["topic"]
                
                self.log_system(f"♻️ Đang viết lại tiêu đề cho ID {task_id}...")
                
                # Hàm callback nội bộ để cập nhật
                def on_single_title_done(titles):
                    if titles:
                        target_task["title"] = titles[0] # Lấy cái đầu tiên
                        self.db.save_projects(self.projects)
                        self.refresh_task_table()
                        self.log_system(f"✅ Đã cập nhật tiêu đề mới: {titles[0]}")
                    else:
                        QMessageBox.warning(self, "Lỗi", "AI không trả về tiêu đề nào.")

                # Khởi tạo Worker (Lưu ý: phải giữ tham chiếu self.regen_worker để không bị GC thu hồi)
                self.regen_worker = BatchTitleGeneratorWorker(key, 1, country, topic)
                self.regen_worker.finished_signal.connect(on_single_title_done)
                self.regen_worker.start()

    # [HÀM MỚI: TRÍ TUỆ LỌC JSON SIÊU VIỆT V2]
    # PR-5b: body lifted to modules/content/json_extractor.py. The method
    # now thin-wraps the pure helper so behaviour stays identical for every
    # caller (run_ai_writer_*, on_ai_finished). Edit the pure module if you
    # need to change the parsing strategy.
    def extract_json_from_text(self, text):
        return _pure_extract_json_from_text(text)
        
    # [HÀM XỬ LÝ KẾT QUẢ - PHIÊN BẢN CHẤP NHẬN MỌI DỮ LIỆU]
    def on_ai_finished(self, project_idx, task_id, result_text):
        worker_key = f"{project_idx}_{task_id}"
        if hasattr(self, 'active_workers') and worker_key in self.active_workers:
            del self.active_workers[worker_key]
        
        # 1. Tìm task mục tiêu
        target_task = None
        if project_idx < len(self.projects):
            tasks = self.projects[project_idx]["tasks"]
            target_task = next((t for t in tasks if t["id"] == task_id), None)
        
        if not target_task: return

        # 2. Xử lý dữ liệu trả về
        final_status = "✅ Hoàn thành"
        final_color = "#2ecc71" # Xanh
        
        # Thử lọc JSON
        valid_json = self.extract_json_from_text(result_text)
        
        # --- [BỘ LỌC LỖI AI CHẶN ĐỨNG "XONG ẢO"] ---
        is_real_error = False
        error_msg = ""
        
        # 1. Kiểm tra nếu JSON trả về là JSON Lỗi (Google API Error)
        if isinstance(valid_json, dict) and "error" in valid_json:
            is_real_error = True
            error_msg = f"AI Error JSON: {valid_json['error'].get('message', 'Unknown error')}"
        
        # 2. Kiểm tra nếu Text chứa từ khóa lỗi hệ thống (nhưng không phải nội dung bài viết)
        elif not valid_json:
            result_lower = result_text.lower()
            if any(k in result_lower for k in ["503", "exhausted", "limit reached", "unavailable", "overloaded", "thất bại", "error"]):
                is_real_error = True
                error_msg = f"AI System Error: {result_text[:100]}..."

        if valid_json and not is_real_error:
            # A. Trường hợp JSON Ngon Lành -> Lưu chuẩn
            target_task["script_content"] = result_text # Lưu gốc
            self.log_system(f"✅ JSON OK: Bài ID {task_id}")
        else:
            # B. Trường hợp Lỗi JSON hoặc Lỗi AI thực sự
            if is_real_error:
                final_status = "⛔ Lỗi AI"
                final_color = "#e74c3c"
                self.log_system(f"❌ THẤT BẠI CẬP ĐỘ 1: Bài ID {task_id} - {error_msg}")
                
                # --- [FIX QUAN TRỌNG] DỪNG TOÀN BỘ HÀNG ĐỢI ---
                self.stop_requested = True 
                if hasattr(self, 'rewrite_queue'): self.rewrite_queue = []
                self.log_system("🛑 HỆ THỐNG ĐÃ DỪNG TỰ ĐỘNG để bảo vệ tài khoản (Do gặp lỗi hệ thống từ Google).")
                QMessageBox.critical(self, "Lỗi AI Hệ Thống", f"Phát hiện lỗi nặng từ Google:\n{error_msg}\n\nĐã dừng toàn bộ hàng đợi tự động.")
            else:
                final_status = "⚠️ Text Thô (Check)"
                final_color = "#f1c40f"
                self.log_system(f"⚠️ RAW TEXT: Bài ID {task_id} (AI không trả JSON chuẩn)")
            
            target_task["script_content"] = result_text

        # 3. Update Database
        target_task["status"] = final_status
        self.db.save_projects(self.projects)

        # 4. Update Giao diện (QUAN TRỌNG: LUÔN UPDATE DÙ LỖI HAY KHÔNG)
        if self.current_project_index == project_idx:
            row_idx = self.find_row_by_task_id(task_id)
            if row_idx != -1:
                item_status = QTableWidgetItem(final_status)
                item_status.setForeground(QColor(final_color))
                item_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table_tasks.setItem(row_idx, 2, item_status)
                
                # --- [FIX CHÍNH]: TỰ ĐỘNG HIỆN NỘI DUNG LÊN CÁC Ô ---
                # Nếu đang chọn dòng đó -> Đổ dữ liệu ra ngay lập tức
                if self.table_tasks.currentRow() == row_idx:
                    print(f"DEBUG: Đang đổ dữ liệu ra UI. Độ dài: {len(target_task.get('script_content', ''))}")
                    self.distribute_data_to_boxes(target_task["script_content"])
        
        self.refresh_project_list()

    # Hàm phụ trợ lưu file JSON (Tách ra cho gọn code)
    # --- [HÀM MỚI] DỊCH NGẦM AN TOÀN (CÓ DELAY CHỐNG BAN) ---
    def _translate_safe_batch(self, text):       
        if not text: return ""
        try:
            # Nghỉ 1 chút để Google không chặn (QUAN TRỌNG)
            time.sleep(1.5) 
            
            # Cắt ngắn nếu quá dài
            safe_text = text[:4500]
            
            # Dịch
            translator = GoogleTranslator(source='auto', target='vi')
            return translator.translate(safe_text)
        except:
            return "Lỗi dịch (Quá tải hoặc mất mạng)"
        
    def _save_output_json(self, task, content):
        try:
            clean_json = content
            if "```json" in clean_json: 
                clean_json = clean_json.split("```json")[1].split("```")[0].strip()
            
            # (Phần logic lưu file giống hệt cũ, ngài copy lại đoạn save_path... ở đây)
            # Để tiết kiệm chỗ tôi viết vắn tắt, ngài giữ nguyên logic lưu file cũ nhé
            output_dir = os.path.join("VEO_DB", "output_media")
            os.makedirs(output_dir, exist_ok=True)
            safe_name = "".join([c if c.isalnum() else "_" for c in task['key_vua']])
            path = os.path.join(output_dir, f"{task['id']}_{safe_name}.json")
            
            with open(path, "w", encoding="utf-8") as f:
                # Format đơn giản để demo, ngài dùng cấu trúc chuẩn ở bài trước
                f.write(clean_json) 
        except: pass
            
    # [HÀM BATCH WRITER - BẢN FINAL - DELAY 3000ms - STOPPABLE]
    def run_ai_writer_batch(self):
        row_count = self.table_tasks.rowCount()
        if row_count == 0:
            QMessageBox.warning(self, "Trống", "Dự án này chưa có bài nào!")
            return

        # [FIX] Đóng đinh Project Index ngay lúc bấm nút
        # Để dù CEO có chuyển sang kênh khác, Worker vẫn biết phải viết cho kênh nào
        frozen_project_index = self.current_project_index 
        current_tasks_data = self.projects[frozen_project_index]["tasks"]

        # 1. Lọc danh sách
        ids_to_run = []
        for i in range(row_count):
            try:
                task_id = int(self.table_tasks.item(i, 0).text())
                status = self.table_tasks.item(i, 2).text()
                worker_key = f"{self.current_project_index}_{task_id}"
                is_running = hasattr(self, 'active_workers') and worker_key in self.active_workers

                # --- ĐIỀU KIỆN VIẾT LẠI (QUAN TRỌNG) ---
                # Viết lại nếu:
                # 1. Không chứa chữ "Xong", "Hoàn thành", "Ready"
                # 2. HOẶC chứa chữ "Lỗi", "Thô", "Check" (Bài lỗi hoặc kém chất lượng)
                is_done = "Xong" in status or "Hoàn thành" in status or "Ready" in status
                is_bad = "Lỗi" in status or "Error" in status or "Thô" in status or "Check" in status or "Gián đoạn" in status
                if not is_running and (not is_done or is_bad):
                    ids_to_run.append(task_id)
            except: pass

        if not ids_to_run:
            QMessageBox.information(self, "Nhàn rỗi", "Không có bài nào cần chạy!")
            return

        confirm = QMessageBox.question(self, "Xác nhận", f"Chạy {len(ids_to_run)} bài?\n(Delay 3s/bài để dùng Model cao cấp)", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if confirm == QMessageBox.StandardButton.No: return
        
        # Reset cờ Stop
        self.stop_requested = False
        current_tasks_data = self.projects[self.current_project_index]["tasks"]
        
        # --- [CHỈNH DELAY 5000ms TẠI ĐÂY] ---
        delay_ms = 0
        step_delay = 5000 # 5 giây
        # ------------------------------------
        
        for task_id in ids_to_run:
            task_data = next((t for t in current_tasks_data if t["id"] == task_id), None)
            if not task_data: continue

            ## Update UI màu vàng (Chỉ update nếu đang đứng đúng kênh)
            if self.current_project_index == frozen_project_index:
                row_idx = self.find_row_by_task_id(task_id)
                if row_idx != -1:
                    self.table_tasks.setItem(row_idx, 2, QTableWidgetItem("⏳ Đang xếp hàng..."))

            # >>> [THÊM ĐOẠN NÀY] Cập nhật luôn vào biến data để List bên trái đếm được <<<
            task_data["status"] = "⏳ Đang xếp hàng..."
            
            # Hàm phóng lính
            def launch_worker(t_id=task_id, t_data=task_data, p_idx=frozen_project_index):
                # --- [CHECK CỜ HIỆU ĐỂ DỪNG] ---
                if getattr(self, 'stop_requested', False): 
                    if self.current_project_index == p_idx:
                         r_idx = self.find_row_by_task_id(t_id)
                         if r_idx != -1: self.table_tasks.setItem(r_idx, 2, QTableWidgetItem("⛔ Đã hủy lệnh"))
                    return
                # -------------------------------

                prompt = self.generate_dynamic_prompt(t_data)
                worker = ScriptWriterWorker(prompt, p_idx, t_id)
                worker.finished_signal.connect(self.on_ai_finished)
                
                w_key = f"{p_idx}_{t_id}"
                if not hasattr(self, 'active_workers'): self.active_workers = {}
                self.active_workers[w_key] = worker
                worker.start()
                
                # Update UI màu cam (Chỉ nếu đang xem đúng kênh đó)
                if self.current_project_index == p_idx:
                    r_idx = self.find_row_by_task_id(t_id)
                    if r_idx != -1:
                        item = QTableWidgetItem("✍️ Đang viết...")
                        item.setForeground(QColor("#e67e22"))
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                        self.table_tasks.setItem(r_idx, 2, item)

                self.log_system(f"🚀 KÍCH HOẠT: ID {t_id}")
        
            # Hẹn giờ
            QTimer.singleShot(delay_ms, launch_worker)
            delay_ms += step_delay # Cộng dồn 5000ms
        
        self.refresh_project_list() # Nháy đèn vàng ngay lập tức

        QMessageBox.information(self, "Đã kích hoạt", f"Đã lên lịch chạy {len(ids_to_run)} bài!\n(Tốc độ: 1 bài / 3 giây)")

    # --- [HÀM MỚI] DỌN DẸP & LÀM TƯƠI DỰ ÁN ---
    def cleanup_current_project(self):
        if self.current_project_index < 0:
            QMessageBox.warning(self, "Lỗi", "Chưa chọn dự án nào để dọn dẹp!")
            return
        # 1. TẠO BACKUP TRƯỚC KHI QUÉT RÁC
        self.create_backup()

        current_tasks = self.projects[self.current_project_index]["tasks"]
        initial_count = len(current_tasks)
        
        # Dùng Dictionary để lọc trùng (Key là tiêu đề, Value là Task)
        # Cách này sẽ giữ lại task cuối cùng hoặc đầu tiên tùy logic
        unique_tasks = {}
        valid_tasks = []
        
        for task in current_tasks:
            key = task["key_vua"].strip()
            title = task.get("title", "").strip()
            
            # 1. Bỏ qua nếu key rỗng (Rác)
            if not key and not title: continue
            
            # Tạo mã duy nhất: Nếu có Key thì dùng Key, không thì dùng Title
            # (Để tránh trường hợp 2 bài khác tiêu đề nhưng cùng Key bị xóa oan)
            unique_id = key if key else title
            # [MỚI] Thêm ID phụ để phân biệt nếu muốn giữ cả 2 bài cùng Key nhưng khác Title
            # Nhưng chuẩn nhất là: Key Vua là duy nhất. 
            # Nếu ngài muốn giữ cả 2 bài cùng Key -> Thì phải dùng unique_id = f"{k}_{t}"
            
            # Ở đây tôi dùng unique_id = k (Chấp nhận luật 1 Key = 1 Bài). 
            # Nếu ngài muốn giữ cả 2 bài cùng key thì bỏ comment dòng dưới:
            unique_id = f"{key}|{title}"
            # 2. Nếu chưa có trong danh sách sạch -> Thêm vào
            if unique_id not in unique_tasks:
                unique_tasks[key] = task
                valid_tasks.append(task)
            else:
                # Nếu trùng, ta ưu tiên giữ lại bài nào ĐÃ VIẾT XONG (Status = Hoàn thành)
                # Nếu bài cũ chưa viết, mà bài mới trùng -> Kệ nó (coi như xóa bài trùng sau)
                existing = unique_tasks[unique_id]
                if "Hoàn thành" in task["status"] and "Hoàn thành" not in existing["status"]:
                    # Thay thế bài cũ (chưa xong) bằng bài mới (đã xong)
                    idx = valid_tasks.index(existing)
                    valid_tasks[idx] = task
                    unique_tasks[unique_id] = task
        
        # 2. [QUAN TRỌNG] ĐÁNH SỐ LẠI ID (RE-INDEX)
        # Sắp xếp lại ID từ 1 -> N để hết trùng
        for i, task in enumerate(valid_tasks):
            task["id"] = i + 1
            
        self.projects[self.current_project_index]["tasks"] = valid_tasks
        
        # Lưu và Vẽ lại
        self.db.save_projects(self.projects)
        self.refresh_task_table()
        
        removed_count = initial_count - len(valid_tasks)
        QMessageBox.information(self, "Dọn dẹp xong", f"Đã quét sạch rác & Đánh số lại ID!\n\n🗑️ Đã xóa: {removed_count} bài trùng/lỗi.\n✅ Còn lại: {len(valid_tasks)} bài sạch.")
        self.log_system(f"🧹 CLEANUP: Đã xóa {removed_count} bài rác khỏi dự án.")

    # [HÀM MỚI: ÉP TOOL ĐỌC LẠI DỮ LIỆU TỪ Ổ CỨNG]
    def hard_reload_data(self):
        try:
            self.log_system("🔄 Đang thực hiện Hard Reload...")
            
            # 1. Xóa sạch dữ liệu trên RAM
            self.projects = []
            
            # 2. Reset các trạng thái
            self.current_project_index = -1
            self.active_workers = {} # Cảnh báo: Việc này sẽ ngắt kết nối các worker đang chạy ngầm (nhưng an toàn)

            # 2. Xóa sạch giao diện
            self.list_projects.clear()
            self.table_tasks.setRowCount(0)

            # Reset các ô nhập liệu về trắng
            self.txt_channel_name.clear()
            self.txt_channel_handle.clear()
            self.txt_channel_desc.clear()
            self.txt_logo_prompt.clear()
            self.txt_banner_prompt.clear()
            self.txt_visual_style.clear()
            self.txt_skeleton_preview.clear()
            
            # Reset các ô bên phải (Editor)
            self.distribute_data_to_boxes("") 

            # 3. Nạp lại từ ổ cứng (Database chuẩn)
            self.db = DatabaseManager() # Khởi tạo lại kết nối DB cho chắc
            self.projects = self.db.load_projects()
            
            # 4. Vẽ lại
            self.refresh_project_list()
            
            QMessageBox.information(self, "Xong", "✅ Đã làm mới toàn bộ dữ liệu từ ổ cứng!")
            self.log_system("✅ Hard Reload hoàn tất.")
            
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Không thể nạp lại: {e}")
    # [HÀM CẬP NHẬT]: PHÂN PHỐI DỮ LIỆU VÀO CÁC Ô (FIX LỖI DỒN CỤC)
    # [HÀM CẬP NHẬT V2]: PHÂN PHỐI DỮ LIỆU THÔNG MINH (XỬ LÝ CẢ JSON & TEXT THƯỜNG)
    # [HÀM CẬP NHẬT]: HIỂN THỊ DỮ LIỆU (CHẾ ĐỘ NGHIÊM KHẮC)
    def distribute_data_to_boxes(self, raw_text):
        src_title = ""
        src_voice = ""
        # 1. Dọn dẹp
        self.box_script_board.text_edit.clear()
        self.box_target.text_edit.clear()
        self.box_title.text_edit.clear()
        self.box_desc.text_edit.clear()
        self.box_tags.text_edit.clear()
        self.box_thumb_text.text_edit.clear()
        self.box_visual.text_edit.clear()
        self.box_music.text_edit.clear()
        self.box_vn.text_edit.clear()

        self.box_script_board.text_edit.setText(raw_text)
        if not raw_text: return

        try:
            # 2. Lọc JSON
            json_data = self.extract_json_from_text(raw_text)

            # =========================================================
            # TRƯỜNG HỢP: DỮ LIỆU HỎNG / KHÔNG ĐÚNG CẤU TRÚC
            # =========================================================
            if not json_data:
                # Hiện thông báo lỗi thẳng vào ô Kịch bản để CEO biết
                msg = (
                    "❌ DỮ LIỆU KHÔNG HỢP LỆ (NON-JSON)\n"
                    "--------------------------------------------------\n"
                    "AI đã trả về văn bản không đúng cấu trúc quy định.\n"
                    "Hệ thống từ chối phân bổ dữ liệu này sang Media để tránh lỗi dây chuyền.\n\n"
                    "👉 GIẢI PHÁP: Vui lòng bấm nút [✍ Viết bài này] để tạo lại.\n\n"
                    "--- NỘI DUNG GỐC (DUMP) ---\n"
                )
                self.box_script_board.text_edit.setText(msg + raw_text)
                return # DỪNG NGAY, KHÔNG LÀM GÌ THÊM

            # =========================================================
            # TRƯỜNG HỢP: DỮ LIỆU SẠCH (JSON OK)
            # =========================================================
            # A. Marketing Kit
            mk = json_data.get("marketing_kit", {}) if isinstance(json_data, dict) else {}
            # Fallback thông minh: tìm key ở root nếu AI quên lồng ghép
            if not mk and isinstance(json_data, dict):
                if "title_primary" in json_data: mk = json_data

            if mk:
                self.box_title.text_edit.setText(mk.get('title_primary', ''))
                self.box_desc.text_edit.setText(mk.get('description', ''))
                tags = mk.get('tags', [])
                self.box_tags.text_edit.setText(", ".join(tags) if isinstance(tags, list) else str(tags))
                self.box_thumb_text.text_edit.setText(mk.get("thumbnail_text", ""))
                self.box_visual.text_edit.setText(mk.get("thumbnail_prompt", ""))

            # B. Kịch bản & Voice
            script_board = []
            if isinstance(json_data, dict):
                script_board = json_data.get("script_board", []) or json_data.get("scenes", [])
            elif isinstance(json_data, list):
                script_board = json_data

            # Cập nhật lại ô JSON cho đẹp (Pretty Print)
            if script_board:
                self.box_script_board.text_edit.setText(json.dumps(script_board, indent=2, ensure_ascii=False))
                
                # --- BẮT ĐẦU ĐOẠN CODE MỚI ---
                    
                # Cách 1: Tìm key chuẩn (voice_text)
                voice_clean = ""
                for scene in script_board:
                    if isinstance(scene, dict):
                        # Tìm đủ các loại tên mà AI có thể đặt
                        txt = scene.get("voice_text", "") or scene.get("content", "") or scene.get("script", "") or scene.get("narration", "")
                        if txt: voice_clean += f"{txt}\n\n"

                # Cách 2 (Cứu cánh): Nếu Cách 1 không tìm thấy gì, quét toàn bộ JSON tìm chuỗi dài
                if not voice_clean.strip():
                    def find_any_long_text(data):
                        found = ""
                        if isinstance(data, dict):
                            for k, v in data.items():
                                # Lấy những chuỗi dài > 50 ký tự, trừ mấy cái prompt
                                if isinstance(v, str) and len(v) > 50 and k not in ["prompt", "description", "visual_prompt", "thumbnail_prompt"]:
                                    found += f"{v}\n\n"
                                elif isinstance(v, (dict, list)):
                                    found += find_any_long_text(v)
                        elif isinstance(data, list):
                            for item in data:
                                found += find_any_long_text(item)
                        return found
                    
                    voice_clean = find_any_long_text(json_data)

                self.box_target.text_edit.setText(voice_clean.strip())
                # Giờ mới hiển thị kết quả cuối cùng
                self.update_vn_signal.emit(f"(Google Translate quá tải. Hãy copy và dịch thủ công)\n\nOriginal: {src_title}")

           # C. XỬ LÝ ÂM THANH (NÂNG CẤP: HỖ TRỢ CẢ AMBIENT 3 TẦNG & NARRATIVE)
            # -----------------------------------------------------
            music_display = ""
            
            # 1. Ưu tiên tìm cấu trúc Ambient (3 Tầng âm thanh) trước
            recipe = json_data.get("audio_engineer_recipe", {})
            if recipe:
                # Nếu có công thức pha chế -> Hiển thị chi tiết từng lớp cho dễ nhìn
                l1 = recipe.get("layer_1_ambience_search", "") or recipe.get("layer_1_ambience", "")
                l2 = recipe.get("layer_2_music_search", "") or recipe.get("layer_2_music", "")
                l3 = recipe.get("layer_3_sfx_search", "") or recipe.get("layer_3_sfx", "")
                
                music_display = f"[AMBIENT RECIPE]\n🌊 L1: {l1}\n🎹 L2: {l2}\n🔔 L3: {l3}"
            
            # 2. Nếu không có Ambient, quay về tìm cấu trúc Narrative cũ
            else:
                audio = json_data.get("audio_director", {})
                music_display = audio.get('music_keywords', '')

            # 3. CƠ CHẾ SMART FALLBACK: Chỉ điền hộ nếu cả 2 cách trên đều thất bại
            if not music_display or len(str(music_display)) < 3:
                # Lấy Tone và Topic hiện tại trên giao diện để làm từ khóa nhạc
                current_tone = self.cb_tone.currentText().split('(')[0].strip()
                current_topic = self.cb_topic.currentText().split('/')[0].strip()
                
                music_display = f"{current_tone}, {current_topic}, Cinematic, Background Music"
                
                # Log báo để biết là tool tự điền
                self.log_system(f"⚠️ AI quên nhạc -> Tool tự điền: '{music_display}'")

            self.box_music.text_edit.setText(str(music_display))
            # -----------------------------------------------------

            # --- D. DỊCH TỰ ĐỘNG (AUTO TRANSLATE) ---
            # Lấy giá trị sau khi đã điền vào ô (để đảm bảo có dữ liệu)
            src_title = self.box_title.text_edit.toPlainText()
            src_voice = self.box_target.text_edit.toPlainText()
            
            if src_title or src_voice:
                self.box_vn.text_edit.setPlaceholderText("⏳ Đang kết nối Google Dịch...")
                
                # Hàm chạy ngầm
                def run_trans_safe():
                    try:
                        # Ghép chuỗi để dịch 1 lần cho nhanh
                        full_text = f"TITLE: {src_title}\n\nCONTENT:\n{src_voice}"
                        
                        # Cắt ngắn bớt để tránh Google từ chối (Max 4500 ký tự)
                        safe_text = full_text[:4500]
                        
                        # Dùng deep_translator
                        translator = GoogleTranslator(source='auto', target='vi')
                        res = translator.translate(safe_text)
                        
                        if res:
                            self.update_vn_signal.emit(res)
                        else:
                            self.update_vn_signal.emit("⚠️ Google trả về rỗng (Có thể do mạng lag).")
                            
                    except Exception as e:
                        # Báo lỗi rõ ràng ra ô text
                        self.update_vn_signal.emit(f"❌ Lỗi dịch: {str(e)}\n(Hãy thử copy text và dịch thủ công)")

                # Kích hoạt luồng riêng
                threading.Thread(target=run_trans_safe, daemon=True).start()
        
        except Exception as e:
            print(f"Lỗi hiển thị dữ liệu: {e}")
            # Nếu lỗi, vẫn cố hiển thị text gốc để CEO không bị mất dữ liệu
            self.box_script_board.text_edit.setText(f"⚠️ LỖI HIỂN THỊ: {e}\n\n--- DỮ LIỆU GỐC ---\n{raw_text}")
        
    # ============================================================
    # 🟢 HỆ THỐNG LƯU TRỮ TRUNG TÂM (CORE SAVING ENGINE)
    # ============================================================

    # [HÀM PHỤ TRỢ] Tách thông tin từ dữ liệu thô (JSON Text)
    # Vì lưu hàng loạt không đọc được ô trên UI, nên phải parse lại từ text gốc
    def _parse_task_data(self, task):
        raw_text = task.get("script_content", "")
        if not raw_text: return None

        # Dùng lại hàm trích xuất JSON thông minh
        data = self.extract_json_from_text(raw_text)
        if not data: return None
        
        # Chuẩn hóa dữ liệu về 1 format chung
        parsed = {
            "title": "", "desc": "", "tags": "", "thumb_text": "",
            "voice": "", "visual": "", "music": "", "script_board": []
        }

        # 1. Lấy Meta
        mk = data.get("marketing_kit", {})
        # Fallback nếu cấu trúc phẳng
        if not mk and isinstance(data, dict): mk = data 

        # Hàm con để ép kiểu thành chuỗi
        def force_str(val):
            if isinstance(val, list): return ", ".join([str(x) for x in val])
            if val is None: return ""
            return str(val)
        
        parsed["title"] = mk.get("title_primary", "") or task.get("key_vua", "")
        parsed["desc"] = mk.get("description", "")
        parsed["tags"] = mk.get("tags", "")
        if isinstance(parsed["tags"], list): parsed["tags"] = ", ".join(parsed["tags"])
        parsed["thumb_text"] = mk.get("thumbnail_text", "")
        parsed["visual"] = mk.get("thumbnail_prompt", "")

        # 2. Lấy Voice & Script
        sb = data.get("script_board", []) or data.get("scenes", [])
        parsed["script_board"] = sb
        
        voice_accum = ""
        visual_scenes_accum = ""
        if sb:
            for scene in sb:
                if isinstance(scene, dict):
                    txt = scene.get("voice_text", "")
                    if txt: voice_accum += f"{txt}\n\n"
                    # B. Lấy Visual Prompt (MỚI)
                    # Ưu tiên lấy visual_prompt, nếu không có thì lấy mô tả
                    vis = scene.get("visual_prompt", "") or scene.get("visual_desc", "")
                    if vis: 
                        # Làm sạch dòng visual (xóa các ký tự thừa)
                        clean_vis = vis.replace("\n", " ").strip()
                        visual_scenes_accum += f"{clean_vis}\n"
        parsed["voice"] = voice_accum.strip()
        parsed["visual_scenes"] = visual_scenes_accum.strip()

        # 3. [FIX QUAN TRỌNG] XỬ LÝ ÂM THANH ĐA CHẾ ĐỘ
        # -----------------------------------------------------------
        music_final = ""
        
        # A. Ưu tiên tìm công thức Ambient (3 Tầng) - Dành cho Lofi/Sleep
        recipe = data.get("audio_engineer_recipe", {})
        if recipe:
            l1 = recipe.get("layer_1_ambience_search", "") or recipe.get("layer_1_ambience", "")
            l2 = recipe.get("layer_2_music_search", "") or recipe.get("layer_2_music", "")
            l3 = recipe.get("layer_3_sfx_search", "") or recipe.get("layer_3_sfx", "")
            
            music_final = (
                f"--- AMBIENT FORMULA (3 LAYERS) ---\n"
                f"1. BASE (Nền): {l1}\n"
                f"2. MUSIC (Nhạc): {l2}\n"
                f"3. ACCENT (Điểm nhấn): {l3}"
            )
        
        # B. Nếu không có Ambient, tìm kiểu Narrative cũ (Music Keywords)
        else:
            ad = data.get("audio_director", {})
            music_final = force_str(ad.get("music_keywords", "") or ad.get("music_mood", "")) or \
                    ad.get("layer_1_ambience", "") # Fallback cho Ambient mode

        parsed["music"] = music_final
        # -----------------------------------------------------------

        return parsed
    
    # [FIX TRIỆT ĐỂ 100%] LÀM SẠCH TÊN FILE & FOLDER
    # PR-5b: body lifted to modules/content/file_naming.py. Behaviour preserved
    # verbatim (same regex, same 50-char cap, same fallback).
    def _sanitize_filename(self, name):
        return _pure_sanitize_filename(name)
          
    # --- [HÀM PHỤ TRỢ 2] LỌC VOICE & TÁCH SFX (TRÍ TUỆ NHÂN TẠO CẤP THẤP) ---
    # PR-5b: body lifted to modules/content/safety_filter.py. Returns
    # (voice_text, sfx_block) just like before; SFX cues are stripped from
    # the voice payload and emitted on their own newline-separated block.
    def _process_voice_and_sfx(self, raw_text):
        return _pure_process_voice_and_sfx(raw_text)
    
    # [HÀM MỚI] BỘ LỌC TỪ CẤM (SAFETY BLACKLIST FILTER)
    # PR-5b: 166-line body lifted to modules/content/safety_filter.py.
    # The blacklist + matching strategy (sort-longest-first, Latin uses
    # word boundaries, CJK/Thai/Indic uses substring match) is preserved
    # verbatim so every save-task call rewrites identically.
    def _apply_safety_filter(self, text):
        return _pure_apply_safety_filter(text)
    
    # [ĐỘNG CƠ LƯU CHÍNH THỨC - BẢN FULL AN TOÀN]
    def _core_save_task(self, task, channel_dir_path):
        try:
            # 1. Parse dữ liệu (Lấy từ bộ nhớ)
            parsed_data = self._parse_task_data(task)
            if not parsed_data: return False, "Không đọc được dữ liệu JSON"
            
            # =========================================================
            # 🛡️ KÍCH HOẠT BỘ LỌC AN TOÀN (SAFETY FILTER) TẠI ĐÂY
            # =========================================================
            # Lọc Tiêu đề, Mô tả, và cả Thumbnail Text
            parsed_data["title"] = self._apply_safety_filter(parsed_data["title"])
            parsed_data["desc"] = self._apply_safety_filter(parsed_data["desc"])
            parsed_data["thumb_text"] = self._apply_safety_filter(parsed_data["thumb_text"])            
            parsed_data["tags"] = self._apply_safety_filter(parsed_data["tags"])
            # =========================================================

            # 2. Chuẩn bị đường dẫn cha
            # 2. Chuẩn bị đường dẫn theo cấu trúc chuẩn (V3.2)
            p_platform = task.get("platform", "Youtube")
            p_country = task.get("country", "Global").split('~')[0].strip()
            p_topic = task.get("topic", "General")
            p_keyword = task.get("key_vua", "Untitled")
            p_channel = project.get("name", "DefaultChannel")
            
            is_short = any(x in p_platform.lower() for x in ["short", "tiktok", "reel"])
            p_type = "Shorts" if is_short else "Long"

            # Cấu trúc: VEO_DB / Platform / Country / Topic / Channel / Type
            channel_dir_path = os.path.join("VEO_DB", p_platform, p_country, p_topic, p_channel)
            parent_dir = os.path.join(channel_dir_path, p_type)
            if not os.path.exists(parent_dir): os.makedirs(parent_dir, exist_ok=True)

            # -------------------------------------------------------------
            # 🕵️ LOGIC SMART RENAME (CHỐNG RÁC)
            # -------------------------------------------------------------
            task_id = str(task['id'])
            current_folder_name = ""
            
            # Quét thư mục cha để tìm folder cũ của ID này
            try:
                subfolders = [f for f in os.listdir(parent_dir) if os.path.isdir(os.path.join(parent_dir, f))]
                for folder in subfolders:
                    if folder.startswith(f"{task_id}_"):
                        current_folder_name = folder
                        break
            except: pass

            safe_title = self._sanitize_filename(parsed_data["title"])[:30].strip()
            target_folder_name = f"{task_id}_{safe_title}"
            
            # Đường dẫn đích cuối cùng
            final_path = os.path.join(parent_dir, target_folder_name)

            # THỰC HIỆN ĐỔI TÊN NẾU CẦN
            if current_folder_name and current_folder_name != target_folder_name:
                old_full_path = os.path.join(parent_dir, current_folder_name)
                try:
                    os.rename(old_full_path, final_path)
                    print(f"♻️ Auto-Rename: '{current_folder_name}' -> '{target_folder_name}'")
                except Exception as e:
                    print(f"Lỗi rename (có thể file đang mở): {e}")
            
            # Tạo mới nếu chưa có
            if not os.path.exists(final_path): os.makedirs(final_path)
            # -------------------------------------------------------------

            # 3. XỬ LÝ VOICE & SFX
            clean_voice, sfx_list = self._process_voice_and_sfx(parsed_data["voice"])

            # 4. DỊCH NGẦM TỰ ĐỘNG
            content_to_trans = f"TITLE: {parsed_data['title']}\n\nCONTENT:\n{clean_voice}"
            translated_content = self._translate_safe_batch(content_to_trans)

            # 5. GHI FILE (Physical Write)
            with open(os.path.join(final_path, "voice.txt"), "w", encoding="utf-8") as f: 
                f.write(clean_voice)
            
            with open(os.path.join(final_path, "sfx.txt"), "w", encoding="utf-8") as f: 
                f.write("--- DANH SÁCH SFX & CHỈ DẪN ---\n" + sfx_list)

            meta_json = {
                "title": parsed_data["title"], 
                "description": parsed_data["desc"],
                "tags": parsed_data["tags"], 
                "thumbnail_text": parsed_data["thumb_text"],
                "seo_focus_keyword": p_keyword,
                "platform": p_platform,
                "country": p_country,
                "topic": p_topic,
                "channel": project.get("name", "Default"),
                "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            with open(os.path.join(final_path, "meta.json"), "w", encoding="utf-8") as f: 
                json.dump(meta_json, f, indent=2, ensure_ascii=False)

            with open(os.path.join(final_path, "thumbnail.txt"), "w", encoding="utf-8") as f: 
                f.write(parsed_data.get("visual", ""))
            
            with open(os.path.join(final_path, "text_thumb.txt"), "w", encoding="utf-8") as f: 
                f.write(parsed_data.get("thumb_text", ""))
            
            with open(os.path.join(final_path, "scenes_visual.txt"), "w", encoding="utf-8") as f: 
                f.write(parsed_data["visual_scenes"])
            
            with open(os.path.join(final_path, "music.txt"), "w", encoding="utf-8") as f: 
                f.write(parsed_data["music"])
            
            with open(os.path.join(final_path, "vietnamese.txt"), "w", encoding="utf-8") as f: 
                f.write(translated_content)
            
            with open(os.path.join(final_path, "script.json"), "w", encoding="utf-8") as f: 
                json.dump(parsed_data["script_board"], f, indent=2, ensure_ascii=False)

            # 6. Cập nhật Status
            task["status"] = "🟢 Sẵn sàng dựng"
            task["output_path"] = final_path
            
            return True, final_path

        except Exception as e:
            # Bắt lỗi toàn bộ quá trình
            print(f"LỖI LƯU BÀI ID {task.get('id')}: {str(e)}")
            return False, str(e)

    # ------------------------------------------------------------
    # HÀM 1: LƯU LẺ (Bấm nút "Lưu bài này")
    # ------------------------------------------------------------
    def on_save_media(self):
        row = self.table_tasks.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Chưa chọn", "Vui lòng chọn 1 video!")
            return
            
        task_id = int(self.table_tasks.item(row, 0).text())
        project = self.projects[self.current_project_index] # Lấy cả project object
        tasks = self.projects[self.current_project_index]["tasks"]
        task = next((t for t in tasks if t["id"] == task_id), None)

        # 1. Lưu Hồ Sơ Kênh TRƯỚC
        channel_path = self._save_channel_assets_to_disk(project)
        if not channel_path:
            QMessageBox.critical(self, "Lỗi", "Không tạo được thư mục kênh!")
            return

        # 2. Lưu Video vào folder kênh đó
        success, msg = self._core_save_task(task, channel_path)
        
        if success:
            # Update UI dòng đó
            self.table_tasks.setItem(row, 2, QTableWidgetItem("🟢 Ready"))
            self.db.save_projects(self.projects)
            self.refresh_project_list()
            self.log_system(f"💾 SAVE: Đã lưu bài ID {task_id} thành công.")
            QMessageBox.information(self, "Thành công", f"Đã lưu tại:\n{msg}")
            os.startfile(msg)
        else:
            QMessageBox.critical(self, "Lỗi Lưu", msg)

    # ------------------------------------------------------------
    # HÀM 2: LƯU HÀNG LOẠT (Bấm nút "Lưu Tất Cả")
    # ------------------------------------------------------------
    # [HÀM LƯU HÀNG LOẠT - BẢN FINAL SẠCH SẼ]
    def on_save_media_batch(self):
        # Gom bài theo Dự án (Để lưu Info kênh 1 lần cho mỗi dự án)
        # Cấu trúc: { project_index: [list_of_tasks] }
        tasks_by_project = {}        
        total_tasks = 0

        print("\n--- BẮT ĐẦU QUÉT BÀI ĐỂ LƯU ---") # Debug
        
        for idx, project in enumerate(self.projects):
            tasks = project.get("tasks", [])
            ready_tasks = []

            print(f"📂 Đang quét Dự án: {project['name']} (Tổng {len(tasks)} bài)") # Debug

            for t in tasks:
                st = t.get("status", "")

                # [THAY ĐỔI CHIẾN THUẬT]
                # Thay vì tìm "Hoàn thành", ta LOẠI TRỪ những bài chưa xong.
                # Nếu KHÔNG PHẢI là "Chờ viết" và KHÔNG PHẢI "Đang viết" -> LƯU HẾT!
                bad_keywords = ["Chờ viết", "Waiting", "Đang viết", "Writing", "Lỗi", "Error"]
                
                # Nếu trạng thái KHÔNG chứa từ khóa xấu nào -> Coi như là Lưu được
                is_valid = not any(bad in st for bad in bad_keywords)
                
                # Hoặc nếu nội dung kịch bản đã có -> Cũng lưu luôn cho chắc
                has_content = len(t.get("script_content", "")) > 50
                
                if is_valid or has_content:
                    ready_tasks.append(t)
                else:
                    print(f"   ❌ BỎ QUA ID {t['id']} (Lý do: Status='{st}' và Không có nội dung)")
            
            if ready_tasks:
                tasks_by_project[idx] = ready_tasks
                total_tasks += len(ready_tasks)

        if total_tasks == 0:
            QMessageBox.information(self, "Trống", "Không tìm thấy bài nào để lưu!")
            return

        # 2. Xác nhận
        confirm = QMessageBox.question(self, "Xác nhận", 
                                     f"Tìm thấy {total_tasks} bài.\nLƯU ĐÈ tất cả ra ổ cứng?", 
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if confirm == QMessageBox.StandardButton.No: return

        # 3. Chạy Progress Bar
        
        progress = QProgressDialog("Đang lưu...", "Hủy", 0, total_tasks, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.show()
        
        count_ok = 0
        count_fail = 0
        processed = 0
        last_paths = ""

        # --- [VÒNG LẶP CHÍNH: DUYỆT TỪNG DỰ ÁN] ---
        for p_idx, tasks in tasks_by_project.items():
            project = self.projects[p_idx]
            
            # A. Tạo Folder Kênh & Lưu Info Kênh (Chỉ làm 1 lần mỗi dự án)
            # Hàm này ngài đã thêm ở bước 1, nó trả về đường dẫn folder kênh
            channel_path = self._save_channel_assets_to_disk(project)
            
            if not channel_path:
                print(f"❌ Lỗi tạo folder kênh cho dự án: {project['name']}")
                # Nếu không tạo được folder kênh, bỏ qua các bài của kênh này
                processed += len(tasks)
                count_fail += len(tasks)
                progress.setValue(processed)
                continue

            # B. Lưu từng bài trong dự án đó vào Folder Kênh
            for task in tasks:
                if progress.wasCanceled(): break
                
                processed += 1
                # Hiển thị tên bài đang lưu
                key_display = task.get("key_vua", "Untitled")[:30]
                progress.setLabelText(f"Saving ({processed}/{total_tasks}):\n{key_display}...")
                progress.setValue(processed)
                QApplication.processEvents()

                try:
                    # Gọi động cơ lưu chính (Truyền channel_path vào)
                    success, path = self._core_save_task(task, channel_path)            
                    if success:
                        count_ok += 1
                        last_path = path # Lưu lại đường dẫn để tí mở lên xem
                    else:
                        count_fail += 1
                        print(f"❌ Lỗi lưu task {task.get('id')}")

                except Exception as e:
                    count_fail += 1
                    print(f"❌ Crash task {task.get('id')}: {e}")

        # 4. Kết thúc & Dọn dẹp
        self.db.save_projects(self.projects) # Lưu lại trạng thái (đã chuyển sang 'Sẵn sàng dựng')
        progress.close()
        
        self.refresh_task_table() # Vẽ lại bảng nếu đang xem
        self.refresh_project_list()

        # 5. Thông báo & Log
        msg = f"🏁 HOÀN TẤT!\n\n✅ Thành công: {count_ok}/{total_tasks}\n❌ Thất bại: {count_fail}/{total_tasks}"
        if count_fail > 0:
            msg += "\n(Xem cửa sổ đen để biết chi tiết lỗi)"
            
        self.log_system(f"📦 BATCH SAVE: {count_ok} OK / {count_fail} FAIL.")
        QMessageBox.information(self, "Kết quả", msg)
        
        # 6. Mở thư mục bài cuối cùng để kiểm tra
        if last_path:
            try:
                # Mở folder chứa video (lên 1 cấp) hoặc folder kênh (lên 2 cấp)
                # last_path là folder của video cụ thể. Ta mở folder kênh để nhìn tổng quan.
                channel_dir = os.path.dirname(os.path.dirname(last_path))
                os.startfile(channel_dir)
            except: pass

    # [HÀM MỚI] LƯU HỒ SƠ KÊNH (ASSETS) RA Ổ CỨNG
    def _save_channel_assets_to_disk(self, project):
        # 1. Xử lý Platform: Gộp "Youtube Long/Shorts" thành "Youtube"
        raw_plat = project.get("platform", "Youtube")
        if "Youtube" in raw_plat: p_platform = "Youtube"
        elif "TikTok" in raw_plat: p_platform = "TikTok"
        elif "Facebook" in raw_plat: p_platform = "Facebook"
        else: p_platform = raw_plat

        p_country = project.get("country", "Global").split('~')[0].strip()
        p_topic = project.get("topic", "General")
        
        # Lấy tên kênh (Nếu chưa đặt tên thì lấy tên Dự án)
        profile = project.get("channel_profile", {})
        channel_name = profile.get("channel_name", "")
        if not channel_name: channel_name = project.get("name", "Unnamed_Channel")

        # 2. Tạo đường dẫn: VEO_DB / Platform / Country / Topic / Tên Kênh
        safe_plat = self._sanitize_filename(p_platform)
        safe_country = self._sanitize_filename(p_country)
        safe_topic = self._sanitize_filename(p_topic)
        safe_channel = self._sanitize_filename(channel_name)
        
        channel_dir = os.path.join("VEO_DB", safe_plat, safe_country, safe_topic, safe_channel)
        if not os.path.exists(channel_dir): os.makedirs(channel_dir)

        # 3. Xuất file Nguyên liệu Kênh (Để sau này tool Reg kênh dùng)
        try:
            # File JSON tổng hợp
            with open(os.path.join(channel_dir, "channel_profile.json"), "w", encoding="utf-8") as f:
                json.dump(profile, f, indent=2, ensure_ascii=False)
            
            # File Text rời (để dễ copy paste)
            if profile.get("channel_handle"):
                with open(os.path.join(channel_dir, "handle.txt"), "w", encoding="utf-8") as f:
                    f.write(profile["channel_handle"])
            
            if profile.get("description"):
                with open(os.path.join(channel_dir, "bio_description.txt"), "w", encoding="utf-8") as f:
                    f.write(profile["description"])

            # Prompt Logo & Banner (Cho đội design)
            visuals = profile.get("visual_identity", {})
            if visuals.get("logo_prompt"):
                with open(os.path.join(channel_dir, "prompt_logo.txt"), "w", encoding="utf-8") as f:
                    f.write(visuals["logo_prompt"])
            
            if visuals.get("banner_prompt"):
                with open(os.path.join(channel_dir, "prompt_banner.txt"), "w", encoding="utf-8") as f:
                    f.write(visuals["banner_prompt"])
                    
            print(f"✅ Đã lưu hồ sơ kênh tại: {channel_dir}")
            return channel_dir # Trả về đường dẫn để dùng cho việc lưu video
            
        except Exception as e:
            print(f"❌ Lỗi lưu hồ sơ kênh: {e}")
            return None
    
