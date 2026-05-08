import os
import requests
import time
from .base_platform import BasePublisherPlatform

class InstagramPlatform(BasePublisherPlatform):
    def __init__(self):
        self.credentials_dir = "VEO_DB/credentials/instagram"
        os.makedirs(self.credentials_dir, exist_ok=True)

    @property
    def platform_name(self) -> str:
        return "Instagram"

    @property
    def auth_method(self) -> str:
        return "Graph API (IG Creator/Business)"

    def authenticate(self, credentials: dict) -> bool:
        """
        Yêu cầu:
        - 'ig_user_id': Instagram Business/Creator Account ID
        - 'access_token': Page Access Token được cấp quyền instagram_basic, instagram_content_publish
        """
        self.ig_user_id = credentials.get("ig_user_id")
        self.access_token = credentials.get("access_token")
        
        if not self.ig_user_id or not self.access_token:
            return False
        return True

    def upload_video(self, video_path: str, metadata: dict) -> dict:
        """
        LƯU Ý QUAN TRỌNG: 
        Instagram Graph API KHÔNG cho phép upload trực tiếp file MP4 cục bộ từ máy tính.
        Nó yêu cầu một `video_url` (Public URL) để Facebook tự tải về.
        
        Để ứng dụng này tự động hóa 100%, có 2 giải pháp:
        1. (Đang dùng) Tải file tạm lên một server / Cloud Storage (VD: Imgur, AWS S3, Dropbox public link).
        2. Chạy một HTTP Server nội bộ ngắn hạn bằng Python ngrok để expose file.
        
        *Code dưới đây giả định video_path đã được đẩy lên mây và biến thành Public URL,
        hoặc người dùng đưa vào một URL public sẵn.*
        """
        
        if not hasattr(self, 'access_token'):
            return {"status": "error", "error": "Chưa xác thực."}

        # [GIẢ ĐỊNH] Nếu truyền vào file nội bộ, cần có logic Upload to Cloud ở đây.
        # Tạm thời giả lập public_url
        public_video_url = video_path if video_path.startswith("http") else "ERROR_LOCAL_FILE_NEEDS_CLOUD_LINK"
        
        if "ERROR" in public_video_url:
            return {
                "status": "error", 
                "error": "Instagram API yêu cầu Video URL công khai. Vui lòng thêm module S3 Storage hoặc Ngrok để làm Public URL trước khi gọi API này."
            }

        try:
            # --- BƯỚC 1: Tạo Container ---
            print("[Instagram] Đang tạo Media Container...")
            container_url = f"https://graph.facebook.com/v19.0/{self.ig_user_id}/media"
            payload_container = {
                "media_type": "REELS",
                "video_url": public_video_url,
                "caption": metadata.get("description", "Instagram Reel via VeoSuite"),
                "access_token": self.access_token
            }
            
            resp1 = requests.post(container_url, data=payload_container).json()
            creation_id = resp1.get("id")
            
            if not creation_id:
                return {"status": "error", "error": f"Lỗi tạo container: {resp1}"}

            # --- BƯỚC 2: Chờ Instagram tải video từ Server về ---
            status_url = f"https://graph.facebook.com/v19.0/{creation_id}?fields=status_code&access_token={self.access_token}"
            print("[Instagram] Chờ Facebook Render Video...")
            for _ in range(15): # Chờ tối đa 15x3 = 45 giây
                status_resp = requests.get(status_url).json()
                if status_resp.get("status_code") == "FINISHED":
                    break
                time.sleep(3)

            # --- BƯỚC 3: Xuất bản (Publish) ---
            print("[Instagram] Bắt đầu xuất bản...")
            publish_url = f"https://graph.facebook.com/v19.0/{self.ig_user_id}/media_publish"
            payload_publish = {
                "creation_id": creation_id,
                "access_token": self.access_token
            }
            
            resp_publish = requests.post(publish_url, data=payload_publish).json()
            published_id = resp_publish.get("id")
            
            if published_id:
                return {"status": "success", "url": f"https://instagram.com/reel/{published_id}", "video_id": published_id}
            else:
                return {"status": "error", "error": f"Lỗi Publish: {resp_publish}"}
                
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def get_status(self) -> str:
        if hasattr(self, 'access_token') and self.access_token:
            return "⚠️ Cần kho lưu trữ Đám mây (S3/Ngrok) cho IG"
        return "❌ Chưa thiết lập thông tin"
