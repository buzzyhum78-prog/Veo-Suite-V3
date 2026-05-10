"""Production-history persistence for RadarTab.

Extracted from ui/widgets/radar_tab.py in PR-5d. RadarTab used two thin
JSON-backed routines (`check_production_history` and `log_production_history`)
to remember which (topic, country) pairs had already been promoted to the
content factory. Both routines mixed three concerns:

1. The key shape  (``f"{topic}_{country}"``).
2. Disk IO       (open / json.load / json.dump under ``VEO_DB/``).
3. Predicate     (``key in history`` → return ``(True, history[key]['date'])``).

The first and third concerns are pure; the second is just file handling.
This module gives each concern its own function so unit tests can pin them
down without Qt, without monkey-patching ``builtins.open``, and without
touching the real ``VEO_DB`` folder. The wrapper in RadarTab simply
delegates and keeps the original method signatures intact.

Behaviour invariants (preserved verbatim from the original code):

* The key format is ``f"{topic}_{country}"`` — yes, with an underscore
  separator, NOT a slash or pipe. Existing production_log.json files in
  the wild rely on this exact shape.
* ``check_topic_history`` returns ``(False, None)`` when the key is absent,
  matching the original ``return False, None`` fall-through.
* ``load_history`` swallows *all* exceptions (corrupt file, IO error,
  permission denied) and returns ``{}`` — the original used a bare
  ``except: pass`` block, so we keep that behaviour.
* ``record_topic_history`` is mutating: it overwrites any existing entry
  for the same key. The original code did the same (``history[key] = ...``).
* The timestamp format is ``"%Y-%m-%d %H:%M:%S"`` (no timezone, local
  clock). ``now`` is injected so tests can pin a deterministic value.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from typing import Any


HISTORY_DIR = "VEO_DB"
HISTORY_PATH = os.path.join(HISTORY_DIR, "production_log.json")


def make_history_key(topic, country) -> str:
    """Return the canonical history-store key for ``(topic, country)``.

    Format is ``f"{topic}_{country}"`` with no normalisation. The original
    RadarTab code used the raw user input (after a light text clean) as
    the key, so we keep the same coupling here. Callers that want
    normalisation should apply it before passing values in.
    """
    return f"{topic}_{country}"


def load_history(path: str = HISTORY_PATH) -> dict[str, Any]:
    """Read the production-log JSON. Returns ``{}`` on any failure.

    Matches the original behaviour: missing file -> ``{}``; corrupt file
    or read error -> ``{}`` (bare ``except: pass``). The original then
    used ``history`` as a dict, so we coerce non-dict payloads to ``{}``
    as well (defensive — the file is owned by us).
    """
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def save_history(history: dict[str, Any], path: str = HISTORY_PATH) -> None:
    """Persist the production-log JSON.

    Creates the parent directory if needed (RadarTab's wrapper assumed
    ``VEO_DB/`` may not exist on first run). Writes UTF-8 with
    ``indent=4`` and ``ensure_ascii=False`` so Vietnamese topic labels
    round-trip cleanly.
    """
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=4, ensure_ascii=False)


def check_topic_history(
    history: dict[str, Any], topic, country
) -> tuple[bool, str | None]:
    """Return ``(is_duplicate, last_date)`` for the given ``(topic, country)``.

    Matches the original ``check_production_history`` semantics exactly:

    * Key absent  -> ``(False, None)``.
    * Key present but no ``"date"`` field -> ``(True, None)`` (the original
      called ``history[key]['date']`` which would raise — we soften this
      to ``None`` so callers that pass a hand-crafted history dict don't
      explode. The original on-disk format always includes ``date``, so
      this is purely defensive.)
    * Key present with ``"date"`` -> ``(True, history[key]["date"])``.
    """
    key = make_history_key(topic, country)
    entry = history.get(key)
    if entry is None:
        return False, None
    if not isinstance(entry, dict):
        return True, None
    return True, entry.get("date")


def record_topic_history(
    history: dict[str, Any],
    topic,
    country,
    now: _dt.datetime | None = None,
) -> dict[str, Any]:
    """Stamp ``(topic, country)`` into ``history`` and return the same dict.

    Mutates ``history`` in place (matches the original ``history[key] = ...``
    assignment) and also returns it for fluent use in ``save_history``. The
    entry shape is ``{"date": "YYYY-MM-DD HH:MM:SS", "status": "Created"}``,
    identical to the original.

    ``now`` is injected so tests can pin a deterministic datetime; the
    production wrapper passes ``None`` and the helper falls back to
    ``datetime.datetime.now()``.
    """
    when = now if now is not None else _dt.datetime.now()
    key = make_history_key(topic, country)
    history[key] = {
        "date": when.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "Created",
    }
    return history
