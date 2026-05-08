import logging
import os
import json
import uuid

logger = logging.getLogger("VeoSuite.Publisher.AccountManager")


class PublisherAccountManager:
    """Quản lý thông tin đăng nhập/API Keys của các tài khoản xuất bản đa nền tảng"""
    def __init__(self):
        self.db_path = "VEO_DB/publisher_accounts.json"
        self._ensure_db_exists()

    def _ensure_db_exists(self):
        if not os.path.exists("VEO_DB"):
            os.makedirs("VEO_DB", exist_ok=True)
        if not os.path.exists(self.db_path):
            self.save_accounts([])

    def load_accounts(self) -> list:
        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.info(f"[AccountManager] Lỗi đọc DB: {e}")
            return []

    def save_accounts(self, accounts: list):
        try:
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(accounts, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.info(f"[AccountManager] Lỗi lưu DB: {e}")

    def add_account(self, platform: str, account_name: str, credentials: dict):
        accounts = self.load_accounts()
        new_acc = {
            "id": str(uuid.uuid4()),
            "platform": platform,
            "account_name": account_name,
            "credentials": credentials,
            "status": "Vừa thêm mới"
        }
        accounts.append(new_acc)
        self.save_accounts(accounts)
        return new_acc

    def delete_account(self, account_id: str):
        accounts = self.load_accounts()
        accounts = [acc for acc in accounts if acc.get("id") != account_id]
        self.save_accounts(accounts)
