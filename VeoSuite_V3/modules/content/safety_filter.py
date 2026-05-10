"""Pure safety-filter helpers extracted from ``ui/widgets/content_tab.py``.

These functions used to live as ``ContentTab._apply_safety_filter`` and
``ContentTab._process_voice_and_sfx`` — both already pure (no Qt, no
filesystem, no network), but trapped inside a 4136-line god-class which made
them impossible to unit-test in isolation. PR-5b lifts them out unchanged
so the same blacklist + same regex strategy keeps producing the same
output, but each function is now testable on its own.

If you change anything in this file, the matching tests in
``tests/test_pr5b_content_refactor.py::TestTcontentSafetyFilter`` will
catch behaviour drift.
"""

from __future__ import annotations

import re

# --- Public API -------------------------------------------------------------

__all__ = [
    "SAFETY_BLACKLIST",
    "apply_safety_filter",
    "process_voice_and_sfx",
]

# Multi-language blacklist of risky words → safer rewrites. Sourced verbatim
# from the original ``_apply_safety_filter`` body so every caller (Channel
# Designer, IdeaExpansion, save-task pipeline) stays bit-for-bit identical.
#
# Notes on the dict shape:
#   * Keys are lowercased "risky" tokens. Latin keys are matched with
#     ``\b`` word boundaries; CJK/Thai/Indic keys are matched as raw
#     substrings (those scripts don't use spaces between words).
#   * Some keys collide across languages (e.g. "cancer" appears in EN and
#     ES). Python dict-literal semantics give us the LAST occurrence — that
#     matches the original behaviour exactly because the in-place dict in
#     ``content_tab.py`` was built the same way.
SAFETY_BLACKLIST: dict[str, str] = {
    # =======================================================
    # 🇻🇳 VIETNAM (TIẾNG VIỆT - INPUT CHUẨN CỦA BẠN)
    # =======================================================
    # --- Nhóm 1: Cam kết & Khẳng định quá đà ---
    "chữa khỏi": "hỗ trợ giảm",
    "trị dứt điểm": "xoa dịu",
    "đặc trị": "hỗ trợ",
    "cam kết khỏi": "cải thiện",
    "vĩnh viễn": "lâu dài",
    "tuyệt đối": "hiệu quả",
    "hết bệnh": "khỏe mạnh",
    "sạch bệnh": "thanh lọc",
    "khỏi hẳn": "đỡ hơn",
    "dứt điểm": "giảm dần",
    "cam kết": "hứa hẹn",
    "bảo đảm": "tin cậy",
    # --- Nhóm 2: Từ vựng Y tế & Bệnh lý ---
    "ung thư": "tổn thương",
    "tiểu đường": "sức khỏe",
    "đột quỵ": "căng thẳng",
    "huyết áp": "nhịp sống",
    "xương khớp": "cơ thể",
    "trầm cảm": "lo âu",
    "mất ngủ kinh niên": "khó ngủ",
    "viêm": "nhức mỏi",
    "bệnh lý": "tình trạng",
    # --- Nhóm 3: Đối tượng & Thuốc ---
    "thuốc": "liệu pháp",
    "thần dược": "phương pháp",
    "bệnh viện": "trung tâm",
    "bác sĩ": "chuyên gia",
    "dược sĩ": "người hướng dẫn",
    "phác đồ": "quy trình",
    "điều trị": "chăm sóc",
    "y tế": "sức khỏe",
    # =======================================================
    # 🇺🇸 ENGLISH (GLOBAL / TIER 1 / TIER 3 / TIER 5 / TIER 6)
    # =======================================================
    "cure": "soothe",
    "treat": "relieve",
    "medicine": "therapy",
    "medication": "method",
    # NB: EN "hospital" → "center" is dead in the original dict because
    # ES "hospital" → "centro" appears later and wins (Python last-write).
    # Kept that drop here so behaviour stays bit-for-bit identical.
    "doctor": "expert",
    "physician": "guide",
    "cancer": "damage",
    "disease": "condition",
    "illness": "struggle",
    "diabetes": "wellness",
    "stroke": "tension",
    "depression": "sadness",
    "insomnia": "sleep trouble",
    "virus": "negativity",
    "pain killer": "pain relief",
    "miracle": "powerful",
    "instant": "fast",
    "permanent": "lasting",
    "guarantee": "promise",
    "absolutely": "effectively",
    "100%": "pure",
    # =======================================================
    # 🇪🇺 TIER 1 & 2: TÂY ÂU & BẮC ÂU (GERMANIC & LATIN)
    # =======================================================
    # Đức (De - DE, AT, CH)
    "heilen": "lindern",
    "heilung": "besserung",
    "krebs": "schaden",
    "arzt": "experte",
    "medizin": "therapie",
    "garantie": "versprechen",
    "krankheit": "zustand",
    "klinik": "zentrum",
    # Pháp (Fr - FR, BE, CH)
    "guérir": "apaiser",
    "guérison": "mieux-être",
    "médecin": "expert",
    "médicament": "thérapie",
    "hôpital": "centre",
    "maladie": "problème",
    "garanti": "promis",
    # Hà Lan (Nl - NL, BE)
    "genezen": "verlichten",
    # NB: NL "kanker" → "schade" is dead in the original dict because
    # ID "kanker" → "kerusakan" appears later and wins (Python last-write).
    # Kept the drop here so behaviour stays bit-for-bit identical.
    "arts": "expert",
    "medicijn": "therapie",
    "ziekenhuis": "centrum",
    # Thụy Điển (Sv) | Na Uy (No) | Đan Mạch (Da) | Phần Lan (Fi)
    "bota": "lindra",
    "läkare": "expert",  # Sv
    "kurere": "lindre",
    "kreft": "skade",  # No
    "helbrede": "lindre",
    "kræft": "skade",  # Da
    "parantaa": "helpottaa",
    "syöpä": "vaurio",
    "lääkäri": "asiantuntija",  # Fi
    # =======================================================
    # 🇮🇹 TIER 4 & 5: NAM ÂU & ĐÔNG ÂU & LATIN AMERICA
    # =======================================================
    # Tây Ban Nha (Es - ES, MX, AR, CL)
    "curar": "acalmar",  # PT overrides ES; matches original last-write-wins behaviour
    "cura": "bem-estar",
    "cáncer": "daño",
    "enfermedad": "condición",
    "médico": "especialista",
    "medicina": "terapia",
    "hospital": "centro",
    "milagro": "poderoso",
    "garantía": "promesa",
    # Bồ Đào Nha (Pt - PT, BR)
    "câncer": "dano",
    "remédio": "terapia",
    "doença": "condição",
    # Ý (It)
    "curare": "alleviare",
    "cancro": "danno",
    "medico": "esperto",
    "ospedale": "centro",
    # Đông Âu: Ba Lan (Pl), Séc (Cs), Hungary (Hu), Nga (Ru), Ukraine (Uk)
    "wyleczyć": "złagodzić",
    "rak": "uszkodzenie",
    "lekarz": "ekspert",  # Pl
    "léčit": "zmírnit",
    "rakovina": "poškození",
    "doktor": "expert",  # Cs
    "gyógyít": "enyhít",
    "rák": "károsodás",
    "orvos": "szakértő",  # Hu
    "вылечить": "облегчить",
    "рак": "повреждение",
    "врач": "эксперт",
    "больница": "центр",  # Ru
    "вилікувати": "полегшити",
    "лікар": "експерт",
    "гарантія": "обіцянка",  # Uk
    # Hy Lạp (El) & Thổ Nhĩ Kỳ (Tr)
    "θεραπεία": "ανακούφιση",
    "καρκίνος": "βλάβη",
    "γιατρός": "ειδικός",  # El
    "tedavi": "rahatlama",
    "kanser": "hasar",
    "mucize": "güçlü",  # Tr (note: "doktor" already in Cs above)
    # =======================================================
    # 🌏 TIER 3 & ASIA (RỒNG HỔ & TRUNG ĐÔNG)
    # =======================================================
    # Trung (Zh - CN, TW, HK)
    "治愈": "舒缓",
    "治疗": "调理",
    "癌症": "损伤",
    "医生": "专家",
    "药": "疗法",
    "医院": "中心",
    "奇迹": "强力",
    "根除": "改善",
    "保证": "承诺",
    # Nhật (Ja)
    "治す": "和らげる",
    "治療": "ケア",
    "癌": "ダメージ",
    "医者": "専門家",
    "薬": "セラピー",
    "病院": "センター",
    "奇跡": "強力",
    "完治": "改善",
    "絶対": "効果的",
    # Hàn (Ko)
    "치료": "케어",
    "완치": "개선",
    "암": "손상",
    "의사": "전문가",
    "약": "요법",
    "병원": "센터",
    "기적": "강력한",
    "보장": "약속",
    # Ả Rập (Ar - QA, AE, SA, KW, IQ, EG)
    "علاج": "سکون",  # UR overrides AR (matches original last-write-wins)
    "شفاء": "راحة",
    "دواء": "علاجي",
    "سرطان": "آسیب",  # FA overrides AR
    "طبيب": "خبير",
    "مستشفى": "مركز",
    "فوري": "سريع",
    "معجزة": "قوي",
    "ضمان": "وعد",
    # Do Thái (He - IL) & Ba Tư (Fa - IR)
    "ריפוי": "הקלה",
    "סרטן": "נזק",
    "רופא": "מומחה",
    "תרופה": "טיפול",  # He
    "درمان": "تسکین",
    "پزشک": "کارشناس",
    "دارو": "تراپی",  # Fa
    # =======================================================
    # 🏝️ TIER 5 & 6: ĐÔNG NAM Á & NAM Á
    # =======================================================
    # Indo (Id) & Malay (Ms)
    "sembuh": "meredakan",
    "mengobati": "menenangkan",
    "kanker": "kerusakan",
    "obat": "terapi",
    "dokter": "ahli",
    "rumah sakit": "pusat",
    "jaminan": "janji",
    # Thái (Th)
    "รักษา": "บรรเทา",
    "หายขาด": "ดีขึ้น",
    "มะเร็ง": "ความเสียหาย",
    "หมอ": "ผู้เชี่ยวชาญ",
    "ยา": "การบำบัด",
    "โรงพยาบาล": "ศูนย์",
    # Nam Á: Hindi (Hi), Urdu (Ur), Bengali (Bn)
    "इलाज": "राहत",
    "दवा": "थेरेपी",
    "कैंसर": "क्षति",
    "डॉक्टर": "विशेषज्ञ",  # Hi
    "کینسر": "نقصان",  # Ur
    "নিরাময়": "উপশম",
    "ক্যান্সার": "ক্ষতি",
    "ডাক্তার": "বিশেষজ্ঞ",  # Bn
    # Lào (Lo) & Campuchia (Km)
    "ປິ່ນປົວ": "ບັນເທົາ",
    "ມະເຮັງ": "ຄວາມເສຍຫາຍ",
    "ຫມໍ": "ຜູ້ຊ່ຽວຊານ",  # Lo
    "ព្យាបាល": "សម្រាល",
    "មហារីក": "ការខូចខាត",
    "គ្រូពេទ្យ": "អ្នកជំនាញ",  # Km
}


