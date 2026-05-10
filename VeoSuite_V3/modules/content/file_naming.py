"""Filesystem-name sanitiser extracted from ``ui/widgets/content_tab.py``.

Lifted verbatim from ``ContentTab._sanitize_filename`` so callers in the
content pipeline (project naming, channel asset folders, output JSON paths)
keep producing identical results. Pure: no Qt, no IO.
"""

from __future__ import annotations

import re

__all__ = ["sanitize_filename"]

# Windows-forbidden filename characters: < > : " / \ | ? *
_FORBIDDEN_CHARS = re.compile(r'[\\/*?:"<>|]')
_NEWLINE_TAB = re.compile(r"[\r\n\t]")
_RUN_OF_SPACE_OR_UNDERSCORE = re.compile(r"[\s_]+")
_MAX_LEN = 50


def sanitize_filename(name: object) -> str:
    """Return a Windows-safe filename derived from ``name``.

    Behaviour mirrors the original implementation step-for-step:

    1. Coerce to str and strip whitespace from both ends.
    2. Collapse \\r \\n \\t to a plain space.
    3. Replace each forbidden char (``< > : " / \\ | ? *``) with ``_``.
    4. Collapse any run of whitespace/underscores to a single space.
    5. Truncate to 50 characters.
    6. Strip leading/trailing dots and spaces (Windows refuses these).
    7. Fall back to ``"Untitled"`` if the result is empty.

    Falsy ``name`` (``None``, ``""``, etc.) short-circuits to
    ``"Untitled"``.
    """
    if not name:
        return "Untitled"

    name_str = str(name).strip()
    name_str = _NEWLINE_TAB.sub(" ", name_str)
    clean = _FORBIDDEN_CHARS.sub("_", name_str)
    clean = _RUN_OF_SPACE_OR_UNDERSCORE.sub(" ", clean)
    clean = clean[:_MAX_LEN]
    clean = clean.strip(". ")
    return clean if clean else "Untitled"
