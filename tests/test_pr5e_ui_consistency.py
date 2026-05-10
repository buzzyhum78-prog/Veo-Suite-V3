"""PR-5e adversarial test suite for the UI-consistency pass.

Background
----------
Before PR-5e each tab (admin_tab.py, publisher_tab.py, ops_tab.py,
editor_tab.py, content_tab.py, media_tab.py, radar_tab.py) called
``widget.setStyleSheet("background: #27ae60; color: white; ...")``
hundreds of times with subtly different colours. The user complaint
that opening *Quản Trị → Ops Center* "feels like a different app"
traced straight back to those drifting inline strings.

PR-5e introduced two semantic helpers in ``ui.style_kit``::

    apply_kind(button,    "primary" | "success" | "warning" | ...)
    apply_accent(groupbox, "emerald" | "lilac"   | "red"     | ...)

…and matching CSS selectors in ``ui/styles.py``. The helpers set a Qt
dynamic property and re-polish the widget so the global stylesheet
takes effect.

What these tests pin down
-------------------------
* The helpers tag the right dynamic property, raise on typos, and
  re-polish without crashing — even if the platform plugin is offscreen
  or the widget is unparented.
* The whitelist constants stay in sync with ``KIND_COLORS`` /
  ``ACCENT_COLORS``.
* Every semantic kind/accent has a corresponding CSS selector in
  ``DARK_THEME_STYLESHEET`` so the property actually paints.
* Every migrated tab imports the helpers and uses them at least N
  times (otherwise the import would silently be dead).
* AST scan caps the number of inline ``setStyleSheet`` calls per tab
  at the post-migration level so future drift fails CI immediately.

The AST budgets below are NOT lower bounds — they're upper bounds on
inline-style call count. Lowering them is a feature; raising them is
a regression unless you justify it in the PR description.
"""

from __future__ import annotations

import ast
import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG_ROOT = os.path.join(REPO_ROOT, "VeoSuite_V3")
if PKG_ROOT not in sys.path:
    sys.path.insert(0, PKG_ROOT)

from ui import styles  # noqa: E402
from ui.style_kit import (  # noqa: E402
    ACCENT_COLORS,
    BUTTON_KINDS,
    GROUPBOX_ACCENTS,
    KIND_COLORS,
    apply_accent,
    apply_kind,
    clear_accent,
    clear_kind,
)

# ---------------------------------------------------------------------------
# Headless Qt fixtures — work without an X server.
# ---------------------------------------------------------------------------

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication, QGroupBox, QPushButton  # noqa: E402

    _QT_AVAILABLE = True
except ImportError:  # pragma: no cover - PyQt6 always installed in CI
    _QT_AVAILABLE = False


def _ensure_qapp():
    """Create a QApplication if one isn't already running."""
    if not _QT_AVAILABLE:
        return None
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    return app


# ---------------------------------------------------------------------------
# Class 1 — style_kit helpers: behavioural contract.
# ---------------------------------------------------------------------------


