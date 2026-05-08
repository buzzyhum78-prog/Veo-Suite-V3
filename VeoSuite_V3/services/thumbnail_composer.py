# services/thumbnail_composer.py

import os
import io
import json
import random
import traceback
import math
import re
import logging

import requests
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter, ImageOps, ImageChops

logger = logging.getLogger("VeoSuite.Thumbnail")

REMBG_AVAILABLE = False
try:
    from rembg import remove
    import onnxruntime
    device = onnxruntime.get_device()
    logger.info(f"AI Rembg ready (device: {device})")
    REMBG_AVAILABLE = True

except ImportError:
    logger.info("Rembg not installed - background removal disabled")
    REMBG_AVAILABLE = False
except Exception as e:
    logger.warning(f"Rembg backend error: {e} - background removal disabled")
    REMBG_AVAILABLE = False
class ThumbnailComposer:
    def __init__(self):
        # 1. Cấu hình đường dẫn
        self.root_dir = "assets"
        self.font_dir = os.path.join(self.root_dir, "fonts")
        self.overlay_dir = os.path.join(self.root_dir, "overlays")
        
        # 2. TỰ ĐỘNG TẠO KHO NGUYÊN LIỆU (THEO CHỦ ĐỀ)
        # Để CEO chỉ cần ném ảnh vào là dùng được ngay
        self.topics = ["Money", "Horror", "Kids", "News", "General"]
        self.categories = ["Stickers", "VFX", "Arrows", "Badges"]
        
        for cat in self.categories:
            for top in self.topics:
                p = os.path.join(self.overlay_dir, cat, top)
                os.makedirs(p, exist_ok=True)
        
        # Tạo folder font
        os.makedirs(self.font_dir, exist_ok=True)

        # --- 2. FONT MAPPING (BẢN FULL QUỐC TẾ) ---
        self.mood_fonts = {
            "Horror": ["Creepster.ttf", "MetalMania.ttf", "Nosifer.ttf"],
            "Kids": ["FredokaOne.ttf", "Bangers.ttf", "Chewy.ttf"],
            "Funny": ["Bangers.ttf", "LuckiestGuy.ttf", "CarterOne.ttf"],
            "Tech": ["Montserrat-ExtraBold.ttf", "Oswald-Bold.ttf", "Roboto-Black.ttf"],
            "News": ["Impact.ttf", "Oswald-Bold.ttf"],
            "Cinematic": ["Cinzel.ttf", "PlayfairDisplay-Bold.ttf"],
            "Vintage": ["Rye.ttf", "PlayfairDisplay-Bold.ttf"],
            "Chill": ["Pacifico.ttf", "DancingScript-Bold.ttf"],
            "Love": ["DancingScript-Bold.ttf", "Pacifico.ttf"]
        }

        self.global_fonts = {
            "vietnamese": "Roboto-Black.ttf",
            "japanese": "ReggaeOne.ttf",      
            "korean": "BlackHanSans.ttf",     
            "arabic": "Lalezar.ttf",          
            "thai": "ChakraPetch.ttf",           
            "chinese_sc": "NotoSansSC-Black.ttf",
            "chinese_tc": "NotoSansTC-Black.ttf",
            "lao": "NotoSansLao-Black.ttf",
            "khmer": "NotoSansKhmer-Black.ttf",
            "hindi": "NotoSansDevanagari-Black.ttf",
            "hebrew": "NotoSansHebrew-Black.ttf",
            "fallback": "Roboto-Black.ttf"
        }

    # --- BRIDGE: TÁCH NỀN TỪ FILE PATH ---
    def remove_background(self, input_path, output_path):
        if not REMBG_AVAILABLE: return False
        try:
            if not os.path.exists(input_path): return False
            img = Image.open(input_path).convert("RGBA")
            # Tách nền
            import io
            img_byte = io.BytesIO()
            img.save(img_byte, format='PNG')
            res_data = remove(img_byte.getvalue())
            out_img = Image.open(io.BytesIO(res_data)).convert("RGBA")
            out_img.save(output_path)
            return True
        except Exception as e:
            logger.warning(f"Rembg error: {e}")
            return False

    # --- CORE: QUY TRÌNH GHÉP (MULTI-LAYER) ---
    def create_thumbnail(self, bg_path, text_primary, text_secondary, output_path, 
                         brand_color="#FF0000", mood="Cinematic", layout_mode="standard", 
                         sticker_path=None, topic="General"):
        """
        Quy trình ghép 5 Lớp: Background -> VFX -> Sticker -> Text -> Arrow
        """
        try:
            # 1. Base Canvas
            if not os.path.exists(bg_path): return False, "Missing BG"
            img = Image.open(bg_path).convert("RGBA")
            img = img.resize((1280, 720), Image.Resampling.LANCZOS)
            W, H = img.size
            draw = ImageDraw.Draw(img)

            # Determine Alignment
            align = "left"
            if layout_mode == "swap": align = "right"
            elif layout_mode == "center": align = "center"

            # 2. [LAYER 2] VFX Overlay (Tự động lấy theo Topic)
            # Code sẽ tự tìm trong assets/overlays/VFX/{Topic}
            self._apply_auto_vfx(img, topic)
            
            # Refresh draw sau khi paste ảnh
            draw = ImageDraw.Draw(img)

            # 3. [LAYER 1.5] Gradient (Làm tối nền để nổi bật lớp trên)
            grad = self._create_gradient(W, H, direction=align)
            img.paste(grad, (0,0), grad)

            # 4. [LAYER 3] Sticker (Chủ thể)
            # Biến lưu tâm điểm để mũi tên chỉ vào
            target_point = None
            
            if sticker_path and os.path.exists(sticker_path):
                sticker = Image.open(sticker_path).convert("RGBA")
                
                # Resize Sticker (Cao 85% khung hình)
                s_h = int(H * 0.85)
                s_w = int(s_h * (sticker.width / sticker.height))
                sticker = sticker.resize((s_w, s_h), Image.Resampling.LANCZOS)
                
                # Hiệu ứng Pop (Viền trắng + Bóng)
                sticker = self._add_sticker_effects(sticker)
                
                # Vị trí
                s_y = H - s_h
                if align == "left": 
                    s_x = W - s_w + 40
                    target_point = (s_x + s_w//2, s_y + s_h//3)
                elif align == "right":
                    s_x = -40
                    target_point = (s_x + s_w//2, s_y + s_h//3)
                    img = ImageOps.mirror(img) # Flip nền nếu đổi bên
                    draw = ImageDraw.Draw(img)
                else: 
                    s_x = W - s_w
                
                img.paste(sticker, (s_x, s_y), sticker)

            # 5. [LAYER 4] Text Rendering
            font_size = 140
            font = self._get_font(text_primary, mood, font_size)
            
            lines = self._wrap_text(text_primary, font, 650 if align != "center" else 1000)
            total_h = len(lines) * 145
            if text_secondary: total_h += 120
            
            curr_y = (H - total_h) / 2 - 30
            text_end_point = None
            
            for i, line in enumerate(lines):
                lw = font.getlength(line)
                if align == "left": px = 50
                elif align == "right": px = W - lw - 50
                else: px = (W - lw) / 2
                
                # Rich Text (Tô màu số)
                self._draw_rich_text(draw, (px, curr_y), line, font, "white", "#FFDD00")
                
                if i == len(lines)-1: text_end_point = (px + lw/2, curr_y + 145)
                curr_y += 145

            # 6. [LAYER 5] CTA Box
            if text_secondary:
                curr_y += 20
                font_sub = self._get_font(text_secondary, mood, 80)
                l,t,r,b = font_sub.getbbox(text_secondary)
                bw, bh = r-l+60, b-t+40
                
                if align == "left": bx = 50
                elif align == "right": bx = W - bw - 50
                else: bx = (W - bw)/2
                
                brand_rgb = self._hex_to_rgb(brand_color)
                # Shadow
                draw.rectangle([(bx+10, curr_y+10), (bx+bw+10, curr_y+bh+10)], fill=(0,0,0,180))
                # Main
                draw.rectangle([(bx, curr_y), (bx+bw, curr_y+bh)], fill=brand_rgb, outline="white", width=4)
                draw.text((bx+30, curr_y+10), text_secondary, font=font_sub, fill="white")

            # 7. [LAYER 6] Arrow (Auto Pick from Assets)
            if align != "center" and target_point and text_end_point:
                self._apply_auto_arrow(img, text_end_point, target_point, align)

            # 8. Final Output
            final = img.convert("RGB")
            final = ImageEnhance.Contrast(final).enhance(1.2)
            final = ImageEnhance.Sharpness(final).enhance(1.4)
            
            final.save(output_path, quality=95)
            return True, output_path

        except Exception as e:
            traceback.print_exc()
            return False, str(e)
# --- HELPER LOGIC ---
    def _apply_auto_vfx(self, img, topic):
        """Tìm VFX trong assets/overlays/VFX/{Topic}"""
        # Map topic sang folder (nếu chưa có thì dùng General)
        topic_folder = topic if topic in self.topics else "General"
        vfx_path = os.path.join(self.overlay_dir, "VFX", topic_folder)
        
        # Nếu không có file, thử tìm folder cha
        if not os.path.exists(vfx_path) or not os.listdir(vfx_path):
            vfx_path = os.path.join(self.overlay_dir, "VFX", "General")
            
        if os.path.exists(vfx_path):
            files = [f for f in os.listdir(vfx_path) if f.endswith('.png')]
            if files:
                vf = Image.open(os.path.join(vfx_path, random.choice(files))).convert("RGBA")
                vf = vf.resize(img.size)
                # Blend nhẹ (Screen mode giả lập)
                img.alpha_composite(vf)

    def _apply_auto_arrow(self, img, start_p, end_p, align):
        """Lấy mũi tên PNG thay vì vẽ"""
        arrow_dir = os.path.join(self.overlay_dir, "Arrows", "General")
        # Fallback nếu chưa tạo folder con
        if not os.path.exists(arrow_dir): arrow_dir = os.path.join(self.overlay_dir, "Arrows")
        
        if os.path.exists(arrow_dir):
            files = [f for f in os.listdir(arrow_dir) if f.endswith('.png')]
            if files:
                arrow = Image.open(os.path.join(arrow_dir, random.choice(files))).convert("RGBA")
                arrow = arrow.resize((250, 150))
                
                # Xoay và đặt
                x = 600 if align == "left" else img.width - 600 - 250
                y = int((start_p[1] + end_p[1]) / 2) - 50
                
                if align == "right": arrow = ImageOps.mirror(arrow)
                arrow = arrow.rotate(random.randint(-15, 15), expand=True)
                
                img.paste(arrow, (x, y), arrow)

    def _get_font(self, text, mood, size):
        """Logic chọn font thông minh dựa trên Ngôn ngữ và Cảm xúc (Fixed)"""
        text_str = str(text)
        font_name = self.global_fonts["fallback"]
        
        # 1. Ưu tiên check Ngôn ngữ (Để tránh lỗi ô vuông)
        if any("\u0e00" <= c <= "\u0e7f" for c in text_str): font_name = self.global_fonts["thai"]
        elif any("\u3040" <= c <= "\u30ff" for c in text_str): font_name = self.global_fonts["japanese"]
        elif any("\uac00" <= c <= "\ud7af" for c in text_str): font_name = self.global_fonts["korean"]
        elif any(c in "àáạảãâèéẹẻẽêìíịỉĩòóọỏõôùúụủũưýỳỵỷỹđ" for c in text_str.lower()):
            font_name = self.global_fonts["vietnamese"]
        else:
            # 2. Nếu là tiếng Anh/Latin -> Chọn theo Mood (Cảm xúc)
            for k, v in self.mood_fonts.items():
                if k.lower() in str(mood).lower():
                    font_name = random.choice(v)
                    break
        
        # 3. Load Font từ file
        path = os.path.join(self.font_dir, font_name)
        
        # Fallback 1: Thử các font dự phòng
        if not os.path.exists(path):
            bk_map = {"ReggaeOne.ttf": "NotoSansJP-Black.ttf", "BlackHanSans.ttf": "NotoSansKR-Black.ttf"}
            if font_name in bk_map: path = os.path.join(self.font_dir, bk_map[font_name])
            
            # Fallback 2: Về Roboto
            if not os.path.exists(path): path = os.path.join(self.font_dir, "Roboto-Black.ttf")

        try: 
            return ImageFont.truetype(path, size)
        except Exception: 
            return ImageFont.load_default()

    def _create_gradient(self, w, h, direction="left"):
        base = Image.new('RGBA', (w, h), (0,0,0,0))
        draw = ImageDraw.Draw(base)
        limit = int(w * 0.7)
        if direction == "left":
            for x in range(limit):
                alpha = int(230 * (1 - (x/limit)**1.5))
                draw.line([(x,0), (x,h)], fill=(0,0,0, alpha))
        elif direction == "right":
            for x in range(w - limit, w):
                alpha = int(230 * ((x - (w-limit))/limit)**1.5)
                draw.line([(x,0), (x,h)], fill=(0,0,0, alpha))
        return base

    def _draw_rich_text(self, draw, pos, text, font, fill, high):
        """Vẽ text có viền, tô màu keyword và có hiệu ứng Drop Shadow"""
        x, int_y = pos
        words = text.split()
        curr_x = x
        
        # Dùng một hệ số để chữ hơi nhảy lên/xuống nhẹ (tùy chọn, hiện tại để y cố định)
        y = int_y 
        
        for w in words:
            # Kiểm tra xem từ này có phải là số / tiền tệ không
            is_highlight = re.search(r"[\d$€%]", w)
            c = high if is_highlight else fill
            
            # 1. Vẽ Drop Shadow (Bóng mờ) - Tạo chiều sâu
            shadow_offset = 12
            draw.text((curr_x + shadow_offset, y + shadow_offset), w, font=font, fill=(0,0,0, 150))
            
            # 2. Vẽ Stroke Dày (Viền đen 8px) - Giống Submagic
            stroke_w = 8
            for dx in range(-stroke_w, stroke_w+1, 2): # Bước nhảy 2 để render nhanh hơn
                for dy in range(-stroke_w, stroke_w+1, 2):
                    if dx*dx + dy*dy <= stroke_w*stroke_w: # Làm viền bo tròn hơn
                        draw.text((curr_x+dx, y+dy), w, font=font, fill="black")
            
            # 3. Vẽ chữ chính
            draw.text((curr_x, y), w, font=font, fill=c)
            
            # Dịch con trỏ sang phải
            curr_x += font.getlength(w) + font.getlength(" ")

    def _wrap_text(self, text, font, max_w):
        lines = []
        words = text.split()
        curr = []
        for w in words:
            curr.append(w)
            if font.getlength(" ".join(curr)) > max_w:
                curr.pop()
                lines.append(" ".join(curr))
                curr = [w]
        if curr: lines.append(" ".join(curr))
        return lines

    def _add_sticker_effects(self, img):
        # Tạo viền trắng (Stroke)
        stroke = Image.new("RGBA", img.size, (0,0,0,0))
        alpha = img.split()[3]
        mask = alpha.filter(ImageFilter.MaxFilter(7))
        stroke_bg = Image.new("RGBA", img.size, "white")
        stroke_bg.putalpha(mask)
        
        # Shadow
        shadow = mask.filter(ImageFilter.GaussianBlur(10))
        shadow_ly = Image.new("RGBA", img.size, (0,0,0,150))
        shadow_ly.putalpha(shadow)
        
        comp = Image.new("RGBA", img.size)
        comp.paste(shadow_ly, (10,10), shadow_ly)
        comp.paste(stroke_bg, (0,0), stroke_bg)
        comp.paste(img, (0,0), img)
        return comp

    def _hex_to_rgb(self, h):
        h = h.lstrip('#')
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

    # =========================================================================
    # AI THUMBNAIL PIPELINE (Lấy cảm hứng từ yt_thumbnail_creator)
    # =========================================================================
    # Pipeline hoàn toàn tự động:
    #   1. AI Director phân tích topic → Quyết định concept
    #   2. Tạo ảnh nền + Subject bằng Pollinations AI (miễn phí)
    #   3. Xóa nền Subject bằng rembg
    #   4. Ghép multi-layer: BG → Gradient → Subject → Text → CTA
    # =========================================================================

    # --- PROMPT TEMPLATES (Lấy cảm hứng từ yt_thumbnail_creator) ---
    THUMBNAIL_DIRECTOR_PROMPT = """You are a professional YouTube thumbnail designer.
Given a video topic/title, design a thumbnail concept.

Respond ONLY with this JSON format (no extra text):
```json
{{
    "concept": "brief description of the thumbnail idea",
    "background": {{
        "prompt": "detailed prompt for AI background image, cinematic, 4K, no text, no letters",
        "style": "cinematic | vibrant | dark | minimal | neon"
    }},
    "subject": {{
        "prompt": "detailed prompt for the main subject/character, isolated, white background, centered, high quality",
        "has_subject": true
    }},
    "text_primary": "SHORT CATCHY TITLE (max 5 words, ALL CAPS)",
    "text_secondary": "CTA text like WATCH NOW",
    "mood": "Horror | Kids | Funny | Tech | Money | Cinematic | Chill | Emotional",
    "brand_color": "#FF4444"
}}
```

VIDEO TOPIC: {topic}"""

    NEGATIVE_PROMPT_SUFFIX = (
        "(deformed, distorted, disfigured:1.3), poorly drawn, bad anatomy, "
        "wrong anatomy, extra limb, missing limb, floating limbs, "
        "(mutated hands and fingers:1.4), disconnected limbs, mutation, "
        "ugly, disgusting, blurry, amputation, text, letters, watermark, "
        "words, logo, signature"
    )

    def create_ai_thumbnail(self, topic: str, output_path: str, 
                            title_override: str = None,
                            brand_color: str = "#FF0000",
                            country: str = "US",
                            progress_callback=None) -> tuple:
        """
        🚀 Pipeline tự động tạo Thumbnail từ Topic (Lấy cảm hứng yt_thumbnail_creator).
        
        Chỉ cần nhập topic → ra thumbnail 1280x720 hoàn chỉnh.
        
        Args:
            topic: Chủ đề video (VD: "10 cách kiếm tiền online 2025")
            output_path: Đường dẫn file output (VD: "thumbnail.png")
            title_override: Text hiển thị trên thumbnail (nếu None → AI tự sinh)
            brand_color: Màu thương hiệu
            country: Quốc gia đích (để chọn CTA language)
            progress_callback: Hàm log (fn(str))
            
        Returns:
            (success: bool, output_path_or_error: str)
        """
        def log(msg):
            logger.info(msg)
            if progress_callback:
                progress_callback(msg)

        log("🎨 [AI Thumbnail Studio] Bắt đầu pipeline...")
        
        # Tạo thư mục tạm
        temp_dir = os.path.join(os.path.dirname(output_path), "_thumb_ai_temp")
        os.makedirs(temp_dir, exist_ok=True)
        
        try:
            # ─── BƯỚC 1: AI DIRECTOR LÊN Ý TƯỞNG ───
            log("🧠 Bước 1/4: AI Director đang phân tích topic...")
            concept = self._ai_director_plan(topic)
            
            if concept:
                log(f"💡 Concept: {concept.get('concept', 'N/A')}")
                bg_prompt = concept.get("background", {}).get("prompt", "")
                subject_prompt = concept.get("subject", {}).get("prompt", "")
                has_subject = concept.get("subject", {}).get("has_subject", True)
                text_primary = title_override or concept.get("text_primary", topic[:30].upper())
                text_secondary = concept.get("text_secondary", "WATCH NOW")
                mood = concept.get("mood", "Cinematic")
                ai_brand_color = concept.get("brand_color", brand_color)
            else:
                log("⚠️ AI Director không phản hồi, dùng fallback...")
                bg_prompt = f"{topic}, cinematic background, high contrast, dramatic lighting, 4K, no text"
                subject_prompt = f"Person reacting to {topic}, shocked face, white background, centered"
                has_subject = True
                text_primary = title_override or topic[:30].upper()
                text_secondary = "WATCH NOW"
                mood = "Cinematic"
                ai_brand_color = brand_color
            
            # CTA localization
            cta_map = {
                "VN": "XEM NGAY", "JP": "今すぐ見る", "KR": "지금 보세요",
                "DE": "ANSEHEN", "FR": "REGARDER", "ES": "VER AHORA",
                "TH": "ดูเลย", "ID": "TONTON", "RU": "СМОТРЕТЬ"
            }
            text_secondary = cta_map.get(country.upper(), text_secondary)
            
            # ─── BƯỚC 2: TẠO ASSETS (Pollinations AI) ───
            log("🖼️ Bước 2/4: Đang tạo Background...")
            bg_path = self._generate_ai_image(
                f"{bg_prompt}, clean empty space on the left, NO TEXT, NO LETTERS, NO WATERMARK",
                os.path.join(temp_dir, "bg_raw.jpg"),
                width=1280, height=720
            )
            
            if not bg_path:
                return False, "❌ Không tạo được ảnh nền"
            
            subject_path = None
            if has_subject:
                log("👤 Đang tạo Subject (Chủ thể)...")
                subject_raw = self._generate_ai_image(
                    f"{subject_prompt}, isolated subject, clean white background, centered, high detail",
                    os.path.join(temp_dir, "subject_raw.png"),
                    width=768, height=768
                )
                
                if subject_raw and REMBG_AVAILABLE:
                    log("✂️ Đang xóa nền Subject (rembg)...")
                    subject_nobg = os.path.join(temp_dir, "subject_nobg.png")
                    if self.remove_background(subject_raw, subject_nobg):
                        subject_path = subject_nobg
                    else:
                        subject_path = subject_raw
                elif subject_raw:
                    subject_path = subject_raw

            # ─── BƯỚC 3: COMPOSITE LAYERS ───
            log("🔧 Bước 3/4: Đang ghép các lớp (5-Layer Composite)...")
            success, result = self._composite_ai_thumbnail(
                bg_path=bg_path,
                subject_path=subject_path,
                text_primary=text_primary,
                text_secondary=text_secondary,
                output_path=output_path,
                mood=mood,
                brand_color=ai_brand_color
            )
            
            # ─── BƯỚC 4: DỌN DẸP ───
            log("🧹 Bước 4/4: Dọn file tạm...")
            import shutil
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass
            
            if success:
                log(f"🎉 HOÀN TẤT! Thumbnail: {output_path}")
                return True, output_path
            else:
                return False, result
                
        except Exception as e:
            logger.error(f"AI Thumbnail pipeline error: {e}", exc_info=True)
            return False, f"❌ Lỗi pipeline: {e}"

    def _ai_director_plan(self, topic: str) -> dict:
        """Gọi AI (qua AIFactory) để lên concept thumbnail."""
        try:
            from services.ai_factory import AIFactory
            ai = AIFactory()
            
            prompt = self.THUMBNAIL_DIRECTOR_PROMPT.format(topic=topic)
            
            # Thử Gemini trước, fallback Pollinations
            for provider in ["google", "pollinations_text"]:
                success, response = ai.execute_custom_ai(provider, prompt)
                if success and response:
                    # Parse JSON từ response
                    match = re.search(r'\{.*\}', str(response), re.DOTALL)
                    if match:
                        json_str = match.group(0)
                        # Fix common JSON issues
                        json_str = json_str.replace("'", '"')
                        return json.loads(json_str)
            
        except Exception as e:
            logger.warning(f"AI Director failed: {e}")
        
        return None

    def _generate_ai_image(self, prompt: str, save_path: str, 
                           width: int = 1280, height: int = 720) -> str:
        """Tạo ảnh bằng Pollinations AI (miễn phí, không cần API key)."""
        try:
            clean_prompt = f"{prompt}, {self.NEGATIVE_PROMPT_SUFFIX}"
            url = (
                f"https://image.pollinations.ai/prompt/"
                f"{requests.utils.quote(clean_prompt)}"
                f"?width={width}&height={height}&nologo=true"
            )
            
            resp = requests.get(url, timeout=60)
            if resp.status_code == 200 and len(resp.content) > 5000:
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                with open(save_path, "wb") as f:
                    f.write(resp.content)
                return save_path
            else:
                logger.warning(f"Pollinations returned status {resp.status_code}")
                
        except requests.Timeout:
            logger.warning(f"Pollinations timeout for: {prompt[:50]}")
        except Exception as e:
            logger.warning(f"AI image generation failed: {e}")
        
        return None

    def _composite_ai_thumbnail(self, bg_path: str, subject_path: str,
                                 text_primary: str, text_secondary: str,
                                 output_path: str, mood: str = "Cinematic",
                                 brand_color: str = "#FF0000") -> tuple:
        """
        Ghép multi-layer thumbnail (5 lớp):
        Layer 1: Background
        Layer 2: Gradient overlay (tạo negative space)
        Layer 3: Subject (đã xóa nền)
        Layer 4: Text chính (rich text + stroke)
        Layer 5: CTA Button
        """
        try:
            # 1. Load & resize background
            img = Image.open(bg_path).convert("RGBA")
            img = img.resize((1280, 720), Image.Resampling.LANCZOS)
            W, H = img.size
            
            # 2. VFX overlay (nếu có trong kho)
            topic_folder = mood if mood in self.topics else "General"
            self._apply_auto_vfx(img, topic_folder)

            # 3. Gradient (tối nền bên trái để text nổi)
            grad = self._create_gradient(W, H, direction="left")
            img.paste(grad, (0, 0), grad)

            # 4. Subject (bên phải)
            if subject_path and os.path.exists(subject_path):
                subject = Image.open(subject_path).convert("RGBA")
                
                # Resize subject (chiều cao 85% canvas)
                s_h = int(H * 0.85)
                s_w = int(s_h * (subject.width / max(subject.height, 1)))
                s_w = min(s_w, int(W * 0.55))  # Không quá 55% chiều rộng
                subject = subject.resize((s_w, s_h), Image.Resampling.LANCZOS)
                
                # Hiệu ứng pop (viền + bóng)
                subject = self._add_sticker_effects(subject)
                
                # Đặt bên phải
                s_x = W - s_w + 30
                s_y = H - s_h
                img.paste(subject, (s_x, s_y), subject)

            # 5. Text chính (bên trái)
            draw = ImageDraw.Draw(img)
            font_size = 130
            font = self._get_font(text_primary, mood, font_size)
            
            max_text_w = 600 if subject_path else 1000
            lines = self._wrap_text(text_primary, font, max_text_w)
            total_h = len(lines) * 140
            if text_secondary:
                total_h += 110
            
            curr_y = (H - total_h) / 2 - 20
            
            for line in lines:
                self._draw_rich_text(draw, (50, curr_y), line, font, "white", "#FFDD00")
                curr_y += 140

            # 6. CTA Button
            if text_secondary:
                curr_y += 20
                font_cta = self._get_font(text_secondary, mood, 75)
                l, t, r, b = font_cta.getbbox(text_secondary)
                bw, bh = r - l + 60, b - t + 40
                bx = 50

                brand_rgb = self._hex_to_rgb(brand_color)
                # Shadow
                draw.rectangle(
                    [(bx + 8, curr_y + 8), (bx + bw + 8, curr_y + bh + 8)],
                    fill=(0, 0, 0, 180)
                )
                # Main button
                draw.rectangle(
                    [(bx, curr_y), (bx + bw, curr_y + bh)],
                    fill=brand_rgb, outline="white", width=4
                )
                draw.text((bx + 30, curr_y + 10), text_secondary, font=font_cta, fill="white")

            # 7. Arrow (nếu có trong kho)
            if subject_path:
                text_end = (50 + max_text_w // 2, curr_y)
                target = (W - 300, H // 3)
                self._apply_auto_arrow(img, text_end, target, "left")

            # 8. Final output
            final = img.convert("RGB")
            final = ImageEnhance.Contrast(final).enhance(1.25)
            final = ImageEnhance.Sharpness(final).enhance(1.5)
            final = ImageEnhance.Color(final).enhance(1.15)
            
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            final.save(output_path, quality=95)
            return True, output_path

        except Exception as e:
            traceback.print_exc()
            return False, str(e)