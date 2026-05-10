"""Pure CTA-button localization extracted from ui/widgets/media_tab.py.

The Media tab's thumbnail composer overlays a country-specific
call-to-action button (e.g. "WATCH NOW" / "ANSEHEN" / "立即觀看") next
to the channel title. The country -> CTA mapping and the fallback rules
live here so they can be tested in isolation and reused from CLI /
plugin / batch contexts.

Behaviour preserved verbatim from `MediaTab._run_composer_merge` (the
big inline ``cta_map`` dict plus the override branch that forces VN
markets to ``XEM NGAY``).
"""

from __future__ import annotations

__all__ = ["CTA_BY_COUNTRY", "DEFAULT_CTA", "cta_for_country"]

DEFAULT_CTA = "WATCH NOW"

# ISO country codes (or VEO-Suite tier labels) -> localized button text.
# Lookup is substring-based (``code in target_country``) so we keep the
# keys upper-case here and uppercase the lookup arg in `cta_for_country`.
CTA_BY_COUNTRY: dict[str, str] = {
    # --- TIER 1: KHO BÁU TỶ ĐÔ ---
    "US": "WATCH NOW",
    "AU": "WATCH NOW",
    "CA": "WATCH NOW",
    "GB": "WATCH NOW",
    "CH": "ANSEHEN",
    "NO": "SE NÅ",
    "NZ": "WATCH NOW",
    # --- TIER 2: CHÂU ÂU ---
    "DE": "ANSEHEN",
    "NL": "KIJK NU",
    "SE": "TITTA NU",
    "DK": "SE NU",
    "FI": "KATSO NYT",
    "FR": "REGARDER",
    "IE": "WATCH NOW",
    "AT": "ANSEHEN",
    # --- TIER 3: CHÂU Á ---
    "QA": "شاهد الآن",
    "AE": "شاهد الآن",
    "SG": "WATCH NOW",
    "JP": "今すぐ見る",
    "KR": "지금 보세요",
    "IL": "צפו עכשיו",
    "SA": "شاهد الآن",
    "HK": "立即觀看",
    "TW": "立即觀看",
    "KW": "شاهد الآن",
    "CN": "立即观看",
    # --- TIER 4-7 ---
    "ES": "VER AHORA",
    "IT": "GUARDA ORA",
    "PT": "VER AGORA",
    "PL": "OGLĄDAJ",
    "CZ": "SLEDOVAT",
    "GR": "ΔΕΙΤΕ ΤΩΡΑ",
    "HU": "NÉZD MEG",
    "RU": "СМОТРЕТЬ",
    "TR": "İZLE",
    "BR": "ASSISTIR",
    "MX": "VER AHORA",
    "IN": "WATCH NOW",
    "VN": "XEM NGAY",
    "ID": "TONTON",
    "PH": "WATCH NOW",
    "TH": "ดูเลย",
    "LA": "ເບິ່ງເລີຍ",
    "KH": "ទស្សនា",
    "GLOBAL": "WATCH NOW",
}


def cta_for_country(country) -> str:
    """Return the CTA-button text for a country / locale string.

    Behaviour preserved verbatim from `MediaTab._run_composer_merge`:
      1. Coerce ``country`` to str + uppercase, default ``""`` if falsy.
      2. Initial value: ``"WATCH NOW"``.
      3. Iterate ``CTA_BY_COUNTRY.items()`` in insertion order; first
         entry whose key is a substring of the uppercased country wins,
         and the loop ``break``s (so US-style codes don't fall through
         into Russian/CJK entries).
      4. Final override: if the uppercased country contains
         ``"VIỆT NAM"`` or ``"VN"``, force ``"XEM NGAY"``. This is the
         original last-line override and remains intentional — VN
         channels often label their country as ``"Việt Nam"`` rather
         than ``"VN"``.
    """
    if not country:
        return DEFAULT_CTA
    target = str(country).upper()
    cta = DEFAULT_CTA
    for code, text in CTA_BY_COUNTRY.items():
        if code in target:
            cta = text
            break
    # Preserved verbatim — the original logic uppercased ``country`` once
    # and checked both the Vietnamese label and the bare ``"VN"`` token.
    if "VIỆT NAM" in target or "VN" in target:
        cta = "XEM NGAY"
    return cta