def _is_latin_key(token: str) -> bool:
    """True if ``token`` should be matched with ``\\b`` word boundaries.

    The original implementation used a single ``any(...)`` check covering
    Thai (U+0E00–U+0FFF), CJK Unified Ideographs (U+4E00–U+9FFF), Hiragana
    + Katakana (U+3040–U+30FF) and Hangul Syllables (U+AC00–U+D7AF). We
    keep the same set so the regex behaviour is identical.
    """
    for c in token:
        if (
            "\u0e00" <= c <= "\u0fff"
            or "\u4e00" <= c <= "\u9fff"
            or "\u3040" <= c <= "\u30ff"
            or "\uac00" <= c <= "\ud7af"
        ):
            return False
    return True


def apply_safety_filter(text: str, blacklist: dict[str, str] | None = None) -> str:
    """Return ``text`` with risky words rewritten using ``blacklist``.

    Behaviour preserved verbatim from ``ContentTab._apply_safety_filter``:

    * Empty / falsy ``text`` returns ``""`` unchanged.
    * Blacklist keys are sorted longest-first so multi-word entries
      (``"chữa khỏi"``) replace BEFORE their substrings (``"chữa"``)
      would have matched something different.
    * Latin keys use ``\\b<token>\\b`` so ``"secure"`` is NOT rewritten
      because of ``"cure"``.
    * CJK/Thai/Indic keys are plain substring replacements (those scripts
      don't word-break with whitespace).
    * Replacement is case-insensitive (``re.IGNORECASE``) for both code
      paths.

    ``blacklist`` defaults to :data:`SAFETY_BLACKLIST`. Tests can pass a
    custom dict to assert pure ordering / boundary behaviour without
    depending on the production word list.
    """
    if not text:
        return ""

    table = blacklist if blacklist is not None else SAFETY_BLACKLIST
    clean = text

    # Sort longest keys first so multi-word entries take precedence over
    # any of their substrings.
    for bad in sorted(table, key=len, reverse=True):
        safe = table[bad]
        if _is_latin_key(bad):
            pattern = re.compile(r"\b" + re.escape(bad) + r"\b", re.IGNORECASE)
        else:
            pattern = re.compile(re.escape(bad), re.IGNORECASE)
        clean = pattern.sub(safe, clean)

    return clean


