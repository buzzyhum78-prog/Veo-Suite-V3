"""
VEO SUITE V3.3 — Stock Media Service (Multi-Source Fallback)
==============================================================
Tìm và tải ảnh/video stock từ nhiều nguồn (lấy cảm hứng MoneyPrinterTurbo):
  1. Pexels (ưu tiên — chất lượng cao nhất)
  2. Pixabay (fallback)
  3. AI Image Generate (fallback cuối — Pollinations free)

Hỗ trợ: landscape/portrait, video fallback sang ảnh, HD/4K ưu tiên.
"""

import logging
import os
import random

import requests

from services.ai_factory import AIFactory

logger = logging.getLogger("VeoSuite.Stock")

# Timeout cho API calls
API_TIMEOUT = 15
DOWNLOAD_TIMEOUT = 30


class StockService:
    """Service tìm và tải stock media (ảnh/video)."""

    def __init__(self, api_key_pexels: str = None, api_key_pixabay: str = None):
        self.ai = AIFactory()

        # Pexels key: truyền vào > env > registry > rỗng
        self.pexels_key = (
            api_key_pexels
            or os.getenv("PEXELS_API_KEY", "").strip()
            or self.ai.registry.get("providers", {})
            .get("pexels", {})
            .get("api_key", "")
        )

        # Pixabay key: truyền vào > env > registry > rỗng (KHÔNG hardcode key)
        self.pixabay_key = (
            api_key_pixabay
            or os.getenv("PIXABAY_API_KEY", "").strip()
            or self.ai.registry.get("providers", {})
            .get("pixabay", {})
            .get("api_key", "")
        )

        # API Endpoints
        self._pexels_img = "https://api.pexels.com/v1/search"
        self._pexels_vid = "https://api.pexels.com/videos/search"
        self._pixabay_img = "https://pixabay.com/api/"
        self._pixabay_vid = "https://pixabay.com/api/videos/"

    # =========================================================================
    # PUBLIC: Download visual
    # =========================================================================

    def download_visual(self, keyword: str, save_folder: str,
                        orientation: str = "landscape", media_type: str = "video"):
        """
        Tìm và tải visual. Returns (success: bool, path_or_message: str).

        Args:
            keyword: Từ khóa tìm kiếm
            save_folder: Thư mục lưu file
            orientation: 'landscape' hoặc 'portrait'
            media_type: 'video' hoặc 'image'
        """
        os.makedirs(save_folder, exist_ok=True)
        logger.info(f"Searching '{media_type}' ({orientation}): '{keyword}'")

        has_pexels = self.pexels_key and len(self.pexels_key) > 10

        # Video pipeline
        if media_type == "video":
            # 1. Pexels Video
            if has_pexels:
                url = self._search_pexels_video(keyword, orientation)
                if url:
                    return self._download_file(url, save_folder, "pex_vid")

            # 2. Pixabay Video
            url = self._search_pixabay_video(keyword, orientation)
            if url:
                return self._download_file(url, save_folder, "pix_vid")

            logger.info("No video found, falling back to image")

        # Image pipeline
        if has_pexels:
            url = self._search_pexels_image(keyword, orientation)
            if url:
                return self._download_file(url, save_folder, "pex_img", ".jpg")

        url = self._search_pixabay_image(keyword, orientation)
        if url:
            return self._download_file(url, save_folder, "pix_img", ".jpg")

        # ═══ FALLBACK CUỐI: AI Image Generate (Pollinations) ═══
        logger.info(f"All stock sources failed for '{keyword}', falling back to AI generation")
        try:
            ai_prompt = f"{keyword}, photorealistic, high quality, 4K"
            ai_url = f"https://image.pollinations.ai/prompt/{requests.utils.quote(ai_prompt)}?width=1920&height=1080&nologo=true"
            # Tăng timeout lên 60s và bắt lỗi cụ thể
            resp = requests.get(ai_url, timeout=60)
            if resp.status_code == 200:
                rand_id = random.randint(1000, 9999)
                save_path = os.path.join(save_folder, f"ai_fallback_{rand_id}.jpg")
                with open(save_path, "wb") as f:
                    f.write(resp.content)
                logger.info(f"AI fallback generated: {save_path}")
                return True, save_path
        except requests.Timeout:
            logger.warning(f"AI fallback timed out after 60s for: {keyword}")
        except Exception as e:
            logger.warning(f"AI fallback failed: {e}")

        return False, "No visual found from any source (Pexels → Pixabay → AI)"

    # =========================================================================
    # PRIVATE: Search APIs
    # =========================================================================

    def _search_pexels_video(self, query: str, orient: str):
        """Tìm video trên Pexels. Returns URL hoặc None."""
        try:
            resp = requests.get(
                self._pexels_vid,
                headers={"Authorization": self.pexels_key},
                params={"query": query, "per_page": 10, "orientation": orient, "size": "large"},
                timeout=API_TIMEOUT,
            )
            if resp.status_code == 200:
                videos = resp.json().get("videos", [])
                if videos:
                    # Ưu tiên HD file đúng orientation (MoneyPrinterTurbo approach)
                    best_url = None
                    best_quality = 0
                    for vid in videos:
                        for f in vid["video_files"]:
                            w = f.get("width", 0)
                            h = f.get("height", 0)
                            quality = w * h
                            ok_orient = (
                                (orient == "portrait" and h > w) or
                                (orient == "landscape" and w > h) or
                                orient not in ("portrait", "landscape")
                            )
                            if ok_orient and quality > best_quality and quality <= 1920*1080:
                                best_quality = quality
                                best_url = f["link"]
                    if best_url:
                        return best_url
                    # Fallback: bất kỳ file nào
                    return videos[0]["video_files"][0]["link"]
        except requests.RequestException as e:
            logger.debug(f"Pexels video search failed: {e}")
        return None

    def _search_pixabay_video(self, query: str, orient: str):
        """Tìm video trên Pixabay. Returns URL hoặc None."""
        try:
            resp = requests.get(
                self._pixabay_vid,
                params={"key": self.pixabay_key, "q": query, "video_type": "film", "per_page": 10},
                timeout=API_TIMEOUT,
            )
            if resp.status_code == 200:
                hits = resp.json().get("hits", [])
                if hits:
                    # Ưu tiên chất lượng cao nhất: large > medium > small
                    vid = hits[0]["videos"]
                    return (vid.get("large", {}) or vid.get("medium", {})).get("url", "")
        except requests.RequestException as e:
            logger.debug(f"Pixabay video search failed: {e}")
        return None

    def _search_pexels_image(self, query: str, orient: str):
        """Tìm ảnh trên Pexels. Returns URL hoặc None."""
        try:
            resp = requests.get(
                self._pexels_img,
                headers={"Authorization": self.pexels_key},
                params={"query": query, "per_page": 5, "orientation": orient},
                timeout=API_TIMEOUT,
            )
            if resp.status_code == 200:
                photos = resp.json().get("photos", [])
                if photos:
                    return photos[0]["src"]["large2x"]
        except requests.RequestException as e:
            logger.debug(f"Pexels image search failed: {e}")
        return None

    def _search_pixabay_image(self, query: str, orient: str):
        """Tìm ảnh trên Pixabay. Returns URL hoặc None."""
        try:
            orient_param = "vertical" if orient == "portrait" else "horizontal"
            resp = requests.get(
                self._pixabay_img,
                params={"key": self.pixabay_key, "q": query, "image_type": "photo",
                        "orientation": orient_param},
                timeout=API_TIMEOUT,
            )
            if resp.status_code == 200:
                hits = resp.json().get("hits", [])
                if hits:
                    return hits[0]["largeImageURL"]
        except requests.RequestException as e:
            logger.debug(f"Pixabay image search failed: {e}")
        return None

    # =========================================================================
    # PUBLIC: Download music
    # =========================================================================

    def download_music(self, keyword: str, save_path: str):
        """
        Tìm và tải nhạc từ Pixabay. Returns (success, message).
        """
        logger.info(f"Searching music for: '{keyword}'")
        if not self.pixabay_key:
            return False, (
                "Pixabay API key chưa được cấu hình. Đặt biến môi trường "
                "PIXABAY_API_KEY hoặc nhập trong Tab Quản Trị (provider 'pixabay')."
            )
        url = "https://pixabay.com/api/audio/"

        try:
            resp = requests.get(url, params={
                "key": self.pixabay_key,
                "q": keyword,
                "per_page": 5
            }, timeout=API_TIMEOUT)
            
            if resp.status_code == 200:
                hits = resp.json().get("hits", [])
                if hits:
                    # Lấy track đầu tiên
                    track = hits[0]
                    audio_url = track.get("unlocked_url") or track.get("url")
                    if audio_url:
                        return self._download_file_to_path(audio_url, save_path)
            
            return False, "No music found"
        except Exception as e:
            logger.error(f"Music search failed: {e}")
            return False, str(e)

    # =========================================================================
    # PRIVATE: Download file
    # =========================================================================

    def _download_file_to_path(self, url: str, full_path: str):
        """Download file trực tiếp vào đường dẫn chỉ định."""
        try:
            with requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT) as r:
                r.raise_for_status()
                with open(full_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            return True, full_path
        except Exception as e:
            return False, str(e)

    @staticmethod
    def _download_file(url: str, folder: str, prefix: str, ext: str = ".mp4"):
        """Download file từ URL. Returns (success, filepath)."""
        try:
            # Auto-detect extension
            if ".jpg" in url:
                ext = ".jpg"
            elif ".png" in url:
                ext = ".png"
            elif ".mp4" in url:
                ext = ".mp4"

            rand_id = random.randint(1000, 9999)
            filename = f"{prefix}_{rand_id}{ext}"
            path = os.path.join(folder, filename)

            with requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT) as r:
                r.raise_for_status()
                with open(path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)

            logger.info(f"Downloaded: {filename}")
            return True, path

        except Exception as e:
            logger.error(f"Download failed: {e}")
            return False, str(e)
