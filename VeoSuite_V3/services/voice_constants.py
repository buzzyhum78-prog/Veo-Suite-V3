import json
import logging
import os
import asyncio
import edge_tts
import random

logger = logging.getLogger("VeoSuite.Voice")

# =============================================================================
# VEO MEDIA ENGINE - ULTIMATE VOICE MATRIX (DYNAMIC)
# Cơ chế: Tự động tải danh sách giọng từ Microsoft Server
# =============================================================================

# Đường dẫn file cache (Để không phải tải lại mỗi lần bật app)
CACHE_DIR = "VEO_DB"
VOICE_DB_FILE = os.path.join(CACHE_DIR, "voice_list_cache.json")

# --- [QUAN TRỌNG] BIẾN RAM CACHE ---
_GLOBAL_VOICE_CACHE = None

# --- DANH SÁCH GIỌNG CỨNG DỰ PHÒNG (STATIC FALLBACK) ---
# Giúp tool khởi động ngay lập tức kể cả khi chưa tải xong list full
STATIC_VOICES = [
    {'ShortName': 'vi-VN-HoaiMyNeural', 'Gender': 'Female', 'Locale': 'vi-VN'},
    {'ShortName': 'vi-VN-NamMinhNeural', 'Gender': 'Male', 'Locale': 'vi-VN'},
    {'ShortName': 'en-US-AriaNeural', 'Gender': 'Female', 'Locale': 'en-US'},
    {'ShortName': 'en-US-GuyNeural', 'Gender': 'Male', 'Locale': 'en-US'},
    {'ShortName': 'en-US-ChristopherNeural', 'Gender': 'Male', 'Locale': 'en-US'},
    {'ShortName': 'en-US-JennyNeural', 'Gender': 'Female', 'Locale': 'en-US'},
    {'ShortName': 'zh-CN-XiaoxiaoNeural', 'Gender': 'Female', 'Locale': 'zh-CN'},
    {'ShortName': 'ja-JP-NanamiNeural', 'Gender': 'Female', 'Locale': 'ja-JP'},
    {'ShortName': 'ko-KR-SunHiNeural', 'Gender': 'Female', 'Locale': 'ko-KR'},
]

# --- BẢN ĐỒ MÃ QUỐC GIA (MỞ RỘNG TOÀN CẦU) ---
# Map từ Mã 2 ký tự (VN, US) -> Locale chuẩn (vi-VN, en-US)
COUNTRY_LOCALE_MAP = {
    # Châu Á & Thái Bình Dương
    "VN": "vi-VN", "CN": "zh-CN", "TW": "zh-TW", "HK": "zh-HK",
    "JP": "ja-JP", "KR": "ko-KR", "TH": "th-TH", "ID": "id-ID",
    "IN": "hi-IN", "MY": "ms-MY", "PH": "en-PH", "SG": "en-SG",
    "PK": "ur-PK", "BD": "bn-BD", "LK": "ta-LK", 
    "LA": "lo-LA", "KH": "km-KH", # Lào, Cam (Edge-TTS có hỗ trợ giọng Lào/Khmer)

    # Trung Đông (Dầu Mỏ)
    "QA": "ar-QA", # Qatar
    "AE": "ar-AE", # UAE
    "SA": "ar-SA", # Saudi
    "KW": "ar-KW", # Kuwait
    "EG": "ar-EG", # Ai Cập
    "IQ": "ar-IQ", # Iraq
    "IR": "fa-IR", # Iran (Farsi)
    "IL": "he-IL", # Israel
    "TR": "tr-TR", # Thổ Nhĩ Kỳ

    # Âu - Mỹ
    "US": "en-US", "GB": "en-GB", "UK": "en-GB", 
    "AU": "en-AU", "CA": "en-CA", "NZ": "en-NZ", "IE": "en-IE", # Thêm IE
    "DE": "de-DE", "FR": "fr-FR", "ES": "es-ES", "IT": "it-IT",
    "RU": "ru-RU", "UA": "uk-UA", "PL": "pl-PL", "PT": "pt-PT",
    "NL": "nl-NL", "SE": "sv-SE", "NO": "nb-NO", "DK": "da-DK",
    "FI": "fi-FI", "CH": "de-CH", 
    "AT": "de-AT", "BE": "fr-BE",
    "GR": "el-GR", "HU": "hu-HU", 
    "CZ": "cs-CZ", "CS": "cs-CZ", "SK": "sk-SK", "RO": "ro-RO", # Thêm Séc, Slovak, Rumani

    # Nam Mỹ & Phi
    "BR": "pt-BR", "MX": "es-MX", "AR": "es-AR", "CL": "es-CL", "CO": "es-CO",
    "ZA": "af-ZA", "NG": "en-NG"
}

