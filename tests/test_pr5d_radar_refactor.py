"""PR-5d adversarial test suite for ui/widgets/radar_tab.py refactor.

Pins down the behaviour of the pure modules that were lifted out of
RadarTab in PR-5d:

* modules/radar/history_store.py        (production_log persistence)
* modules/radar/text_normalizers.py     (label clean-up helpers)
* modules/radar/intent_strategy.py      (intent_hint + strict/semi/free)

Plus a structural-invariant class (TestTradarStructuralInvariants) that
uses ``ast`` to walk radar_tab.py and confirm:

* It still parses.
* It imports each pure helper.
* The wrapper methods are thin (≤ 3 statements).
* The previously-inlined ``cta_map`` / ``intent_hint`` / nested helper
  blocks are gone.
* ``check_production_history`` / ``log_production_history`` call the
  pure helpers (so future drift fails CI here, not at runtime).

The tests intentionally exercise edge cases (None, empty string, unicode,
missing keys, corrupt JSON, non-dict payloads, hour rollover for…
oh wait that's PR-5c, never mind) so that future refactors can't quietly
relax invariants.
"""

from __future__ import annotations

import ast
import datetime
import json
import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG_ROOT = os.path.join(REPO_ROOT, "VeoSuite_V3")
if PKG_ROOT not in sys.path:
    sys.path.insert(0, PKG_ROOT)

from modules.radar.history_store import (  # noqa: E402
    HISTORY_PATH,
    check_topic_history,
    load_history,
    make_history_key,
    record_topic_history,
    save_history,
)
from modules.radar.intent_strategy import (  # noqa: E402
    DEFAULT_INTENT_HINT,
    FREE_RULE,
    INTENT_RULES,
    SEMI_RULE,
    SEMI_TOPICS,
    STRICT_RULE,
    STRICT_TOPICS,
    classify_intent,
    classify_topic_strictness,
    rule_for_strictness,
)
from modules.radar.text_normalizers import (  # noqa: E402
    clean_input_string,
    clean_staging_topic,
    clean_topic_name,
)


# ============================================================================
# Tradar.1 — history_store
# ============================================================================
class TestTradarHistoryStore(unittest.TestCase):
    def test_tr1_1_make_key_underscore_separator(self):
        self.assertEqual(make_history_key("Rain", "VN"), "Rain_VN")

    def test_tr1_2_make_key_preserves_spaces(self):
        # Original code did not normalise — round-trip must match the
        # existing on-disk format.
        self.assertEqual(
            make_history_key("Rain on Roof", "Hoa Kỳ"),
            "Rain on Roof_Hoa Kỳ",
        )

    def test_tr1_3_load_history_missing_returns_empty(self):
        self.assertEqual(load_history("/nonexistent/path/xyz.json"), {})

    def test_tr1_4_load_history_corrupt_returns_empty(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            f.write("not json {{{")
            path = f.name
        try:
            self.assertEqual(load_history(path), {})
        finally:
            os.unlink(path)

    def test_tr1_5_load_history_non_dict_payload_returns_empty(self):
        # Defensive: original code assumed dict; if someone wrote a list,
        # we should not explode.
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(["not", "a", "dict"], f)
            path = f.name
        try:
            self.assertEqual(load_history(path), {})
        finally:
            os.unlink(path)

    def test_tr1_6_check_absent_returns_false_none(self):
        self.assertEqual(check_topic_history({}, "X", "Y"), (False, None))

    def test_tr1_7_check_present_returns_true_and_date(self):
        h = {"X_Y": {"date": "2025-01-02 03:04:05", "status": "Created"}}
        self.assertEqual(check_topic_history(h, "X", "Y"), (True, "2025-01-02 03:04:05"))

    def test_tr1_8_check_present_no_date_field_returns_true_none(self):
        # Defensive: original would have raised KeyError. We soften.
        h = {"X_Y": {"status": "Created"}}
        self.assertEqual(check_topic_history(h, "X", "Y"), (True, None))

    def test_tr1_9_check_present_non_dict_entry_returns_true_none(self):
        h = {"X_Y": "anything"}
        self.assertEqual(check_topic_history(h, "X", "Y"), (True, None))

    def test_tr1_10_record_stamps_and_mutates(self):
        fixed = datetime.datetime(2025, 7, 4, 12, 34, 56)
        h: dict = {}
        out = record_topic_history(h, "Topic", "VN", now=fixed)
        # Returns same dict (mutated in place).
        self.assertIs(out, h)
        self.assertEqual(h["Topic_VN"], {"date": "2025-07-04 12:34:56", "status": "Created"})

    def test_tr1_11_record_overwrites_existing(self):
        fixed = datetime.datetime(2030, 1, 1, 0, 0, 0)
        h = {"K_C": {"date": "OLD", "status": "Created"}}
        record_topic_history(h, "K", "C", now=fixed)
        self.assertEqual(h["K_C"]["date"], "2030-01-01 00:00:00")

    def test_tr1_12_save_then_load_roundtrip(self):
        # End-to-end round trip including dir creation.
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "subdir", "log.json")
            payload = {"K_C": {"date": "2025-05-05 05:05:05", "status": "Created"}}
            save_history(payload, path)
            self.assertTrue(os.path.exists(path))
            self.assertEqual(load_history(path), payload)

    def test_tr1_13_save_handles_unicode(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "log.json")
            payload = {"Lịch sử_Việt Nam": {"date": "2025-01-01 00:00:00", "status": "Created"}}
            save_history(payload, path)
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read()
            # ensure_ascii=False means unicode survives unescaped.
            self.assertIn("Việt Nam", raw)

    def test_tr1_14_default_history_path_constant(self):
        self.assertEqual(HISTORY_PATH, os.path.join("VEO_DB", "production_log.json"))


