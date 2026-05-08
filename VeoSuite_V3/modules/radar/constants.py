
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
import json

# =============================================================================
# 0. CẤU HÌNH HỆ THỐNG (TỰ ĐỘNG ĐỌC TỪ ADMIN)
# =============================================================================
def load_proxy_settings():
    """Hàm đọc cấu hình Proxy do Tab Admin lưu"""
    config_path = "VEO_DB/proxy_config.json"
    default_config = {
        "use_proxy": False,
        "http_proxy": "",
        "https_proxy": ""
    }
    
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Map key từ file json sang key mà code đang dùng
                return {
                    "USE_PROXY": data.get("use_proxy", False),
                    "HTTP_PROXY": data.get("http_proxy", ""),
                    "HTTPS_PROXY": data.get("https_proxy", "")
                }
        except: pass
    return default_config

# Gọi hàm ngay khi khởi động file để lấy cấu hình mới nhất
PROXY_CONFIG = load_proxy_settings()

# =============================================================================
# 1. DỮ LIỆU CẤU HÌNH (CONSTANTS)
# =============================================================================
COUNTRIES_FULL = BATCH_LANGUAGES =[
    "--- TIER 1: KHO BÁU TỶ ĐÔ (RPM $10 - $35+) ---",
    "🇺🇸 Hoa Kỳ (En) ~$15.5-35.0", 
    "🇦🇺 Úc (En) ~$12.0-28.0",
    "🇨🇭 Thụy Sĩ (De/Fr) ~$18.5-40.0", 
    "🇬🇧 Anh Quốc (En) ~$10.0-25.0", 
    "🇨🇦 Canada (En) ~$10.5-24.0", 
    "🇳🇴 Na Uy (No) ~$12.5-26.0",
    "🇳🇿 New Zealand (En) ~$9.5-22.0",

    "--- TIER 2: CHÂU ÂU THỊNH VƯỢNG (RPM $6 - $18) ---",
    "🇩🇪 Đức (De) ~$7.5-18.0", 
    "🇳🇱 Hà Lan (Nl) ~$7.2-16.5",
    "🇸🇪 Thụy Điển (Sv) ~$7.0-16.0", 
    "🇩🇰 Đan Mạch (Da) ~$7.5-17.0", 
    "🇫🇮 Phần Lan (Fi) ~$6.8-15.5",
    "🇫🇷 Pháp (Fr) ~$6.2-15.0", 
    "🇮🇪 Ireland (En) ~$7.0-16.0", 
    "🇦🇹 Áo (De) ~$6.5-15.0", 
    "🇧🇪 Bỉ (Fr/Nl) ~$6.0-14.5",

    "--- TIER 3: CHÂU Á RỒNG HỔ & DẦU MỎ (RPM $4 - $12) ---",
    "🇶🇦 Qatar (Ar) ~$5.5-13.0", 
    "🇦🇪 UAE (Ar/En) ~$4.8-11.0",
    "🇸🇬 Singapore (En) ~$5.5-13.5", 
    "🇯🇵 Nhật Bản (Ja) ~$4.5-11.0", 
    "🇰🇷 Hàn Quốc (Ko) ~$4.0-10.0", 
    "🇮🇱 Israel (He) ~$4.2-9.8",
    "🇸🇦 Ả Rập Xê Út (Ar) ~$3.5-8.5", 
    "🇭🇰 Hồng Kông (Zh) ~$3.8-9.5",
    "🇹🇼 Đài Loan (Zh) ~$2.8-7.0",
    "🇰🇼 Kuwait (Ar) ~$3.2-8.0",

    "--- TIER 4: NAM ÂU & ĐÔNG ÂU (RPM $2 - $8) ---",
    "🇪🇸 Tây Ban Nha (Es) ~$2.8-7.2", 
    "🇮🇹 Ý (It) ~$3.2-7.8", 
    "🇵🇹 Bồ Đào Nha (Pt) ~$2.2-5.8",
    "🇵🇱 Ba Lan (Pl) ~$2.0-5.0", 
    "🇨🇿 Séc (Cs) ~$2.1-5.2", 
    "🇬🇷 Hy Lạp (El) ~$1.8-4.5", 
    "🇭🇺 Hungary (Hu) ~$1.5-4.0",
    "🇷🇺 Nga (Ru) ~$0.8-2.5", 
    "🇹🇷 Thổ Nhĩ Kỳ (Tr) ~$0.9-2.8",

    "--- TIER 5: MỸ LATIN & NAM Á (RPM $1 - $5) ---",
    "🇧🇷 Brazil (Pt) ~$1.5-4.8", 
    "🇲🇽 Mexico (Es) ~$1.2-4.0", 
    "🇦🇷 Argentina (Es) ~$0.8-2.8", 
    "🇨🇱 Chile (Es) ~$1.5-3.8",
    "🇮🇳 Ấn Độ (Hi/En) ~$0.4-1.8", 
    "🇿🇦 Nam Phi (En) ~$2.5-6.0",

    "--- TIER 6: ĐÔNG NAM Á (VOLUME LỚN, RPM THẤP <$3) ---",
    "🇻🇳 Việt Nam (Vi) ~$0.3-1.5", 
    "🇮🇩 Indonesia (Id) ~$0.4-1.9", 
    "🇵🇭 Philippines (En) ~$0.6-2.4", 
    "🇹🇭 Thái Lan (Th) ~$0.5-2.0", 
    "🇲🇾 Malaysia (Ms) ~$1.2-3.8", 
    "🇵🇰 Pakistan (Ur) ~$0.2-1.0", 
    "🇧🇩 Bangladesh (Bn) ~$0.2-0.9",
    "🇱🇦 Lào (Lo) ~$0.2-0.8", 
    "🇰🇭 Campuchia (Km) ~$0.3-0.9",

    "--- TIER 7: CÁC NƯỚC KHÁC (HỖ TRỢ FULL) ---",
    "🇮🇷 Iran (Fa) ~Global/VPN", 
    "🇮🇶 Iraq (Ar) ~Global/VPN", 
    "🇪🇬 Ai Cập (Ar) ~$0.5-1.8", 
    "🇳🇬 Nigeria (En) ~$0.6-2.0",
    "🇺🇦 Ukraine (Uk) ~$0.8-2.2"
]

