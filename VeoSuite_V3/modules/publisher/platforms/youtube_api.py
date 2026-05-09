import os
import pickle

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from .base_platform import BasePublisherPlatform


class YouTubePlatform(BasePublisherPlatform):
    # Các quyền cần thiết để upload video
    SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

    def __init__(self):
        self.credentials_dir = "VEO_DB/credentials/youtube"
        os.makedirs(self.credentials_dir, exist_ok=True)
        self.client_secret_file = os.path.join(self.credentials_dir, "client_secret.json")

    @property
    def platform_name(self) -> str:
        return "YouTube"

    @property
    def auth_method(self) -> str:
        return "OAuth 2.0 (Google API)"

    def authenticate(self, credentials: dict) -> bool:
        """
        credentials_dict có thể chứa 'channel_id' để lưu token riêng cho từng kênh.
        VD: {"channel_id": "Keto_Daily"}
        """
        channel_id = credentials.get("channel_id", "default_channel")
        token_file = os.path.join(self.credentials_dir, f"{channel_id}_token.pickle")

        creds = None
        # Đọc token đã lưu nếu có
        if os.path.exists(token_file):
            with open(token_file, "rb") as token:
                creds = pickle.load(token)

        # Nếu không có token hợp lệ, yêu cầu người dùng đăng nhập
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    print(f"[YouTube] Lỗi refresh token: {e}")
                    creds = None

            if not creds:
                if not os.path.exists(self.client_secret_file):
                    print(
                        f"[YouTube] LỖI CHÍNH: Thiếu file {self.client_secret_file}. Vui lòng tạo OAuth App trên Google Cloud Console và tải xuống."
                    )
                    return False

                # Mở trình duyệt để xác thực
                flow = InstalledAppFlow.from_client_secrets_file(self.client_secret_file, self.SCOPES)
                creds = flow.run_local_server(port=0)

            # Lưu lại token cho lần sau
            with open(token_file, "wb") as token:
                pickle.dump(creds, token)

        self.creds = creds
        return True

    def upload_video(self, video_path: str, metadata: dict) -> dict:
        """
        Thực hiện tải lên YouTube.
        metadata = {
            "title": "...", "description": "...", "tags": ["tag1", "tag2"],
            "categoryId": "22", "privacyStatus": "public", "made_for_kids": False
        }
        """
        if not hasattr(self, "creds") or not self.creds:
            return {"status": "error", "error": "Chưa xác thực OAuth2."}

        if not os.path.exists(video_path):
            return {"status": "error", "error": f"Không tìm thấy file video: {video_path}"}

        try:
            youtube = build("youtube", "v3", credentials=self.creds)

            body = {
                "snippet": {
                    "title": metadata.get("title", "Video Tự động VeoSuite"),
                    "description": metadata.get("description", ""),
                    "tags": metadata.get("tags", []),
                    "categoryId": metadata.get("categoryId", "22"),
                },
                "status": {
                    "privacyStatus": metadata.get("privacyStatus", "private"),
                    "selfDeclaredMadeForKids": metadata.get("made_for_kids", False),
                },
            }

            # Khởi tạo tiến trình tải lên (Chunked upload)
            media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
            request = youtube.videos().insert(part=",".join(body.keys()), body=body, media_body=media)

            # Thực thi tải lên
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    print(f"[YouTube] Uploading... {progress}%")

            video_id = response.get("id")
            return {
                "status": "success",
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "video_id": video_id,
            }

        except Exception as e:
            return {"status": "error", "error": str(e)}

    def get_status(self) -> str:
        if hasattr(self, "creds") and self.creds and self.creds.valid:
            return "✅ Sẵn sàng (OAuth Hợp lệ)"
        return "❌ Chưa xác thực hoặc Token hết hạn"
