"""Local font discovery & registration for Veo Suite V3.

Veo Suite ships a fixed set of TTF files under
``VeoSuite_V3/assets/fonts/``. At startup we want to:

1. Inspect what is on disk (some users may delete fonts manually).
2. Optionally register them with Qt's font database so widgets can
   request the family by name without worrying about the file path.

This module deliberately does NOT download fonts at runtime — that
would couple "first launch" to internet access and surface licence
questions we don't want to litigate. The "auto-bundle" promise is
fulfilled by shipping the fonts in the repo + a discovery API.

Functions in this module are import-time-safe: Qt is imported lazily
inside :func:`register_with_qt` so headless tests can still verify
the discovery logic without a QApplication.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("VeoSuite.Fonts")

# Resolved relative to this file so it works from any CWD.
_DEFAULT_FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

# Fonts the app actively requests by family name. The first column is
# the family the app code uses; the second column is the TTF basename
# we expect to find. If a future change adds a new family the test
# suite will surface the addition so this list stays in sync.
REQUIRED_FONTS: dict[str, str] = {
    "Montserrat ExtraBold": "Montserrat-ExtraBold.ttf",
    "Cinzel": "Cinzel.ttf",
    "DancingScript Bold": "DancingScript-Bold.ttf",
    "Noto Sans JP Black": "NotoSansJP-Black.ttf",
    "Noto Sans KR Black": "NotoSansKR-Black.ttf",
}


@dataclass(frozen=True)
class FontStatus:
    family: str
    filename: str
    available: bool
    path: Path | None


def fonts_dir() -> Path:
    """Where the app looks for bundled fonts."""
    return _DEFAULT_FONTS_DIR


def list_available(dir_: Path | None = None) -> list[FontStatus]:
    """Return a status row for every font in :data:`REQUIRED_FONTS`.

    Pure function — does not touch Qt and never raises. If the
    directory is missing every font is marked unavailable.
    """
    base = Path(dir_) if dir_ is not None else _DEFAULT_FONTS_DIR
    statuses: list[FontStatus] = []
    for family, filename in REQUIRED_FONTS.items():
        path = base / filename
        if path.is_file():
            statuses.append(FontStatus(family=family, filename=filename, available=True, path=path))
        else:
            statuses.append(FontStatus(family=family, filename=filename, available=False, path=None))
    return statuses


def coverage_summary(dir_: Path | None = None) -> tuple[int, int]:
    """Return ``(available_count, total_count)`` for required fonts."""
    statuses = list_available(dir_)
    return sum(1 for s in statuses if s.available), len(statuses)


def register_with_qt(dir_: Path | None = None) -> tuple[int, list[str]]:
    """Register every available font with ``QFontDatabase``.

    Returns ``(registered_count, families)``. Skips files that fail
    to load — Qt logs them via its own channel. If PyQt6 is not
    installed (which can happen in pure-Python lint/test pipelines)
    the function returns ``(0, [])`` without raising.
    """
    statuses = [s for s in list_available(dir_) if s.available]

    try:
        from PyQt6.QtGui import QFontDatabase  # noqa: F401  (imported for side effect)
    except ImportError:  # pragma: no cover - the production envs have PyQt6
        logger.info("font_bundle: PyQt6 unavailable, skipping registration")
        return 0, []

    registered = 0
    families: list[str] = []
    for status in statuses:
        font_id = QFontDatabase.addApplicationFont(str(status.path))
        if font_id < 0:
            logger.warning("font_bundle: Qt rejected %s", status.path)
            continue
        registered += 1
        families.extend(QFontDatabase.applicationFontFamilies(font_id))
    return registered, families
