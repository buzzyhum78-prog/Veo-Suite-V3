"""Small text-cleanup helpers used across RadarTab.

Extracted from ui/widgets/radar_tab.py in PR-5d. RadarTab had three nested
helpers — one inside ``_real_update_prompt`` (``clean_input_string``), one
inside ``run_channel_planning`` (``clean_topic_name``), and one inside
``transfer_staging_to_factory`` (``final_clean``). All three normalised a
combo-box / table label such as ``"🌊 Ocean & Water (Sóng nước)"`` down to
something Prompt-friendly like ``"Ocean & Water"``. They differed only in
the regex used to strip emoji/punctuation, so we lift the shared shape
here and keep three distinct entry points so behaviour is preserved
verbatim per call-site.

Invariants per function (preserved verbatim):

* ``clean_input_string`` — the prompt-builder flavour.
    - If ``"("`` is present, keep only the part before it.
    - If ``"---"`` is present, return ``""`` (it's a divider row).
    - Strip everything except ``\\w`` (unicode word chars), whitespace,
      ``&``, ``,``.
    - ``.strip()`` the result.

* ``clean_topic_name`` — the channel-planner flavour.
    - If falsy or contains ``"---"``, return ``"General"`` (note: NOT
      empty string — the planner needs a fallback niche).
    - Take the part before the first ``"("``, strip it.
    - Strip a leading run of any chars except ``\\w \\s`` (so an emoji
      prefix vanishes but internal ``&`` survives).

* ``clean_staging_topic`` — the staging-table flavour (was ``final_clean``).
    - If falsy, return ``"General"``.
    - Take the part before the first ``"("``, strip it.
    - Strip a leading run of any chars except ``\\w \\s & ,``.

Why three flavours? They look near-identical but the regex differs in
which trailing characters are tolerated mid-string vs. at the start.
Consolidating to one function would silently change behaviour for at
least one call-site, which is exactly the kind of drift PR-5d is trying
to prevent.
"""

from __future__ import annotations

import re

# Pre-compiled for hot paths (prompt builder fires on every combo change).
_RE_KEEP_WORD_AMP_COMMA = re.compile(r"[^\w\s&,]")
_RE_LEADING_NON_WORD = re.compile(r"^[^\w\s]*")
_RE_LEADING_NON_WORD_AMP_COMMA = re.compile(r"^[^\w\s&,]*")


def clean_input_string(text) -> str:
    """Normalise a topic combo-box label for the prompt builder.

    See module docstring for the precise rule. Returns ``""`` for divider
    rows (containing ``"---"``).
    """
    if text is None:
        return ""
    s = str(text)
    if "(" in s:
        s = s.split("(")[0]
    if "---" in s:
        return ""
    s = _RE_KEEP_WORD_AMP_COMMA.sub("", s)
    return s.strip()


def clean_topic_name(text) -> str:
    """Normalise the channel-planner niche label. Falls back to "General"."""
    if not text or "---" in str(text):
        return "General"
    s = str(text).split("(")[0].strip()
    s = _RE_LEADING_NON_WORD.sub("", s).strip()
    return s


def clean_staging_topic(text) -> str:
    """Normalise a staging-table niche cell. Falls back to "General".

    Was ``final_clean`` nested in ``transfer_staging_to_factory``.
    Differs from :func:`clean_topic_name` only in the leading-strip regex
    (this one also tolerates a leading ``&`` or ``,``).
    """
    if not text:
        return "General"
    s = str(text).split("(")[0].strip()
    s = _RE_LEADING_NON_WORD_AMP_COMMA.sub("", s).strip()
    return s
