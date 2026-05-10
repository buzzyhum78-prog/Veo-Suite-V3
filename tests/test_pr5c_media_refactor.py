"""Adversarial test suite for PR-5c (media_tab.py refactor).

Pins down behaviour of the four pure modules lifted out of
`ui/widgets/media_tab.py` plus the structural invariants that keep the
wrappers thin. Mirrors the pattern from PR-5b (`test_pr5b_content_refactor.py`).

Test classes:
  - TestTmediaFilename            (8)  sanitize_filename_strict edge cases
  - TestTmediaTimecode            (8)  format_time_ms arithmetic + types
  - TestTmediaJsonCleaner         (12) clean_json_script + extract_data_from_script
  - TestTmediaCtaLocalization     (10) cta_for_country dispatch + overrides
  - TestTmediaStructuralInvariants (8) AST checks on media_tab.py wrappers
"""

from __future__ import annotations

import ast
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VEO_ROOT = REPO_ROOT / "VeoSuite_V3"
if str(VEO_ROOT) not in sys.path:
    sys.path.insert(0, str(VEO_ROOT))

from modules.media.cta_localization import (  # noqa: E402
    CTA_BY_COUNTRY,
    DEFAULT_CTA,
    cta_for_country,
)
from modules.media.filename import sanitize_filename_strict  # noqa: E402
from modules.media.json_cleaner import (  # noqa: E402
    clean_json_script,
    extract_data_from_script,
)
from modules.media.timecode import format_time_ms  # noqa: E402

MEDIA_TAB_PATH = VEO_ROOT / "ui" / "widgets" / "media_tab.py"


# ---------------------------------------------------------------------------
# filename
# ---------------------------------------------------------------------------


class TestTmediaFilename(unittest.TestCase):
    def test_tm1_1_none_returns_untitled(self):
        self.assertEqual(sanitize_filename_strict(None), "Untitled")

    def test_tm1_2_empty_returns_untitled(self):
        self.assertEqual(sanitize_filename_strict(""), "Untitled")

    def test_tm1_3_zero_is_falsy_returns_untitled(self):
        # Original `if not name` treats 0 / 0.0 / False as falsy.
        self.assertEqual(sanitize_filename_strict(0), "Untitled")

    def test_tm1_4_plain_ascii_preserved(self):
        self.assertEqual(sanitize_filename_strict("My Channel 01"), "My Channel 01")

    def test_tm1_5_windows_forbidden_chars_stripped_not_replaced(self):
        # Strict mode DROPS forbidden chars (vs. content_tab which replaces).
        self.assertEqual(
            sanitize_filename_strict('foo<bar>:"/\\|?*baz'),
            "foobarbaz",
        )

    def test_tm1_6_leading_trailing_whitespace_stripped(self):
        self.assertEqual(sanitize_filename_strict("  hello world  "), "hello world")

    def test_tm1_7_unicode_word_chars_preserved(self):
        # \w in Python regex matches unicode letters by default.
        self.assertEqual(sanitize_filename_strict("Tiêu_Đề 2024"), "Tiêu_Đề 2024")

    def test_tm1_8_non_string_coerced(self):
        # 12345 -> "12345" (digits in \w). int(0) still falls through to Untitled.
        self.assertEqual(sanitize_filename_strict(12345), "12345")


# ---------------------------------------------------------------------------
# timecode
# ---------------------------------------------------------------------------


class TestTmediaTimecode(unittest.TestCase):
    def test_tm2_1_zero(self):
        self.assertEqual(format_time_ms(0), "00:00")

    def test_tm2_2_under_one_second(self):
        self.assertEqual(format_time_ms(999), "00:00")

    def test_tm2_3_one_second_exact(self):
        self.assertEqual(format_time_ms(1000), "00:01")

    def test_tm2_4_one_minute_exact(self):
        self.assertEqual(format_time_ms(60_000), "01:00")

    def test_tm2_5_one_minute_thirty(self):
        self.assertEqual(format_time_ms(90_000), "01:30")

    def test_tm2_6_no_hour_rollover(self):
        # 2 hours exactly -> 120:00, never 02:00:00 (matches original).
        self.assertEqual(format_time_ms(7_200_000), "120:00")

    def test_tm2_7_float_input_truncates(self):
        # 1500.7 ms -> int(1500) -> seconds=1, minutes=0
        self.assertEqual(format_time_ms(1500.7), "00:01")

    def test_tm2_8_padding_width(self):
        # 9 minutes 5 seconds -> 09:05, both fields width 2
        self.assertEqual(format_time_ms(545_000), "09:05")


