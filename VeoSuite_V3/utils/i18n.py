"""Minimal i18n stub for Veo Suite V3.

This is intentionally a *stub*: it gives the rest of the codebase a
single ``tr("key", ...)`` entry point so callers don't bake Vietnamese
into UI strings, but it doesn't pretend to be gettext-compatible.

Translations live in ``VeoSuite_V3/assets/i18n/<lang>.json``. Each
file is a flat ``{ "key": "value" }`` mapping. Missing keys fall back
to the key itself (NOT a blank string — easier to spot regressions in
the UI).

Pluralisation is a thin convention: if a key has ``"one"`` and
``"other"`` sub-keys in the JSON, ``tr_plural(key, n)`` picks the
right form. Otherwise we fall back to the bare key.

The default language is ``vi`` (Vietnamese) — matching the UI as it
stands today. Switching languages at runtime is supported via
``set_language("en")`` but does not retro-translate already-rendered
widgets; callers must re-render.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("VeoSuite.i18n")

_DEFAULT_LANG = "vi"
_SUPPORTED_LANGS = frozenset({"vi", "en"})

# Resolve at import-time relative to this file so the lookup works whether
# the package is installed, run directly, or vendored under a different
# top-level path.
_I18N_DIR = Path(__file__).resolve().parent.parent / "assets" / "i18n"

_translations: dict[str, dict[str, Any]] = {}
_current_lang: str = _DEFAULT_LANG


def _load(lang: str) -> dict[str, Any]:
    """Read a single language file. Returns ``{}`` on any failure.

    Failures are logged but never raised — a missing/corrupt
    translation file must not crash the host UI.
    """
    path = _I18N_DIR / f"{lang}.json"
    if not path.is_file():
        logger.warning("i18n: missing translation file %s", path)
        return {}
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("i18n: cannot load %s: %s", path, exc)
        return {}
    if not isinstance(data, dict):
        logger.warning("i18n: %s is not a JSON object (got %s)", path, type(data).__name__)
        return {}
    return data


def set_language(lang: str) -> None:
    """Switch the active language. Unknown languages reset to default."""
    global _current_lang
    if lang not in _SUPPORTED_LANGS:
        logger.warning("i18n: unsupported language %r, falling back to %r", lang, _DEFAULT_LANG)
        lang = _DEFAULT_LANG
    _current_lang = lang
    if lang not in _translations:
        _translations[lang] = _load(lang)


def current_language() -> str:
    return _current_lang


def supported_languages() -> frozenset[str]:
    return _SUPPORTED_LANGS


def _lookup(key: str) -> Any:
    """Look up a translation by key.

    Supports two JSON layouts so authors can pick whichever is more
    readable for a given file:

    * **Flat** — ``{"departments.dashboard": "Tổng Quan"}``
    * **Nested** — ``{"departments": {"dashboard": "Tổng Quan"}}``

    Returns the raw value (str, dict, or anything stored under the
    key) or ``None`` when nothing matches.
    """
    if _current_lang not in _translations:
        _translations[_current_lang] = _load(_current_lang)
    table = _translations.get(_current_lang, {})

    # Fast path: the JSON file uses flat dotted keys directly.
    if key in table:
        return table[key]

    # Otherwise walk a nested structure.
    node: Any = table
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def tr(key: str, **kwargs: Any) -> str:
    """Translate ``key`` for the active language.

    Format-string interpolation is performed with ``str.format_map``,
    so callers can write ``tr("greeting", name="Bob")`` and the JSON
    value would be ``"Chào {name}"``.

    Missing keys return the key itself unchanged — easier to spot in
    the UI than a blank string.
    """
    raw = _lookup(key)
    if not isinstance(raw, str):
        return key
    if not kwargs:
        return raw
    try:
        return raw.format_map(_SafeFormatDict(kwargs))
    except (KeyError, IndexError, ValueError) as exc:
        logger.warning("i18n: format failure for %r: %s", key, exc)
        return raw


def tr_plural(key: str, n: int, **kwargs: Any) -> str:
    """Pluralise ``key`` based on integer ``n``.

    The JSON entry must look like::

        { "items": { "one": "{n} item", "other": "{n} items" } }

    Falls back to ``tr(key)`` if no plural forms are present. Always
    injects ``n`` into the format kwargs so callers don't have to.
    """
    raw = _lookup(key)
    kwargs.setdefault("n", n)
    if isinstance(raw, dict):
        chosen = raw.get("one") if n == 1 else raw.get("other")
        if isinstance(chosen, str):
            try:
                return chosen.format_map(_SafeFormatDict(kwargs))
            except (KeyError, IndexError, ValueError) as exc:
                logger.warning("i18n: plural format failure for %r: %s", key, exc)
                return chosen
    return tr(key, **kwargs)


class _SafeFormatDict(dict):
    """Format dict that returns ``{name}`` literally for missing keys.

    Prevents ``KeyError`` from crashing a UI render when a translation
    references a placeholder the caller forgot to pass — far better
    than a blank string.
    """

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


# Eagerly populate the default language so first-call latency is bounded.
_translations[_DEFAULT_LANG] = _load(_DEFAULT_LANG)
