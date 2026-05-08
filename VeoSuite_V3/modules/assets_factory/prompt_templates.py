"""
VEO SUITE V3.3 — Visual Style Prompt Templates
=================================================
Kho phong cách hình ảnh trực quan cho Visual Pipeline.
Lấy cảm hứng từ Pixelle-Video (20+ templates) và MoneyPrinterTurbo.

Mỗi style gồm:
  - name: Tên hiển thị
  - emoji: Icon trực quan
  - prompt_prefix: Thêm vào đầu mỗi prompt tạo ảnh AI
  - description: Mô tả ngắn (tooltip)
  - stock_keywords: Từ khóa bổ sung khi tìm stock
  - color_accent: Màu chủ đạo hiển thị trên UI card
"""

# ============================================================================
# 20 PHONG CÁCH HÌNH ẢNH (Phân loại theo nhóm)
# ============================================================================

STYLE_CATALOG = [
    # ─── NHÓM 1: CINEMATIC & FILM ───
    {
        "name": "Cinematic",
        "emoji": "🎬",
        "prompt_prefix": "Cinematic 4K shot, dramatic lighting, shallow depth of field, film grain texture, anamorphic lens flare, color graded in teal and orange",
        "description": "Phong cách điện ảnh Hollywood — ánh sáng kịch tính, lens flare, tông teal-orange",
        "stock_keywords": "cinematic dramatic",
        "color_accent": "#e67e22"
    },
    {
        "name": "Documentary",
        "emoji": "📹",
        "prompt_prefix": "Documentary photography style, natural lighting, candid moment, high detail, photojournalism, realistic composition, authentic atmosphere",
        "description": "Phong cách phim tài liệu — chân thực, tự nhiên, ánh sáng thật",
        "stock_keywords": "documentary real life",
        "color_accent": "#95a5a6"
    },
    {
        "name": "Film Noir",
        "emoji": "🖤",
        "prompt_prefix": "Film noir style, high contrast black and white, dramatic shadows, venetian blind lighting, moody atmosphere, 1940s detective aesthetic",
        "description": "Phim đen trắng cổ điển — tương phản cao, bóng đổ kịch tính",
        "stock_keywords": "noir dark moody",
        "color_accent": "#2c3e50"
    },

    # ─── NHÓM 2: NGHỆ THUẬT SỐ (DIGITAL ART) ───
    {
        "name": "Anime",
        "emoji": "🌸",
        "prompt_prefix": "Anime style illustration, vibrant colors, cel shading, Studio Ghibli inspired, detailed background, expressive characters, Japanese animation art",
        "description": "Phong cách Anime Nhật Bản — màu sắc rực rỡ, nét vẽ mềm mại",
        "stock_keywords": "anime illustration colorful",
        "color_accent": "#e91e63"
    },
    {
        "name": "Cyberpunk",
        "emoji": "🌆",
        "prompt_prefix": "Cyberpunk neon cityscape, rain-slicked streets, holographic displays, dark atmosphere, blade runner aesthetic, purple and cyan neon lights, futuristic technology",
        "description": "Thế giới tương lai — neon rực rỡ, mưa, công nghệ cao",
        "stock_keywords": "cyberpunk neon futuristic",
        "color_accent": "#9b59b6"
    },
    {
        "name": "3D Render",
        "emoji": "🧊",
        "prompt_prefix": "3D rendered scene, soft lighting, Pixar style, clean geometry, subsurface scattering, ambient occlusion, pastel colors, smooth surfaces",
        "description": "Đồ họa 3D phong cách Pixar — mềm mại, sáng sủa, dễ thương",
        "stock_keywords": "3d render clean",
        "color_accent": "#3498db"
    },
    {
        "name": "Pixel Art",
        "emoji": "👾",
        "prompt_prefix": "Pixel art style, 16-bit retro gaming aesthetic, limited color palette, clean pixels, nostalgic, sprite-based illustration, dithering effects",
        "description": "Game retro 16-bit — pixel rõ nét, màu giới hạn, hoài cổ",
        "stock_keywords": "retro pixel game",
        "color_accent": "#27ae60"
    },
    {
        "name": "Comic Book",
        "emoji": "💥",
        "prompt_prefix": "Comic book style, bold ink outlines, halftone dots pattern, dynamic action poses, speech bubble composition, vivid primary colors, Marvel/DC aesthetic",
        "description": "Truyện tranh Marvel/DC — nét mực đậm, chấm halftone, màu nguyên bản",
        "stock_keywords": "comic pop art bold",
        "color_accent": "#e74c3c"
    },

    # ─── NHÓM 3: HỘI HỌA TRUYỀN THỐNG ───
    {
        "name": "Oil Painting",
        "emoji": "🎨",
        "prompt_prefix": "Oil painting on canvas, visible brushstrokes, rich impasto texture, Renaissance lighting, classical composition, warm earth tones, museum quality artwork",
        "description": "Tranh sơn dầu cổ điển — nét cọ dày, chất liệu phong phú",
        "stock_keywords": "painting artistic classic",
        "color_accent": "#d35400"
    },
    {
        "name": "Watercolor",
        "emoji": "💧",
        "prompt_prefix": "Delicate watercolor painting, soft wet-on-wet technique, gentle color bleeds, paper texture visible, light washes, transparent layers, dreamy botanical illustration",
        "description": "Màu nước nhẹ nhàng — loang màu tự nhiên, trong suốt, thơ mộng",
        "stock_keywords": "watercolor soft pastel",
        "color_accent": "#5dade2"
    },
    {
        "name": "Vintage",
        "emoji": "📷",
        "prompt_prefix": "Vintage photograph, faded warm tones, light leaks, vignette edges, 1970s Kodachrome film look, analog grain, slightly overexposed highlights, nostalgic mood",
        "description": "Ảnh phim Kodachrome thập niên 70 — tone ấm, rò sáng, hoài cổ",
        "stock_keywords": "vintage retro nostalgic",
        "color_accent": "#f39c12"
    },

    # ─── NHÓM 4: HIỆN ĐẠI & SÁNG TẠO ───
    {
        "name": "Neon Glow",
        "emoji": "✨",
        "prompt_prefix": "Neon glow effect, vibrant luminescent colors, dark background, electric blue and hot pink, glowing edges, light trails, futuristic nightclub atmosphere",
        "description": "Ánh neon phát sáng — rực rỡ trên nền tối, hiệu ứng phát quang",
        "stock_keywords": "neon glow lights dark",
        "color_accent": "#ff00ff"
    },
    {
        "name": "Minimalist",
        "emoji": "⬜",
        "prompt_prefix": "Minimalist design, clean composition, abundant negative space, simple geometric shapes, limited color palette, modern typography, Bauhaus inspired, Swiss design",
        "description": "Tối giản — không gian âm rộng, hình học đơn giản, sạch sẽ",
        "stock_keywords": "minimal clean simple",
        "color_accent": "#ecf0f1"
    },
    {
        "name": "Surreal",
        "emoji": "🌀",
        "prompt_prefix": "Surrealist art, dreamlike impossible landscape, Salvador Dali inspired, melting reality, floating objects, unexpected scale, vivid imagination, otherworldly atmosphere",
        "description": "Siêu thực — cảnh tượng bất khả thi, giấc mơ, biến dạng thực tế",
        "stock_keywords": "surreal dream fantasy",
        "color_accent": "#8e44ad"
    },
    {
        "name": "Pastel Dream",
        "emoji": "🍬",
        "prompt_prefix": "Soft pastel color palette, dreamy atmosphere, gentle gradients, cotton candy colors, baby pink and lavender, soft focus, whimsical kawaii aesthetic",
        "description": "Màu pastel nhẹ nhàng — hồng, lavender, dễ thương, mơ màng",
        "stock_keywords": "pastel soft dreamy cute",
        "color_accent": "#f8bbd0"
    },

    # ─── NHÓM 5: ĐẶC BIỆT (VIDEO MOTION) ───
    {
        "name": "Dark Tech",
        "emoji": "⚡",
        "prompt_prefix": "Dark technology aesthetic, circuit board patterns, data visualization, matrix code rain, dark UI interface, holographic HUD elements, tech startup vibe",
        "description": "Công nghệ tối — mạch điện, dữ liệu, giao diện HUD tương lai",
        "stock_keywords": "technology dark digital",
        "color_accent": "#00e676"
    },
    {
        "name": "Nature Epic",
        "emoji": "🏔️",
        "prompt_prefix": "Epic nature landscape, golden hour sunlight, dramatic clouds, majestic mountains, aerial drone perspective, National Geographic quality, HDR photography",
        "description": "Thiên nhiên hùng vĩ — National Geographic, giờ vàng, drone view",
        "stock_keywords": "nature landscape epic scenic",
        "color_accent": "#1abc9c"
    },
    {
        "name": "Horror",
        "emoji": "👻",
        "prompt_prefix": "Dark horror atmosphere, eerie fog, abandoned places, dim flickering light, creepy shadows, desaturated cold tones, supernatural dread, gothic architecture",
        "description": "Kinh dị — sương mù, bóng tối, màu lạnh, không khí rùng rợn",
        "stock_keywords": "horror dark creepy scary",
        "color_accent": "#c0392b"
    },
    {
        "name": "Luxury",
        "emoji": "💎",
        "prompt_prefix": "Luxury premium aesthetic, gold and black color scheme, marble texture, crystal reflections, elegant typography, high fashion editorial, opulent lifestyle",
        "description": "Sang trọng thượng lưu — vàng ròng, đá cẩm thạch, pha lê, thời trang",
        "stock_keywords": "luxury gold premium elegant",
        "color_accent": "#f1c40f"
    },
    {
        "name": "Isometric",
        "emoji": "🏗️",
        "prompt_prefix": "Isometric 3D illustration, flat design with depth, clean vector look, soft shadows, modern infographic style, bright cheerful colors, low-poly aesthetic",
        "description": "Góc nhìn isometric — đồ họa vector 3D phẳng, infographic hiện đại",
        "stock_keywords": "isometric design flat",
        "color_accent": "#2196f3"
    },
]

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_style_by_name(name: str) -> dict:
    """Tìm style theo tên (case-insensitive)."""
    for s in STYLE_CATALOG:
        if s["name"].lower() == name.lower():
            return s
    return STYLE_CATALOG[0]  # Fallback → Cinematic

def get_all_style_names() -> list:
    """Trả về list tên tất cả styles."""
    return [s["name"] for s in STYLE_CATALOG]

def get_prompt_prefix(style_name: str) -> str:
    """Trả về prompt prefix cho style đã cho."""
    style = get_style_by_name(style_name)
    return style.get("prompt_prefix", "")

def get_style_for_ai_detect(script_text: str) -> str:
    """
    AI tự chọn style phù hợp nhất dựa trên nội dung kịch bản.
    Trả về tên style.
    """
    style_names = get_all_style_names()
    prompt = f"""Analyze this video script and choose the BEST visual style from this list: {style_names}.
Consider the mood, topic, and target audience.

Script: "{script_text[:500]}"

Reply with ONLY the style name, nothing else."""
    
    try:
        from services.ai_factory import AIFactory
        success, result = AIFactory().execute_custom_ai("google", prompt, "gemini-2.0-flash")
        if success:
            chosen = result.strip().strip('"').strip("'")
            # Validate
            for name in style_names:
                if name.lower() == chosen.lower():
                    return name
    except Exception:
        pass
    
    return "Cinematic"  # Default fallback
