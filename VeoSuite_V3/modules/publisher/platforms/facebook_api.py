import os
import requests
import json
from .base_platform import BasePublisherPlatform

class FacebookReelsPlatform(BasePublisherPlatform):
    def __init__(self):
        self.credentials_dir = "VEO_DB/credentials/facebook"
        os.makedirs(self.credentials_dir, exist_ok=True)

    @property
    def platform_name(self) -> str:
        return "Facebook Reels"

    @property
    def auth_method(self) -> str:
        return "Graph API / Page Access Token"

    def authenticate(self, credentials: dict) -> bool:
        """
        credentials yêu cầu:
        - 'page_id': ID của Fanpage
        - 'access_token': Page Access Token (Loại Never Expire lấy từ Facebook Developer)
        """
        self.page_id = credentials.get("page_id")
        self.access_token = credentials.get("access_token")
        
        if not self.page_id or not self.access_token:
            print("[Facebook] Thiếu page_id hoặc access_token")
            return False
            
        # Kiểm tra token hợp lệ bằng cách lấy thông tin Page
        url = f"https://graph.facebook.com/v19.0/{self.page_id}?access_token={self.access_token}"
        resp = requests.get(url)
        if resp.status_code == 200:
            return True
        else:
            print(f"[Facebook] Token không hợp lệ: {resp.json()}")
            return False

    def upload_video(self, video_path: str, metadata: dict) -> dict:
        """
        Tải lên Facebook Reels theo chuẩn 3 bước của Graph API v19.0+
        """
        if not hasattr(self, 'access_token'):
            return {"status": "error", "error": "Chưa xác thực Graph API"}
            
        if not os.path.exists(video_path):
            return {"status": "error", "error": "File không tồn tại."}

        try:
            file_size = os.path.getsize(video_path)
            
            # --- BƯỚC 1: Khởi tạo phiên tải lên (Start Phase) ---
            init_url = f"https://graph.facebook.com/v19.0/{self.page_id}/video_reels"
            init_payload = {
                "upload_phase": "start",
                "access_token": self.access_token
            }
            init_resp = requests.post(init_url, data=init_payload).json()
            video_id = init_resp.get("video_id")
            upload_url = init_resp.get("upload_url") # Không dùng upload_url này vì deprecated, dùng rupload thay thế
            
            if not video_id:
                return {"status": "error", "error": f"Khởi tạo lỗi: {init_resp}"}

            print(f"[Facebook] Đã khởi tạo Video ID: {video_id}")

            # --- BƯỚC 2: Upload File (Transfer Phase) ---
            # Graph API mới yêu cầu bắn binary lên rupload.facebook.com
            rupload_url = f"https://rupload.facebook.com/video-upload/v19.0/{video_id}"
            headers = {
                "Authorization": f"OAuth {self.access_token}",
                "offset": "0",
                "file_size": str(file_size)
            }
            
            print("[Facebook] Đang truyền tải dữ liệu (Transferring)...")
            with open(video_path, 'rb') as f:
                upload_resp = requests.post(rupload_url, headers=headers, data=f)
            
            if upload_resp.status_code != 200:
                return {"status": "error", "error": f"Lỗi Transfer Phase: {upload_resp.text}"}

            # --- BƯỚC 3: Xuất bản (Publish Phase) ---
            print("[Facebook] Đang xuất bản (Publishing)...")
            publish_payload = {
                "upload_phase": "finish",
                "access_token": self.access_token,
                "video_state": "PUBLISHED",
                "description": metadata.get("description", "Video Reels")
            }
            publish_resp = requests.post(init_url, data=publish_payload).json()
            
            if publish_resp.get("success"):
                return {
                    "status": "success", 
                    "url": f"https://facebook.com/{self.page_id}/videos/{video_id}",
                    "video_id": video_id
                }
            else:
                return {"status": "error", "error": f"Lỗi Publish Phase: {publish_resp}"}
                
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def get_status(self) -> str:
        if hasattr(self, 'access_token') and self.access_token:
            return "✅ Sẵn sàng (Token đang hoạt động)"
        return "❌ Chưa thiết lập Page ID hoặc Token"
