# Plugin Registry
from .youtube_api import YouTubePlatform
from .tiktok_api import TikTokPlatform
from .facebook_api import FacebookReelsPlatform
from .instagram_api import InstagramPlatform

# Danh sách các plugin được hỗ trợ sẵn
AVAILABLE_PLATFORMS = {
    "YouTube": YouTubePlatform,
    "TikTok": TikTokPlatform,
    "Facebook Reels": FacebookReelsPlatform,
    "Instagram": InstagramPlatform
}

def get_platform_instance(platform_name: str):
    """Factory method để lấy instance của một nền tảng dựa trên tên"""
    if platform_name in AVAILABLE_PLATFORMS:
        return AVAILABLE_PLATFORMS[platform_name]()
    return None
