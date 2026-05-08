"""
VEO SUITE V3.2 — Assets Factory Constants
==========================================
Dữ liệu cấu hình cho AI Director Brain và Sticker Brain.
File này chỉ chứa constants (data) — KHÔNG chứa logic UI hay service.
"""

import random
import logging

logger = logging.getLogger("VeoSuite.AssetsFactory")

# ============================================================================
# 🧠 AI DIRECTOR BRAIN (MA TRẬN CẤU HÌNH THÔNG MINH)
# ============================================================================
DIRECTOR_BRAIN = {
    # --- NHÓM GIẢI TRÍ / VIRAL ---
    "kids": {
        "keywords": ["kids", "kể chuyện bé", "đồ chơi", "baby", "mầm non"],
        "voice": {"rate": 5, "pitch": 15, "gender_priority": "Female"}, 
        "visual_style": "3d disney pixar style, bright vibrant colors, cute, soft lighting, cartoon",
        "music_query": "happy ukulele cute upbeat playground"
    },
    "horror": {
        "keywords": ["ma", "kinh dị", "crime", "vụ án", "scary", "ghost"],
        "voice": {"rate": -12, "pitch": -5, "gender_priority": "Male"}, 
        "visual_style": "dark cinematic, horror atmosphere, low key lighting, mysterious, 8k realism",
        "music_query": "horror suspense ambient dark creepy tension"
    },
    "funny": {
        "keywords": ["thú cưng", "funny", "hài hước", "meme", "prank"],
        "voice": {"rate": 15, "pitch": 5, "gender_priority": "Any"}, 
        "visual_style": "high saturation, bright, meme style, funny moments, clear",
        "music_query": "funny comedy silly quirky fast"
    },
    "gaming": {
        "keywords": ["gaming", "e-sport", "highlight", "game", "liên quân"],
        "voice": {"rate": 10, "pitch": 0, "gender_priority": "Male"}, 
        "visual_style": "cyberpunk, neon lights, glitch effect, action packed, futuristic, 4k",
        "music_query": "edm energetic action gaming dubstep"
    },
    "asmr": {
        "keywords": ["asmr", "relax", "mưa", "thiền", "ngủ ngon"],
        "voice": {"rate": -20, "pitch": -2, "gender_priority": "Female"}, 
        "visual_style": "nature, pastel colors, soft focus, rain window, cozy atmosphere, lo-fi aesthetic",
        "music_query": "lofi chill rain meditation calm piano"
    },

    # --- NHÓM KIẾN THỨC / SỰ THẬT ---
    "facts": {
        "keywords": ["facts", "sự thật", "top 10", "khám phá", "khoa học"],
        "voice": {"rate": 5, "pitch": 0, "gender_priority": "Male"}, 
        "visual_style": "documentary style, realistic, infographic, macro photography, detailed",
        "music_query": "tech futuristic documentary rhythm neutral"
    },
    "history": {
        "keywords": ["lịch sử", "chiến tranh", "địa chính trị", "sử thi"],
        "voice": {"rate": 0, "pitch": -5, "gender_priority": "Male"}, 
        "visual_style": "vintage style, sepia tone, oil painting, cinematic war scene, historical map",
        "music_query": "epic orchestral cinematic war history drums"
    },

    # --- NHÓM KIẾM TIỀN CAO (HIGH CPM) ---
    "money": {
        "keywords": ["crypto", "tài chính", "đầu tư", "kinh doanh", "bất động sản", "luxury"],
        "voice": {"rate": 2, "pitch": -2, "gender_priority": "Male"}, 
        "visual_style": "luxury, golden hour, modern architecture, business minimalist, 8k",
        "music_query": "corporate success luxury lounge modern beat"
    },
    "tech": {
        "keywords": ["công nghệ", "review", "code", "tutorial", "ai"],
        "voice": {"rate": 5, "pitch": 0, "gender_priority": "Male"}, 
        "visual_style": "futuristic, studio lighting, product shot, blue and white theme, clean",
        "music_query": "technology synthwave modern review background"
    },
    "news": {
        "keywords": ["tin tức", "thời sự", "showbiz", "drama"],
        "voice": {"rate": 8, "pitch": 0, "gender_priority": "Female"}, 
        "visual_style": "news studio, breaking news background, professional, broadcasting",
        "music_query": "breaking news intro drama suspense urgent"
    },

    # --- NHÓM CẢM XÚC ---
    "motivation": {
        "keywords": ["động lực", "gym", "thể thao", "nghị lực"],
        "voice": {"rate": 5, "pitch": -3, "gender_priority": "Male"}, 
        "visual_style": "high contrast, sweat, gym atmosphere, sun rays, cinematic emotion",
        "music_query": "epic motivational cinematic emotional build-up"
    },
    "emotional": {
        "keywords": ["tâm sự", "podcast", "hẹn hò", "thầm kín", "phật giáo"],
        "voice": {"rate": -5, "pitch": 0, "gender_priority": "Female"}, 
        "visual_style": "warm lighting, close up, emotional, bokeh, storytelling style",
        "music_query": "sad piano emotional acoustic warm cello"
    },
    
    # Mặc định
    "default": {
        "voice": {"rate": 0, "pitch": 0, "gender_priority": "Any"},
        "visual_style": "cinematic, 4k, realistic, detailed",
        "music_query": "cinematic background"
    }
}

