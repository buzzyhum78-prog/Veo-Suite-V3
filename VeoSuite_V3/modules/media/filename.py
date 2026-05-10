"""Pure filename helpers extracted from ui/widgets/media_tab.py.

The MediaTab uses a *stricter* sanitiser than ContentTab: it keeps only
word characters, whitespace, hyphens, and dots; everything else is stripped
(not replaced). This matches the original `_sanitize_filename` in
`media_tab.py` byte-for-byte so existing export folders keep working.

If you need the looser ContentTab variant (forbidden Windows chars
replaced with underscores, length-truncated, etc.), use
`modules.content.file_naming.sanitize_filename` instead.
"""

from __future__ import annotations

import re

__all__ = ["sanitize_filename_strict"]


def sanitize_filename_strict(name) -> str:
    """Make a Windows-safe folder name using a strict allow-list.

    Allow-list: ``[A-Za-z0-9_\\s\\-\\.]``. Anything else is dropped.

    Behaviour preserved verbatim from `MediaTab._sanitize_filename`:
      * Empty / None / falsy input  -> ``"Untitled"``
      * Coerce to str via ``str(name)``
      * Strip leading/trailing whitespace AFTER the regex sub
    """
    if not name:
        return "Untitled"
    clean_name = re.sub(r"[^\w\s\-\.]", "", str(name))
    return clean_name.strip()
