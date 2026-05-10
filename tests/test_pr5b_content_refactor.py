"""Adversarial tests for PR-5b — pure helpers extracted from content_tab.py.

These tests pin down the behaviour of the four pure modules that were lifted
out of ``ui/widgets/content_tab.py`` so a future refactor that accidentally
changes the regex, keyword order, or Latin/CJK boundary heuristics fails
immediately::

    QT_QPA_PLATFORM=offscreen python -m pytest tests/test_pr5b_content_refactor.py -v

The class names follow the PR-5 ``TestT{n}{TopicName}`` convention so they
group nicely in the test runner output.
"""

from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "VeoSuite_V3"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ===========================================================================
# Tcontent.1 — file_naming.sanitize_filename
# ===========================================================================
class TestTcontentFileNaming:
    """Pure-helper guardrails for ``modules.content.file_naming``."""

    def test_tc1_1_returns_untitled_for_none(self):
        from modules.content.file_naming import sanitize_filename

        assert sanitize_filename(None) == "Untitled"

    def test_tc1_2_returns_untitled_for_empty_string(self):
        from modules.content.file_naming import sanitize_filename

        assert sanitize_filename("") == "Untitled"

    def test_tc1_3_strips_forbidden_windows_chars(self):
        from modules.content.file_naming import sanitize_filename

        result = sanitize_filename('a/b\\c:d"e<f>g|h?i*j')
        # All forbidden chars must be replaced by underscores → collapsed to
        # single spaces in step 4.
        assert "/" not in result
        assert "\\" not in result
        assert ":" not in result
        assert '"' not in result
        assert "<" not in result
        assert ">" not in result
        assert "|" not in result
        assert "?" not in result
        assert "*" not in result

    def test_tc1_4_collapses_runs_of_whitespace(self):
        from modules.content.file_naming import sanitize_filename

        # Triple-space + tab + newline all collapse to a single space.
        assert sanitize_filename("a   b\tc\nd") == "a b c d"

    def test_tc1_5_truncates_to_fifty_chars(self):
        from modules.content.file_naming import sanitize_filename

        result = sanitize_filename("x" * 200)
        assert len(result) <= 50

    def test_tc1_6_strips_trailing_dot(self):
        # Windows forbids file names ending in "." or " " — the original
        # implementation explicitly handles this with rstrip(". ") as the
        # final step.
        from modules.content.file_naming import sanitize_filename

        assert sanitize_filename("good name.") == "good name"
        assert sanitize_filename("good name. ") == "good name"
        assert sanitize_filename("good name . ") == "good name"

    def test_tc1_7_strips_leading_dot(self):
        from modules.content.file_naming import sanitize_filename

        assert sanitize_filename(".hidden") == "hidden"
        assert sanitize_filename(" .hidden ") == "hidden"

    def test_tc1_8_unicode_preserved(self):
        from modules.content.file_naming import sanitize_filename

        # Vietnamese / Thai / CJK characters are NOT in the Windows
        # forbidden set, so they must survive verbatim.
        assert sanitize_filename("Lịch sử Việt Nam") == "Lịch sử Việt Nam"
        assert sanitize_filename("中国历史") == "中国历史"

    def test_tc1_9_only_forbidden_chars_returns_untitled(self):
        from modules.content.file_naming import sanitize_filename

        # If sanitisation reduces the name to empty / whitespace / dots
        # only, the helper must fall back to "Untitled".
        assert sanitize_filename("...") == "Untitled"
        assert sanitize_filename("   ") == "Untitled"

    def test_tc1_10_coerces_non_string(self):
        from modules.content.file_naming import sanitize_filename

        # The original method does ``str(name).strip()`` — pass an int and
        # confirm we get the stringified value back.
        assert sanitize_filename(42) == "42"


