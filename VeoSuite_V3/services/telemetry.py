"""Local-only, opt-in telemetry for Veo Suite V3.

Why local-only:

The application is intended to be installable on machines without
guaranteed internet access (offline content production) and is also
deployed to users who may legitimately not want to send data
elsewhere. So this module never talks to the network — events go to
a JSONL file under the user's data directory and stay there. The
diagnostics UI / "share with developer" workflow can read the file
back later; that's a separate concern.

Why opt-in:

Default is **disabled**. ``record(...)`` is a no-op unless the user
has explicitly flipped the flag in settings. The single
``TelemetrySink.enabled`` property controls everything — there is no
secret bypass.

Rotation:

JSONL files are appended forever in principle, but we rotate when
the active file grows past ``max_bytes`` so a long-running session
doesn't quietly fill the disk. Rotation moves ``events.jsonl`` to
``events.jsonl.1`` (overwriting any older ``.1`` file).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("VeoSuite.Telemetry")

_VALID_EVENT_TYPES = frozenset(
    {
        "session_started",
        "session_ended",
        "feature_used",
        "error_occurred",
        "plugin_loaded",
        "plugin_failed",
        "tab_switched",
    }
)

# Default size cap — large enough that production sessions almost never
# rotate, small enough that a runaway loop is contained quickly.
_DEFAULT_MAX_BYTES = 1024 * 1024  # 1 MiB


@dataclass
class TelemetrySink:
    """Append-only JSONL sink.

    Parameters
    ----------
    path:
        Target file. Parent directory is created on first write.
    enabled:
        Master opt-in switch. When False, every ``record`` call is a
        no-op (no file IO, no allocation beyond the early return).
    max_bytes:
        Rotation threshold. The active file is rotated to ``<path>.1``
        when its size exceeds this number of bytes.
    """

    path: Path
    enabled: bool = False
    max_bytes: int = _DEFAULT_MAX_BYTES
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        if self.max_bytes <= 0:
            raise ValueError(f"max_bytes must be positive (got {self.max_bytes})")

    # -------------------------------------------------------------- writing

    def record(self, event_type: str, **payload: Any) -> bool:
        """Append a single event. Returns True if it was written.

        Returns False (without raising) when:
          * the sink is disabled,
          * the event type is not in the whitelist,
          * an IO error occurred (we log it and swallow).
        """
        if not self.enabled:
            return False
        if event_type not in _VALID_EVENT_TYPES:
            logger.warning("Rejected unknown telemetry event %r", event_type)
            return False

        record = {
            "ts": time.time(),
            "type": event_type,
            "payload": _coerce_payload(payload),
        }
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))

        try:
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._rotate_if_needed()
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(line)
                    f.write("\n")
            return True
        except OSError as exc:
            logger.warning("Failed to write telemetry event: %s", exc)
            return False

    # --------------------------------------------------------------- reading

    def read_events(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Return parsed events from the active file (newest last).

        Used by tests and the diagnostics UI. Skips malformed lines
        rather than blowing up — telemetry must never crash the host.
        """
        if not self.path.is_file():
            return []
        events: list[dict[str, Any]] = []
        try:
            with self.path.open(encoding="utf-8") as f:
                for raw in f:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        events.append(json.loads(raw))
                    except json.JSONDecodeError:
                        continue
        except OSError as exc:
            logger.warning("Cannot read telemetry: %s", exc)
            return []
        if limit is not None and limit >= 0:
            return events[-limit:]
        return events

    def clear(self) -> None:
        """Wipe the active file. Rotated copies are left in place."""
        with self._lock:
            try:
                if self.path.is_file():
                    self.path.unlink()
            except OSError as exc:
                logger.warning("Cannot clear telemetry: %s", exc)

    # -------------------------------------------------------------- rotation

    def _rotate_if_needed(self) -> None:
        try:
            size = self.path.stat().st_size if self.path.is_file() else 0
        except OSError:
            return
        if size <= self.max_bytes:
            return
        rotated = self.path.with_suffix(self.path.suffix + ".1")
        try:
            if rotated.exists():
                rotated.unlink()
            os.replace(self.path, rotated)
        except OSError as exc:
            logger.warning("Cannot rotate telemetry: %s", exc)


# --------------------------------------------------------------- helpers

# JSON only accepts a narrow set of leaf types — Path/datetime/bytes/etc.
# need to be normalised first. We keep this private and explicit so a
# bad payload is silently coerced to a printable string rather than
# raising mid-write and corrupting the JSONL file.
_JSON_SAFE = (str, int, float, bool, type(None))


def _coerce_payload(payload: dict[str, Any]) -> dict[str, Any]:
    coerced: dict[str, Any] = {}
    for k, v in payload.items():
        coerced[str(k)] = _coerce_value(v)
    return coerced


def _coerce_value(v: Any) -> Any:
    if isinstance(v, _JSON_SAFE):
        return v
    if isinstance(v, (list, tuple)):
        return [_coerce_value(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _coerce_value(x) for k, x in v.items()}
    return repr(v)


# -------------------------------------------------------------- module API

# Module-level singleton — the host sets this up once at startup. Tests
# always construct their own TelemetrySink to avoid sharing state.
_default_sink: TelemetrySink | None = None


def configure(
    path: Path | str, *, enabled: bool = False, max_bytes: int = _DEFAULT_MAX_BYTES
) -> TelemetrySink:
    """Install (or reinstall) the process-wide default sink."""
    global _default_sink
    _default_sink = TelemetrySink(path=Path(path), enabled=enabled, max_bytes=max_bytes)
    return _default_sink


def get_sink() -> TelemetrySink | None:
    return _default_sink


def record(event_type: str, **payload: Any) -> bool:
    """Convenience wrapper around the module-level sink."""
    sink = _default_sink
    if sink is None:
        return False
    return sink.record(event_type, **payload)