# ---------------------------------------------------------------------------
# json cleaner
# ---------------------------------------------------------------------------


class TestTmediaJsonCleaner(unittest.TestCase):
    # ---- clean_json_script ------------------------------------------------

    def test_tm3_1_clean_none_returns_empty_string(self):
        self.assertEqual(clean_json_script(None), "")

    def test_tm3_2_clean_empty_returns_empty_string(self):
        self.assertEqual(clean_json_script(""), "")

    def test_tm3_3_clean_picks_voice_text_key(self):
        self.assertEqual(
            clean_json_script('{"voice_text": "Hello world"}'),
            "Hello world",
        )

    def test_tm3_4_clean_priority_voice_text_over_content(self):
        # Key order in fallback list: voice_text > voice > content > script.
        payload = '{"content": "C", "voice_text": "VT"}'
        self.assertEqual(clean_json_script(payload), "VT")

    def test_tm3_5_clean_tolerates_trailing_comma(self):
        self.assertEqual(
            clean_json_script('{"voice_text": "ok",}'),
            "ok",
        )

    def test_tm3_6_clean_strips_markdown_fence_lines(self):
        raw = "```json\nactual narration\n```"
        self.assertEqual(clean_json_script(raw), "actual narration")

    def test_tm3_7_clean_strips_residual_voice_text_key_lines(self):
        raw = '"voice_text": "leftover key"\nReal text here'
        self.assertEqual(clean_json_script(raw), "Real text here")

    # ---- extract_data_from_script -----------------------------------------

    def test_tm3_8_extract_none_returns_none(self):
        self.assertIsNone(extract_data_from_script(None))

    def test_tm3_9_extract_garbage_returns_none(self):
        self.assertIsNone(extract_data_from_script("not json at all"))

    def test_tm3_10_extract_full_payload_aggregates_voice_visuals(self):
        payload = {
            "marketing_kit": {
                "thumbnail_prompt": "cinematic city",
                "thumbnail_text": "WATCH NOW",
            },
            "VISUAL_RULES": {"ratio": "16:9", "style": "noir"},
            "audio_director": {"music_keywords": "lofi chill"},
            "script_board": [
                {"voice_text": "Hello.", "visual_prompt": "scene one"},
                {"voice_text": "World.", "visual_prompt": "scene two"},
            ],
        }
        result = extract_data_from_script(json.dumps(payload))
        self.assertIsNotNone(result)
        self.assertEqual(result["voice"], "Hello.\n\nWorld.")
        self.assertEqual(result["visuals"], ["scene one", "scene two"])
        self.assertEqual(result["music"], "lofi chill")
        self.assertEqual(result["thumb_prompt"], "cinematic city")
        self.assertEqual(result["thumb_text"], "WATCH NOW")
        self.assertEqual(result["visual_ratio"], "16:9")
        self.assertEqual(result["visual_style"], "noir")

    def test_tm3_11_extract_fenced_markdown_payload(self):
        body = '```json\n{"script_board": [{"narration": "Hi"}]}\n```'
        result = extract_data_from_script(body)
        self.assertIsNotNone(result)
        self.assertEqual(result["voice"], "Hi")

    def test_tm3_12_extract_falls_back_marketing_kit_at_root(self):
        # If marketing_kit key is absent entirely, the whole dict is treated
        # as the marketing kit (mk = data fallback).
        payload = {"thumbnail_prompt": "P", "thumbnail_text": "T"}
        result = extract_data_from_script(json.dumps(payload))
        self.assertIsNotNone(result)
        self.assertEqual(result["thumb_prompt"], "P")
        self.assertEqual(result["thumb_text"], "T")


# ---------------------------------------------------------------------------
# CTA localization
# ---------------------------------------------------------------------------