# ===========================================================================
# Tcontent.2 — json_extractor.extract_json_from_text
# ===========================================================================
class TestTcontentJsonExtractor:
    """Pure-helper guardrails for ``modules.content.json_extractor``."""

    def test_tc2_1_returns_none_for_none(self):
        from modules.content.json_extractor import extract_json_from_text

        assert extract_json_from_text(None) is None

    def test_tc2_2_returns_none_for_empty(self):
        from modules.content.json_extractor import extract_json_from_text

        assert extract_json_from_text("") is None

    def test_tc2_3_plain_json_round_trip(self):
        from modules.content.json_extractor import extract_json_from_text

        result = extract_json_from_text('{"key": "value", "n": 42}')
        assert result == {"key": "value", "n": 42}

    def test_tc2_4_strips_markdown_fence_with_lang(self):
        from modules.content.json_extractor import extract_json_from_text

        text = '```json\n{"a": 1}\n```'
        assert extract_json_from_text(text) == {"a": 1}

    def test_tc2_5_strips_markdown_fence_no_lang(self):
        from modules.content.json_extractor import extract_json_from_text

        text = '```\n{"a": 1}\n```'
        assert extract_json_from_text(text) == {"a": 1}

    def test_tc2_6_ignores_chatty_prefix_and_suffix(self):
        from modules.content.json_extractor import extract_json_from_text

        text = 'Sure! Here is your JSON:\n{"a": 1}\nLet me know if you need more.'
        assert extract_json_from_text(text) == {"a": 1}

    def test_tc2_7_strips_inline_double_slash_comments(self):
        from modules.content.json_extractor import extract_json_from_text

        text = '{\n// this is a comment\n"a": 1\n// another\n}'
        assert extract_json_from_text(text) == {"a": 1}

    def test_tc2_8_returns_none_for_garbage(self):
        from modules.content.json_extractor import extract_json_from_text

        assert extract_json_from_text("hello world no braces here") is None
        assert extract_json_from_text("{ truly malformed") is None

    def test_tc2_9_supports_nested_objects(self):
        from modules.content.json_extractor import extract_json_from_text

        text = '{"outer": {"inner": [1, 2, 3]}}'
        assert extract_json_from_text(text) == {"outer": {"inner": [1, 2, 3]}}

    def test_tc2_10_unicode_payload(self):
        from modules.content.json_extractor import extract_json_from_text

        text = '{"title": "Lịch sử Việt Nam", "tag": "ASMR"}'
        assert extract_json_from_text(text) == {"title": "Lịch sử Việt Nam", "tag": "ASMR"}


# ===========================================================================
# Tcontent.3 — safety_filter.apply_safety_filter / process_voice_and_sfx
# ===========================================================================
class TestTcontentSafetyFilter:
    """Pure-helper guardrails for ``modules.content.safety_filter``."""

    def test_tc3_1_empty_returns_empty(self):
        from modules.content.safety_filter import apply_safety_filter

        assert apply_safety_filter("") == ""
        assert apply_safety_filter(None) == ""

    def test_tc3_2_word_boundary_protects_substring(self):
        # "cure" is in the blacklist but "secure" must not be rewritten —
        # the Latin code path uses \b word boundaries.
        from modules.content.safety_filter import apply_safety_filter

        out = apply_safety_filter("This product is secure.")
        assert out == "This product is secure."

    def test_tc3_3_latin_replacement_case_insensitive(self):
        from modules.content.safety_filter import SAFETY_BLACKLIST, apply_safety_filter

        # "cure" → "soothe" — confirm case-insensitive matches.
        assert SAFETY_BLACKLIST["cure"] == "soothe"
        out = apply_safety_filter("Cure CURE cure")
        assert "soothe" in out.lower()
        assert "cure" not in out.lower()

    def test_tc3_4_vietnamese_substring_match(self):
        from modules.content.safety_filter import apply_safety_filter

        # Vietnamese is Latin script — uses word boundaries. "ung thư" →
        # "tổn thương".
        out = apply_safety_filter("Bệnh ung thư rất nguy hiểm.")
        assert "tổn thương" in out
        assert "ung thư" not in out

    def test_tc3_5_chinese_substring_replacement(self):
        from modules.content.safety_filter import apply_safety_filter

        # Chinese uses substring match (no \b). "癌症" → "损伤".
        out = apply_safety_filter("癌症是可怕的。")
        assert "损伤" in out
        assert "癌症" not in out

    def test_tc3_6_thai_substring_replacement(self):
        from modules.content.safety_filter import apply_safety_filter

        # Thai uses substring match. "รักษา" → "บรรเทา".
        out = apply_safety_filter("รักษามะเร็ง")
        assert "บรรเทา" in out
        assert "รักษา" not in out

    def test_tc3_7_longer_keys_replace_first(self):
        # "chữa khỏi" must be replaced before its substring "chữa" would
        # have matched — the helper sorts keys by len, descending.
        from modules.content.safety_filter import apply_safety_filter

        custom = {
            "chữa khỏi": "hỗ trợ giảm",
            "chữa": "chăm sóc",
        }
        out = apply_safety_filter("chữa khỏi bệnh", blacklist=custom)
        # Must be the multi-word replacement, not the single word.
        assert out.startswith("hỗ trợ giảm")
        assert "chăm sóc" not in out

    def test_tc3_8_custom_blacklist_is_isolated(self):
        from modules.content.safety_filter import apply_safety_filter

        # A custom blacklist should override the production one entirely,
        # so other risky tokens are NOT rewritten.
        custom = {"foo": "bar"}
        out = apply_safety_filter("cure foo cancer", blacklist=custom)
        assert out == "cure bar cancer"

    def test_tc3_9_no_change_returns_original(self):
        from modules.content.safety_filter import apply_safety_filter

        # If no token in the blacklist appears, the output equals the
        # input bit-for-bit.
        text = "A perfectly clean sentence about cats."
        assert apply_safety_filter(text) == text

    def test_tc3_10_process_voice_and_sfx_empty(self):
        from modules.content.safety_filter import process_voice_and_sfx

        assert process_voice_and_sfx("") == ("", "")
        assert process_voice_and_sfx(None) == ("", "")

    def test_tc3_11_process_voice_and_sfx_splits_bracketed_cues(self):
        from modules.content.safety_filter import process_voice_and_sfx

        raw = "Hello there. [door creaks] How are you?"
        voice, sfx = process_voice_and_sfx(raw)
        # Voice: cue stripped, cleaned up.
        assert "[door creaks]" not in voice
        assert "Hello there." in voice
        # SFX: cue captured.
        assert "[door creaks]" in sfx

    def test_tc3_12_process_voice_and_sfx_splits_parenthesised_cues(self):
        from modules.content.safety_filter import process_voice_and_sfx

        raw = "She whispered (suspenseful). Then ran."
        voice, sfx = process_voice_and_sfx(raw)
        assert "(suspenseful)" not in voice
        assert "(suspenseful)" in sfx

    def test_tc3_13_process_voice_and_sfx_strips_scene_headers(self):
        # Scene / Cảnh + number must be stripped from voice (they're
        # director-only cues that the TTS should not read aloud).
        from modules.content.safety_filter import process_voice_and_sfx

        raw = "Scene 1: A dark forest.\nCảnh 2. Heavy rain falls."
        voice, _ = process_voice_and_sfx(raw)
        assert not re.search(r"(?i)Scene\s+1", voice)
        assert not re.search(r"(?i)Cảnh\s+2", voice)

    def test_tc3_14_process_voice_and_sfx_collapses_blanks(self):
        from modules.content.safety_filter import process_voice_and_sfx

        raw = "Line A\n\n\n\nLine B"
        voice, _ = process_voice_and_sfx(raw)
        # Empty lines stripped — only two non-empty lines, joined with two
        # newlines (paragraph separator).
        assert voice == "Line A\n\nLine B"


