"""Topic → AI-prompt strategy mapping for RadarTab.

Extracted from ui/widgets/radar_tab.py in PR-5d. The prompt builder
``_real_update_prompt`` contained two parallel decision tables:

1. An ``if/elif`` chain over keyword substrings that mapped a topic
   string to a one-line "🎯 STRATEGY" hint included verbatim in the
   AI prompt.
2. Two lists (``strict_topics`` / ``semi_topics``) used to select
   between three multi-line policy paragraphs (STRICT / AUTHENTICITY /
   CREATIVE FREEDOM).

Both are pure data + dispatchers, so they belong in their own module
where tests can pin the exact ordering and the exact returned strings.

Behaviour invariants (preserved verbatim from the original code):

* ``classify_intent`` lower-cases its input once, then walks ``INTENT_RULES``
  in declared order and returns the *first* match. The default fallback
  is ``DEFAULT_INTENT_HINT`` ("Focus on: High Retention…").
* The strict-topic and semi-topic checks use ``any(k in t_str for k in …)``
  on the *original-case* topic string. Strict wins over semi (the original
  used ``if/elif`` in that order), so a topic containing both flags goes
  to STRICT.
* The three policy paragraphs are stored verbatim as constants so the
  prompt sent to the AI is byte-for-byte identical to what RadarTab used
  to inline.
"""

from __future__ import annotations


DEFAULT_INTENT_HINT = "Focus on: High Retention, Clickable Viral concepts."


# Ordered list of (keyword tuple, hint). First match wins. The keyword
# tuple is matched against the lower-cased topic string with ``in``.
INTENT_RULES: list[tuple[tuple[str, ...], str]] = [
    (
        ("rain", "ocean", "healing", "meditation"),
        "🎯 STRATEGY: Sleep Aid, Insomnia Relief, Focus Study, "
        "Stress Reduction (ASMR/Ambience).",
    ),
    (
        ("space", "universe", "geography"),
        "🎯 STRATEGY: Cosmic Horror, Scale Comparisons, "
        "Future Paradoxes, 'Mind-blowing Facts'.",
    ),
    (
        ("history", "ancient"),
        "🎯 STRATEGY: Forgotten Empires, Dark Secrets, "
        "'What they didn't teach you in school', Timeline breakdowns.",
    ),
    (
        ("animal", "cat", "dog"),
        "🎯 STRATEGY: Cute Aggression, Survival Instincts, "
        "Rare Behaviors, 'Try not to laugh', Heartwarming rescues.",
    ),
    (
        ("scary", "crime", "mystery"),
        "🎯 STRATEGY: High Curiosity Gap, Urban Legends, "
        "Unsolved Mysteries, Psychological Thriller vibes.",
    ),
    (
        ("tech", "ai", "coding", "inventions"),
        "🎯 STRATEGY: Productivity Hacks, 'Replace your job', "
        "Future Predictions, Tools You Need.",
    ),
    (
        ("finance", "crypto"),
        "🎯 STRATEGY: Wealth Mindset, Passive Income Realities, "
        "Market Crash Predictions, 'How rich people think'.",
    ),
    (
        ("quote", "stoic"),
        "🎯 STRATEGY: Life Lessons, Sigma Grindset, "
        "Mental Toughness, Philosophy for Modern Life.",
    ),
]


# Topics that MUST be factually accurate (matched against the raw,
# original-case topic string).
STRICT_TOPICS: list[str] = [
    "News",
    "Tin tức",
    "History",
    "Lịch sử",
    "Finance",
    "Tài chính",
    "Health",
    "Sức khỏe",
    "Facts",
    "Sự thật",
    "Tech",
    "Công nghệ",
    "Real Estate",
    "Bất động sản",
    "Science",
    "Khoa học",
    "Crime",
    "Vụ án",
]


# Topics that need a real source but allow emotional flavour.
SEMI_TOPICS: list[str] = [
    "Book",
    "Sách",
    "Podcast",
    "Tâm sự",
    "Cooking",
    "Nấu ăn",
    "Vlog",
    "Du lịch",
]


STRICT_RULE = (
    "🚨 STRICT TRUTH POLICY: The content MUST be based on REAL EVENTS, "
    "HISTORICAL FACTS, or VERIFIED DATA.\n"
    "- DO NOT invent fake news or fake historical events.\n"
    "- For 'Crime/Vụ án': Must be a TRUE CRIME case.\n"
    "- For 'Science/Finance': Must be scientifically/financially accurate.\n"
)


SEMI_RULE = (
    "🌟 AUTHENTICITY POLICY: Content should be based on real experiences "
    "or books, but you can focus on EMOTIONAL VALUE and PERSONAL "
    "PERSPECTIVE.\n"
    "- Titles should trigger curiosity but remain honest to the source "
    "material.\n"
)


FREE_RULE = (
    "✨ CREATIVE FREEDOM: Focus purely on ENTERTAINMENT VALUE, VIRALITY, "
    "and EMOTIONAL HOOKS.\n"
    "- For 'Ghost/Horror': You can create fictional scary stories "
    "(Creepypasta style).\n"
    "- For 'Kids/Funny': Focus on fun, engagement, and retention.\n"
)


def classify_intent(topic_str) -> str:
    """Return the strategy hint for the given topic string.

    The lookup walks :data:`INTENT_RULES` in declared order and returns
    the first hint whose keyword tuple has any element appearing in the
    lower-cased ``topic_str``. Falls back to :data:`DEFAULT_INTENT_HINT`.
    """
    if topic_str is None:
        return DEFAULT_INTENT_HINT
    ts = str(topic_str).lower()
    for keywords, hint in INTENT_RULES:
        for kw in keywords:
            if kw in ts:
                return hint
    return DEFAULT_INTENT_HINT


def classify_topic_strictness(topic_str) -> str:
    """Return one of ``"strict"``, ``"semi"`` or ``"free"``.

    Matches the original ``is_strict``/``is_semi`` priority: strict wins
    over semi (the original used ``if/elif/else`` in that order).
    """
    if topic_str is None:
        return "free"
    raw = str(topic_str)
    if any(k in raw for k in STRICT_TOPICS):
        return "strict"
    if any(k in raw for k in SEMI_TOPICS):
        return "semi"
    return "free"


def rule_for_strictness(level: str) -> str:
    """Return the multi-line policy paragraph for the given strictness."""
    if level == "strict":
        return STRICT_RULE
    if level == "semi":
        return SEMI_RULE
    return FREE_RULE