def process_voice_and_sfx(raw_text: str) -> tuple[str, str]:
    """Split ``raw_text`` (AI-generated narration) into clean voice + SFX cue list.

    Behaviour mirrors ``ContentTab._process_voice_and_sfx``:

    * SFX cues are anything wrapped in ``[...]``, ``(...)`` or ``*...*``.
    * The cue list is returned as a single newline-joined string in the
      order of appearance.
    * Voice text has those cues removed, then any leading
      ``Scene N:``/``Cảnh N:`` line markers stripped, then re-joined with
      blank lines between paragraphs.
    * Empty input returns ``("", "")`` like the original.
    """
    if not raw_text:
        return "", ""

    sfx_matches = re.findall(r"(\[.*?\]|\(.*?\)|(?:\*.*?\*))", raw_text)
    sfx_list_str = "\n".join(sfx_matches)

    voice_clean = re.sub(r"\[.*?\]", "", raw_text)
    voice_clean = re.sub(r"\(.*?\)", "", voice_clean)
    voice_clean = re.sub(r"\*.*?\*", "", voice_clean)
    voice_clean = re.sub(r"(?i)^(Scene|Cảnh)\s+\d+[:.]?", "", voice_clean, flags=re.MULTILINE)

    lines = [line.strip() for line in voice_clean.split("\n") if line.strip()]
    voice_final = "\n\n".join(lines)
    return voice_final, sfx_list_str