# ===========================================================================
# Tcontent.4 — topic_classifier.classify_tone_by_topic
# ===========================================================================
class TestTcontentToneClassifier:
    """Pure-helper guardrails for ``classify_tone_by_topic``."""

    def test_tc4_1_decoration_row_returns_default(self):
        from modules.content.topic_classifier import (
            DEFAULT_TONE,
            classify_tone_by_topic,
        )

        assert classify_tone_by_topic("--- Format ---") == DEFAULT_TONE

    def test_tc4_2_horror_keyword_wins(self):
        from modules.content.topic_classifier import classify_tone_by_topic

        assert classify_tone_by_topic("Truyện ma đêm khuya") == "Kinh dị (Horror/Creepy)"
        assert classify_tone_by_topic("True crime stories") == "Kinh dị (Horror/Creepy)"

    def test_tc4_3_kids_bedtime_branch(self):
        from modules.content.topic_classifier import classify_tone_by_topic

        # "kids" + bedtime keyword → bedtime tone.
        assert classify_tone_by_topic("Kids bedtime stories") == "Nhẹ nhàng / Ru ngủ (Bedtime Story)"

    def test_tc4_4_kids_playful_branch(self):
        from modules.content.topic_classifier import classify_tone_by_topic

        # "kids" without bedtime → playful tone.
        assert classify_tone_by_topic("Kids toys unboxing") == "Vui tươi / Háo hức (Kids Playful)"

    def test_tc4_5_news_tone(self):
        from modules.content.topic_classifier import classify_tone_by_topic

        assert classify_tone_by_topic("Tin tức showbiz") == "Tin tức (News Anchor)"

    def test_tc4_6_finance_tone(self):
        from modules.content.topic_classifier import classify_tone_by_topic

        assert classify_tone_by_topic("Crypto đầu tư") == "Nghiêm túc (Professional)"

    def test_tc4_7_health_tone(self):
        from modules.content.topic_classifier import classify_tone_by_topic

        assert classify_tone_by_topic("Sức khỏe & dinh dưỡng") == "Y tế / Sức khỏe (Health/Care)"

    def test_tc4_8_history_tone_last_rule_wins(self):
        # Last priority bucket — make sure earlier groups don't accidentally
        # swallow these keywords.
        from modules.content.topic_classifier import classify_tone_by_topic

        assert classify_tone_by_topic("Lịch sử thế giới") == "Kịch tính (Dramatic/Suspense)"

    def test_tc4_9_unknown_topic_returns_default(self):
        from modules.content.topic_classifier import (
            DEFAULT_TONE,
            classify_tone_by_topic,
        )

        assert classify_tone_by_topic("Completely unrelated random topic") == DEFAULT_TONE

    def test_tc4_10_none_returns_default(self):
        from modules.content.topic_classifier import (
            DEFAULT_TONE,
            classify_tone_by_topic,
        )

        assert classify_tone_by_topic(None) == DEFAULT_TONE
        assert classify_tone_by_topic("") == DEFAULT_TONE


