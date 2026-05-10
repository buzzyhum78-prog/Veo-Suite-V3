"""Robust JSON extractor lifted from ``ui/widgets/content_tab.py``.

LLM responses often wrap JSON in markdown fences, prepend an apology, or
sneak in ``//`` line-comments. The original ``ContentTab.extract_json_from_text``
walked through these failure modes one by one; this module preserves that
exact strategy so every existing caller (single-task AI writer, batch
writer, on_ai_finished completion handler) receives identical objects.

Pure: ``re`` + ``json`` only. No Qt, no IO.
"""

from __future__ import annotations

import json
import re
from typing import Any

__all__ = ["extract_json_from_text"]

_MARKDOWN_FENCE = re.compile(r"```(?:json)?(.*?)```", re.DOTALL)


def extract_json_from_text(text: str | None) -> Any | None:
    """Best-effort recover a JSON object from messy LLM output.

    Strategy (matches ``ContentTab.extract_json_from_text`` exactly):

    1. Treat falsy input as "no JSON" → return ``None``.
    2. Strip surrounding whitespace.
    3. If the text contains a ```\u200bjson ... ``` (or plain ``\u200b``\u200b)
       fenced code block, narrow the search to its body.
    4. Look for the first ``{`` and the last ``}``; use the slice between
       them as the JSON candidate. This skips chatty pre/post text.
    5. Try ``json.loads(...)``. If that fails because the LLM inserted
       ``//`` comments, drop comment-only lines and retry once.
    6. Anything else → log a short preview to stdout (parity with the
       original) and return ``None``.

    Returns the decoded Python object on success; ``None`` on any
    failure path.
    """
    if not text:
        return None

    text = text.strip()

    fence_match = _MARKDOWN_FENCE.search(text)
    if fence_match:
        text = fence_match.group(1).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        print(f"❌ Lỗi Parse JSON. Raw text preview: {text[:100]}...")
        return None

    candidate = text[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        clean_lines = [line for line in candidate.split("\n") if not line.strip().startswith("//")]
        clean_text = "\n".join(clean_lines)
        try:
            return json.loads(clean_text)
        except json.JSONDecodeError:
            pass

    print(f"❌ Lỗi Parse JSON. Raw text preview: {text[:100]}...")
    return None