@unittest.skipUnless(_QT_AVAILABLE, "PyQt6 not available")
class TestTui1StyleKitBehaviour(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _ensure_qapp()

    def test_tui1_1_apply_kind_sets_property(self):
        btn = QPushButton("save")
        apply_kind(btn, "primary")
        self.assertEqual(btn.property("kind"), "primary")

    def test_tui1_2_apply_kind_overwrites_previous(self):
        btn = QPushButton("save")
        apply_kind(btn, "primary")
        apply_kind(btn, "danger")
        self.assertEqual(btn.property("kind"), "danger")

    def test_tui1_3_apply_kind_rejects_unknown(self):
        btn = QPushButton("nope")
        with self.assertRaises(ValueError):
            apply_kind(btn, "neon")
        # Property must not be set on a failed call.
        self.assertIsNone(btn.property("kind"))

    def test_tui1_4_apply_kind_emits_no_stylesheet(self):
        # The whole point: helper must NOT emit an inline stylesheet.
        btn = QPushButton("save")
        apply_kind(btn, "success")
        self.assertEqual(btn.styleSheet(), "")

    def test_tui1_5_apply_kind_handles_unparented_widget(self):
        # Re-polish must survive when widget has no parent / no style.
        btn = QPushButton("orphan")
        try:
            apply_kind(btn, "muted")
        except Exception as exc:  # pragma: no cover - defensive
            self.fail(f"apply_kind raised on unparented widget: {exc!r}")

    def test_tui1_6_apply_accent_sets_property(self):
        grp = QGroupBox("Edge TTS")
        apply_accent(grp, "emerald")
        self.assertEqual(grp.property("accent"), "emerald")

    def test_tui1_7_apply_accent_rejects_unknown(self):
        grp = QGroupBox("Edge TTS")
        with self.assertRaises(ValueError):
            apply_accent(grp, "magenta")
        self.assertIsNone(grp.property("accent"))

    def test_tui1_8_apply_accent_emits_no_stylesheet(self):
        grp = QGroupBox("Edge TTS")
        apply_accent(grp, "lilac")
        self.assertEqual(grp.styleSheet(), "")

    def test_tui1_9_clear_kind_resets(self):
        btn = QPushButton("save")
        apply_kind(btn, "primary")
        clear_kind(btn)
        self.assertIsNone(btn.property("kind"))

    def test_tui1_10_clear_accent_resets(self):
        grp = QGroupBox("Edge TTS")
        apply_accent(grp, "blue")
        clear_accent(grp)
        self.assertIsNone(grp.property("accent"))


# ---------------------------------------------------------------------------
# Class 2 — whitelist invariants.
# ---------------------------------------------------------------------------


class TestTui2Whitelists(unittest.TestCase):
    def test_tui2_1_button_kinds_match_color_table(self):
        self.assertEqual(set(BUTTON_KINDS), set(KIND_COLORS.keys()))

    def test_tui2_2_groupbox_accents_match_color_table(self):
        self.assertEqual(set(GROUPBOX_ACCENTS), set(ACCENT_COLORS.keys()))

    def test_tui2_3_button_kinds_are_lowercase_idents(self):
        for kind in BUTTON_KINDS:
            self.assertRegex(kind, r"^[a-z][a-z_]+$")

    def test_tui2_4_groupbox_accents_are_lowercase_idents(self):
        for accent in GROUPBOX_ACCENTS:
            self.assertRegex(accent, r"^[a-z][a-z_]+$")

    def test_tui2_5_required_kinds_present(self):
        # The seven semantic kinds the migration was built around.
        required = {
            "primary",
            "success",
            "warning",
            "danger",
            "info",
            "muted",
            "ai_magic",
        }
        self.assertTrue(required.issubset(BUTTON_KINDS))

    def test_tui2_6_required_accents_present(self):
        # The seven groupbox accents the migration was built around.
        required = {
            "emerald",
            "lilac",
            "red",
            "amber",
            "blue",
            "slate",
            "cyan",
        }
        self.assertTrue(required.issubset(GROUPBOX_ACCENTS))

    def test_tui2_7_kind_colors_are_hex(self):
        for kind, value in KIND_COLORS.items():
            self.assertRegex(value, r"^#[0-9a-fA-F]{6}$", msg=f"kind={kind!r}")

    def test_tui2_8_accent_colors_are_hex(self):
        for accent, value in ACCENT_COLORS.items():
            self.assertRegex(value, r"^#[0-9a-fA-F]{6}$", msg=f"accent={accent!r}")


# ---------------------------------------------------------------------------
# Class 3 — DARK_THEME_STYLESHEET has selectors for every semantic value.
# ---------------------------------------------------------------------------


class TestTui3StylesheetCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qss = styles.DARK_THEME_STYLESHEET

    def test_tui3_1_qpushbutton_kind_selectors_exist(self):
        for kind in BUTTON_KINDS:
            self.assertIn(
                f'QPushButton[kind="{kind}"]',
                self.qss,
                msg=f"missing selector for kind={kind!r}",
            )

    def test_tui3_2_qpushbutton_kind_hover_selectors_exist(self):
        for kind in BUTTON_KINDS:
            self.assertIn(
                f'QPushButton[kind="{kind}"]:hover',
                self.qss,
                msg=f"missing :hover for kind={kind!r}",
            )

    def test_tui3_3_qgroupbox_accent_selectors_exist(self):
        for accent in GROUPBOX_ACCENTS:
            self.assertIn(
                f'QGroupBox[accent="{accent}"]',
                self.qss,
                msg=f"missing selector for accent={accent!r}",
            )

    def test_tui3_4_qgroupbox_accent_title_recoloured(self):
        for accent in GROUPBOX_ACCENTS:
            self.assertIn(
                f'QGroupBox[accent="{accent}"]::title',
                self.qss,
                msg=f"missing ::title for accent={accent!r}",
            )

    def test_tui3_5_named_object_selectors_present(self):
        # These named-object selectors back the per-tab migrations.
        required_named = [
            "QLabel#hintLabel",
            "QLabel#adminTitleLabel",
            "QLabel#sectionTitleLabel",
            "QTabWidget#adminSubTabs",
            "QScrollArea#transparentScroll",
            "QPushButton#externalLinkButton",
            "QLabel#infoBanner",
            "QFrame#statsCard",
            "QTextEdit#consoleArea",
            "QFrame#editorHeader",
            "QFrame#previewContainer",
            "QScrollArea#contentEditorScroll",
            "QFrame#contentActionBar",
            "QFrame#controlContainer",
            "QFrame#mediaActionBar",
            "QScrollArea#mediaBenchScroll",
        ]
        for sel in required_named:
            self.assertIn(sel, self.qss, msg=f"missing named selector: {sel}")


# ---------------------------------------------------------------------------
# Class 4 — Per-tab structural invariants.
# ---------------------------------------------------------------------------


# Inline-stylesheet budgets — upper bounds. Raising these is a regression.
# Some legitimate inline stylesheets remain for:
#   * Multi-line custom widget styles (Spy panel, header banners).
#   * Dynamic colour states (status indicators that flip green/red at runtime
#     without a corresponding semantic kind/accent).
#   * Plain font-family / font-size tweaks where no semantic concept exists.
TAB_BUDGETS = {
    "VeoSuite_V3/ui/admin_tab.py": 5,
    "VeoSuite_V3/ui/widgets/publisher_tab.py": 3,
    "VeoSuite_V3/ui/widgets/ops_tab.py": 1,
    "VeoSuite_V3/ui/widgets/editor_tab.py": 5,
    "VeoSuite_V3/ui/widgets/content_tab.py": 18,
    "VeoSuite_V3/ui/widgets/media_tab.py": 46,
    "VeoSuite_V3/ui/widgets/radar_tab.py": 32,
}


# Minimum number of apply_kind + apply_accent calls per migrated tab.
# These prove the import isn't dead and protect against future
# "revert to inline" drift.
TAB_MIN_HELPER_CALLS = {
    "VeoSuite_V3/ui/admin_tab.py": 5,
    "VeoSuite_V3/ui/widgets/publisher_tab.py": 3,
    "VeoSuite_V3/ui/widgets/ops_tab.py": 3,
    "VeoSuite_V3/ui/widgets/editor_tab.py": 5,
    "VeoSuite_V3/ui/widgets/content_tab.py": 15,
    "VeoSuite_V3/ui/widgets/media_tab.py": 20,
    "VeoSuite_V3/ui/widgets/radar_tab.py": 15,
}


def _count_setstylesheet_calls(tree: ast.AST) -> int:
    """Count calls of the form ``<expr>.setStyleSheet(...)`` in an AST."""
    count = 0
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "setStyleSheet"
        ):
            count += 1
    return count