# ============================================================================
# Tradar.2 — text_normalizers
# ============================================================================
class TestTradarTextNormalizers(unittest.TestCase):
    # ---------- clean_input_string ----------
    def test_tr2_1_clean_input_drops_divider(self):
        self.assertEqual(clean_input_string("--- HOT TOPICS ---"), "")

    def test_tr2_2_clean_input_strips_emoji(self):
        self.assertEqual(clean_input_string("🌊 Ocean & Water (Sóng nước)"), "Ocean & Water")

    def test_tr2_3_clean_input_preserves_comma_and_amp(self):
        self.assertEqual(clean_input_string("Tech, AI & Coding"), "Tech, AI & Coding")

    def test_tr2_4_clean_input_none_returns_empty(self):
        self.assertEqual(clean_input_string(None), "")

    def test_tr2_5_clean_input_no_parens_no_emoji(self):
        self.assertEqual(clean_input_string("History"), "History")

    def test_tr2_6_clean_input_preserves_vietnamese_word_chars(self):
        # \w includes unicode word chars, so Vietnamese accents survive.
        self.assertEqual(clean_input_string("Lịch sử"), "Lịch sử")

    # ---------- clean_topic_name ----------
    def test_tr2_7_topic_name_falsy_returns_general(self):
        self.assertEqual(clean_topic_name(""), "General")
        self.assertEqual(clean_topic_name(None), "General")

    def test_tr2_8_topic_name_divider_returns_general(self):
        self.assertEqual(clean_topic_name("--- HOT ---"), "General")

    def test_tr2_9_topic_name_strips_leading_emoji(self):
        self.assertEqual(clean_topic_name("🎯 Finance"), "Finance")

    def test_tr2_10_topic_name_strips_parens(self):
        self.assertEqual(clean_topic_name("Finance (Tài chính)"), "Finance")

    def test_tr2_11_topic_name_leading_amp_stripped(self):
        # clean_topic_name's regex is r'^[^\w\s]*' which strips leading &.
        # (clean_staging_topic uses r'^[^\w\s&,]*' which preserves it.)
        self.assertEqual(clean_topic_name("& Co"), "Co")

    # ---------- clean_staging_topic ----------
    def test_tr2_12_staging_falsy_returns_general(self):
        self.assertEqual(clean_staging_topic(""), "General")
        self.assertEqual(clean_staging_topic(None), "General")

    def test_tr2_13_staging_strips_leading_emoji_keeps_amp(self):
        self.assertEqual(clean_staging_topic("🎯 Finance & Crypto"), "Finance & Crypto")

    def test_tr2_14_staging_strips_parens(self):
        self.assertEqual(clean_staging_topic("Cooking (Nấu ăn)"), "Cooking")