# ===========================================================================
# Tcontent.5 — topic_classifier.classify_duration_and_visual
# ===========================================================================
class TestTcontentDurationClassifier:
    """Pure-helper guardrails for ``classify_duration_and_visual``."""

    def test_tc5_1_shorts_forces_short_form(self):
        from modules.content.topic_classifier import classify_duration_and_visual

        # All three short-form platforms force (0, 0) regardless of topic.
        assert classify_duration_and_visual("Youtube Shorts", "history") == (0, 0)
        assert classify_duration_and_visual("TikTok", "sleep") == (0, 0)
        assert classify_duration_and_visual("Instagram Reels", "tech") == (0, 0)

    def test_tc5_2_relax_loop_topic(self):
        from modules.content.topic_classifier import classify_duration_and_visual

        # NHÓM 1 (relax loop) → (5, 2) = 1 Giờ Loop, 100% Stock.
        assert classify_duration_and_visual("Youtube", "lofi music") == (5, 2)
        assert classify_duration_and_visual("Youtube", "Thiền chill") == (5, 2)

    def test_tc5_3_documentary_topic(self):
        from modules.content.topic_classifier import classify_duration_and_visual

        # NHÓM 2 (documentary) → (4, 0) = 20+ phút, Hybrid.
        assert classify_duration_and_visual("Youtube", "vụ án thế kỷ") == (4, 0)
        assert classify_duration_and_visual("Youtube", "World War 2 documentary") == (4, 0)

    def test_tc5_4_horror_topic(self):
        from modules.content.topic_classifier import classify_duration_and_visual

        # NHÓM 3 (horror / fantasy) → (3, 1) = 12-15 phút, 100% AI.
        assert classify_duration_and_visual("Youtube", "alien space mystery") == (3, 1)
        assert classify_duration_and_visual("Youtube", "Truyện ma") == (3, 1)

    def test_tc5_5_finance_topic(self):
        from modules.content.topic_classifier import classify_duration_and_visual

        # NHÓM 4 (finance / tech) → (2, 0) = 8-10 phút, Hybrid.
        assert classify_duration_and_visual("Youtube", "crypto money") == (2, 0)
        assert classify_duration_and_visual("Youtube", "Top 10 tech reviews") == (2, 0)

    def test_tc5_6_news_topic(self):
        from modules.content.topic_classifier import classify_duration_and_visual

        # NHÓM 5 (news) → (1, 2) = 3-5 phút, 100% Stock.
        assert classify_duration_and_visual("Youtube", "tin tức showbiz") == (1, 2)

    def test_tc5_7_default_fallback(self):
        from modules.content.topic_classifier import classify_duration_and_visual

        # Anything that doesn't match any rule → (1, 0) — the safe default.
        assert classify_duration_and_visual("Youtube", "random unrelated topic") == (1, 0)

    def test_tc5_8_facebook_clamps_duration(self):
        from modules.content.topic_classifier import classify_duration_and_visual

        # Facebook + topic that would otherwise return duration > 2 must
        # clamp to 2 (the 8-10 phút bucket).
        d, v = classify_duration_and_visual("Facebook", "history documentary")
        assert d == 2
        # Visual index from the matched rule must NOT change.
        assert v == 0

        d2, v2 = classify_duration_and_visual("Facebook", "lofi music")
        assert d2 == 2
        assert v2 == 2  # Stock from the matched rule survives clamp.

    def test_tc5_9_facebook_does_not_inflate_short_durations(self):
        from modules.content.topic_classifier import classify_duration_and_visual

        # Default fallback is 1 — Facebook clamp only ever shrinks, never
        # extends, so the duration must stay at 1 for unknown topics.
        d, v = classify_duration_and_visual("Facebook", "random topic")
        assert d == 1
        assert v == 0

    def test_tc5_10_none_inputs_use_defaults(self):
        from modules.content.topic_classifier import classify_duration_and_visual

        # None / empty platform + None / empty topic should resolve to the
        # safe defaults without raising.
        assert classify_duration_and_visual(None, None) == (1, 0)
        assert classify_duration_and_visual("", "") == (1, 0)