def _count_helper_calls(tree: ast.AST) -> int:
    """Count calls of ``apply_kind`` and ``apply_accent`` in an AST."""
    count = 0
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"apply_kind", "apply_accent"}
        ):
            count += 1
    return count


def _imports_style_kit(tree: ast.AST) -> bool:
    """True iff the file imports apply_kind/apply_accent from ui.style_kit."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "ui.style_kit":
            names = {alias.name for alias in node.names}
            if "apply_kind" in names or "apply_accent" in names:
                return True
    return False


class TestTui4TabStructure(unittest.TestCase):
    """One method per tab — fast, individual failure messages."""

    @classmethod
    def setUpClass(cls):
        cls.trees: dict[str, ast.AST] = {}
        for relpath in TAB_BUDGETS:
            abspath = os.path.join(REPO_ROOT, relpath)
            with open(abspath, encoding="utf-8") as f:
                cls.trees[relpath] = ast.parse(f.read(), filename=abspath)

    def _assert_tab(self, relpath: str):
        tree = self.trees[relpath]
        # 4a — file parses (implicit via setUpClass).
        self.assertIsNotNone(tree)

        # 4b — imports style_kit helpers.
        self.assertTrue(
            _imports_style_kit(tree),
            msg=f"{relpath} does not import ui.style_kit",
        )

        # 4c — at least N apply_kind/apply_accent calls.
        helper_calls = _count_helper_calls(tree)
        min_required = TAB_MIN_HELPER_CALLS[relpath]
        self.assertGreaterEqual(
            helper_calls,
            min_required,
            msg=(
                f"{relpath} has {helper_calls} apply_kind/apply_accent calls "
                f"(min required {min_required}). Did someone revert the migration?"
            ),
        )

        # 4d — setStyleSheet call count must not exceed budget.
        inline_calls = _count_setstylesheet_calls(tree)
        budget = TAB_BUDGETS[relpath]
        self.assertLessEqual(
            inline_calls,
            budget,
            msg=(
                f"{relpath} has {inline_calls} inline setStyleSheet calls "
                f"(budget {budget}). Lower the budget if you migrated more; "
                f"otherwise migrate the regression."
            ),
        )

    def test_tui4_1_admin_tab(self):
        self._assert_tab("VeoSuite_V3/ui/admin_tab.py")

    def test_tui4_2_publisher_tab(self):
        self._assert_tab("VeoSuite_V3/ui/widgets/publisher_tab.py")

    def test_tui4_3_ops_tab(self):
        self._assert_tab("VeoSuite_V3/ui/widgets/ops_tab.py")

    def test_tui4_4_editor_tab(self):
        self._assert_tab("VeoSuite_V3/ui/widgets/editor_tab.py")

    def test_tui4_5_content_tab(self):
        self._assert_tab("VeoSuite_V3/ui/widgets/content_tab.py")

    def test_tui4_6_media_tab(self):
        self._assert_tab("VeoSuite_V3/ui/widgets/media_tab.py")

    def test_tui4_7_radar_tab(self):
        self._assert_tab("VeoSuite_V3/ui/widgets/radar_tab.py")


# ---------------------------------------------------------------------------
# Class 5 — End-to-end: a button styled with apply_kind ends up reading
# the global stylesheet's colour through QApplication.
# ---------------------------------------------------------------------------


@unittest.skipUnless(_QT_AVAILABLE, "PyQt6 not available")
class TestTui5StylesheetWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _ensure_qapp()
        cls.app.setStyleSheet(styles.DARK_THEME_STYLESHEET)

    def test_tui5_1_kind_property_visible_via_qss(self):
        # Smoke test: the global stylesheet contains a selector for every
        # kind we ship. We've already proven this in TestTui3 — this test
        # walks the live application stylesheet (which mirrors the source
        # constant) to catch the case where someone forks the QSS at
        # runtime without updating both copies.
        live_qss = self.app.styleSheet()
        for kind in BUTTON_KINDS:
            self.assertIn(
                f'QPushButton[kind="{kind}"]',
                live_qss,
                msg=f"runtime QSS missing selector for kind={kind!r}",
            )

    def test_tui5_2_accent_property_visible_via_qss(self):
        live_qss = self.app.styleSheet()
        for accent in GROUPBOX_ACCENTS:
            self.assertIn(
                f'QGroupBox[accent="{accent}"]',
                live_qss,
                msg=f"runtime QSS missing selector for accent={accent!r}",
            )

    def test_tui5_3_button_round_trip(self):
        # Real-world flow: create a button, tag it via apply_kind, verify
        # the property is queryable through Qt's selector engine.
        btn = QPushButton("Save")
        apply_kind(btn, "success")
        self.assertEqual(btn.property("kind"), "success")
        # Inline stylesheet must remain empty — the cascade comes from app.
        self.assertEqual(btn.styleSheet(), "")

    def test_tui5_4_groupbox_round_trip(self):
        grp = QGroupBox("Edge TTS")
        apply_accent(grp, "emerald")
        self.assertEqual(grp.property("accent"), "emerald")
        self.assertEqual(grp.styleSheet(), "")


if __name__ == "__main__":  # pragma: no cover - manual run helper
    unittest.main(verbosity=2)