# ============================================================================
# Tradar.3 — intent_strategy
# ============================================================================
class TestTradarIntentStrategy(unittest.TestCase):
    def test_tr3_1_default_for_general(self):
        self.assertEqual(classify_intent("General"), DEFAULT_INTENT_HINT)

    def test_tr3_2_default_for_empty(self):
        self.assertEqual(classify_intent(""), DEFAULT_INTENT_HINT)

    def test_tr3_3_default_for_none(self):
        self.assertEqual(classify_intent(None), DEFAULT_INTENT_HINT)

    def test_tr3_4_rain_match_sleep_aid(self):
        self.assertIn("Sleep Aid", classify_intent("Rain on Roof"))

    def test_tr3_5_finance_match(self):
        self.assertIn("Wealth Mindset", classify_intent("Finance & Crypto"))

    def test_tr3_6_history_match(self):
        self.assertIn("Forgotten Empires", classify_intent("Ancient History"))

    def test_tr3_7_first_match_wins(self):
        # "history" matches the History rule even with "tech" present
        # because History is declared earlier in INTENT_RULES.
        ts = "history tech"
        self.assertIn("Forgotten Empires", classify_intent(ts))

    def test_tr3_8_case_insensitive(self):
        self.assertIn("Sleep Aid", classify_intent("MEDITATION"))

    def test_tr3_9_strictness_news_is_strict(self):
        self.assertEqual(classify_topic_strictness("News, Tin tức"), "strict")

    def test_tr3_10_strictness_podcast_is_semi(self):
        self.assertEqual(classify_topic_strictness("Podcast"), "semi")

    def test_tr3_11_strictness_horror_is_free(self):
        self.assertEqual(classify_topic_strictness("Horror"), "free")

    def test_tr3_12_strictness_strict_wins_over_semi(self):
        # If both strict and semi keywords are present, strict wins.
        self.assertEqual(classify_topic_strictness("News, Podcast"), "strict")

    def test_tr3_13_strictness_none_is_free(self):
        self.assertEqual(classify_topic_strictness(None), "free")

    def test_tr3_14_rule_for_strict(self):
        self.assertEqual(rule_for_strictness("strict"), STRICT_RULE)
        self.assertIn("STRICT TRUTH POLICY", rule_for_strictness("strict"))

    def test_tr3_15_rule_for_semi(self):
        self.assertEqual(rule_for_strictness("semi"), SEMI_RULE)
        self.assertIn("AUTHENTICITY POLICY", rule_for_strictness("semi"))

    def test_tr3_16_rule_for_free(self):
        self.assertEqual(rule_for_strictness("free"), FREE_RULE)
        self.assertIn("CREATIVE FREEDOM", rule_for_strictness("free"))

    def test_tr3_17_rule_for_unknown_defaults_to_free(self):
        # Defensive: an unknown level falls through to FREE.
        self.assertEqual(rule_for_strictness("nonsense"), FREE_RULE)

    def test_tr3_18_intent_rules_table_size(self):
        # Pin the table size — adding a rule must come with a test update
        # so reviewers notice.
        self.assertEqual(len(INTENT_RULES), 8)

    def test_tr3_19_strict_topics_list_size(self):
        # 18 strict topics in the original (English + Vietnamese pairs).
        self.assertEqual(len(STRICT_TOPICS), 18)

    def test_tr3_20_semi_topics_list_size(self):
        self.assertEqual(len(SEMI_TOPICS), 8)