# Map các trường hợp đặc biệt (Tên đầy đủ -> Mã 2 chữ)
NAME_TO_CODE = {
    # --- CHÂU Á ---
    "VIETNAM": "VN", "VIỆT NAM": "VN", "VIỆT": "VN", "VN": "VN",
    "JAPAN": "JP", "NHẬT BẢN": "JP", "NHẬT": "JP", "JA": "JP", "JP": "JP",
    "CHINA": "CN", "TRUNG QUỐC": "CN", "TRUNG": "CN", "ZH": "CN", "CN": "CN",
    "TAIWAN": "TW", "ĐÀI LOAN": "TW", "TW": "TW",
    "HONG KONG": "HK", "HỒNG KÔNG": "HK", "HK": "HK",
    "KOREA": "KR", "HÀN QUỐC": "KR", "HÀN": "KR", "NAM HÀN": "KR", "KO": "KR", "KR": "KR",
    "THAILAND": "TH", "THÁI LAN": "TH", "THÁI": "TH", "TH": "TH",
    "INDONESIA": "ID", "INDO": "ID", "ID": "ID",
    "INDIA": "IN", "ẤN ĐỘ": "IN", "ẤN": "IN", "HINDI": "IN", "IN": "IN",
    "PHILIPPINES": "PH", "PHILIPPIN": "PH", "PHI": "PH", "PH": "PH",
    "SINGAPORE": "SG", "SING": "SG", "SG": "SG",
    "MALAYSIA": "MY", "MÃ LAI": "MY", "MY": "MY",
    "LAOS": "LA", "LÀO": "LA", "LA": "LA",
    "CAMBODIA": "KH", "CAMPUCHIA": "KH", "CAM": "KH", "KHMER": "KH", "KH": "KH",

    # --- CHÂU ÂU ---
    "GERMANY": "DE", "DEUTSCHLAND": "DE", "ĐỨC": "DE", "DE": "DE",
    "FRANCE": "FR", "PHÁP": "FR", "FR": "FR",
    "UNITED KINGDOM": "GB", "UK": "GB", "ANH QUỐC": "GB", "ANH": "GB", "BRITAIN": "GB", "GB": "GB",
    "IRELAND": "IE", "AI LEN": "IE", "IE": "IE",
    "SPAIN": "ES", "ESPAÑA": "ES", "TÂY BAN NHA": "ES", "TÂY": "ES", "ES": "ES",
    "ITALY": "IT", "ITALIA": "IT", "Ý": "IT", "IT": "IT",
    "RUSSIA": "RU", "NGA": "RU", "RU": "RU",
    "PORTUGAL": "PT", "BỒ ĐÀO NHA": "PT", "PT": "PT",
    "POLAND": "PL", "BA LAN": "PL", "PL": "PL",
    "NETHERLANDS": "NL", "HÀ LAN": "NL", "DUTCH": "NL", "NL": "NL",
    "SWEDEN": "SE", "THỤY ĐIỂN": "SE", "SE": "SE",
    "NORWAY": "NO", "NA UY": "NO", "NO": "NO",
    "DENMARK": "DK", "ĐAN MẠCH": "DK", "DK": "DK",
    "FINLAND": "FI", "PHẦN LAN": "FI", "FI": "FI",
    "SWITZERLAND": "CH", "THỤY SĨ": "CH", "CH": "CH",
    "AUSTRIA": "AT", "ÁO": "AT", "AT": "AT",
    "BELGIUM": "BE", "BỈ": "BE", "BE": "BE",
    "GREECE": "GR", "HY LẠP": "GR", "GR": "GR",
    "HUNGARY": "HU", "HUNG": "HU", "HU": "HU",
    "CZECH": "CZ", "CZECHIA": "CZ", "CZ": "CZ",
    "SEC": "CZ", "CS": "CZ", "SZ": "CZ",
    "TIỆP": "CZ", "TIỆP KHẮC": "CZ","CZECH": "CZ", "SÉC": "CZ", "CZ": "CZ",
    "UKRAINE": "UA", "UCRAINA": "UA", "UA": "UA",

    # --- CHÂU MỸ ---
    "UNITED STATES": "US", "USA": "US", "HOA KỲ": "US", "MỸ": "US", "AMERICA": "US", "US": "US",
    "CANADA": "CA", "CA": "CA",
    "BRAZIL": "BR", "BRAZIN": "BR", "BR": "BR",
    "MEXICO": "MX", "MÊ HI CÔ": "MX", "MX": "MX",
    "ARGENTINA": "AR", "AR": "AR",

    # --- CHÂU ÚC ---
    "AUSTRALIA": "AU", "ÚC": "AU", "AU": "AU",
    "NEW ZEALAND": "NZ", "NIU DI LÂN": "NZ", "NZ": "NZ",

    # --- TRUNG ĐÔNG & KHÁC ---
    "SAUDI ARABIA": "SA", "ARAB": "SA", "SAUDI": "SA", "Ả RẬP": "SA", "SA": "SA",
    "UAE": "AE", "TIỂU VƯƠNG QUỐC": "AE", "AE": "AE",
    "EGYPT": "EG", "AI CẬP": "EG", "EG": "EG",
    "TURKEY": "TR", "THỔ NHĨ KỲ": "TR", "THỔ": "TR", "TR": "TR",
    "ISRAEL": "IL", "DO THÁI": "IL", "IL": "IL",
    "IRAN": "IR", "BA TƯ": "IR", "IR": "IR",
    "IRAQ": "IQ", "IQ": "IQ",
    "QATAR": "QA", "QA": "QA",
    "KUWAIT": "KW", "KW": "KW",
    "SOUTH AFRICA": "ZA", "NAM PHI": "ZA", "ZA": "ZA"
}

