"""
VEO SUITE V3.2 — VPN Manager
================================
Quản lý đổi IP đa năng:
  1. Cloudflare WARP (miễn phí)
  2. DCOM 3G/4G (reset kết nối)
  3. HTTP Proxy rotation

Đọc cấu hình từ VEO_DB/config.json (do Admin Tab tạo).
"""

import json
import logging
import os
import random
import shutil
import subprocess
import time

from services.config_manager import VPN_CONFIG_FILE

logger = logging.getLogger("VeoSuite.VPN")


class VPNManager:
    """Quản lý đổi IP tự động."""

    def __init__(self):
        self.config = self._load_config()
        self.provider = self.config.get("vpn_provider", "none")

    def _load_config(self) -> dict:
        """Load VPN config từ file."""
        if VPN_CONFIG_FILE.exists():
            try:
                with open(VPN_CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                logger.warning("VPN config corrupted, using defaults")
        return {}

    # =========================================================================
    # PUBLIC: Rotate IP
    # =========================================================================

    def rotate_ip(self) -> bool:
        """Đổi IP theo provider đã cấu hình. Returns success."""
        logger.info(f"IP rotation triggered (mode: {self.provider.upper()})")

        if self.provider == "warp":
            return self._rotate_warp()
        elif self.provider == "dcom":
            return self._rotate_dcom()
        elif self.provider == "proxy":
            return self._rotate_proxy()
        else:
            logger.info("No VPN configured, skipping")
            return True

    # =========================================================================
    # PRIVATE: Cloudflare WARP
    # =========================================================================

    def _rotate_warp(self) -> bool:
        """Disconnect/reconnect WARP."""
        warp_path = self.config.get(
            "warp_path",
            r"C:\Program Files\Cloudflare\Cloudflare WARP\warp-cli.exe"
        ).replace('"', '')

        if not os.path.exists(warp_path) and not shutil.which("warp-cli"):
            logger.error("warp-cli.exe not found")
            return False

        try:
            exe = f'"{warp_path}"'
            subprocess.run(
                f"{exe} disconnect", shell=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            time.sleep(2)
            subprocess.run(
                f"{exe} connect", shell=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            time.sleep(5)
            logger.info("WARP IP rotated successfully")
            return True
        except Exception as e:
            logger.error(f"WARP error: {e}")
            return False

    # =========================================================================
    # PRIVATE: DCOM 3G/4G
    # =========================================================================

    def _rotate_dcom(self) -> bool:
        """Reset DCOM connection."""
        profile = self.config.get("dcom_profile", "Viettel")
        try:
            logger.info(f"Resetting DCOM: {profile}")
            subprocess.run(
                f'rasdial "{profile}" /DISCONNECT', shell=True,
                stdout=subprocess.DEVNULL
            )
            time.sleep(3)
            subprocess.run(
                f'rasdial "{profile}"', shell=True,
                stdout=subprocess.DEVNULL
            )
            time.sleep(5)
            logger.info("DCOM IP rotated successfully")
            return True
        except Exception as e:
            logger.error(f"DCOM error: {e}")
            return False

    # =========================================================================
    # PRIVATE: HTTP Proxy
    # =========================================================================

    def _rotate_proxy(self) -> bool:
        """Chọn random proxy từ danh sách."""
        proxies_str = self.config.get("proxy_list", "")
        if not proxies_str:
            logger.error("Proxy list is empty")
            return False

        proxy_list = [p.strip() for p in proxies_str.split('\n') if p.strip()]
        if not proxy_list:
            return False

        chosen = random.choice(proxy_list)
        os.environ['http_proxy'] = chosen
        os.environ['https_proxy'] = chosen
        logger.info(f"Proxy set to: {chosen}")
        return True