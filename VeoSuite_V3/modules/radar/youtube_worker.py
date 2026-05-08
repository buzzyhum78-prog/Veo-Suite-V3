
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

logger = logging.getLogger("VeoSuite.Radar.YouTubeWorker")


class RealYouTubeWorker(QThread):
    progress = pyqtSignal(int)
    status_signal = pyqtSignal(str) # [MỚI] Bắn tin nhắn trạng thái ra ngoài
    # [MỚI] Signal bắn từng video ra ngay lập tức (thay vì chờ cả cục)
    video_found = pyqtSignal(dict) 
    finished_signal = pyqtSignal() # Đổi tên cho đỡ nhầm với finished mặc định của QThread
    #results_ready = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, list_data, rpm_config, time_filter_mode="all", target_region=None, topic_label=None, country_label=None):
        super().__init__()
        self.is_running = True # [MỚI] Cờ để kiểm soát việc dừng chạy
        self.data_queue = list_data
        self.rpm_config = rpm_config
        self.time_filter_mode = time_filter_mode # Lưu chế độ lọc
        self.target_region = target_region # Lưu mã quốc gia (VD: JP, KR, US)
        self.ai_factory = AIFactory()

        # Các biến label này có thể giữ lại để tham khảo (dù logic mới lấy từ gói tin)
        self.topic_label = topic_label
        self.country_label = country_label

    def stop(self):
        self.is_running = False

    # [HÀM MỚI] Dịch thời lượng ISO 8601 (PT1H2M) -> Chuỗi đẹp (01:02:00)
    def parse_duration(self, pt_str):
        import re
        if not pt_str: return "N/A"
        
        # Regex bắt Giờ, Phút, Giây
        h = re.search(r'(\d+)H', pt_str)
        m = re.search(r'(\d+)M', pt_str)
        s = re.search(r'(\d+)S', pt_str)
        
        hours = int(h.group(1)) if h else 0
        mins = int(m.group(1)) if m else 0
        secs = int(s.group(1)) if s else 0
        
        total_sec = hours * 3600 + mins * 60 + secs
        
        # Logic phân loại
        if total_sec < 60: return "Shorts" # Dưới 60s là Shorts
        
        # Format lại: H:MM:SS
        if hours > 0:
            return f"{hours}:{mins:02}:{secs:02}"
        else:
            return f"{mins}:{secs:02}"
        
    # [ĐÃ NÂNG CẤP] Hàm chấm điểm Faceless chuẩn Hunter Engine
    # [HÀM ĐÃ NÂNG CẤP - HỖ TRỢ ĐA NGÔN NGỮ / TOÀN CẦU]
    def check_faceless_viability(self, title, current_keyword):
        """
        Trả về: (is_valid, score)
        - is_valid: True/False (Có vi phạm từ cấm không)
        - score: 0.0 -> 1.0 (Độ tín nhiệm Faceless)
        """
        title_lower = title.lower()
        
        # 1. Hard Reject (Bộ lọc tử thần - Giữ nguyên vì đây là chốt chặn cuối)
        # Nếu dính từ cấm -> Loại thẳng tay
        # (Lưu ý: Nếu muốn kỹ hơn, sau này bạn có thể bổ sung từ cấm tiếng Nhật/Hàn vào list FACELESS_NEGATIVE)
        if any(neg in title_lower for neg in FACELESS_NEGATIVE):
            return False, 0.0
            
        # 2. XÁC ĐỊNH CHIẾN THUẬT LỌC DỰA TRÊN QUỐC GIA (REGION)
        # Các nước dùng chữ tượng hình hoặc ít dùng tiếng Anh trong tiêu đề
        # Cần nới lỏng bộ lọc Positive
        relaxed_markets = [
            'JP', 'KR', 'TW', 'CN', 'HK', # Đông Á (Chữ tượng hình)
            'TH', 'VN', 'LA', 'KH',       # Đông Nam Á
            'RU', 'UA',                   # Đông Âu (Cyrillic)
            'SA', 'QA', 'AE', 'KW', 'EG', 'IQ' # Ả Rập
        ]
        
        # Kiểm tra xem quốc gia hiện tại (self.target_region) có nằm trong nhóm cần nới lỏng không
        # Lưu ý: self.target_region được truyền vào khi khởi tạo Worker
        is_relaxed_market = self.target_region in relaxed_markets
        
        hits = 0
        
        # Check 1: Có chứa từ khóa gốc không? (QUAN TRỌNG NHẤT VỚI ĐA NGÔN NGỮ)
        # Nếu bạn tìm "Mèo cute" (bằng tiếng Nhật) mà tiêu đề có chứa từ đó -> +2 điểm uy tín
        if current_keyword.lower() in title_lower:
            hits += 2 
            
        # Check 2: Các từ khóa Faceless tiếng Anh (ASMR, Relax...)
        # Vẫn check để cộng thêm điểm nếu có
        for pos in FACELESS_POSITIVE:
            if pos in title_lower:
                hits += 1
                
        # 3. QUYẾT ĐỊNH ĐIỂM SỐ (NORMALIZE)
        
        if is_relaxed_market:
            # --- CHIẾN THUẬT THỊ TRƯỜNG NGÁCH (NON-ENGLISH) ---
            # Với Nhật/Hàn..., chỉ cần KHÔNG DÍNH TỪ CẤM là đã có thể chấp nhận.
            # Nếu dính thêm từ khóa gốc thì càng tốt.
            
            if hits == 0:
                # Không dính từ khóa gốc, cũng ko có từ tiếng Anh
                # Nhưng vì đã qua được vòng Negative -> Vẫn cho qua mức trung bình khá
                return True, 0.6 
            else:
                # Có dính từ khóa gốc -> Uy tín cao
                return True, 0.9
        else:
            # --- CHIẾN THUẬT THỊ TRƯỜNG ÂU MỸ (US/UK/EU) ---
            # Bắt buộc phải khắt khe hơn vì rác nhiều
            if hits == 0:
                return True, 0.1 # Điểm thấp -> Sẽ bị loại ở vòng filter sau (money_score < 5)
            
            # Tính điểm chuẩn: Max là 1.0
            final_score = min(1.0, hits / 2) # Chia 2 thôi cho dễ đạt điểm cao
            return True, final_score

    # [MỚI] Công thức tính điểm MONEY SCORE (Thay thế V/S Ratio)
    def calculate_money_score(self, views, subs, days_old, faceless_score):
        # 1. Chuẩn hóa tham số
        if days_old < 1: days_old = 1
        if subs < 1: subs = 1 # Tránh chia cho 0
        
        # 2. Tính Velocity (Tốc độ view mỗi ngày)
        velocity = views / days_old
        
        # [MỚI] BỘ LỌC ZOMBIE: Nếu view lẹt đẹt < 10 view/ngày -> Cho 0 điểm luôn
        if velocity < 10: return 0.0

        # 3. Tính Chỉ số Clone (Clone-ability Index)
        # Logic: Kênh càng nhỏ mà View càng to -> Càng dễ bắt chước
        # Kênh > 500k sub mà view to -> Là chuyện thường -> Điểm thấp
        # Kênh < 10k sub mà view to -> Bất thường -> Điểm cao
        
        channel_factor = 1.0
        if subs > 500000: channel_factor = 0.2 # Kênh lớn bị dìm điểm
        elif subs > 100000: channel_factor = 0.5
        elif subs < 10000: channel_factor = 1.5 # Kênh nhỏ được buff điểm
        elif subs < 1000: channel_factor = 2.0 # Kênh siêu nhỏ
        
        # [MỚI] Điều chỉnh: Kênh nhỏ nhưng view cũng phải TƯƠNG ĐỐI thì mới được buff
        # Nếu kênh < 1000 sub mà view < 500 thì cũng không ăn thua
        if subs < 1000 and views < 500: channel_factor = 0.5

        # 4. Công thức tổng hợp (0 - 100)
        # Money Score = Log(Velocity) * Channel_Factor * Faceless_Score
        import math
        raw_score = math.log10(velocity + 1) * channel_factor * (faceless_score + 0.5) * 10
        
        # Cap điểm lại ở 100
        return min(round(raw_score, 1), 100)

    # [MỚI] Hàm tìm kiếm chuẩn API (Xử lý vấn đề 1 & 2)
    def _search_youtube_api(self, youtube_service, keyword, published_after=None, region_code=None):
        """Hàm gọi API tìm kiếm với bộ lọc Duration và Region"""
        try:
            # 1. BẢN ĐỒ NGÔN NGỮ (Mapping Region -> Language Code)
            # Đây là chìa khóa để ép YouTube trả về video đúng tiếng bản xứ
            REGION_TO_LANG = {
                # --- TIER 1: KHO BÁU TỶ ĐÔ ---
                "US": "en",       # Hoa Kỳ
                "AU": "en",       # Úc
                "GB": "en",       # Anh
                "CA": "en",       # Canada
                "NZ": "en",       # New Zealand
                "CH": "de",       # Thụy Sĩ (Ưu tiên Đức, hoặc 'fr' nếu muốn Pháp)
                "NO": "no",       # Na Uy

                # --- TIER 2: CHÂU ÂU THỊNH VƯỢNG ---
                "DE": "de",       # Đức
                "NL": "nl",       # Hà Lan
                "SE": "sv",       # Thụy Điển
                "DK": "da",       # Đan Mạch
                "FI": "fi",       # Phần Lan
                "FR": "fr",       # Pháp
                "IE": "en",       # Ireland
                "AT": "de",       # Áo
                "BE": "fr",       # Bỉ (Ưu tiên Pháp)

                # --- TIER 3: CHÂU Á RỒNG HỔ & DẦU MỎ ---
                "JP": "ja",       # Nhật Bản
                "KR": "ko",       # Hàn Quốc
                "TW": "zh-Hant",  # Đài Loan (Phồn thể)
                "HK": "zh-Hant",  # Hồng Kông (Phồn thể)
                "SG": "en",       # Singapore
                "IL": "he",       # Israel (Hebrew)
                "QA": "ar",       # Qatar
                "AE": "ar",       # UAE
                "SA": "ar",       # Ả Rập Xê Út
                "KW": "ar",       # Kuwait

                # --- TIER 4: NAM ÂU & ĐÔNG ÂU ---
                "ES": "es",       # Tây Ban Nha
                "IT": "it",       # Ý
                "PT": "pt",       # Bồ Đào Nha
                "PL": "pl",       # Ba Lan
                "CZ": "cs",       # Séc
                "GR": "el",       # Hy Lạp
                "HU": "hu",       # Hungary
                "RU": "ru",       # Nga
                "TR": "tr",       # Thổ Nhĩ Kỳ

                # --- TIER 5: MỸ LATIN & NAM Á ---
                "BR": "pt",       # Brazil
                "MX": "es",       # Mexico
                "AR": "es",       # Argentina
                "CL": "es",       # Chile
                "IN": "hi",       # Ấn Độ (Ưu tiên Tiếng Hindi để bắt native)
                "ZA": "en",       # Nam Phi

                # --- TIER 6: ĐÔNG NAM Á ---
                "VN": "vi",       # Việt Nam
                "ID": "id",       # Indonesia
                "TH": "th",       # Thái Lan
                "MY": "ms",       # Malaysia
                "PH": "en",       # Philippines (Dùng En hoặc 'tl' cho Tagalog)
                "PK": "ur",       # Pakistan
                "BD": "bn",       # Bangladesh
                "LA": "lo",       # Lào
                "KH": "km",       # Campuchia

                # --- TIER 7: CÁC NƯỚC KHÁC ---
                "UA": "uk",       # Ukraine
                "EG": "ar",       # Ai Cập
                "IQ": "ar",       # Iraq
                "IR": "fa",       # Iran (Persian)
                "NG": "en"        # Nigeria
            }

            search_params = {
                "q": keyword,
                "part": "id,snippet",
                "maxResults": 20,
                "type": "video",
                "order": "viewCount",
                "videoDuration": "any", # <--- FIX 1: Chỉ lấy video > 4 phút (Medium = 4-20p)
                #"regionCode": self.target_region # <--- FIX 2: Ép tìm theo quốc gia (VD: JP ra video Nhật)
            }
            if published_after:
                search_params["publishedAfter"] = published_after
            # [THÊM ĐOẠN NÀY] Ép tìm theo quốc gia của từ khóa đó

            if region_code and len(region_code) == 2 and region_code.upper() != "GLOBAL":
                # 1. Ép vùng lãnh thổ (VD: Tìm tại server Nhật)
                search_params["regionCode"] = region_code

                # 2. Ép ngôn ngữ ưu tiên (VD: Ưu tiên tiếng Nhật)
                # Nếu không có trong map thì mặc định 'en' (Tiếng Anh)
                lang_code = REGION_TO_LANG.get(region_code, "en")
                search_params["relevanceLanguage"] = lang_code

                # [DEBUG LOG] In ra để CEO kiểm tra xem nó có nhận đúng không
                logger.info(f"   >>> API Search Config: Region={region_code} | Lang={lang_code} | Kw='{keyword}'")
            # Gọi API
            search_response = youtube_service.search().list(**search_params).execute()
            return search_response.get('items', [])
        except Exception as e:
            logger.info(f"⚠️ Lỗi tìm kiếm '{keyword}': {e}")
            raise e  
    
    def run(self):
        # Import module chuẩn
        import time, datetime 
        import requests
        from datetime import timedelta, timezone
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError # Để bắt lỗi Quota
        
        logger.info("\n⚡ [DEBUG] WORKER ĐANG CHẠY - CHẾ ĐỘ 'XE TĂNG' (VÉT CẠN) ⚡\n")

        # 1. LOAD KEYS
        raw_keys = self.ai_factory.registry["providers"]["youtube"].get("api_key", "")
        api_keys = [k.strip() for k in raw_keys.replace(",", "\n").split("\n") if k.strip()]
        
        if not api_keys:
            self.error.emit("❌ Hết Key! Vui lòng nhập thêm API Key YouTube vào Admin Tab.")
            return
        
        # Khởi tạo client ban đầu
        current_key_index = 0
        youtube = None
        try:
            youtube = build('youtube', 'v3', developerKey=api_keys[current_key_index])
        except Exception:
            logger.info(f"⚠️ Key đầu tiên lỗi, sẽ thử key tiếp theo trong vòng lặp.")

        # 2. XÁC ĐỊNH CHIẾN LƯỢC QUÉT (SMART FALLBACK STRATEGY)
        # Tạo ra các "Tầng" quét dựa trên lựa chọn của CEO
        # Cấu trúc: (Tên hiển thị, Số ngày lùi lại) - None là mọi lúc
        scan_stages = []
        if "7 ngày" in self.time_filter_mode:
            scan_stages = [("7 Ngày", 7), ("30 Ngày", 30), ("1 Năm", 365), ("Mọi lúc", None)]
        elif "30 ngày" in self.time_filter_mode:
            scan_stages = [("30 Ngày", 30), ("1 Năm", 365), ("Mọi lúc", None)]
        elif "90 ngày" in self.time_filter_mode:
            scan_stages = [("90 Ngày", 90), ("1 Năm", 365), ("Mọi lúc", None)]
        elif "1 năm" in self.time_filter_mode:
            scan_stages = [("1 Năm", 365), ("Mọi lúc", None)]
        else:
            scan_stages = [("Mọi lúc", None)]        

        #final_results = []
        seen_ids = set()
        total_items = len(self.data_queue)
        #current_key_index = 0
        #try: youtube = build('youtube', 'v3', developerKey=api_keys[0])
        #except Exception: pass
        now_utc = datetime.datetime.now(timezone.utc)

        # --- VÒNG LẶP TỪ KHÓA ---
        for idx, item in enumerate(self.data_queue):
            if not self.is_running: break
            
            # [MỚI] Bóc tách thông tin từ gói hàng
            kw = item['keyword']
            target_region = item.get('country_code', 'GLOBAL') # Mã nước (VD: US)
            display_country = item.get('country_name', 'Global') # Tên nước (VD: Hoa Kỳ)
            target_topic = item.get('topic', 'General') # Chủ đề
            meaning = item.get('meaning', '')

            current_region_code = target_region if target_region != "GLOBAL" else None

            # Cờ đánh dấu đã tìm thấy video chưa (để dừng quét các mốc thời gian xa hơn)
            found_video_for_keyword = False

            for stage_name, days_back in scan_stages:
                if not self.is_running: break 
                if found_video_for_keyword: break # Nếu đã tìm thấy ở 7 ngày thì thôi 30 ngày (Tiết kiệm)
                self.status_signal.emit(f"🔍 [{idx+1}/{total_items}] {kw} | ⏳ Quét {stage_name} tại {self.target_region}...")

                published_after = None
                if days_back:
                    published_after = (datetime.datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%dT%H:%M:%SZ")

                # --- CƠ CHẾ RETRY KEY (VÒNG LẶP NGUY HIỂM - ĐÃ FIX) ---
                # Biến này để đếm số lần thử trong lượt này
                attempts_with_current_config = 0
                max_attempts = len(api_keys) + 2 # Cho phép thử hết key + dự phòng

                while attempts_with_current_config < max_attempts:
                    # [CHỐT CHẶN 3] Kiểm tra Hủy (QUAN TRỌNG NHẤT)
                    if not self.is_running: break

                #retry_count = 0
                #while retry_count < len(api_keys):
                    # Check youtube client
                    if youtube is None:
                        try:
                            youtube = build('youtube', 'v3', developerKey=api_keys[current_key_index])
                        except Exception:
                            logger.info("⚠️ Lỗi khởi tạo Key, thử key kế...")
                            current_key_index = (current_key_index + 1) % len(api_keys)
                            attempts_with_current_confi += 1
                            continue

                    try:
                        # GỌI API 1: TÌM KIẾM VIDEO ID
                        video_items = self._search_youtube_api(youtube, kw, published_after, current_region_code)
                        
                        if not video_items: 
                            # logger.info(f"   ⚠️ Key {current_key_index} trả về 0 kết quả cho '{kw}'.")
                            break # Key sống nhưng ko có data -> Break để sang mốc thời gian khác

                        video_ids = [item['id']['videoId'] for item in video_items]
 
                        # GỌI API 2: LẤY CHI TIẾT
                        vid_response = youtube.videos().list(id=','.join(video_ids), part="statistics,snippet,contentDetails").execute()
                        
                        # GỌI API 3: LẤY KÊNH (Để tính Sub
                        channel_ids = list(set([item['snippet']['channelId'] for item in vid_response['items']]))
                        chan_response = youtube.channels().list(id=','.join(channel_ids), part="statistics").execute()
                        #chan_map = {c['id']: int(c['statistics'].get('subscriberCount', 0)) if not c['statistics'].get('hiddenSubscriberCount') else 0 for c in chan_response['items']}
                        
                        chan_map = {}      # Map lưu Sub (như cũ)
                        chan_avg_map = {}  # Map lưu Trung bình view (Mới)

                        for c in chan_response['items']:
                            c_id = c['id']
                            stats = c['statistics']
                            
                            # 1. Lấy Sub (Logic cũ)
                            subs = int(stats.get('subscriberCount', 0)) if not stats.get('hiddenSubscriberCount') else 0
                            chan_map[c_id] = subs
                            
                            # 2. Tính Avg Views (Mới)
                            total_views = int(stats.get('viewCount', 0))
                            video_count = int(stats.get('videoCount',0))
                            if video_count == 0: video_count = 1
                            chan_avg_map[c_id] = total_views / video_count

                        videos_found_in_batch = 0

                        for vid_item in vid_response.get('items', []):
                            if not self.is_running: break # [CHỐT CHẶN 4]

                            vid_id = vid_item['id']
                            
                            # [FIX TRÙNG LẶP] Nếu ID này đã lấy rồi -> Bỏ qua ngay
                            if vid_id in seen_ids: continue

                            snippet = vid_item['snippet']
                            stats = vid_item['statistics']
                            content_details = vid_item.get('contentDetails', {})

                            # [MỚI] XỬ LÝ THỜI LƯỢNG (DURATION) & LỌC VIDEO NGẮN
                            duration_iso = content_details.get('duration', '')
                            
                            # 1. Tính tổng số giây (Dùng Regex xử lý ISO 8601)
                            import re
                            h = re.search(r'(\d+)H', duration_iso)
                            m = re.search(r'(\d+)M', duration_iso)
                            s = re.search(r'(\d+)S', duration_iso)
                            
                            hours = int(h.group(1)) if h else 0
                            mins = int(m.group(1)) if m else 0
                            secs = int(s.group(1)) if s else 0
                            
                            total_seconds = hours * 3600 + mins * 60 + secs
                            
                            # 2. [BỘ LỌC CHIẾN LƯỢC] CHỈ LẤY VIDEO > 3 PHÚT (180s)
                            # Để tập trung vào content kiếm tiền RPM cao (Long-form)
                            if total_seconds < 60: continue 
                            
                            # 3. Tạo chuỗi hiển thị đẹp (VD: 05:30)
                            duration_pretty = f"{hours:02d}:{mins:02d}:{secs:02d}" if hours > 0 else f"{mins:02d}:{secs:02d}"
                        
                            # --- [B] LỌC RÁC FACELESS ---
                            title = snippet['title']
                            is_valid_content, faceless_score = self.check_faceless_viability(title, kw)
                            if not is_valid_content: continue 

                            # --- [C] XỬ LÝ NGÀY THÁNG ---
                            try:
                                pub_date = datetime.datetime.strptime(snippet['publishedAt'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                                delta = now_utc - pub_date
                                days_old = delta.days
                                if days_old < 0: days_old = 0
                                
                                if days_old < 7:
                                    hours = delta.seconds // 3600
                                    recency_label = f"🔥 Mới ({hours}h)" if days_old == 0 else f"🔥 Mới ({days_old} ngày)"
                                elif days_old < 30: recency_label = f"✅ {days_old} ngày"
                                elif days_old > 730: recency_label = f"💀 {days_old} ngày"
                                else: recency_label = f"⚪ {days_old} ngày"
                            except Exception: 
                                days_old = 999; recency_label = "Old"
                            
                            if days_old < 1: days_old = 1
                            views = int(stats.get('viewCount', 0))
                            subs = chan_map.get(snippet['channelId'], 0)
                            
                            # --- [D] TÍNH ĐIỂM & QUYẾT ĐỊNH LẤY ---
                            money_score = self.calculate_money_score(views, subs, days_old, faceless_score)
                            
                            # [QUAN TRỌNG] Logic Outlier
                            avg_channel_view = chan_avg_map.get(snippet['channelId'], 1)
                            if avg_channel_view < 1: avg_channel_view = 1
                            outlier_score = round(views / avg_channel_view, 1)
                            
                            # [QUAN TRỌNG - NỚI LỎNG TUYỆT ĐỐI]
                            # Chỉ loại bỏ những video CỰC KỲ TỆ (điểm < 5). 
                            # Còn lại lấy hết để đưa ra bảng cho CEO chọn.
                            # Vì thị trường Nhật/Hàn view ban đầu có thể thấp.
                            if money_score < 1: continue

                            # --- ĐÓNG GÓI ---
                            display_title = title
                            if faceless_score >= 0.6: display_title = f"🎭 {title}"
                            
                            # Phân loại hiển thị màu
                            rating_text = "⚪ Thường"; rating_color = "#aaaaaa"
                            if money_score >= 80: rating_text = "💎 GEM"; rating_color = "#00ffea"
                            elif money_score >= 40: rating_text = "🔥 HOT"; rating_color = "#f1c40f"
                            elif money_score >= 10: rating_text = "✅ OK"; rating_color = "#2ecc71" # Hạ chuẩn OK xuống 10

                            multiplier = 3.0 if any(x in title.lower() for x in ['crypto', 'invest', 'finance']) else 1.0
                            # [MỚI] Tính RPM động dựa trên Quốc gia của từ khóa
                            current_rpm = 1.0
                            region_check = current_region_code if current_region_code else "GLOBAL"
                            
                            # Tier 1
                            if region_check in ["US", "AU", "GB", "CA", "CH", "NO"]: current_rpm = 15.0
                            # Tier 2 & 3
                            elif region_check in ["DE", "FR", "JP", "KR", "SE", "AE", "SG"]: current_rpm = 8.0
                            # Tier thấp hơn
                            elif region_check in ["VN", "TH", "ID", "IN", "PH"]: current_rpm = 0.5
                            
                            thumbnails = snippet.get('thumbnails', {})
                            thumb_url = thumbnails.get('maxres', thumbnails.get('high', thumbnails.get('medium')))['url']
                            try: thumb_bytes = requests.get(thumb_url, timeout=3).content
                            except Exception: thumb_bytes = None
                            
                            video_data = {
                                "id": vid_id, 
                                "title": display_title, 
                                "raw_title": title,
                                "topic_label": target_topic,     # <--- THÊM
                                "country_label": display_country, # <--- THÊM
                                "duration": duration_pretty,         # <--- THÊM
                                "published_at": snippet['publishedAt'].split("T")[0], 
                                "days_old": days_old, 
                                "views_per_day": views / days_old,
                                "recency": recency_label, # <--- Đã có số ngày
                                "views": views, 
                                "subs": subs, 
                                "vs_ratio": (views / subs) if subs > 0 else 0.0,
                                "rating": rating_text,
                                "color": rating_color,
                                "revenue": (views / 1000) * current_rpm, # <--- Sửa: Dùng current_rpm
                                "outlier_score": outlier_score,
                                "thumb": thumb_url, 
                                "thumb_bytes": thumb_bytes,
                                "keyword": kw, 
                                "meaning_vi": meaning,
                                "link": f"https://www.youtube.com/watch?v={vid_id}",
                                "money_score": money_score
                            }
                            
                            # [THAY ĐỔI QUAN TRỌNG] Bắn tín hiệu NGAY LẬP TỨC
                            self.video_found.emit(video_data)
                            seen_ids.add(vid_id)
                            #found_valid_video_in_this_batch = True
                            videos_found_in_batch += 1      # Đếm là đã tìm thấy 1 video

                            # [QUAN TRỌNG] Đánh dấu ID này đã lấy
                            #seen_ids.add(vid_id)
                            # [QUAN TRỌNG: THÊM DÒNG NÀY NGAY SAU VÒNG LẶP FOR vid_item]
                            # Để thoát khỏi vòng lặp Retry API nếu đã tìm thấy video
                        if videos_found_in_batch > 0:
                            found_video_for_keyword = True # Đánh dấu để break luôn loop thời gian
                            break
                            # API OK -> Break vòng lặp retry Key
                        # Nếu API trả về nhưng không có video nào thỏa mãn bộ lọc -> Cũng coi là xong, break loop retry
                        break

                    except Exception as e:
                        error_msg = str(e)
                        attempts_with_current_config += 1

                        # --- XỬ LÝ LỖI ---
                        if "quota" in error_msg.lower() or "403" in error_msg:
                            logger.info(f"⚠️ Key {current_key_index} HẾT HẠN (Quota). Đổi Key...")
                            current_key_index = (current_key_index + 1) % len(api_keys)
                            youtube = None # Reset để vòng lặp sau init lại
                            
                            # Nếu hết sạch key trong danh sách
                            if current_key_index== 0 and attempts_with_current_config >= len(api_keys):
                                self.error.emit("❌ Hết sạch Key! Dừng quét.")
                                self.is_running = False # Dừng toàn bộ
                                return 
                            
                            # Đổi key mới
                            try: youtube = build('youtube', 'v3', developerKey=api_keys[current_key_index])
                            except Exception: pass
                            
                        elif "Unable to find" in error_msg or "Connection" in error_msg:
                            logger.info(f"⚠️ Lỗi mạng. Đợi 5s...")
                            time.sleep(5)
                            # Không tăng index, thử lại key cũ
                        else:
                            logger.info(f"⚠️ Lỗi lạ ({error_msg}). Bỏ qua keyword này.")
                            break # Lỗi lạ thì bỏ qua từ khóa này luôn, sang từ khóa tiếp theo

            self.progress.emit(int((idx + 1) / total_items * 100))

        if self.is_running:
            # Nếu chạy hết vòng lặp mà không bị ai Stop -> Báo hoàn tất
            self.status_signal.emit("✅ Đã hoàn tất quét!")
        else:
            # Nếu bị Stop giữa chừng -> Báo đã dừng
            self.status_signal.emit("🛑 Đã dừng quét theo yêu cầu!")
        self.finished_signal.emit() # Báo xong

# =============================================================================
# 4. GIAO DIỆN CHÍNH (RADAR TAB - THE FUNNEL)
# =============================================================================

