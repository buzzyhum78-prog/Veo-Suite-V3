
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

class SpyMetadataWorker(QThread):
    finished = pyqtSignal(dict) # Trả về gói dữ liệu đầy đủ

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        import os, re, time
        import yt_dlp
        import requests
        import html # Để giải mã ký tự &amp; trong XML
        import xml.etree.ElementTree as ET # Để đọc XML
        from PyQt6.QtGui import QImage, QPixmap
        # [MỚI] Import thư viện Transcript
        from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
        # [MÃ CẤP CỨU FIX SUB] Tự động gỡ bản lỗi và cài bản chuẩn 0.6.2
        import sys, subprocess, pkg_resources, json
        try:
            # Kiểm tra phiên bản hiện tại
            version = pkg_resources.get_distribution("youtube-transcript-api").version
            # Nếu là bản 1.2.3 quái lạ kia hoặc không phải 0.6.x -> Cài lại ngay
            if version == "1.2.3" or not version.startswith("0.6"):
                print(f"⚠️ Phát hiện bản youtube-transcript-api lạ ({version}). Đang cài lại bản chuẩn...")
                raise ImportError("Wrong version")
                
            from youtube_transcript_api import YouTubeTranscriptApi
            if not hasattr(YouTubeTranscriptApi, 'list_transcripts'):
                raise ImportError("Missing method")
                
        except (ImportError, Exception):
            # Lệnh cưỡng chế cài lại
            print("⏳ Đang cài đặt lại thư viện Subtitle...")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "uninstall", "-y", "youtube-transcript-api"])
                subprocess.check_call([sys.executable, "-m", "pip", "install", "youtube-transcript-api==0.6.2"])
                print("✅ Đã cài xong bản 0.6.2! Vui lòng khởi động lại Tool.")
                # Gửi tín hiệu báo user khởi động lại
                self.finished.emit({"success": False, "error": "Đã cập nhật thư viện Sub. Vui lòng TẮT TOOL và mở lại để có hiệu lực!"})
                return
            except Exception as e:
                print(f"Lỗi cài đặt: {e}")
        
        # [MỚI] Load Proxy từ cấu hình chung (nếu CEO đã bật bên Admin)
        # Giả sử biến PROXY_CONFIG đã được load ở đầu file
        proxy_opts = {}
        http_proxy = ""
        if "PROXY_CONFIG" in globals() and PROXY_CONFIG.get("USE_PROXY"):
             http_proxy = PROXY_CONFIG["HTTP_PROXY"]
             # Format cho thư viện transcript
             proxy_opts = {"http": PROXY_CONFIG["HTTP_PROXY"], "https": PROXY_CONFIG["HTTPS_PROXY"]}
             print(f"🕵️ Spy đang chạy qua Proxy: {http_proxy}")

        # [QUAN TRỌNG] ĐƯỜNG DẪN COOKIES
        # Tool sẽ tự tìm file cookies.txt ở thư mục gốc
        cookies_path = "cookies.txt" if os.path.exists("cookies.txt") else None
        
        if cookies_path:
            print(f"🍪 Đã tìm thấy Cookies: {cookies_path} -> Kích hoạt chế độ User thật!")
        else:
            print("⚠️ Không thấy 'cookies.txt'. Một số video có thể không lấy được Sub.")

        # Cấu hình yt-dlp (Lấy nhanh, không tải video)
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False, # Phải để False mới lấy được chi tiết (Tags, Desc)
            'skip_download': True,
            'cookiefile': 'cookies.txt', # [Mẹo] Nếu có file cookies.txt thì để vào để tránh bị Google chặn
            # ---> Thêm đoạn này để lấy Link Sub (nhưng chưa tải file) <---
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': ['all'],
        }
        # Thêm Proxy cho yt-dlp
        if http_proxy: ydl_opts['proxy'] = http_proxy
        if cookies_path: ydl_opts['cookiefile'] = cookies_path # Nạp Cookies cho yt-dlp

        data = {"success": False}
        full_transcript = ""
        video_description = "" # Lưu description để dùng fallback
        yt_dlp_sub_info = None # Biến để lưu info sub

        # --- GIAI ĐOẠN 1: LẤY THÔNG TIN CƠ BẢN (TITLE, DESC, THUMB) ---
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
            
            video_id = info.get('id')
            video_description = info.get("description", "") or "" # Lưu lại

            # [QUAN TRỌNG] Lưu lại thông tin sub để lát dùng cho Cách 2
            # Nó chứa các Link tải sub (json3, vtt...)
            yt_dlp_sub_info = info.get('requested_subtitles')

            # Format lại số liệu
            view_count = info.get('view_count', 0)
            like_count = info.get('like_count', 0)
            duration = info.get('duration') or 0

            data = {
                "success": True,
                "id": video_id,
                "title": info.get("title", "Unknown Video"),
                "channel_name": info.get("uploader", "Unknown Channel"),
                "views": view_count,
                "upload_date": info.get("upload_date", ""),
                "duration": info.get("duration", 0),
                "description": info.get("description", ""),
                "tags": info.get("tags", []),
                "thumbnail_url": info.get("thumbnail", ""),
                "webpage_url": info.get("webpage_url", self.url),
                "stats_text": f"{int(view_count):,} views • {int(like_count):,} likes",
                "transcript": "(Đang tải...)" # Placeholder
            }

            # Tải ảnh Thumb ngay tại đây
            if data["thumbnail_url"]:
                try:
                    resp = requests.get(data["thumbnail_url"], timeout=5, proxies=proxy_opts if http_proxy else None)
                    if resp.status_code == 200:
                        img = QImage()
                        img.loadFromData(resp.content)
                        data["pixmap_thumb"] = QPixmap.fromImage(img)
                except: 
                    data["pixmap_thumb"] = None

        except Exception as e:
            print(f"❌ Lỗi yt-dlp: {e}")
            self.finished.emit({"success": False, "error": str(e)})
            return # Dừng luôn nếu không lấy được info cơ bản
        
        # ------------------------------------------------------------------
        # PHẦN 4: LẤY TRANSCRIPT - CHIẾN THUẬT "HYBRID ENGINE"
        # ------------------------------------------------------------------
        try:
            # --- CÁCH 1: DÙNG API WRAPPER (NHANH NHẤT) ---
            print("🚀 [Try 1] Đang thử lấy Sub bằng API...")
            from youtube_transcript_api import YouTubeTranscriptApi
            from youtube_transcript_api.formatters import TextFormatter 
            
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id, proxies=proxy_opts if http_proxy else None, cookies=cookies_path)
            
            transcript = None
            try: transcript = next(iter(transcript_list._manually_created_transcripts.values()))
            except:
                try: transcript = next(iter(transcript_list._generated_transcripts.values()))
                except: pass

            if transcript:
                formatter = TextFormatter()
                full_transcript = formatter.format_transcript(transcript.fetch())
                print("✅ Lấy Sub thành công bằng API!")
                
        except Exception as e1:
            print(f"⚠️ Cách 1 thất bại ({str(e1)}). Chuyển sang Cách 2...")
            
            # --- CÁCH 2: DÙNG YT-DLP URL (FALLBACK) ---
            if yt_dlp_sub_info:
                print("🚀 [Cách 2] Đang tải Sub từ Link yt-dlp...")
                import re 
                import json
                # 1. Tìm ngôn ngữ ưu tiên (Việt -> Anh -> Nhật -> Hàn)
                target_sub = None
                for lang in ['vi', 'en', 'ja', 'ko']:
                    if lang in yt_dlp_sub_info:
                        target_sub = yt_dlp_sub_info[lang]
                        break
                
                # 2. Nếu không có, lấy bất kỳ cái nào tìm thấy
                if not target_sub and yt_dlp_sub_info:
                    target_sub = next(iter(yt_dlp_sub_info.values()))

                # 3. Tiến hành tải (Bắt buộc phải có Try/Except ở đây)
                if target_sub and 'url' in target_sub:
                    try:
                        sub_url = target_sub['url']
                        p_req = {"http": http_proxy, "https": http_proxy} if http_proxy else None
                        
                        # [QUAN TRỌNG] Headers giả danh Chrome
                        headers = {
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                        }
                        
                        # Gọi request có Timeout 10s
                        r = requests.get(sub_url, proxies=p_req, headers=headers, timeout=10)
                        
                        if r.status_code == 200:
                            raw_sub = r.text
                            full_transcript = ""

                            # [DEBUG] Xem header để biết định dạng gì
                            print(f"📦 Header Sub: {raw_sub[:50].replace(chr(10), ' ')}...")

                            # --- XỬ LÝ ĐỊNH DẠNG JSON3 (Youtube mới) ---
                            if "events" in raw_sub and "segs" in raw_sub:
                                try:
                                    json_data = json.loads(raw_sub)
                                    lines = []
                                    for event in json_data.get('events', []):
                                        if 'segs' in event:
                                            # Nối các đoạn text nhỏ lại
                                            line_text = "".join([s.get('utf8', '') for s in event['segs']])
                                            line_text = line_text.replace('\n', ' ').strip()
                                            if line_text: lines.append(line_text)
                                    full_transcript = " ".join(lines)
                                    print("-> Đã parse theo định dạng JSON3.")
                                except: pass
                            
                            # --- TRƯỜNG HỢP B: XML / SRV1 (Youtube Cổ điển - HAY GẶP NHẤT) ---
                            if not full_transcript and ("<text" in raw_sub or "<p" in raw_sub):
                                try:
                                    import xml.etree.ElementTree as ET
                                    import html
                                    # Xử lý chuỗi XML thô
                                    root = ET.fromstring(raw_sub)
                                    # Lấy nội dung trong thẻ <text>
                                    lines = []
                                    for child in root.findall('.//text'):
                                        if child.text and child.text.strip() > 0:
                                            # Giải mã ký tự đặc biệt (&amp; -> &) và xóa xuống dòng                                
                                            clean_line = html.unescape(child.text).replace('\n', ' ').strip()
                                            if "{" not in clean_line:  # Bỏ qua nếu dòng chứa JSON lạ
                                                lines.append(clean_line)                                            
                                    full_transcript = " ".join(lines)
                                    print("-> Đã parse theo định dạng XML (srv1).")
                                except Exception as e_xml:
                                    print(f"-> Lỗi parse XML: {e_xml}")

                            # --- TRƯỜNG HỢP C: VTT / RAW (Xử lý dòng-từng-dòng chuẩn xác) ---
                            if not full_transcript:
                                try:
                                    # 1. Xóa toàn bộ thẻ nằm trong ngoặc nhọn <...> (HTML, XML tags, Karaoke)
                                    text_clean = re.sub(r'<[^>]+>', ' ', raw_sub)
                                    
                                    # 2. Xóa Header rác của WebVTT
                                    text_clean = re.sub(r'WEBVTT', '', text_clean)
                                    text_clean = re.sub(r'Kind:.*', '', text_clean)
                                    text_clean = re.sub(r'Language:.*', '', text_clean)
                                    
                                    # 3. Xóa Timecode (00:00:00.000 --> ...)
                                    # Regex này diệt mọi thể loại số dạng thời gian
                                    text_clean = re.sub(r'\d{2}:\d{2}:\d{2}[\.,]\d{3}.*?', '', text_clean)
                                    
                                    # 4. Xóa tham số định dạng (align:start position:0%)
                                    text_clean = re.sub(r'[a-z]+:\S+', '', text_clean)

                                    # 5. Xử lý từng dòng để lọc trùng
                                    lines = [l.strip() for l in text_clean.split('\n') if l.strip()]
                                    unique_lines = []
                                    last_line = ""
                                    
                                    for line in lines:
                                        # Bỏ qua các dòng quá ngắn hoặc toàn ký tự lạ
                                        if len(line) < 2: continue
                                        if "-->" in line: continue
                                        
                                        if line != last_line:
                                            unique_lines.append(line)
                                            last_line = line
                                            
                                    full_transcript = " ".join(unique_lines)
                                    print("-> Đã parse theo thuật toán Universal Cleaner.")
                                except Exception as e_univ:
                                    print(f"Lỗi Universal Cleaner: {e_univ}")

                            if full_transcript and len(full_transcript) > 50:
                                print(f"✅ [Cách 2] Thành công! Độ dài: {len(full_transcript)} ký tự.")
                            else:
                                print(f"⚠️ [Cách 2] Thất bại. Raw sub không chứa nội dung text.")

                    except Exception as e_sub:
                        print(f"❌ [Cách 2] Lỗi tải/xử lý sub: {e_sub}")
                        # Không làm gì cả, để nó tự trôi xuống Fallback (Description)

        # ------------------------------------------------------------------
        # PHẦN 5: XỬ LÝ KẾT QUẢ CUỐI CÙNG (SMART FALLBACK)
        # ------------------------------------------------------------------
        full_transcript = full_transcript.strip()

        if full_transcript:
            data["transcript"] = full_transcript
        else:
            # [QUAN TRỌNG] Nếu video không có sub (Lofi, Music...)
            # Thay vì để rỗng khiến AI bị ngu, ta lấy DESCRIPTION đắp vào
            print("💡 Không tìm thấy Sub -> Dùng Description thay thế cho AI.")
            # [NÂNG CẤP] BỘ LỌC MÁY CHÉM NGAY TẠI NGUỒN
            import re
            raw_desc = video_description or ""
            
            # --- CHIẾN THUẬT: DUYỆT BINH TỪNG DÒNG (LINE-BY-LINE) ---
            # Tách thành các dòng để xử lý, thay vì xử lý nguyên cục
            lines = raw_desc.split('\n')
            clean_lines = []
            
            # --- TỪ ĐIỂN RÁC ĐA QUỐC GIA (GLOBAL JUNK FILTER V8.0 - SOFT CTA INCLUDED) ---
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

            # 2. REGEX DIỆT KÝ TỰ HÌNH HỌC & ĐƯỜNG KẺ (UNICODE BLOCK)
            # Diệt sạch: ▬▬▬▬, ►, ■, ★, ➔, ...
            symbol_pattern = r'[\u2500-\u257F\u2580-\u259F\u25A0-\u25FF\u2600-\u26FF\u2700-\u27BF]+'

            # --- VÒNG LẶP SỬ DỤNG INDEX ĐỂ "NHÌN TRƯỚC" (LOOK-AHEAD) ---
            N = len(lines)
            i = 0
            while i < N:
                line_str = lines[i] # Dòng gốc (để check khoảng trắng/số lượng ký tự nếu cần)

                # A. Tẩy trần ký tự rác hình học ngay lập tức
                line_clean = re.sub(symbol_pattern, '', line_str).strip()
                
                # B. Nếu tẩy xong mà dòng thành rỗng -> Vứt
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
                # Ưu tiên xóa cái này sớm vì nó vô nghĩa
                if re.match(r'^[-=_*~—–]+$', line_clean):
                    i += 1; continue

                # 4. [MÁY CHÉM 3 - TỔ HỢP] Diệt Hashtag (#) & Handle (@) & Tag Cloud
                # A. Bắt Handle (@user) ở đầu dòng
                if line_clean.startswith("@") or line_clean.startswith("- @") or line_clean.startswith("• @"):
                    i += 1; continue
                
                # Diệt dòng chứa email (kể cả khi không có http)
                if "@" in line_clean and ("mail" in line_lower or ".com" in line_lower):
                    i += 1; continue
                
                # B. Bắt Hashtag ở đầu dòng
                if line_clean.startswith("#"):
                    i += 1; continue

                # C. [TUYỆT CHIÊU] Diệt "Đám mây Hashtag" (Tag Cloud)
                # Nếu dòng chứa từ 2 dấu # trở lên -> Chắc chắn là spam tag -> Xóa
                if line_str.count("#") >= 2:
                    i += 1; continue

                # D. Diệt dòng chỉ chứa toàn hashtag (Dù chỉ 1 cái # nhưng đứng một mình hoặc kèm ít chữ)
                # Ví dụ: "Hamster #pet" -> Xóa
                # Logic: Xóa hết các từ bắt đầu bằng #, nếu phần còn lại quá ngắn (< 2 ký tự) -> Xóa
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
                # Logic: Dòng ngắn + Không dấu kết câu + Dòng sau là Link hoặc Viết Hoa Tiêu Đề
                words = line_clean.split()
                if len(words) < 15 and not line_clean.endswith(('.', '!', '?', '"', '”', ')')):
                    is_next_link = False
                    # Nhìn trộm dòng kế tiếp
                    if i + 1 < N:
                        next_line = lines[i+1]
                        if "http://" in next_line or "https://" in next_line or "www." in next_line:
                            is_next_link = True
                    
                    if is_next_link:
                        i += 1; continue # Xóa dòng này vì nó là tiêu đề của link sau
                    
                    # Nếu không có link sau, nhưng nhìn nó giống tiêu đề (Viết Hoa > 50% số từ) -> Xóa
                    upper_words = sum(1 for w in words if w[0].isupper())
                    if len(words) > 0 and (upper_words / len(words) > 0.5):
                        i += 1; continue

                # 8. [MÁY CHÉM 7] Dòng quá ngắn vô nghĩa
                # Trừ khi nó là tiêu đề chương (Intro, Body...) nhưng thường < 3 ký tự là rác
                if len(line_clean) < 3: # VD: ".", "Hi", "ky"
                     i += 1; continue

                # --- CHỐT HẠ: Sống sót qua 8 cửa ải -> Được giữ lại ---
                clean_lines.append(line_clean)
                i += 1
            
            # Ghép lại thành văn bản
            clean_desc = "\n".join(clean_lines)
            
            # Cắt ngắn 2000 ký tự (Nội dung chính thường nằm ở đầu)
            final_pseudo_transcript = clean_desc[:2000]

            if final_pseudo_transcript:
                data["transcript"] = (
                    f"[KHÔNG CÓ LỜI THOẠI - DỮ LIỆU TỪ MÔ TẢ VIDEO]\n"
                    f"Lưu ý cho AI: Hãy phân tích DNA video dựa trên Tiêu đề, Thời lượng và Mô tả dưới đây:\n"
                    f"{final_pseudo_transcript}"
                )
            else:
                data["transcript"] = (
                    "[KHÔNG CÓ DỮ LIỆU]\n"
                    "Lưu ý cho AI: Video này không có Sub và không có Mô tả. "
                    "Hãy phân tích dựa trên Tiêu đề và các chỉ số."
                )

        self.finished.emit(data)

# =============================================================================
# MAIN ENTRY POINT
# =============================================================================
if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    window = RadarTab()
    window.resize(1100, 750)
    window.show()
    sys.exit(app.exec())