# ============================================================================
# 🎨 BỘ NÃO STICKER (Tự động suy luận hình ảnh từ từ khóa)
# ============================================================================
STICKER_BRAIN = {
    # Tài chính / Tiền
    "money": ["3d gold coin stack", "flying dollar bills", "money bag with dollar sign", "diamond gem"],
    "rich": ["luxury crown", "gold bars", "diamond"],
    "crypto": ["bitcoin gold coin", "rocket flying up", "bull market chart"],
    
    # Kinh dị / Ma
    "horror": ["scary ghost face", "blood hand print", "skull with glowing eyes", "haunted house icon"],
    "scary": ["scream mask face", "red devil eyes"],
    
    # Động vật / Cute
    "cat": ["cute fat cat face", "cat paw"],
    "dog": ["funny dog face", "dog bone"],
    "animal": ["cute panda face", "lion head logo"],
    
    # Cảm xúc / Reaction
    "funny": ["laughing emoji 3d", "clown face"],
    "sad": ["crying emoji 3d", "broken heart"],
    "shock": ["shocked face open mouth", "explosion boom"],
    
    # Mặc định (Nếu không tìm thấy từ khóa)
    "default": ["red arrow cursor", "play button glossy", "youtube logo 3d", "like button thumb up"]
}


def get_auto_sticker_prompt(text_input):
    """Phân tích text để ra prompt vẽ sticker."""
    text = str(text_input).lower()
    
    # 1. Quét từ khóa
    candidates = []
    for key, prompts in STICKER_BRAIN.items():
        if key in text:
            candidates.extend(prompts)
            
    # 2. Nếu không có từ khóa nào khớp -> Lấy random mặc định
    if not candidates:
        candidates = STICKER_BRAIN["default"]
        
    # 3. Chọn 1 cái ngẫu nhiên
    selected_subject = random.choice(candidates)
    
    # 4. Tạo Prompt chuẩn cho Sticker (Nền xanh để dễ tách)
    return f"{selected_subject}, vector sticker style, white border, isolated on solid green background, high quality, 8k render, 3d glossy style"


def get_director_config(text_context):
    """Hàm lõi phân tích văn bản (Text Analyzer) định tuyến cấu hình Media tự động."""
    text_lower = str(text_context).lower()
    
    # 1. Quét từ khóa
    for topic, config in DIRECTOR_BRAIN.items():
        if topic == "default":
            continue
        for kw in config.get("keywords", []):
            if kw in text_lower:
                logger.debug(f"Director matched topic '{topic}' via keyword '{kw}'")
                return config
                
    return DIRECTOR_BRAIN["default"]