TOPICS_FULL = BATCH_NICHE_IDEAS = [
    "--- 🧬 FORMAT 1: RELAX / AMBIENT / LOOP ---",
    "🌧️ Rain & Thunder (Mưa & Sấm)", "🌊 Ocean & Water (Sóng nước)", 
    "🔥 Campfire & Fireplace (Lửa trại)", "❄️ Snow & Winter (Tuyết rơi)", 
    "🧘 Meditation & Healing (Thiền/Chữa lành)", "🎧 Lofi & Study Music (Nhạc học tập)",
    "🔊 ASMR No Talking (Âm thanh không lời)",

    "--- 🧠 FORMAT 2: FACTS / KNOWLEDGE / EXPLAIN ---",
    "👽 Space & Universe (Vũ trụ)", "🌍 Geography & Maps (Địa lý)", 
    "⏳ History & Ancient (Lịch sử)", "🦁 Animal Facts (Sự thật động vật)", 
    "💡 Crazy Inventions (Phát minh lạ)", "🧠 Psychology & Human (Tâm lý học)",
    "💰 Finance & Crypto (Tài chính)",

    "--- 👻 FORMAT 3: STORY / NARRATIVE (Horror/Mystery) ---",
    "👻 Scary Stories (Chuyện ma)", "🕵️ True Crime (Vụ án)", 
    "🏺 Unsolved Mysteries (Bí ẩn)", "👾 Creepypasta/Reddit Horror",
    "🚪 Liminal Spaces (Không gian lạ)",

    "--- 🐼 FORMAT 4: VISUAL COMPILATION (Cute/Funny) ---",
    "🐱 Cute Cats (Mèo)", "🐶 Funny Dogs (Chó)", "🐹 Hamsters/Capybara",
    "🦁 Wild Life (Động vật hoang dã)", "😂 Oddly Satisfying (Thỏa mãn thị giác)",

    "--- 🤖 FORMAT 5: TECH & FUTURE ---",
    "🤖 AI & Robots (Trí tuệ nhân tạo)", "🚀 Future Tech (Công nghệ tương lai)",
    "💻 Coding & Tools (Lập trình/Tool)",

    "--- 📖 FORMAT 6: TEXT & QUOTES ---",
    "💬 Reddit Confessions (Tâm sự)", "📜 Motivational Quotes (Động lực)",
    "🗿 Stoic Philosophy (Triết học)"
]

