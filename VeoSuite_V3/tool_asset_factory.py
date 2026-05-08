# tool_asset_factory.py
# Phiên bản "Du kích" - Chống block 502

import os
import requests
import time
import random
from PIL import Image
from io import BytesIO

# --- 1. DANH SÁCH MONG MUỐN (Giữ nguyên) ---
ASSET_WISH_LIST = {
    "Money": [
        "stack of gold coins 3d", "flying dollar bills", "money bag with dollar sign", 
        "diamond gem 3d", "gold bar bullion", "green raising graph arrow", 
        "piggy bank 3d", "bitcoin coin gold", "wallet full of money"
    ],
    "Horror": [
        "scary ghost face", "human skull realistic", "blood splatter pattern", 
        "zombie hand reaching out", "spooky pumpkin jack o lantern", "red devil eyes",
        "creepy doll face", "haunted house silhouette", "knife with blood"
    ],
    "Reaction": [
        "shocked emoji face 3d", "crying laughing emoji 3d", "angry face red 3d", 
        "thumbs up 3d icon blue", "heart shape 3d red", "fire flame icon 3d", 
        "explosion boom comic style", "question mark 3d yellow", "exclamation mark red"
    ],
    "News": [
        "breaking news badge", "microphone press 3d", "live stream red badge", 
        "world globe 3d", "newspaper roll", "police siren light"
    ],
    "Arrows": [
        "red curved arrow pointing right", "yellow curved arrow pointing down", 
        "neon green arrow glowing", "hand finger pointing right 3d"
    ]
}

# Thư mục gốc
BASE_DIR = os.path.join("assets", "overlays")

# --- DANH SÁCH USER-AGENT GIẢ LẬP (Để ko bị chặn) ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"
]

def setup_folders():
    for cat in ASSET_WISH_LIST.keys():
        path = os.path.join(BASE_DIR, "Stickers", cat)
        if cat == "Arrows": path = os.path.join(BASE_DIR, "Arrows", "General")
        os.makedirs(path, exist_ok=True)

def generate_and_save(category, keyword):
    # 1. Xác định nơi lưu
    save_folder = os.path.join(BASE_DIR, "Stickers", category)
    if category == "Arrows": save_folder = os.path.join(BASE_DIR, "Arrows", "General")
    
    safe_name = keyword.replace(" ", "_").lower()
    file_path = os.path.join(save_folder, f"{safe_name}.png")
    
    if os.path.exists(file_path):
        print(f"⏩ Đã có: {keyword} -> Bỏ qua.")
        return

    # 2. Tạo Prompt đơn giản hóa (Giảm bớt từ khóa phức tạp để server xử lý nhanh hơn)
    seed = random.randint(1, 999999)
    # Prompt ngắn gọn hơn để tăng khả năng thành công
    prompt = f"{keyword}, 3d icon, white background" 
    
    # URL tối giản (Không tham số query, dùng path)
    # Đây là định dạng cũ nhưng ổn định hơn: /prompt/noidung
    url_prompt = requests.utils.quote(prompt)
    image_url = f"https://image.pollinations.ai/prompt/{url_prompt}?nologo=true&seed={seed}"

    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Chọn ngẫu nhiên 1 trình duyệt để giả dạng
            headers = {"User-Agent": random.choice(USER_AGENTS)}
            
            print(f"🎨 Đang vẽ (Lần {attempt+1}): {keyword}...")
            # Tăng timeout lên 60s
            resp = requests.get(image_url, headers=headers, timeout=60)
            
            if resp.status_code == 200:
                img = Image.open(BytesIO(resp.content)).convert("RGBA")
                
                print(f"   ✂️ Đang tách nền...")
                try:
                    from rembg import remove
                    img_byte = BytesIO()
                    img.save(img_byte, format='PNG')
                    
                    output_data = remove(img_byte.getvalue())
                    final_img = Image.open(BytesIO(output_data)).convert("RGBA")
                    final_img.thumbnail((512, 512), Image.Resampling.LANCZOS)
                    final_img.save(file_path)
                    print(f"   ✅ Thành công: {safe_name}.png")
                    
                    # QUAN TRỌNG: Nghỉ 5 giây sau khi thành công để không bị block tiếp
                    time.sleep(5) 
                    return
                    
                except Exception as e:
                    print(f"   ❌ Lỗi xử lý ảnh: {e}")
                    return
            else:
                print(f"   ⚠️ Server lỗi {resp.status_code}. Đợi 10s...")
                time.sleep(10) # Lỗi thì nghỉ hẳn 10s

        except Exception as e:
            print(f"   ⚠️ Lỗi mạng: {e}")
            time.sleep(10)
            
    print(f"❌ BỎ QUA: '{keyword}' (Server đang quá tải)")

def run_factory():
    print("🏭 KHỞI ĐỘNG AI FACTORY (CHẾ ĐỘ CHẬM MÀ CHẮC)...")
    setup_folders()
    
    # Kiểm tra rembg
    try: import rembg
    except: 
        print("⚠️ Chưa cài rembg -> Sẽ lưu ảnh nền trắng.")

    total_tasks = sum(len(v) for v in ASSET_WISH_LIST.values())
    count = 0
    
    for category, keywords in ASSET_WISH_LIST.items():
        print(f"\n--- NHÓM: {category.upper()} ---")
        for kw in keywords:
            count += 1
            print(f"[{count}/{total_tasks}]", end=" ")
            generate_and_save(category, kw)
            
    print("\n🏁 KẾT THÚC.")

if __name__ == "__main__":
    run_factory()