# ============================================================================
# Tradar.4 — structural invariants on radar_tab.py
# ============================================================================
def _function_count_statements(node: ast.FunctionDef) -> int:
    # Counts top-level statements in the function body, ignoring docstrings.
    body = list(node.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    return len(body)


def _has_call_to(node: ast.AST, name: str) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            fn = child.func
            if isinstance(fn, ast.Name) and fn.id == name:
                return True
            if isinstance(fn, ast.Attribute) and fn.attr == name:
                return True
    return False


def _find_method(tree: ast.AST, class_name: str, method_name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return item
    raise AssertionError(f"{class_name}.{method_name} not found")


class TestTradarStructuralInvariants(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = os.path.join(REPO_ROOT, "VeoSuite_V3", "ui", "widgets", "radar_tab.py")
        with open(cls.path, "r", encoding="utf-8") as f:
            cls.source = f.read()
        cls.tree = ast.parse(cls.source, filename=cls.path)

    def test_tr4_1_file_parses(self):
        # If this fails the rest of the suite is meaningless.
        self.assertIsInstance(self.tree, ast.Module)

    def test_tr4_2_imports_pure_helpers(self):
        for name in (
            "_pure_load_history",
            "_pure_save_history",
            "_pure_check_topic_history",
            "_pure_record_topic_history",
            "_PURE_HISTORY_PATH",
            "_pure_clean_input_string",
            "_pure_clean_topic_name",
            "_pure_clean_staging_topic",
            "_pure_classify_intent",
            "_pure_classify_topic_strictness",
            "_pure_rule_for_strictness",
        ):
            self.assertIn(name, self.source, f"{name} missing from radar_tab.py imports")

    def test_tr4_3_check_production_history_is_thin(self):
        fn = _find_method(self.tree, "RadarTab", "check_production_history")
        self.assertLessEqual(_function_count_statements(fn), 3)
        self.assertTrue(_has_call_to(fn, "_pure_load_history"))
        self.assertTrue(_has_call_to(fn, "_pure_check_topic_history"))

    def test_tr4_4_log_production_history_is_thin(self):
        fn = _find_method(self.tree, "RadarTab", "log_production_history")
        self.assertLessEqual(_function_count_statements(fn), 3)
        self.assertTrue(_has_call_to(fn, "_pure_load_history"))
        self.assertTrue(_has_call_to(fn, "_pure_record_topic_history"))
        self.assertTrue(_has_call_to(fn, "_pure_save_history"))

    def test_tr4_5_real_update_prompt_uses_pure_helpers(self):
        fn = _find_method(self.tree, "RadarTab", "_real_update_prompt")
        # Must call all 3 prompt-side helpers.
        for helper in (
            "_pure_clean_input_string",
            "_pure_classify_intent",
            "_pure_classify_topic_strictness",
            "_pure_rule_for_strictness",
        ):
            self.assertTrue(
                _has_call_to(fn, helper),
                f"_real_update_prompt no longer calls {helper}",
            )

    def test_tr4_6_no_inline_intent_table_remaining(self):
        # The original code had `elif "tech" in ts or "ai" in ts`
        # — that exact pattern must be gone now.
        self.assertNotIn('"tech" in ts or "ai" in ts', self.source)

    def test_tr4_7_no_inline_strict_topics_list_remaining(self):
        # Bài bản strict_topics literal had "Bất động sản" — if it's still
        # inline we know the lift didn't take.
        self.assertNotIn(
            'strict_topics = ["News", "Tin tức"',
            self.source,
        )

    def test_tr4_8_run_channel_planning_uses_pure_helper(self):
        fn = _find_method(self.tree, "RadarTab", "run_channel_planning")
        self.assertTrue(_has_call_to(fn, "_pure_clean_topic_name"))

    def test_tr4_9_transfer_staging_uses_pure_helper(self):
        # Two transfer_staging_to_factory definitions exist (Tab 3 vs.
        # Tab 5 staging table). At least one must delegate.
        found = False
        for node in ast.walk(self.tree):
            if (
                isinstance(node, ast.FunctionDef)
                and node.name == "transfer_staging_to_factory"
                and _has_call_to(node, "_pure_clean_staging_topic")
            ):
                found = True
                break
        self.assertTrue(
            found,
            "no transfer_staging_to_factory calls _pure_clean_staging_topic",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
