"""Dashboard tab — system-wide overview at a glance.

Aggregates data from three Tier 5 subsystems so a user can see the
state of their workspace without drilling into a specific tab:

* **Channels** — counts pulled from the accounts table (Money /
  Warmup / Burn). Mirrors the Ops Center stat cards.
* **Plugins** — list of plugins currently loaded by
  :class:`PluginManager`.
* **Telemetry** — opt-in indicator + total event count when active.
* **Fonts** — coverage of bundled font files.

The tab is intentionally read-only. Mutating settings (e.g. toggling
telemetry) lives in :mod:`ui.admin_tab` so we don't fork the source of
truth here.
"""

from __future__ import annotations

import logging
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

try:
    from modules.plugins import PluginManager
    from services import font_bundle, telemetry
    from services.database_manager import DatabaseManager
    from utils import i18n

    from ui.style_kit import apply_kind
except ImportError:  # Fallback for direct-folder execution (mirrors main_window.py).
    # NB: every import in the try-block MUST have a corresponding line here.
    from VeoSuite_V3.modules.plugins import PluginManager  # type: ignore
    from VeoSuite_V3.services import font_bundle, telemetry  # type: ignore
    from VeoSuite_V3.services.database_manager import DatabaseManager  # type: ignore
    from VeoSuite_V3.ui.style_kit import apply_kind  # type: ignore
    from VeoSuite_V3.utils import i18n  # type: ignore

logger = logging.getLogger("VeoSuite.Dashboard")


# Mapping from the account.status column to (i18n key, value-extractor).
# Centralised here so the order of cards stays stable when translations
# are added.
_KPI_DEFS: tuple[tuple[str, str], ...] = (
    ("dashboard.kpi.accounts", "total"),
    ("dashboard.kpi.money_channels", "money"),
    ("dashboard.kpi.warm_channels", "warmup"),
    ("dashboard.kpi.risk_channels", "burn"),
)


def compute_account_kpis(accounts: list[dict[str, Any]]) -> dict[str, int]:
    """Pure-data helper — counts accounts by ``status`` field.

    Extracted as a free function so tests can exercise it without
    instantiating a QWidget.
    """
    totals = {"total": 0, "money": 0, "warmup": 0, "burn": 0}
    for row in accounts:
        totals["total"] += 1
        status = str(row.get("status", "")).strip().lower()
        if status in totals:
            totals[status] += 1
    return totals


class DashboardTab(QWidget):
    """Top-level dashboard widget."""

    # Mirrors the convention used by RadarTab/ContentTab/etc. so the
    # MainWindow log-wire-up loop picks it up automatically.
    log_signal = pyqtSignal(str)

    def __init__(
        self,
        db: DatabaseManager | None = None,
        plugin_manager: PluginManager | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._db = db
        self._plugin_manager = plugin_manager
        self._kpi_value_labels: dict[str, QLabel] = {}

        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(15)

        header = QLabel(i18n.tr("dashboard.header"))
        header.setObjectName("sectionTitleLabel")
        outer.addWidget(header)

        # KPI cards row.
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(10)
        for key, value_key in _KPI_DEFS:
            kpi_row.addWidget(self._make_kpi_card(key, value_key))
        outer.addLayout(kpi_row)

        # Secondary status row: telemetry + fonts + refresh button.
        status_row = QHBoxLayout()
        status_row.setSpacing(10)

        self._lbl_plugins_summary = QLabel(i18n.tr("dashboard.empty"))
        self._lbl_plugins_summary.setObjectName("hintLabel")
        status_row.addWidget(self._lbl_plugins_summary, stretch=1)

        self._lbl_telemetry = QLabel(i18n.tr("dashboard.telemetry.disabled"))
        self._lbl_telemetry.setObjectName("hintLabel")
        status_row.addWidget(self._lbl_telemetry, stretch=1)

        self._lbl_fonts = QLabel("…")
        self._lbl_fonts.setObjectName("hintLabel")
        status_row.addWidget(self._lbl_fonts, stretch=1)

        self._btn_refresh = QPushButton(i18n.tr("dashboard.refresh"))
        apply_kind(self._btn_refresh, "primary")
        self._btn_refresh.clicked.connect(self.refresh)
        status_row.addWidget(self._btn_refresh)
        outer.addLayout(status_row)

        # Plugin list.
        self._plugin_list = QListWidget()
        self._plugin_list.setObjectName("dashboardPluginList")
        self._plugin_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        outer.addWidget(self._plugin_list, stretch=1)

    def _make_kpi_card(self, label_key: str, value_key: str) -> QFrame:
        card = QFrame()
        card.setObjectName("statsCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        title = QLabel(i18n.tr(label_key))
        title.setObjectName("hintLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        value = QLabel("0")
        value.setObjectName("kpiValueLabel")
        value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._kpi_value_labels[value_key] = value

        layout.addWidget(title)
        layout.addWidget(value)
        return card

    # ------------------------------------------------------------ refresh

    def refresh(self) -> None:
        """Re-query every data source and update the visible widgets."""
        self._refresh_kpis()
        self._refresh_plugins()
        self._refresh_telemetry()
        self._refresh_fonts()

    def _refresh_kpis(self) -> None:
        accounts: list[dict[str, Any]] = []
        if self._db is not None:
            try:
                raw = self._db.list_accounts()
                accounts = [dict(row) for row in raw]
            except Exception:
                logger.exception("Cannot load accounts for dashboard KPIs")
                accounts = []
        kpis = compute_account_kpis(accounts)
        for value_key, label in self._kpi_value_labels.items():
            label.setText(str(kpis.get(value_key, 0)))

    def _refresh_plugins(self) -> None:
        self._plugin_list.clear()
        if self._plugin_manager is None:
            self._lbl_plugins_summary.setText(i18n.tr("dashboard.plugins") + ": 0")
            return
        plugins = self._plugin_manager.metadata_list()
        self._lbl_plugins_summary.setText(f"{i18n.tr('dashboard.plugins')}: {len(plugins)}")
        for meta in plugins:
            line = f"{meta.name} v{meta.version}"
            if meta.description:
                line += f" — {meta.description}"
            QListWidgetItem(line, self._plugin_list)

    def _refresh_telemetry(self) -> None:
        sink = telemetry.get_sink()
        if sink is None or not sink.enabled:
            self._lbl_telemetry.setText(i18n.tr("dashboard.telemetry.disabled"))
            return
        events = sink.read_events()
        self._lbl_telemetry.setText(i18n.tr("dashboard.telemetry.enabled", count=len(events)))

    def _refresh_fonts(self) -> None:
        ok, total = font_bundle.coverage_summary()
        self._lbl_fonts.setText(i18n.tr("dashboard.fonts.bundle", ok=ok, total=total))