# --- QUY TẮC ĐẠO DIỄN (GIỮ NGUYÊN LOGIC CŨ) ---
STYLE_RULES = {
    # --- NHÓM 1: UY TÍN / KIẾM TIỀN / KIẾN THỨC (Ưu tiên NAM - Male) ---
    # Lý do: Giọng Nam trầm tạo cảm giác tin cậy, chuyên gia, quyền lực.
    "NEWS":     {"rate": "+10%", "pitch": "+0Hz",  "gender_pref": "Male"},   # Tin tức: Nhanh, rõ, chững chạc
    "TECH":     {"rate": "+5%",  "pitch": "+0Hz",  "gender_pref": "Male"},   # Công nghệ: Gãy gọn, hiện đại
    "FINANCE":  {"rate": "+2%",  "pitch": "-2Hz",  "gender_pref": "Male"},   # Tài chính: Trầm ổn, chắc chắn
    "LUXURY":   {"rate": "-5%",  "pitch": "-4Hz",  "gender_pref": "Male"},   # Sang chảnh: Chậm, trầm, quyến rũ (như quảng cáo xe hơi)
    "STORY":    {"rate": "-5%",  "pitch": "-5Hz",  "gender_pref": "Male"},   # Sự thật/Lịch sử: Trầm hùng, kể chuyện (kiểu Nguyễn Ngọc Ngạn/VTV)
    "ACTION":   {"rate": "+15%", "pitch": "+2Hz",  "gender_pref": "Male"},   # Hành động/Game: Nhanh, mạnh

    # --- NHÓM 2: CẢM XÚC / VIRAL / ĐỜI SỐNG (Ưu tiên NỮ - Female) ---
    # Lý do: Giọng Nữ tạo cảm giác đồng cảm, nhẹ nhàng, hoặc vui tươi.
    "SAD":      {"rate": "-10%", "pitch": "-3Hz",  "gender_pref": "Female"}, # Buồn: Chậm, nghẹn ngào
    "KID":      {"rate": "+12%", "pitch": "+15Hz", "gender_pref": "Female"}, # Trẻ em: Cao vút, nhí nhảnh
    "RELAX":    {"rate": "-15%", "pitch": "-2Hz",  "gender_pref": "Female"}, # ASMR/Thiền: Rất chậm, thì thầm
    "HEALTH":   {"rate": "-2%",  "pitch": "+1Hz",  "gender_pref": "Female"}, # Sức khỏe: Ân cần, nhẹ nhàng (như bác sĩ/y tá)
    "FUNNY":    {"rate": "+15%", "pitch": "+5Hz",  "gender_pref": "Female"}, # Hài hước: Nhanh, tưng tửng

    # --- NHÓM 3: HỖN HỢP / NGẪU NHIÊN (Cân bằng) ---
    "HORROR":   {"rate": "-15%", "pitch": "-6Hz",  "gender_pref": "Male"},   # Ma: Mặc định Nam ồm, nhưng code sẽ random đôi khi ra Nữ ma mị
    "PODCAST":  {"rate": "-3%",  "pitch": "-2Hz",  "gender_pref": "Random"}, # Tâm sự: Random để đổi gió
    "DEFAULT":  {"rate": "+0%",  "pitch": "0Hz",   "gender_pref": "Random"}  # Mặc định: Tung xúc xắc 50/50
}