class TestTmediaCtaLocalization(unittest.TestCase):
    def test_tm4_1_default_for_empty(self):
        self.assertEqual(cta_for_country(""), DEFAULT_CTA)

    def test_tm4_2_default_for_none(self):
        self.assertEqual(cta_for_country(None), DEFAULT_CTA)

    def test_tm4_3_us_returns_watch_now(self):
        self.assertEqual(cta_for_country("US"), "WATCH NOW")

    def test_tm4_4_germany_returns_ansehen(self):
        self.assertEqual(cta_for_country("DE"), "ANSEHEN")

    def test_tm4_5_japan_returns_japanese_cta(self):
        self.assertEqual(cta_for_country("JP"), "今すぐ見る")

    def test_tm4_6_substring_match_country_label(self):
        # Substring match: "Germany (DE)" still hits "DE".
        self.assertEqual(cta_for_country("Germany (DE)"), "ANSEHEN")

    def test_tm4_7_vietnam_label_forces_xem_ngay(self):
        # Override branch — VN label triggers the post-loop force.
        self.assertEqual(cta_for_country("Việt Nam"), "XEM NGAY")

    def test_tm4_8_vn_code_forces_xem_ngay(self):
        self.assertEqual(cta_for_country("VN"), "XEM NGAY")

    def test_tm4_9_unknown_country_returns_default(self):
        self.assertEqual(cta_for_country("ZZ"), DEFAULT_CTA)

    def test_tm4_10_map_has_expected_tier1_keys(self):
        # Guard against accidental dict edits that drop tier-1 markets.
        for code in ("US", "GB", "DE", "JP", "VN", "GLOBAL"):
            self.assertIn(code, CTA_BY_COUNTRY)


# ---------------------------------------------------------------------------
# Structural invariants — AST-based regression guard on media_tab.py
# ---------------------------------------------------------------------------


def _find_method(tree: ast.AST, method_name: str) -> ast.FunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            return node
    return None


def _function_count_statements(fn: ast.FunctionDef) -> int:
    body = list(fn.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    return len(body)


def _has_call_to(fn: ast.FunctionDef, callee_name: str) -> bool:
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == callee_name:
                return True
            if isinstance(func, ast.Attribute) and func.attr == callee_name:
                return True
    return False


class TestTmediaStructuralInvariants(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MEDIA_TAB_PATH.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_tm5_1_file_parses(self):
        # If this fails the rest of the suite is meaningless.
        self.assertIsInstance(self.tree, ast.Module)

    def test_tm5_2_imports_pure_helpers(self):
        # Sanity-check: the new pure-helper imports are present.
        expected = [
            "_pure_sanitize_filename_strict",
            "_pure_clean_json_script",
            "_pure_extract_data_from_script",
            "_pure_format_time_ms",
            "_pure_cta_for_country",
        ]
        for name in expected:
            self.assertIn(name, self.source, f"missing import alias: {name}")

    def test_tm5_3_sanitize_wrapper_is_thin(self):
        fn = _find_method(self.tree, "_sanitize_filename")
        self.assertIsNotNone(fn)
        self.assertLessEqual(_function_count_statements(fn), 3)
        self.assertTrue(_has_call_to(fn, "_pure_sanitize_filename_strict"))

    def test_tm5_4_clean_json_wrapper_is_thin(self):
        fn = _find_method(self.tree, "_clean_json_script")
        self.assertIsNotNone(fn)
        self.assertLessEqual(_function_count_statements(fn), 3)
        self.assertTrue(_has_call_to(fn, "_pure_clean_json_script"))

    def test_tm5_5_extract_data_wrapper_is_thin(self):
        fn = _find_method(self.tree, "_extract_data_from_script")
        self.assertIsNotNone(fn)
        self.assertLessEqual(_function_count_statements(fn), 3)
        self.assertTrue(_has_call_to(fn, "_pure_extract_data_from_script"))

    def test_tm5_6_format_time_wrapper_is_thin(self):
        fn = _find_method(self.tree, "format_time")
        self.assertIsNotNone(fn)
        self.assertLessEqual(_function_count_statements(fn), 3)
        self.assertTrue(_has_call_to(fn, "_pure_format_time_ms"))

    def test_tm5_7_no_inline_cta_map_remaining(self):
        # The big inline dict has been replaced with a pure-helper call.
        # Verify the dict literal is gone (heuristic: no key 'WATCH NOW'
        # appears next to a country code in the file).
        self.assertNotIn('"US": "WATCH NOW"', self.source)
        self.assertNotIn('"DE": "ANSEHEN"', self.source)

    def test_tm5_8_composer_merge_calls_cta_helper(self):
        # Every _run_composer_merge body must call _pure_cta_for_country.
        # The class has two copies (snapshot vs. live) of this method —
        # both must delegate to the helper, otherwise drift returns.
        composer_methods = [
            node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_run_composer_merge"
        ]
        self.assertGreaterEqual(len(composer_methods), 1, "no _run_composer_merge found")
        for fn in composer_methods:
            self.assertTrue(
                _has_call_to(fn, "_pure_cta_for_country"),
                f"_run_composer_merge @ line {fn.lineno} does not call _pure_cta_for_country",
            )


if __name__ == "__main__":
    unittest.main()
