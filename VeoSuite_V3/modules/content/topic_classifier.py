"""Pure tone / duration / visual-source classifiers extracted from
``ui/widgets/content_tab.py``.

Originally embedded in ``ContentTab.auto_select_tone_by_topic`` and
``ContentTab.auto_select_duration``, these routines are simple keyword-table
lookups that decide:

* What ``tone`` (giọng đọc) suits a topic.
* What ``duration_idx`` (index into the duration combo box) and
  ``visual_source_idx`` (index into the visual-source combo box) suit a
  combination of platform + topic.

Lifting the rules out into pure functions makes them unit-testable and
also makes it possible to use them from non-Qt code (e.g. CLI batch
generators, tests, future plugins) without spinning up a QWidget.

The original UI methods become thin Qt-glue wrappers that:

1. Read ``self.cb_topic.currentText()`` / ``self.cb_platform.currentText()``.
2. Call the pure function here.
3. Apply the returned value to the matching combo boxes (with
   ``blockSignals`` to avoid feedback loops) and call
   ``self.update_prompt_preview()``.
"""

from __future__ import annotations

__all__ = [
    "DEFAULT_TONE",
    "TONE_RULES",
    "PLATFORM_SHORT_FORMATS",
    "DURATION_RULES",
    "classify_tone_by_topic",
    "classify_duration_and_visual",
]


DEFAULT_TONE = "Auto (Theo chủ đề)"

# Each rule is (keywords, tone_label). The first rule whose keyword list
# overlaps the (lowercased) topic wins. Order matters and matches the
# original ``auto_select_tone_by_topic`` priority exactly.
#
# The "kids → bedtime vs playful" rule is special: kids+sleep keywords go
# to bedtime, otherwise generic kids → playful. We model that as a single
# rule with a sub-decision in :func:`classify_tone_by_topic` to preserve
# the original branching shape.
TONE_RULES: list[tuple[tuple[str, ...], str]] = [
    # 1. Horror / Crime
    (
        ("ma", "kinh dị", "horror", "creepy", "crime", "vụ án", "sát nhân"),
        "Kinh dị (Horror/Creepy)",
    ),
    # 2. Comedy
    (("funny", "thú cưng", "hài", "meme"), "Hài hước (Funny/Witty)"),
    # 3. Kids — handled with a sub-rule below; placeholder label
    (("kids", "bé", "đồ chơi", "toy"), "__KIDS__"),
    # 4. News
    (
        ("tin tức", "thời sự", "showbiz", "drama", "hot"),
        "Tin tức (News Anchor)",
    ),
    # 5. Finance / Professional
    (
        ("tài chính", "crypto", "kinh doanh", "đầu tư", "money"),
        "Nghiêm túc (Professional)",
    ),
    # 6. Tech / Academic
    (
        ("công nghệ", "code", "tech", "review", "sách", "học"),
        "Nghiêm túc (Professional)",
    ),
    # 7. Luxury / Real-estate
    (
        ("luxury", "xe sang", "bất động sản", "nhà đẹp", "kiến trúc"),
        "Sang trọng (Luxury/Elegant)",
    ),
    # 8. Health / Care
    (
        ("sức khỏe", "y tế", "dinh dưỡng", "bệnh"),
        "Y tế / Sức khỏe (Health/Care)",
    ),
    # 9. Podcast
    (
        ("podcast", "tâm sự", "hẹn hò", "thầm kín"),
        "Tâm sự (Podcast/Conversational)",
    ),
    # 10. Spiritual / Cosmic
    (
        ("tâm linh", "phật", "triết lý", "sâu sắc", "vũ trụ", "space", "universe"),
        "Sâu sắc (Emotional/Deep)",
    ),
    # 11. Motivation / Sports
    (
        ("động lực", "gym", "thể thao", "gaming"),
        "Sôi động (Hype/Energetic)",
    ),
    # 12. ASMR / Relax
    (
        ("asmr", "relax", "thiền", "mưa", "sleep", "lofi"),
        "Thư giãn (Chill/Calm)",
    ),
    # 13. Food / Travel
    (
        ("nấu ăn", "ẩm thực", "food", "du lịch"),
        "Sang trọng (Luxury/Elegant)",
    ),
    # 14. History / Documentary
    (
        ("lịch sử", "history", "war", "chiến tranh", "tài liệu"),
        "Kịch tính (Dramatic/Suspense)",
    ),
]

_KIDS_BEDTIME_KEYS = ("ngủ", "ru", "bedtime", "truyện cổ tích", "fairy")
_KIDS_BEDTIME_TONE = "Nhẹ nhàng / Ru ngủ (Bedtime Story)"
_KIDS_PLAYFUL_TONE = "Vui tươi / Háo hức (Kids Playful)"