def get_all_voices_online():
    """Hàm tải danh sách giọng từ Server (Chỉ chạy khi cần thiết)"""
    try:
        async def _fetch(): return await edge_tts.list_voices()
        return asyncio.run(_fetch())
    except Exception as e:
        logger.warning(f"Edge-TTS connection error: {e}")
        return []
    
def _load_voice_cache():
    """Hàm nội bộ: Load dữ liệu vào RAM (Chỉ chạy 1 lần duy nhất)"""
    global _GLOBAL_VOICE_CACHE
    
    # 1. Nếu RAM đã có -> Dùng luôn
    if _GLOBAL_VOICE_CACHE is not None:
        return _GLOBAL_VOICE_CACHE

    # 2. Nếu chưa có, đọc từ ổ cứng
    if not os.path.exists(CACHE_DIR): os.makedirs(CACHE_DIR)
    
    # Ưu tiên dùng Static List trước để app không bị đơ lần đầu
    _GLOBAL_VOICE_CACHE = STATIC_VOICES

    if os.path.exists(VOICE_DB_FILE) and os.path.getsize(VOICE_DB_FILE) > 100:
        try:
            with open(VOICE_DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if len(data) > 20: # Chỉ dùng nếu file có đủ dữ liệu
                    _GLOBAL_VOICE_CACHE = data
        except: pass
    
    # 3. Nếu Cache file chưa có hoặc lỗi, chạy ngầm tải về (nhưng không block UI)
    if len(_GLOBAL_VOICE_CACHE) < 20:
        logger.info("Loading global voice list...")
        full = get_all_voices_online()
        if full:
            _GLOBAL_VOICE_CACHE = [v if isinstance(v, dict) else v.__dict__ for v in full]
            try:
                with open(VOICE_DB_FILE, "w", encoding="utf-8") as f:
                    json.dump(_GLOBAL_VOICE_CACHE, f, ensure_ascii=False)
                logger.info(f"Voice cache saved: {len(_GLOBAL_VOICE_CACHE)} voices")
            except: pass

    return _GLOBAL_VOICE_CACHE

def get_voice_list_by_country(country_code="US"):
    """
    Lấy danh sách giọng theo quốc gia (Sử dụng RAM Cache)
    """
    # 1. Chuẩn hóa mã nước
    raw_input = str(country_code).upper().strip()
    target_code = "US"
    found_match = False
    
    # --- LOGIC TÌM KIẾM THÔNG MINH ---
    # Sắp xếp từ khóa theo độ dài giảm dần để tránh nhận nhầm (VD: "IRELAND" vs "LA")
    sorted_keys = sorted(NAME_TO_CODE.keys(), key=len, reverse=True)

    for name in sorted_keys:
        if name in raw_input:
            target_code = NAME_TO_CODE[name]
            found_match = True
            break
    
    # Fallback: Nếu không tìm thấy, thử lấy 2 ký tự đầu
    if not found_match and len(raw_input) >= 2:
        pot_code = raw_input[:2]
        if pot_code in COUNTRY_LOCALE_MAP:
            target_code = pot_code

    target_locale_prefix = COUNTRY_LOCALE_MAP.get(target_code, "en-US")

    # 2. LẤY DỮ LIỆU TỪ RAM CACHE (Không đọc ổ cứng nữa)
    all_voices = _load_voice_cache()

    # 3. LỌC GIỌNG
    results = []
    for v in all_voices:
        if target_locale_prefix.lower() in v['ShortName'].lower():
            gender = "Male" if "Male" in v['Gender'] else "Female"
            simple_name = v['ShortName'].split('-')[-1].replace('Neural', '')
            priority = 1 if "Multilingual" in v['ShortName'] else 0
            display_name = f"[{v['Locale']}] {gender} - {simple_name}"

            results.append({
                "id": v['ShortName'],
                "name": simple_name,
                "gender": gender,
                "full_name": display_name,
                "locale": v['Locale'],
                "priority": priority
            })
    
    results.sort(key=lambda x: (x['priority'], x['gender']), reverse=True)
    return results

def get_smart_voice_config(country_code, topic_string):
    """
    AI DIRECTOR V3.0 (Full Logic + Optimization)
    """
    import random
    
    # 1. Lấy danh sách giọng
    voices = get_voice_list_by_country(country_code)
    if not voices: voices = get_voice_list_by_country("US")
        
    topic_str = str(topic_string).upper()
    style_key = "DEFAULT"
    
    # --- Nhóm Male (Kiếm tiền/Kiến thức) ---
    if any(x in topic_str for x in ["TIN", "NEWS", "SỰ KIỆN", "HOT", "DRAMA"]): style_key = "NEWS"
    elif any(x in topic_str for x in ["TECH", "CÔNG NGHỆ", "CODE", "HƯỚNG DẪN", "AI", "REVIEW"]): style_key = "TECH"
    elif any(x in topic_str for x in ["CRYPTO", "COIN", "TIỀN", "KINH DOANH", "ĐẦU TƯ", "CHỨNG KHOÁN"]): style_key = "FINANCE"
    elif any(x in topic_str for x in ["LUXURY", "XE", "GIÀU", "BẤT ĐỘNG SẢN", "NHÀ", "VILLA", "SIÊU XE"]): style_key = "LUXURY"
    elif any(x in topic_str for x in ["SÁCH", "BOOK", "SỰ THẬT", "FACT", "SỬ", "HISTORY", "CHIẾN TRANH", "BÍ ẨN", "VŨ TRỤ"]): style_key = "STORY"
    elif any(x in topic_str for x in ["ACTION", "HYPE", "SPORT", "GYM", "GAME", "BÓNG ĐÁ"]): style_key = "ACTION"
    
    # --- Nhóm Female (Cảm xúc/Đời sống) ---
    elif any(x in topic_str for x in ["KID", "TRẺ", "TOY", "BÉ", "MẦM NON"]): style_key = "KID"
    elif any(x in topic_str for x in ["ASMR", "RELAX", "THIỀN", "NGỦ", "MƯA"]): style_key = "RELAX"
    elif any(x in topic_str for x in ["SAD", "BUỒN", "KHÓC", "TÂM TRẠNG"]): style_key = "SAD"
    elif any(x in topic_str for x in ["FUNNY", "HÀI", "PET", "THÚ", "PRANK", "MEME"]): style_key = "FUNNY"
    elif any(x in topic_str for x in ["HEALTH", "Y TẾ", "SỨC KHỎE", "BỆNH", "YOGA", "LÀM ĐẸP"]): style_key = "HEALTH"
    
    # --- Nhóm Đặc biệt ---
    elif any(x in topic_str for x in ["MA", "HORROR", "CREEPY", "GHOST", "ÁM ẢNH"]): style_key = "HORROR"
    elif any(x in topic_str for x in ["TÂM LÝ", "HẸN HÒ", "TÌNH YÊU", "PODCAST", "VLOG"]): style_key = "PODCAST"
    
    rule = STYLE_RULES.get(style_key, STYLE_RULES["DEFAULT"])
    
    # 3. Xử lý Giới tính
    target_gender = rule["gender_pref"]
    
    if target_gender == "Random":
        target_gender = "Male" if random.random() > 0.5 else "Female"

    if any(x in topic_str for x in ["NAM", "BOY", "MAN", "ÔNG", "ANH"]): target_gender = "Male"
    elif any(x in topic_str for x in ["NỮ", "GIRL", "WOMAN", "BÀ", "CÔ", "EM"]): target_gender = "Female"

    # 4. Tinh chỉnh Rate/Pitch
    try:
        base_rate = int(rule["rate"].replace("%", "").replace("+", ""))
        base_pitch = int(rule["pitch"].replace("Hz", "").replace("+", ""))
    except: base_rate=0; base_pitch=0
    
    # Biến thiên tự nhiên
    final_rate = base_rate + random.randint(-2, 2)
    final_pitch = base_pitch + random.randint(-1, 1)
    
    # Tăng cường độ
    if any(x in topic_str for x in ["CỰC", "RẤT", "SUPER", "MEGA", "SỐC", "HOT"]):
        if final_rate > 0: final_rate += 5
        if final_pitch < 0: final_pitch -= 3

    # 5. Chọn giọng
    candidates = [v for v in voices if v.get("gender") == target_gender]
    selected_voice_id = ""
    
    if not candidates: 
        if voices: selected_voice_id = voices[0]["id"]
        else: selected_voice_id = "vi-VN-HoaiMyNeural"
    else:
        # Ưu tiên Multilingual
        multi = [v for v in candidates if "Multilingual" in v["id"]]
        if multi: selected_voice_id = random.choice(multi)["id"]
        else: selected_voice_id = random.choice(candidates)["id"]

    return {
        "voice_id": selected_voice_id,
        "rate": f"{final_rate:+d}%", 
        "pitch": f"{final_pitch:+d}Hz",
        "style_tag": f"{style_key} ({target_gender})"
    }

# --- INIT ASYNC (Kích hoạt ngay khi import) ---
try: _load_voice_cache()
except: pass