# [MỚI] TỪ KHÓA FACELESS "DƯƠNG TÍNH" (Nên có)
FACELESS_POSITIVE = [
    # Nhóm Relax / Ambient
    "asmr", "no talking", "satisfying", "relax", "relaxing", "rain", "lofi", 
    "sleep", "study", "focus", "noise", "ambient", "meditation",
    "oddly satisfying", "loop", "endless", "visual loop", "before after",
    
    # Nhóm Story / Content
    "story", "short story", "true story", "reddit story", "aita", "confession", "text story",
    "kể chuyện", "tóm tắt", "sự thật", "bí ẩn", "phim", "review phim", "documentary",
    "case", "crime", "scary", "horror", "tales", "mystery",
    
    # Nhóm Explain / Science / AI
    "explained", "did you know", "what if", "science", "space", "universe",
    "ai", "artificial intelligence", "chatgpt", "automation", "tools",
    "top", "facts", "history", "review", "unboxing", "prediction",
    "finance", "crypto", "bitcoin", "stock", "motivation", "quotes", "stoic",
    
    # Nhóm Tutorial / Gameplay
    "tutorial", "how to", "diy", "craft", "restoration", "gameplay", 
    "no commentary", "silent gameplay", "walkthrough", "quiz", "riddle", "test", "iq"
]

# [MỚI] TỪ KHÓA FACELESS "ÂM TÍNH" (Tuyệt đối tránh - Video rác hoặc Vlog)
FACELESS_NEGATIVE = [
    # Nhóm 18+ / Gợi cảm / Trá hình (Chặn ASMR hôn hít)
    "kiss", "kissing", "licking", "ear licking", "mouth sounds", "wet", 
    "moan", "moaning", "sexy", "hot", "bikini", "girl", "bhabhi", "romance", 
    "girlfriend", "boyfriend", "dating", "love", "18+", "adult",

    # Vlog / Cá nhân hóa
    "vlog", "my day", "daily life", "facecam", "livestream", "live",
    "my reaction", "i tried", "i tested", "i spent", "day in my life", 
    "get ready with me", "grwm", "room tour",
    
    # Face-based trá hình
    "prank", "challenge", "social experiment", "street interview", 
    "asking people", "date", "crush",
    "reaction", "react", "interview", "phỏng vấn", "q&a",
    
    # [MỚI] CHẶN REVIEW PHIM (BẢN QUYỀN CAO)
    "review phim", "tóm tắt phim", "recap", "movie review", "film review", 
    "phim hay", "full movie", "full hd", "vietsub", "thuyết minh", "tập 1", "tập full",

    # Rác / Bản quyền / Bán hàng
    "shorts", "#shorts", "tiktok", # Loại bỏ Shorts rác theo yêu cầu
    "offical music video", "cover", "vietsub", "full album", "mv",
    "review shopee", "review lazada", "review tiki", "haul", "unboxing shopee"
]

PLATFORMS = ["Youtube Long", "Youtube Shorts", "Facebook Reels", "TikTok", "Google Search", "Threads"]
THOI_GIAN_QUET = ["7 ngày (Hot)", "30 ngày (Breakout)", "90 ngày (Ổn định)", "1 năm (Bền vững)", "Mọi lúc (Legend)"]

# =============================================================================
# 2. CUSTOM WIDGETS (TỐI ƯU GIAO DIỆN)
# =============================================================================
