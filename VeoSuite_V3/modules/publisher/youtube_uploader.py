"""
VEO SUITE V3 — YouTubeUploader
================================
Upload video lên YouTube qua YouTube Data API v3 (OAuth2).

Yêu cầu (chỉ khi muốn upload thật):
    pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib

Cấu trúc:
- Mỗi channel = 1 cặp (client_secret.json + token.json) lưu ở thư mục credentials.
- `authenticate_channel(channel_id, client_secret_path)` — chạy OAuth flow, cache token.
- `upload_video(channel_id, video_path, title, ...)` — gọi API thật.
- Nếu thư viện google-api chưa cài, class tự động hạ xuống chế độ MOCK
  (giữ nguyên hành vi cũ để các test/UI không break).
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("VeoSuite.Publisher.YouTube")

# Cố gắng import google-api lazy để app chạy được khi chưa cài.
try:
    from google.auth.transport.requests import Request  # type: ignore
    from google.oauth2.credentials import Credentials  # type: ignore
    from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore
    from googleapiclient.discovery import build  # type: ignore
    from googleapiclient.http import MediaFileUpload  # type: ignore
    _GOOGLE_AVAILABLE = True
except ImportError:
    _GOOGLE_AVAILABLE = False
    logger.info(
        "google-api-python-client chưa được cài — YouTubeUploader chạy ở "
        "chế độ MOCK. Cài đặt: pip install google-api-python-client "
        "google-auth-oauthlib"
    )


# Scope upload
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# Thư mục lưu token mặc định: ~/.veo_suite/youtube
DEFAULT_TOKEN_DIR = Path.home() / ".veo_suite" / "youtube"


class YouTubeUploader:
    """Upload video lên YouTube — production-ready khi google-api có sẵn."""

    def __init__(self, token_dir: Optional[str] = None, mock: Optional[bool] = None):
        self.token_dir = Path(token_dir) if token_dir else DEFAULT_TOKEN_DIR
        self.token_dir.mkdir(parents=True, exist_ok=True)
        # Mock mode: tuỳ chọn ép buộc, mặc định = bật khi google-api không có
        self.mock = (not _GOOGLE_AVAILABLE) if mock is None else bool(mock)
        self._services: Dict[str, Any] = {}
        self.is_authenticated = False
        self.channels: Dict[str, bool] = {}

    # =====================================================================
    # OAuth
    # =====================================================================

    def _token_path(self, channel_id: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in channel_id)
        return self.token_dir / f"token_{safe}.json"

    def authenticate_channel(
        self, channel_id: str, client_secret_path: str
    ) -> bool:
        """OAuth2 flow cho 1 channel. Cache token để lần sau auto-refresh."""
        if self.mock:
            logger.info("[MOCK] authenticate_channel(%s)", channel_id)
            self.channels[channel_id] = True
            self.is_authenticated = True
            return True

        if not os.path.exists(client_secret_path):
            logger.error("client_secret not found: %s", client_secret_path)
            return False

        token_path = self._token_path(channel_id)
        creds: Optional[Credentials] = None

        if token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(
                    str(token_path), SCOPES
                )
            except Exception as e:
                logger.warning("Cannot load token (%s): %s", token_path, e)
                creds = None

        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                logger.warning("Token refresh failed: %s — re-authorizing", e)
                creds = None

        if not creds or not creds.valid:
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    client_secret_path, SCOPES
                )
                # run_local_server mở browser; nếu chạy headless thì dùng
                # run_console (deprecated nhưng còn dùng được).
                creds = flow.run_local_server(port=0)
            except Exception as e:
                logger.error("OAuth flow failed: %s", e)
                return False

        try:
            token_path.write_text(creds.to_json(), encoding="utf-8")
        except OSError as e:
            logger.warning("Cannot persist token: %s", e)

        self._services[channel_id] = build("youtube", "v3", credentials=creds)
        self.channels[channel_id] = True
        self.is_authenticated = True
        logger.info("Authenticated channel: %s", channel_id)
        return True

    # =====================================================================
    # Upload
    # =====================================================================

    def upload_video(
        self,
        channel_id: str,
        video_path: str,
        title: str,
        description: str = "",
        tags: Optional[list] = None,
        privacy_status: str = "private",
        category_id: str = "22",  # People & Blogs
    ) -> Tuple[bool, str]:
        """Upload 1 file video. Trả về (success, url_or_error)."""
        if not os.path.exists(video_path):
            return False, f"Video not found: {video_path}"

        if not self.channels.get(channel_id):
            return False, f"Channel '{channel_id}' chưa authenticate"

        if self.mock:
            logger.info(
                "[MOCK] upload %s -> %s (%s, %s)",
                video_path, channel_id, title, privacy_status,
            )
            time.sleep(0.5)  # giả lập latency
            return True, "https://youtube.com/watch?v=mock_id"

        service = self._services.get(channel_id)
        if service is None:
            return False, f"No active service for channel '{channel_id}'"

        body = {
            "snippet": {
                "title": title[:100],          # YouTube giới hạn 100
                "description": description[:5000],
                "tags": (tags or [])[:500],
                "categoryId": category_id,
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }
        media = MediaFileUpload(
            video_path, chunksize=-1, resumable=True, mimetype="video/*"
        )

        try:
            request = service.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media,
            )
            response = None
            last_progress = -1
            while response is None:
                status, response = request.next_chunk()
                if status:
                    pct = int(status.progress() * 100)
                    if pct != last_progress:
                        last_progress = pct
                        logger.info("Upload %s: %d%%", channel_id, pct)
            video_id = response.get("id")
            url = f"https://youtube.com/watch?v={video_id}" if video_id else "(no id)"
            logger.info("Upload OK: %s -> %s", title, url)
            return True, url
        except Exception as e:
            logger.exception("Upload failed: %s", e)
            return False, str(e)

    # =====================================================================
    # Diagnostics
    # =====================================================================

    def list_channels(self) -> Dict[str, Dict[str, Any]]:
        """Trả về channel-status để UI hiển thị."""
        out: Dict[str, Dict[str, Any]] = {}
        for ch_id, ok in self.channels.items():
            out[ch_id] = {
                "authenticated": bool(ok),
                "mock": self.mock,
                "token_path": str(self._token_path(ch_id)),
            }
        return out
