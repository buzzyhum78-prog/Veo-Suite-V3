"""Ops Tab — Channel Vault, Security & Analytics.

PR-5: thay mock data bằng dữ liệu thật từ ``DatabaseManager.list_accounts()``.
Khi không truyền ``db`` (vd test/mock), tab vẫn render bằng dataset rỗng.
"""

from __future__ import annotations

import logging
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.style_kit import apply_kind  # PR-5e: dynamic-property style helpers

logger = logging.getLogger("VeoSuite.UI.OpsTab")


# Bản đồ status → emoji + màu
_STATUS_PRESET = {
    "warmup": ("🟡 Warmup", "#f1c40f"),
    "money": ("🟢 Money", "#2ecc71"),
    "burn": ("🔴 Burn", "#e74c3c"),
}


class OpsTab(QWidget):
    def __init__(self, db: Any | None = None):
        super().__init__()
        self.db = db
        self._build_ui()
        self._apply_style()
        # Nạp data lần đầu (nếu có DB)
        self.refresh()

    # =========================================================================
    # Public API
    # =========================================================================

    def refresh(self) -> None:
        """Reload data từ DB. An toàn khi self.db là None."""
        accounts = self._fetch_accounts()
        self._populate_channel_table(accounts)
        self._update_stat_cards(accounts)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # --- HEADER ---
        header = QHBoxLayout()
        lbl_title = QLabel("🛡️ TRUNG TÂM QUẢN TRỊ & AN NINH (OPS CENTER)")
        lbl_title.setObjectName("sectionTitleLabel")  # PR-5e: cyan section title via global QSS

        # Các nút hành động nhanh
        btn_import_radar = QPushButton("🚀 Tạo Kênh Từ Radar")
        apply_kind(btn_import_radar, "ai_magic")  # PR-5e
        btn_import_radar.setToolTip("Lấy dữ liệu Trend từ Radar để khởi tạo kênh mới tự động")

        btn_add_existing = QPushButton("🔗 Liên kết Kênh có sẵn")
        apply_kind(btn_add_existing, "success")  # PR-5e

        header.addWidget(lbl_title)
        header.addStretch()
        header.addWidget(btn_import_radar)
        header.addWidget(btn_add_existing)
        layout.addLayout(header)

        # --- DASHBOARD TỔNG QUAN (Mini Stats) ---
        stats_frame = QFrame()
        stats_frame.setObjectName("statsCard")  # PR-5e: card-style frame via global QSS
        s_layout = QHBoxLayout(stats_frame)

        # Hàm tạo thẻ thống kê nhỏ — trả (layout, value_label) để cập nhật về sau
        def create_stat_card(label, value, color):
            # PR-5e: the label colour/font-size pair is treated as a
            # token-pair (muted hint + bright value). The hint label uses
            # the standard hintLabel objectName; the value label keeps
            # its colour inline because it varies per-card and is also
            # used to encode status (green = money, red = burn, etc).
            vbox = QVBoxLayout()
            lbl = QLabel(label)
            lbl.setObjectName("hintLabel")
            val = QLabel(value)
            val.setStyleSheet(f"color: {color}; font-size: 20px; font-weight: bold;")
            vbox.addWidget(lbl)
            vbox.addWidget(val)
            vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
            return vbox, val

        total_layout, self._card_total = create_stat_card("Tổng Số Kênh", "0", "#fff")
        active_layout, self._card_active = create_stat_card("Kênh Money", "0", "#2ecc71")
        alert_layout, self._card_alert = create_stat_card("Cảnh Báo Rủi Ro", "0", "#e74c3c")
        revenue_layout, self._card_revenue = create_stat_card("Doanh Thu Hôm Nay", "—", "#f1c40f")
        for lyt in (total_layout, active_layout, alert_layout, revenue_layout):
            s_layout.addLayout(lyt)

        layout.addWidget(stats_frame)

        # --- MAIN TABS ---
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_channel_vault(), "🏦 KHO KÊNH (CHANNEL VAULT)")
        self.tabs.addTab(self._build_security_tab(), "🛡️ AN NINH MẠNG (SECURITY)")
        self.tabs.addTab(self._build_analytics_tab(), "📊 HIỆU SUẤT (ANALYTICS)")
        layout.addWidget(self.tabs)

    def _build_channel_vault(self):
        widget = QWidget()
        layout_v = QVBoxLayout(widget)

        # Toolbar lọc
        tb = QHBoxLayout()
        tb.addWidget(QLabel("Lọc theo:"))
        tb.addWidget(QComboBox())  # Placeholder cho filter Topic
        tb.addWidget(QComboBox())  # Placeholder cho filter Country
        btn_health_check = QPushButton("🩺 KIỂM TRA SỨC KHỎE TOÀN BỘ")
        apply_kind(btn_health_check, "warning")  # PR-5e
        btn_health_check.clicked.connect(self._on_health_check_clicked)
        tb.addStretch()
        tb.addWidget(btn_health_check)
        layout_v.addLayout(tb)

        # Bảng Kênh — đổ data thật trong refresh()
        self.table_channels = QTableWidget(0, 7)
        headers = [
            "Tên Kênh",
            "Ghi chú",
            "Platform",
            "Trạng thái",
            "Proxy",
            "Video chờ",
            "Hành động",
        ]
        self.table_channels.setHorizontalHeaderLabels(headers)
        self.table_channels.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_channels.verticalHeader().setVisible(False)
        self.table_channels.setAlternatingRowColors(True)
        # PR-5e: rely on the global QTableWidget styling instead of an inline override.

        layout_v.addWidget(self.table_channels)
        return widget

    # =========================================================================
    # Data helpers (PR-5)
    # =========================================================================

    def _fetch_accounts(self) -> list[dict]:
        """Lấy danh sách accounts từ DB. Trả về list rỗng nếu lỗi/không có DB."""
        if self.db is None:
            return []
        try:
            return self.db.list_accounts()
        except Exception as e:
            logger.exception("Cannot load accounts from DB: %s", e)
            return []

    def _update_stat_cards(self, accounts: list[dict]) -> None:
        """Cập nhật 4 thẻ tổng hợp ở header."""
        total = len(accounts)
        money = sum(1 for a in accounts if a.get("status") == "money")
        burn = sum(1 for a in accounts if a.get("status") == "burn")
        if hasattr(self, "_card_total"):
            self._card_total.setText(str(total))
        if hasattr(self, "_card_active"):
            self._card_active.setText(str(money))
        if hasattr(self, "_card_alert"):
            self._card_alert.setText(str(burn))

    def _populate_channel_table(self, accounts: list[dict]) -> None:
        """Đổ accounts vào ``self.table_channels``."""
        if not hasattr(self, "table_channels"):
            return
        table = self.table_channels
        table.setRowCount(0)
        for i, a in enumerate(accounts):
            table.insertRow(i)
            status_label, status_color = _STATUS_PRESET.get(
                a.get("status", "warmup"),
                (a.get("status", ""), "#bdc3c7"),
            )
            row = (
                str(a.get("username", "")),
                a.get("notes") or "—",
                a.get("platform", ""),
                status_label,
                a.get("proxy") or "Direct",
                "—",
                "Sửa",
            )
            for j, val in enumerate(row):
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 3:
                    item.setForeground(QColor(status_color))
                table.setItem(i, j, item)

    def _on_health_check_clicked(self) -> None:
        """Stub Health-Check — tới PR-6 sẽ kết nối YouTube API thật."""
        n = self.table_channels.rowCount() if hasattr(self, "table_channels") else 0
        QMessageBox.information(
            self,
            "Health Check",
            f"Đang quét {n} kênh trong DB...\n(Stub — endpoint YouTube Data API sẽ được gắn ở PR-6.)",
        )

    def _build_security_tab(self):
        widget = QWidget()
        layout_v = QVBoxLayout(widget)

        # Cấu hình Proxy
        grp_proxy = QGroupBox("🌐 CẤU HÌNH PROXY & FINGERPRINT")
        form = QFormLayout()

        txt_proxy_list = QTextEdit()
        txt_proxy_list.setPlaceholderText(
            "Dán danh sách Proxy (IP:Port:User:Pass) vào đây...\nMỗi dòng 1 Proxy."
        )
        txt_proxy_list.setMaximumHeight(100)

        cb_rotate = QComboBox()
        cb_rotate.addItems(
            [
                "Xoay vòng theo Kênh (Mỗi kênh 1 IP cố định)",
                "Xoay vòng theo Phiên (Mỗi lần mở đổi IP)",
            ]
        )

        btn_check_proxy = QPushButton("Kiểm tra Proxy sống/chết")

        form.addRow("Danh sách Proxy:", txt_proxy_list)
        form.addRow("Chế độ xoay:", cb_rotate)
        form.addRow("", btn_check_proxy)

        grp_proxy.setLayout(form)
        layout_v.addWidget(grp_proxy)

        # Cảnh báo
        grp_alert = QGroupBox("🚨 HỆ THỐNG CẢNH BÁO SỚM")
        vbox = QVBoxLayout()
        vbox.addWidget(QLabel("Gửi thông báo về Telegram/Email khi:"))
        vbox.addWidget(QPushButton("Login lạ xuất hiện"))
        vbox.addWidget(QPushButton("Kênh bị tụt view bất thường (>50%)"))
        vbox.addWidget(QPushButton("Kênh bị tắt kiếm tiền"))
        grp_alert.setLayout(vbox)
        layout_v.addWidget(grp_alert)
        layout_v.addStretch()

        return widget

    def _build_analytics_tab(self):
        widget = QWidget()
        layout_v = QVBoxLayout(widget)
        layout_v.addWidget(QLabel("📈 BIỂU ĐỒ TĂNG TRƯỞNG (Placeholder)"))

        # Giả lập biểu đồ bằng Progress Bar cho vui mắt
        for metric in ["Views (24h)", "Subscribers", "Revenue"]:
            h = QHBoxLayout()
            h.addWidget(QLabel(f"{metric}:"), 1)
            p = QProgressBar()
            p.setValue(75)
            p.setProperty(
                "chunkColor", "primary"
            )  # PR-5e: see styles.py for QProgressBar[chunkColor="primary"]
            h.addWidget(p, 4)
            layout_v.addLayout(h)

        layout_v.addStretch()
        return widget

    def _apply_style(self):
        # PR-5e: the global DARK_THEME_STYLESHEET applied by MainWindow already
        # provides the QWidget/QTableWidget/QGroupBox styling this method used
        # to inject. The local override here was the main reason switching to
        # Ops Center felt like "jumping into another app". Intentionally a
        # no-op now; kept as a hook for future tab-specific tweaks.
        return None