def classify_tone_by_topic(topic: str | None) -> str:
    """Return the tone label that best matches ``topic``.

    The lookup is case-insensitive. The decoration row markers used in
    the topic combo (``"--- Format ---"``) short-circuit to
    :data:`DEFAULT_TONE` so the auto-selector never overrides the user's
    explicit "Auto" choice.

    Returns the tone STRING, not the combo-box index — the caller is
    responsible for fuzzy-matching the label against the items already
    populated in ``cb_tone`` (mimicking the ``cb_tone.itemText(i)``
    fuzzy logic in the original).
    """
    if not topic:
        return DEFAULT_TONE
    t = topic.lower()
    if "---" in t:
        return DEFAULT_TONE

    for keywords, label in TONE_RULES:
        if any(kw in t for kw in keywords):
            if label == "__KIDS__":
                if any(kw in t for kw in _KIDS_BEDTIME_KEYS):
                    return _KIDS_BEDTIME_TONE
                return _KIDS_PLAYFUL_TONE
            return label

    return DEFAULT_TONE


# Visual-source combo indices (matches ``VISUAL_SOURCE_DATA`` order in
# the original code):
#   0 = Hybrid (80% Stock - 20% AI)
#   1 = 100% AI Generated
#   2 = 100% Stock Footage
#   3 = 50/50

# Platforms whose short-form rule forces target_idx=0 regardless of topic.
PLATFORM_SHORT_FORMATS: tuple[str, ...] = ("shorts", "tiktok", "reels")

# Each rule is (topic_keywords, duration_idx, visual_idx). First match wins.
# Order matches the original ``auto_select_duration`` priority.
DURATION_RULES: list[tuple[tuple[str, ...], int, int]] = [
    # NHÓM 1: LOOP / KHÔNG LỜI — long-form Stock loop content.
    (
        (
            "rain",
            "music",
            "lofi",
            "sleep",
            "asmr",
            "meditation",
            "mưa",
            "thiền",
            "ngủ",
            "nhạc",
            "ambient",
            "yoga",
            "study",
            "relax",
            "piano",
            "noise",
            "focus",
            "snow",
            "winter",
            "tuyết",
            "fire",
            "lửa",
            "ocean",
            "water",
            "biển",
        ),
        5,  # 1 Giờ Loop
        2,  # 100% Stock Footage
    ),
    # NHÓM 2: KỂ CHUYỆN / TƯ LIỆU — long-form Hybrid documentary.
    (
        (
            "crime",
            "war",
            "documentary",
            "history",
            "vụ án",
            "chiến tranh",
            "tài liệu",
            "sát nhân",
            "lịch sử",
            "biography",
        ),
        4,  # 20+ phút
        0,  # Hybrid
    ),
    # NHÓM 3: TRÍ TƯỞNG TƯỢNG / BÍ ẨN — AI-generated visuals required.
    (
        (
            "horror",
            "ghost",
            "ma",
            "kinh dị",
            "creepy",
            "alien",
            "space",
            "universe",
            "vũ trụ",
            "bí ẩn",
            "mystery",
            "ancient",
            "cổ đại",
            "thần thoại",
            "kids",
            "fairy",
            "hoạt hình",
        ),
        3,  # 12-15 phút
        1,  # 100% AI Generated
    ),
    # NHÓM 4: KIẾM TIỀN / KIẾN THỨC — Hybrid for ad-friendly mid-length.
    (
        (
            "finance",
            "tech",
            "money",
            "business",
            "crypto",
            "tài chính",
            "công nghệ",
            "top 10",
            "review",
        ),
        2,  # 8-10 phút
        0,  # Hybrid
    ),
    # NHÓM 5: TIN TỨC / SỰ THẬT — Stock-only short news.
    (
        ("news", "fact", "tin tức", "sự thật", "showbiz", "drama"),
        1,  # 3-5 phút
        2,  # 100% Stock Footage
    ),
]

_DEFAULT_DURATION_IDX = 1  # 3-5 phút
_DEFAULT_VISUAL_IDX = 0  # Hybrid


def classify_duration_and_visual(platform: str | None, topic: str | None) -> tuple[int, int]:
    """Return ``(duration_idx, visual_idx)`` for the given platform/topic.

    Mirrors ``ContentTab.auto_select_duration`` exactly:

    * If ``platform`` is a short-form platform (Shorts / TikTok / Reels),
      return ``(0, 0)`` — short clip, Hybrid visuals.
    * Otherwise scan :data:`DURATION_RULES` in order; first keyword match
      wins.
    * If nothing matches, fall back to ``(1, 0)`` — 3-5 minutes, Hybrid.
    * Facebook adjustment: if ``platform`` contains ``"facebook"`` and
      the chosen ``duration_idx`` is greater than 2, clamp to 2 (so
      ``20+ phút`` and ``1 giờ loop`` both clamp to the 8-10 phút bucket).

    The returned indices are still bounded by the caller's combo box
    sizes — the original code guards with ``if target_idx <
    self.cb_duration.count()`` before applying.
    """
    p = (platform or "").lower()
    t = (topic or "").lower()

    if any(short in p for short in PLATFORM_SHORT_FORMATS):
        return 0, 0

    duration_idx = _DEFAULT_DURATION_IDX
    visual_idx = _DEFAULT_VISUAL_IDX
    for keywords, d_idx, v_idx in DURATION_RULES:
        if any(kw in t for kw in keywords):
            duration_idx = d_idx
            visual_idx = v_idx
            break

    if "facebook" in p and duration_idx > 2:
        duration_idx = 2

    return duration_idx, visual_idx