# ===========================================================================
# Tcontent.6 — content_tab.py structural invariants
# ===========================================================================
class TestTcontentStructuralInvariants:
    """AST-based checks that ContentTab still routes through the pure helpers.

    These tests fail if someone (or a future Devin session) reverts the
    extraction by copy-pasting the original ``_apply_safety_filter`` body
    back into the god-class while leaving the new module in place.
    """

    CONTENT_TAB = Path(__file__).resolve().parents[1] / "VeoSuite_V3" / "ui" / "widgets" / "content_tab.py"

    @classmethod
    def _tree(cls) -> ast.Module:
        return ast.parse(cls.CONTENT_TAB.read_text(encoding="utf-8"))

    def test_tc6_1_file_parses(self):
        # Bare-minimum: the refactored file must still be syntactically
        # valid Python.
        ast.parse(self.CONTENT_TAB.read_text(encoding="utf-8"))

    def test_tc6_2_imports_present(self):
        # The pure helpers must actually be imported into the module so
        # the thin wrappers can call them.
        src = self.CONTENT_TAB.read_text(encoding="utf-8")
        assert "from modules.content.safety_filter" in src
        assert "from modules.content.file_naming" in src
        assert "from modules.content.json_extractor" in src
        assert "from modules.content.topic_classifier" in src

    def _wrapper_body(self, method_name: str) -> list[ast.stmt]:
        tree = self._tree()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "ContentTab":
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == method_name:
                        return item.body
        raise AssertionError(f"Method {method_name!r} not found on ContentTab")

    def test_tc6_3_sanitize_filename_is_thin_wrapper(self):
        # Body must be short (<= 3 statements) and contain a call to the
        # pure helper.
        body = self._wrapper_body("_sanitize_filename")
        assert len(body) <= 3
        src = ast.unparse(ast.Module(body=body, type_ignores=[]))
        assert "_pure_sanitize_filename" in src

    def test_tc6_4_apply_safety_filter_is_thin_wrapper(self):
        # The original body was ~166 lines with the multi-language blacklist
        # inline. After PR-5b it must be a thin wrapper.
        body = self._wrapper_body("_apply_safety_filter")
        assert len(body) <= 3
        src = ast.unparse(ast.Module(body=body, type_ignores=[]))
        assert "_pure_apply_safety_filter" in src

    def test_tc6_5_process_voice_and_sfx_is_thin_wrapper(self):
        body = self._wrapper_body("_process_voice_and_sfx")
        assert len(body) <= 3
        src = ast.unparse(ast.Module(body=body, type_ignores=[]))
        assert "_pure_process_voice_and_sfx" in src

    def test_tc6_6_extract_json_from_text_is_thin_wrapper(self):
        body = self._wrapper_body("extract_json_from_text")
        assert len(body) <= 3
        src = ast.unparse(ast.Module(body=body, type_ignores=[]))
        assert "_pure_extract_json_from_text" in src

    def test_tc6_7_auto_select_tone_routes_through_classifier(self):
        body = self._wrapper_body("auto_select_tone_by_topic")
        src = ast.unparse(ast.Module(body=body, type_ignores=[]))
        # Must call the pure classifier and must NOT contain the long
        # inline keyword chain we lifted out.
        assert "_pure_classify_tone_by_topic" in src
        # Old branches contained "Sang trọng" literal — make sure that
        # massive elif chain is gone.
        assert src.count("elif") <= 1, (
            "auto_select_tone_by_topic still has more than one elif branch — "
            "did the keyword chain leak back in?"
        )

    def test_tc6_8_auto_select_duration_routes_through_classifier(self):
        body = self._wrapper_body("auto_select_duration")
        src = ast.unparse(ast.Module(body=body, type_ignores=[]))
        assert "_pure_classify_duration_and_visual" in src
        assert src.count("elif") <= 1, (
            "auto_select_duration still has more than one elif branch — did the keyword chain leak back in?"
        )
