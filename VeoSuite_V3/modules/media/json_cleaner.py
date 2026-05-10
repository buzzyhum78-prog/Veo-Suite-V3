"""Pure JSON-script helpers extracted from ui/widgets/media_tab.py.

The Media tab consumes two flavours of LLM output:
  * ``_clean_json_script`` — takes raw model output (possibly wrapped in
    ```json fences``` or a chatty JSON-like payload) and returns just the
    narration text. Used when re-importing a script into the voice
    panel.
  * ``_extract_data_from_script`` — parses a full multi-section JSON
    "scriptboard" emitted by the AI Content writer and returns a flat
    dict of ``voice / music / thumb_prompt / thumb_text / visuals /
    visual_ratio / visual_style`` for downstream production steps.

Both are pure: no Qt, no IO. They tolerate malformed input by returning
empty strings / ``None`` rather than raising — the upstream UI logs the
miss and skips the auto-fill step.
"""

from __future__ import annotations

import json
import re
from typing import Any

__all__ = ["clean_json_script", "extract_data_from_script"]


def clean_json_script(raw_text) -> str:
    """Strip JSON noise from a raw model output and return narration text.

    Behaviour preserved verbatim from `MediaTab._clean_json_script`:
      1. Falsy / None input -> ``""``.
      2. ``str(raw_text).strip()``.
      3. If the payload contains both ``{`` and ``}``, try to parse it as
         JSON (after a tolerant trailing-comma fix: ``", }" -> "}"``).
         If parsing succeeds, return the first match from these keys in
         order: ``voice_text``, ``voice``, ``content``, ``script``.
      4. Otherwise fall back to line-based cleanup: drop lines containing
         ``` ``` ``` (markdown fence) and lines with ``"voice_text":``,
         then join with newlines and strip.
    """
    if not raw_text:
        return ""
    text_str = str(raw_text).strip()

    try:
        if "{" in text_str and "}" in text_str:
            text_str_norm = re.sub(r",\s*}", "}", text_str)
            data = json.loads(text_str_norm)
            for key in ("voice_text", "voice", "content", "script"):
                if key in data:
                    return str(data[key])
    except Exception:
        # JSON malformed — fall through to plain-text cleanup.
        pass

    lines = text_str.split("\n")
    clean_lines = []
    for line in lines:
        if "```" in line:
            continue
        if '"voice_text":' in line:
            continue
        clean_lines.append(line)
    return "\n".join(clean_lines).strip()


def extract_data_from_script(raw_text) -> dict[str, Any] | None:
    """Parse an AI Content scriptboard JSON into a flat MediaTab payload.

    Behaviour preserved verbatim from `MediaTab._extract_data_from_script`:
      * Falsy / None -> ``None``.
      * Strip markdown ```json``` fences if present. Else if the payload
        contains ``{`` and ``}``, slice from first ``{`` to last ``}``.
      * ``json.loads`` on the candidate. Any exception -> log and return
        ``None``. (Caller catches the ``None`` and surfaces it.)
      * Return dict with keys (always present, defaults to ``""`` or
        ``[]``): ``voice``, ``music``, ``thumb_prompt``, ``thumb_text``,
        ``visuals`` (list), ``visual_ratio``, ``visual_style``.
      * Aggregation rules:
        - ``visual_ratio``: ``VISUAL_RULES.ratio`` else
          ``VISUAL_CONTROLLER.Settings.ratio`` else ``Ratio`` key in
          either; first non-empty wins.
        - Marketing kit may sit at root level if a ``marketing_kit`` key
          is absent. ``thumb_prompt = mk.thumbnail_prompt``,
          ``thumb_text = mk.thumbnail_text``.
        - Music keyword: ``audio_director.music_keywords`` else
          ``music_mood`` else ``layer_2_music_search`` else
          ``audio_engineer_recipe.*`` (same fallback chain).
        - Voice + visuals: iterate over ``script_board`` else ``scenes``;
          concat ``voice_text``/``narration`` with double-newlines,
          collect ``visual_prompt``/``visual_desc`` (newlines collapsed
          to spaces) into ``visuals``.
        - Visual style: ``visual_identity.style_preset`` else
          ``VISUAL_RULES.style`` else ``VISUAL_RULES.Art_Style``.
    """
    if not raw_text:
        return None
    try:
        json_str = raw_text
        if "```json" in raw_text:
            json_str = raw_text.split("```json")[1].split("```")[0].strip()
        elif "{" in raw_text:
            start = raw_text.find("{")
            end = raw_text.rfind("}") + 1
            json_str = raw_text[start:end]

        data = json.loads(json_str)

        result: dict[str, Any] = {
            "voice": "",
            "music": "",
            "thumb_prompt": "",
            "thumb_text": "",
            "visuals": [],
            "visual_ratio": "",
        }

        vr = data.get("VISUAL_RULES", {}) or data.get("VISUAL_CONTROLLER", {}).get("Settings", {})
        result["visual_ratio"] = vr.get("ratio", "") or vr.get("Ratio", "")

        mk = data.get("marketing_kit", {})
        if not mk and "marketing_kit" not in data:
            mk = data
        result["thumb_prompt"] = mk.get("thumbnail_prompt", "")
        result["thumb_text"] = mk.get("thumbnail_text", "")

        ad = data.get("audio_director", {}) or data.get("audio_engineer_recipe", {})
        music = ad.get("music_keywords", "") or ad.get("music_mood", "") or ad.get("layer_2_music_search", "")
        result["music"] = music

        sb = data.get("script_board", []) or data.get("scenes", [])
        voice_acc = ""
        for scene in sb:
            txt = scene.get("voice_text", "") or scene.get("narration", "")
            if txt:
                voice_acc += f"{txt}\n\n"

            vis = scene.get("visual_prompt", "") or scene.get("visual_desc", "")
            if vis:
                result["visuals"].append(vis.replace("\n", " ").strip())

        result["voice"] = voice_acc.strip()

        style = ""
        if "visual_identity" in data:
            style = data["visual_identity"].get("style_preset", "")
        if not style:
            style = vr.get("style", "") or vr.get("Art_Style", "")
        result["visual_style"] = style

        return result

    except Exception as e:
        # Preserved verbatim — the original code prints to stdout.
        print(f"Lỗi parse JSON trong MediaTab: {e}")
        return None
