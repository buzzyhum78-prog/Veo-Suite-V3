"""Centralised UI-style helpers — PR-5e.

Background
----------
Before this module existed each tab (admin_tab, publisher_tab, ops_tab,
editor_tab, content_tab, media_tab, radar_tab) called
``widget.setStyleSheet("background: #27ae60; color: white; ...")`` inline
hundreds of times with slightly different colours and paddings. The user
complaint that opening *Quản Trị* "feels like a different app" traced
straight back to those drifting inline strings.

This module gives every callsite ONE way to express intent:

    from ui.style_kit import apply_kind, apply_accent
    apply_kind(btn_save, "success")
    apply_accent(grp_openai, "lilac")

``apply_kind`` / ``apply_accent`` set a Qt **dynamic property** on the
widget and re-polish so the matching selectors in
``ui/styles.py::DARK_THEME_STYLESHEET`` take effect. No inline stylesheet
is emitted from this helper — the cascade comes from the global theme.

Why dynamic properties instead of inline stylesheets
-----------------------------------------------------
1. Single source of truth — every colour lives in ``ui/styles.py``.
2. Cheap re-theming — changing one rule recolours every button at once.
3. Tests can grep for raw hex literals and fail the build if drift
   sneaks back in (see ``tests/test_pr5e_ui_consistency.py``).

Behaviour invariants
--------------------
* Sets exactly two dynamic properties: ``kind`` (buttons) and ``accent``
  (groupboxes). Both are namespaced so they cannot collide with anything
  Qt itself uses.
* Re-polishes the widget so the new property takes effect immediately —
  Qt does NOT re-evaluate stylesheet selectors when a dynamic property
  changes, you have to nudge it.
* Validates the value against a small whitelist (``BUTTON_KINDS`` /
  ``GROUPBOX_ACCENTS``) so a typo gets caught loudly instead of silently
  rendering as default-grey.
"""

from __future__ import annotations

from typing import Any

BUTTON_KINDS: frozenset[str] = frozenset(
    {
        "primary",  # save/main confirm action
        "success",  # add/refresh/positive action
        "warning",  # destructive-but-recoverable (start render, queue)
        "danger",  # destructive irreversible (stop / delete)
        "info",  # neutral utility (test/check/connect)
        "muted",  # quiet / disabled-look / cancel
        "ai_magic",  # AI-driven action (purple gradient)
    }
)


GROUPBOX_ACCENTS: frozenset[str] = frozenset(
    {
        "emerald",  # green   #2ecc71 — Edge TTS / success-oriented panels
        "lilac",  # purple  #9b59b6 — AI / OpenAI panels
        "red",  # red     #e74c3c — Google / danger-tinted panels
        "amber",  # yellow  #f1c40f — Custom / advanced panels
        "blue",  # blue    #3498db — Proxy / network panels
        "slate",  # gray    #555    — System / neutral panels
        "cyan",  # cyan    #00e6e6 — API-key / accent panels
    }
)


# Hex colours kept here as the single source of truth. ui/styles.py
# pulls these in for its semantic selectors.
KIND_COLORS: dict[str, str] = {
    "primary": "#3498db",
    "success": "#27ae60",
    "warning": "#e67e22",
    "danger": "#e74c3c",
    "info": "#34495e",
    "muted": "#555555",
    "ai_magic": "#8e44ad",
}


ACCENT_COLORS: dict[str, str] = {
    "emerald": "#2ecc71",
    "lilac": "#9b59b6",
    "red": "#e74c3c",
    "amber": "#f1c40f",
    "blue": "#3498db",
    "slate": "#555555",
    "cyan": "#00e6e6",
}


def _repolish(widget: Any) -> None:
    """Force the Qt style engine to re-evaluate selectors for ``widget``.

    Setting a dynamic property does not trigger a re-style on its own,
    so we have to unpolish + polish manually. Safe to call on a widget
    whose style is None (e.g. in headless tests where the platform
    plugin is offscreen and a particular widget hasn't been parented
    yet).
    """
    style = widget.style() if hasattr(widget, "style") else None
    if style is None:
        return
    style.unpolish(widget)
    style.polish(widget)
    if hasattr(widget, "update"):
        widget.update()


def apply_kind(widget: Any, kind: str) -> None:
    """Tag a button (or any QWidget) with a semantic ``kind``.

    Looks up against :data:`BUTTON_KINDS` so a typo is loud, not silent.
    Sets the ``kind`` dynamic property and re-polishes the widget so the
    matching selectors in ``DARK_THEME_STYLESHEET`` take effect.
    """
    if kind not in BUTTON_KINDS:
        raise ValueError(f"Unknown button kind {kind!r}. Valid kinds: {sorted(BUTTON_KINDS)}")
    widget.setProperty("kind", kind)
    _repolish(widget)


def apply_accent(widget: Any, accent: str) -> None:
    """Tag a QGroupBox (or any QWidget) with a coloured ``accent``.

    Looks up against :data:`GROUPBOX_ACCENTS` so a typo is loud, not
    silent. Sets the ``accent`` dynamic property and re-polishes the
    widget.
    """
    if accent not in GROUPBOX_ACCENTS:
        raise ValueError(f"Unknown groupbox accent {accent!r}. Valid accents: {sorted(GROUPBOX_ACCENTS)}")
    widget.setProperty("accent", accent)
    _repolish(widget)


def clear_kind(widget: Any) -> None:
    """Remove the ``kind`` tag from ``widget`` (revert to default style)."""
    widget.setProperty("kind", None)
    _repolish(widget)


def clear_accent(widget: Any) -> None:
    """Remove the ``accent`` tag from ``widget``."""
    widget.setProperty("accent", None)
    _repolish(widget)
