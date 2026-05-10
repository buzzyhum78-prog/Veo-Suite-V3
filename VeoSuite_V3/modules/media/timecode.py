"""Pure timecode helpers extracted from ui/widgets/media_tab.py.

The MediaTab audio preview displays elapsed / total media-player time as
``MM:SS``. The conversion is purely arithmetic so it lives here instead of
inline on the Qt widget — that way batch / CLI / plugin code can render
the same labels without instantiating a player.
"""

from __future__ import annotations

__all__ = ["format_time_ms"]


def format_time_ms(ms) -> str:
    """Render an integer millisecond duration as ``MM:SS``.

    Behaviour preserved verbatim from `MediaTab.format_time`:
      * Floor-divide ms by 1000 then take ``% 60`` for seconds.
      * Floor-divide ms by 60_000 for minutes (no hour rollover —
        ``120:00`` is intentional, matches existing UI labels).
      * Both fields are zero-padded to width 2.

    The original method also tolerated floats (Qt's `QMediaPlayer`
    sometimes emits durations as int but APIs were typed loose).
    We accept any numeric and coerce to int *before* dividing so a
    float ms doesn't break ``%`` later.
    """
    ms_int = int(ms)
    seconds = (ms_int // 1000) % 60
    minutes = ms_int // 60000
    return f"{minutes:02}:{seconds:02}"
