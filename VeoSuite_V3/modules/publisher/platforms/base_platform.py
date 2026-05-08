from abc import ABC, abstractmethod


class BasePublisherPlatform(ABC):
    """
    Interface gốc cho mọi nền tảng phát hành.
    Kiến trúc Plugin: Để thêm nền tảng mới, chỉ cần kế thừa class này.
    """

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Tên nền tảng (VD: 'YouTube', 'TikTok')"""
        pass

    @property
    @abstractmethod
    def auth_method(self) -> str:
        """Phương thức xác thực (VD: 'OAuth 2.0', 'Session Cookie')"""
        pass

    @abstractmethod
    def authenticate(self, credentials: dict) -> bool:
        """
        Xử lý logic đăng nhập/xác thực.
        Trả về True nếu xác thực thành công.
        """
        pass

    @abstractmethod
    def upload_video(self, video_path: str, metadata: dict) -> dict:
        """
        Thực hiện upload video lên nền tảng.
        Trả về dict chứa thông tin kết quả: {"status": "success/error", "url": "...", "error": "..."}
        """
        pass

    @abstractmethod
    def get_status(self) -> str:
        """Kiểm tra tình trạng tài khoản/token (còn hạn/hết hạn)"""
        pass
