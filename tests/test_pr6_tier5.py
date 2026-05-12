"""
PR-6 — Adversarial test suite for Tier 5 features.

Five test classes, each owning one subsystem so a regression in one
area cannot mask failures in the others:

* **T6.1 Plugin system**  — manifest validation, discovery, lifecycle
  isolation, duplicate-name detection.
* **T6.2 Telemetry**      — opt-in default, JSONL append, rotation,
  payload coercion, thread safety, malformed-line tolerance.
* **T6.3 i18n**           — language switching, missing key fallback,
  format-string safety, pluralisation, supported-language whitelist.
* **T6.4 Font bundle**    — discovery, coverage summary, behaviour
  against an empty directory, REQUIRED_FONTS schema.
* **T6.5 Dashboard tab**  — pure KPI helper, headless construction,
  optional dependency handling, integration with MainWindow stack.

Every test under T6.5 that touches QWidget is guarded by a single
``QApplication`` set up in ``setUpClass`` and skipped if PyQt6 is not
importable so the suite can run on lint-only CI hosts.
"""

from __future__ import annotations

import ast
import json
import os
import tempfile
import textwrap
import threading
import time
import unittest
from pathlib import Path

try:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    _QT_AVAILABLE = True
except ImportError:  # pragma: no cover
    _QT_AVAILABLE = False


REPO_ROOT = Path(__file__).resolve().parent.parent
import sys

sys.path.insert(0, str(REPO_ROOT / "VeoSuite_V3"))

# Imports kept here (not at top) so a missing PyQt6 on a stripped-down
# CI host doesn't break the whole module — the @skipUnless guards on
# T6.5 take care of that case explicitly.
from modules.plugins import Plugin, PluginLoadError, PluginManager, PluginMetadata  # noqa: E402
from services import font_bundle, telemetry  # noqa: E402
from utils import i18n  # noqa: E402


def _qapp() -> QApplication | None:
    if not _QT_AVAILABLE:
        return None
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---------------------------------------------------------------------------
# T6.1 — Plugin system
# ---------------------------------------------------------------------------


class _DummyPlugin(Plugin):
    """In-line plugin used by tests that don't want to write to disk."""

    @classmethod
    def metadata(cls) -> PluginMetadata:
        return PluginMetadata(name="dummy", version="1.0.0")


class _CrashPlugin(Plugin):
    @classmethod
    def metadata(cls) -> PluginMetadata:
        return PluginMetadata(name="crashy", version="0.1.0")

    def on_app_start(self, context):
        raise RuntimeError("synthetic plugin failure")


class TestT6_1_PluginSystem(unittest.TestCase):
    def test_t61_1_metadata_rejects_bad_name(self):
        with self.assertRaises(ValueError):
            PluginMetadata(name="With Spaces", version="1.0.0")
        with self.assertRaises(ValueError):
            PluginMetadata(name="../escape", version="1.0.0")
        with self.assertRaises(ValueError):
            PluginMetadata(name="", version="1.0.0")

    def test_t61_2_metadata_rejects_bad_version(self):
        with self.assertRaises(ValueError):
            PluginMetadata(name="ok", version="1.0")
        with self.assertRaises(ValueError):
            PluginMetadata(name="ok", version="latest")

    def test_t61_3_metadata_rejects_unknown_hook(self):
        with self.assertRaises(ValueError):
            PluginMetadata(name="ok", version="1.0.0", hooks=("on_app_typo",))

    def test_t61_4_metadata_accepts_known_hooks(self):
        meta = PluginMetadata(name="ok", version="1.0.0", hooks=("on_app_start", "on_app_shutdown"))
        self.assertEqual(meta.hooks, ("on_app_start", "on_app_shutdown"))

    def test_t61_5_metadata_is_frozen(self):
        from dataclasses import FrozenInstanceError

        meta = PluginMetadata(name="ok", version="1.0.0")
        with self.assertRaises(FrozenInstanceError):
            meta.name = "renamed"  # type: ignore[misc]

    def test_t61_6_manager_discovery_skips_dunder_files(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / "__init__.py").write_text("# sentinel")
            (base / "_private.py").write_text(
                "from modules.plugins import Plugin, PluginMetadata\n"
                "class P(Plugin):\n"
                "    @classmethod\n"
                "    def metadata(cls):\n"
                "        return PluginMetadata(name='private', version='1.0.0')\n"
            )
            mgr = PluginManager(plugin_dirs=[base])
            files = mgr.discover()
            self.assertTrue(all(not p.name.startswith("__") for p in files))

    def test_t61_7_manager_loads_valid_plugin_from_disk(self):
        plugin_src = textwrap.dedent(
            """
            from modules.plugins import Plugin, PluginMetadata
            class MyP(Plugin):
                @classmethod
                def metadata(cls):
                    return PluginMetadata(name='good', version='1.0.0',
                                          description='ok', hooks=('on_app_start',))
            """
        )
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "good_plugin.py"
            path.write_text(plugin_src)
            mgr = PluginManager(plugin_dirs=[Path(d)])
            loaded, errors = mgr.load_all()
            self.assertEqual(loaded, 1)
            self.assertEqual(errors, [])
            self.assertEqual(len(mgr.metadata_list()), 1)
            self.assertEqual(mgr.metadata_list()[0].name, "good")

    def test_t61_8_manager_rejects_module_with_no_plugin(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "no_plugin.py"
            path.write_text("x = 42\n")
            mgr = PluginManager(plugin_dirs=[Path(d)])
            with self.assertRaises(PluginLoadError):
                mgr.load(path)

    def test_t61_9_manager_rejects_duplicate_name(self):
        src = (
            "from modules.plugins import Plugin, PluginMetadata\n"
            "class P(Plugin):\n"
            "    @classmethod\n"
            "    def metadata(cls):\n"
            "        return PluginMetadata(name='same', version='1.0.0')\n"
        )
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "p1.py").write_text(src)
            (Path(d) / "p2.py").write_text(src)
            mgr = PluginManager(plugin_dirs=[Path(d)])
            loaded, errors = mgr.load_all()
            self.assertEqual(loaded, 1)
            self.assertEqual(len(errors), 1)
            self.assertIn("Duplicate", errors[0][1])

    def test_t61_10_manager_isolates_plugin_exceptions(self):
        mgr = PluginManager()
        mgr._loaded.append(  # type: ignore[attr-defined]
            type(
                "_E",
                (),
                {
                    "instance": _CrashPlugin(),
                    "metadata": _CrashPlugin.metadata(),
                    "path": Path("/dev/null"),
                },
            )()
        )
        mgr._by_name["crashy"] = mgr._loaded[-1]  # type: ignore[attr-defined]
        ok, errs = mgr.start({})
        self.assertEqual(ok, 0)
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0][0], "crashy")

    def test_t61_11_builtin_sample_plugin_is_discoverable(self):
        builtin_dir = REPO_ROOT / "VeoSuite_V3" / "modules" / "plugins" / "builtin"
        mgr = PluginManager(plugin_dirs=[builtin_dir])
        loaded, errors = mgr.load_all()
        self.assertGreaterEqual(loaded, 1)
        names = {m.name for m in mgr.metadata_list()}
        self.assertIn("sample-logger", names)
        self.assertEqual(errors, [])

    def test_t61_12_shutdown_runs_in_reverse_load_order(self):
        order: list[str] = []

        class _A(Plugin):
            @classmethod
            def metadata(cls):
                return PluginMetadata(name="alpha", version="1.0.0")

            def on_app_shutdown(self, ctx):
                order.append("alpha")

        class _B(Plugin):
            @classmethod
            def metadata(cls):
                return PluginMetadata(name="bravo", version="1.0.0")

            def on_app_shutdown(self, ctx):
                order.append("bravo")

        mgr = PluginManager()
        for cls in (_A, _B):
            entry = type(
                "_E",
                (),
                {
                    "instance": cls(),
                    "metadata": cls.metadata(),
                    "path": Path(f"/tmp/{cls.metadata().name}.py"),
                },
            )()
            mgr._loaded.append(entry)  # type: ignore[attr-defined]
            mgr._by_name[cls.metadata().name] = entry  # type: ignore[attr-defined]
        mgr.shutdown({})
        # B loaded last, must shut down first.
        self.assertEqual(order, ["bravo", "alpha"])


# ---------------------------------------------------------------------------
# T6.2 — Telemetry
# ---------------------------------------------------------------------------


class TestT6_2_Telemetry(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "events.jsonl"

    def tearDown(self):
        self._tmp.cleanup()

    def test_t62_1_default_is_disabled(self):
        sink = telemetry.TelemetrySink(path=self.path)
        self.assertFalse(sink.enabled)
        self.assertFalse(sink.record("feature_used"))
        self.assertFalse(self.path.exists())

    def test_t62_2_enabled_records_event(self):
        sink = telemetry.TelemetrySink(path=self.path, enabled=True)
        self.assertTrue(sink.record("feature_used", name="dashboard"))
        events = sink.read_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "feature_used")
        self.assertEqual(events[0]["payload"]["name"], "dashboard")

    def test_t62_3_rejects_unknown_event_type(self):
        sink = telemetry.TelemetrySink(path=self.path, enabled=True)
        self.assertFalse(sink.record("not_a_real_event_type"))
        self.assertEqual(sink.read_events(), [])

    def test_t62_4_coerces_non_json_payload(self):
        sink = telemetry.TelemetrySink(path=self.path, enabled=True)
        self.assertTrue(sink.record("feature_used", path=Path("/tmp/x"), bag={1, 2}))
        events = sink.read_events()
        self.assertEqual(len(events), 1)
        self.assertIsInstance(events[0]["payload"]["path"], str)

    def test_t62_5_rotation_moves_to_dot_1(self):
        sink = telemetry.TelemetrySink(path=self.path, enabled=True, max_bytes=128)
        for _ in range(50):
            sink.record("feature_used", name="x" * 32)
        rotated = self.path.with_suffix(self.path.suffix + ".1")
        # Contract: rotation fires when the active file would exceed
        # ``max_bytes`` on the next append. After 50 writes against a
        # 128 B cap, the rotated archive MUST exist and be non-empty.
        self.assertTrue(rotated.exists())
        self.assertGreater(rotated.stat().st_size, 0)
        # We should have written enough cumulative bytes to require at
        # least one rotation pass — both files combined must exceed
        # the threshold. (The earlier ``rotated >= active`` invariant
        # was timestamp-dependent: when an ISO timestamp lands on an
        # exact-second boundary, ``datetime.isoformat()`` drops the
        # microsecond suffix and shortens that single line by 7 bytes,
        # so the relative sizes are not a stable rotation property.)
        total = self.path.stat().st_size + rotated.stat().st_size
        self.assertGreater(total, 128)

    def test_t62_6_clear_wipes_active_file(self):
        sink = telemetry.TelemetrySink(path=self.path, enabled=True)
        sink.record("feature_used")
        self.assertTrue(self.path.exists())
        sink.clear()
        self.assertFalse(self.path.exists())

    def test_t62_7_malformed_line_is_skipped(self):
        sink = telemetry.TelemetrySink(path=self.path, enabled=True)
        sink.record("feature_used", n=1)
        with self.path.open("a", encoding="utf-8") as f:
            f.write("{not json\n")
        sink.record("feature_used", n=2)
        events = sink.read_events()
        self.assertEqual(len(events), 2)

    def test_t62_8_thread_safe_concurrent_writes(self):
        sink = telemetry.TelemetrySink(path=self.path, enabled=True)

        def writer(n):
            for i in range(50):
                sink.record("feature_used", id=f"{n}-{i}")

        threads = [threading.Thread(target=writer, args=(k,)) for k in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        events = sink.read_events()
        self.assertEqual(len(events), 4 * 50)

    def test_t62_9_max_bytes_must_be_positive(self):
        with self.assertRaises(ValueError):
            telemetry.TelemetrySink(path=self.path, max_bytes=0)
        with self.assertRaises(ValueError):
            telemetry.TelemetrySink(path=self.path, max_bytes=-1)

    def test_t62_10_configure_replaces_module_level_sink(self):
        # Each configure() call must replace, not stack — otherwise
        # tests could leak events between runs.
        path_a = Path(self._tmp.name) / "a.jsonl"
        path_b = Path(self._tmp.name) / "b.jsonl"
        telemetry.configure(path_a, enabled=True)
        telemetry.record("feature_used", n=1)
        telemetry.configure(path_b, enabled=True)
        telemetry.record("feature_used", n=2)
        self.assertEqual(sum(1 for _ in path_a.open(encoding="utf-8")), 1)
        self.assertEqual(sum(1 for _ in path_b.open(encoding="utf-8")), 1)


# ---------------------------------------------------------------------------
# T6.3 — i18n
# ---------------------------------------------------------------------------


class TestT6_3_I18n(unittest.TestCase):
    def setUp(self):
        # Reset to default before each test so the suite doesn't depend
        # on execution order.
        i18n.set_language("vi")

    def test_t63_1_default_language_is_vi(self):
        i18n.set_language("vi")
        self.assertEqual(i18n.current_language(), "vi")

    def test_t63_2_known_key_returns_translation(self):
        # vi.json defines departments.dashboard = "Tổng Quan"
        self.assertEqual(i18n.tr("departments.dashboard"), "Tổng Quan")

    def test_t63_3_unknown_key_returns_self(self):
        self.assertEqual(i18n.tr("this.key.does.not.exist"), "this.key.does.not.exist")

    def test_t63_4_format_kwargs_interpolate(self):
        out = i18n.tr("departments.greeting", name="Bob")
        self.assertIn("Bob", out)
        # Vietnamese template uses "Chào {name}".
        self.assertTrue(out.startswith("Chào"))

    def test_t63_5_missing_format_kwarg_is_safe(self):
        # If the caller forgets a placeholder we must NOT raise.
        out = i18n.tr("departments.greeting")  # no name=
        self.assertIn("{name}", out)

    def test_t63_6_set_language_switches_lookup(self):
        i18n.set_language("en")
        self.assertEqual(i18n.tr("departments.dashboard"), "Dashboard")
        i18n.set_language("vi")
        self.assertEqual(i18n.tr("departments.dashboard"), "Tổng Quan")

    def test_t63_7_unknown_language_falls_back_to_default(self):
        i18n.set_language("klingon")
        self.assertEqual(i18n.current_language(), "vi")

    def test_t63_8_supported_languages_whitelist(self):
        langs = i18n.supported_languages()
        self.assertIn("vi", langs)
        self.assertIn("en", langs)

    def test_t63_9_plural_one_vs_other(self):
        one = i18n.tr_plural("items", 1)
        many = i18n.tr_plural("items", 5)
        self.assertIn("1", one)
        self.assertIn("5", many)

    def test_t63_10_plural_falls_back_to_key_when_not_dict(self):
        # departments.dashboard is a string, not a {one, other} dict.
        out = i18n.tr_plural("departments.dashboard", 3)
        # Falls through to tr(), which returns the raw string.
        self.assertEqual(out, "Tổng Quan")

    def test_t63_11_translation_files_are_parseable(self):
        i18n_dir = REPO_ROOT / "VeoSuite_V3" / "assets" / "i18n"
        for lang in ("vi", "en"):
            with (i18n_dir / f"{lang}.json").open(encoding="utf-8") as f:
                data = json.load(f)
            self.assertIsInstance(data, dict)
            # Both languages must define the same top-level keys so the UI
            # never sees a missing translation after a language switch.
            self.assertIn("app.title", data)
            self.assertIn("departments.dashboard", data)

    def test_t63_12_vi_and_en_share_keyset(self):
        i18n_dir = REPO_ROOT / "VeoSuite_V3" / "assets" / "i18n"
        with (i18n_dir / "vi.json").open(encoding="utf-8") as f:
            vi = json.load(f)
        with (i18n_dir / "en.json").open(encoding="utf-8") as f:
            en = json.load(f)
        self.assertEqual(
            set(vi.keys()),
            set(en.keys()),
            msg="vi.json and en.json have diverged — add the missing keys",
        )


# ---------------------------------------------------------------------------
# T6.4 — Font bundle
# ---------------------------------------------------------------------------


class TestT6_4_FontBundle(unittest.TestCase):
    def test_t64_1_required_fonts_is_nonempty(self):
        self.assertGreater(len(font_bundle.REQUIRED_FONTS), 0)

    def test_t64_2_required_fonts_keys_are_strings(self):
        for family, filename in font_bundle.REQUIRED_FONTS.items():
            self.assertIsInstance(family, str)
            self.assertIsInstance(filename, str)
            self.assertTrue(filename.endswith(".ttf"))

    def test_t64_3_list_available_against_real_dir(self):
        statuses = font_bundle.list_available()
        self.assertEqual(len(statuses), len(font_bundle.REQUIRED_FONTS))

    def test_t64_4_coverage_summary_matches_list_available(self):
        statuses = font_bundle.list_available()
        ok = sum(1 for s in statuses if s.available)
        total = len(statuses)
        self.assertEqual(font_bundle.coverage_summary(), (ok, total))

    def test_t64_5_empty_dir_reports_zero_coverage(self):
        with tempfile.TemporaryDirectory() as d:
            ok, total = font_bundle.coverage_summary(Path(d))
            self.assertEqual(ok, 0)
            self.assertEqual(total, len(font_bundle.REQUIRED_FONTS))

    def test_t64_6_status_has_path_when_available(self):
        for status in font_bundle.list_available():
            if status.available:
                assert status.path is not None  # narrow for type checker
                self.assertTrue(status.path.is_file())
            else:
                self.assertIsNone(status.path)

    def test_t64_7_fonts_dir_resolves_inside_assets(self):
        d = font_bundle.fonts_dir()
        self.assertTrue(str(d).endswith(os.path.join("assets", "fonts")))

    def test_t64_8_actual_repo_has_at_least_one_required_font(self):
        # Sanity check — if someone deletes every TTF the build should
        # surface that immediately, not at end-user runtime.
        ok, _ = font_bundle.coverage_summary()
        self.assertGreater(ok, 0)


# ---------------------------------------------------------------------------
# T6.5 — Dashboard tab
# ---------------------------------------------------------------------------


@unittest.skipUnless(_QT_AVAILABLE, "PyQt6 not available")
class TestT6_5_Dashboard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _qapp()

    def _import_dashboard(self):
        # Lazy import so the module is only loaded when Qt is present.
        from ui.widgets.dashboard_tab import DashboardTab, compute_account_kpis

        return DashboardTab, compute_account_kpis

    def test_t65_1_compute_kpis_handles_empty_list(self):
        _, compute = self._import_dashboard()
        self.assertEqual(
            compute([]),
            {"total": 0, "money": 0, "warmup": 0, "burn": 0},
        )

    def test_t65_2_compute_kpis_buckets_by_status(self):
        _, compute = self._import_dashboard()
        kpis = compute(
            [
                {"status": "money"},
                {"status": "money"},
                {"status": "warmup"},
                {"status": "burn"},
                {"status": "unknown"},
            ]
        )
        self.assertEqual(kpis["total"], 5)
        self.assertEqual(kpis["money"], 2)
        self.assertEqual(kpis["warmup"], 1)
        self.assertEqual(kpis["burn"], 1)

    def test_t65_3_compute_kpis_is_case_insensitive(self):
        _, compute = self._import_dashboard()
        kpis = compute([{"status": "MONEY"}, {"status": "  Warmup  "}])
        self.assertEqual(kpis["money"], 1)
        self.assertEqual(kpis["warmup"], 1)

    def test_t65_4_dashboard_constructs_without_dependencies(self):
        DashboardTab, _ = self._import_dashboard()
        tab = DashboardTab()
        # KPI labels must default to "0".
        for value_key, label in tab._kpi_value_labels.items():
            self.assertEqual(label.text(), "0", msg=value_key)

    def test_t65_5_dashboard_refresh_with_plugin_manager(self):
        DashboardTab, _ = self._import_dashboard()
        mgr = PluginManager()
        tab = DashboardTab(plugin_manager=mgr)
        tab.refresh()
        self.assertEqual(tab._plugin_list.count(), 0)

    def test_t65_6_dashboard_lists_plugin_metadata(self):
        DashboardTab, _ = self._import_dashboard()
        builtin = REPO_ROOT / "VeoSuite_V3" / "modules" / "plugins" / "builtin"
        mgr = PluginManager(plugin_dirs=[builtin])
        mgr.load_all()
        tab = DashboardTab(plugin_manager=mgr)
        self.assertGreaterEqual(tab._plugin_list.count(), 1)

    def test_t65_7_dashboard_handles_db_error(self):
        DashboardTab, _ = self._import_dashboard()

        class _BadDB:
            def list_accounts(self):
                raise RuntimeError("synthetic — DB down")

        tab = DashboardTab(db=_BadDB())  # type: ignore[arg-type]
        # Construction + refresh must not raise.
        tab.refresh()
        self.assertEqual(tab._kpi_value_labels["total"].text(), "0")

    def test_t65_8_dashboard_log_signal_exists(self):
        DashboardTab, _ = self._import_dashboard()
        tab = DashboardTab()
        self.assertTrue(hasattr(tab, "log_signal"))


# ---------------------------------------------------------------------------
# T6.6 — Structural / AST checks (cheap regression gates)
# ---------------------------------------------------------------------------


class TestT6_6_Structural(unittest.TestCase):
    def test_t66_1_main_window_imports_dashboard_in_both_branches(self):
        path = REPO_ROOT / "VeoSuite_V3" / "ui" / "main_window.py"
        with path.open(encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(path))
        # Find every ImportFrom of a `dashboard_tab` symbol — must
        # appear at least twice (primary block + fallback block) so a
        # transitive import failure in the primary block doesn't crash
        # MainWindow with NameError.
        hits = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and "dashboard_tab" in node.module:
                hits += 1
        self.assertGreaterEqual(hits, 2, msg="DashboardTab import is not mirrored in fallback block")

    def test_t66_2_main_py_initialises_all_three_subsystems(self):
        path = REPO_ROOT / "VeoSuite_V3" / "main.py"
        text = path.read_text(encoding="utf-8")
        for needle in (
            "initialize_plugins",
            "initialize_telemetry",
            "font_bundle.register_with_qt",
        ):
            self.assertIn(needle, text, msg=f"main.py is missing {needle} bootstrap")

    def test_t66_3_plugin_metadata_is_frozen(self):
        path = REPO_ROOT / "VeoSuite_V3" / "modules" / "plugins" / "base.py"
        text = path.read_text(encoding="utf-8")
        # Detect the @dataclass(frozen=True) marker. Cheap protection
        # against a future contributor removing the freeze.
        self.assertIn("@dataclass(frozen=True)", text)


# ---------------------------------------------------------------------------
# T7 — Plugin shutdown wiring in MainWindow.closeEvent (PR-7)
# ---------------------------------------------------------------------------
#
# PR-6 wired plugin start at app boot but left shutdown unwired. PR-7
# closes that loop by calling ``plugin_manager.shutdown()`` from
# ``MainWindow.closeEvent``. The tests below lock the contract so a
# future refactor of ``closeEvent`` cannot silently drop the call.


class _ShutdownSpyPlugin(Plugin):
    """Records ``on_app_shutdown`` invocations on a class-level list so
    tests can assert ordering and arg-passing without touching disk."""

    received: list[tuple[str, dict]] = []

    @classmethod
    def metadata(cls) -> PluginMetadata:
        return PluginMetadata(name="shutdown-spy", version="1.0.0")

    def on_app_shutdown(self, context):
        _ShutdownSpyPlugin.received.append(("shutdown-spy", dict(context)))


class TestT7_PluginShutdownWiring(unittest.TestCase):
    """Adversarial tests for PR-7 — MainWindow.closeEvent invokes
    ``plugin_manager.shutdown()`` and emits a telemetry session_ended."""

    def test_t7_1_closeevent_source_invokes_plugin_shutdown(self):
        """AST gate — the textual ``plugin_manager.shutdown`` call must
        appear inside ``closeEvent``. Catches refactors that move the
        call out (or delete it) without anyone noticing."""
        path = REPO_ROOT / "VeoSuite_V3" / "ui" / "main_window.py"
        with path.open(encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(path))

        found = False
        for cls in ast.walk(tree):
            if not (isinstance(cls, ast.ClassDef) and cls.name == "MainWindow"):
                continue
            for fn in cls.body:
                if not (isinstance(fn, ast.FunctionDef) and fn.name == "closeEvent"):
                    continue
                for node in ast.walk(fn):
                    if (
                        isinstance(node, ast.Attribute)
                        and node.attr == "shutdown"
                        and isinstance(node.value, ast.Attribute)
                        and node.value.attr == "plugin_manager"
                    ):
                        found = True
                        break
        self.assertTrue(
            found,
            "MainWindow.closeEvent must call self.plugin_manager.shutdown(...)",
        )

    def test_t7_2_closeevent_records_session_ended_telemetry(self):
        """closeEvent must emit ``telemetry.record('session_ended')`` so
        future opt-in sessions have a clean end marker."""
        path = REPO_ROOT / "VeoSuite_V3" / "ui" / "main_window.py"
        text = path.read_text(encoding="utf-8")
        self.assertIn("session_ended", text)
        self.assertIn("telemetry.record", text)

    def test_t7_3_plugin_manager_shutdown_called_with_dict_context(self):
        """The actual plugin shutdown invocation must hand the host
        a *dict* context, not a list/tuple — plugins index into it."""
        manager = PluginManager()
        # Smuggle a spy directly via the private slot to avoid a temp file.
        from modules.plugins.manager import _LoadedPlugin

        entry = _LoadedPlugin(
            instance=_ShutdownSpyPlugin(),
            metadata=_ShutdownSpyPlugin.metadata(),
            path=REPO_ROOT,
        )
        manager._loaded.append(entry)
        manager._by_name[entry.metadata.name] = entry
        _ShutdownSpyPlugin.received.clear()

        ok, errs = manager.shutdown({"app": "stub", "db": None})
        self.assertEqual(ok, 1)
        self.assertEqual(errs, [])
        self.assertEqual(len(_ShutdownSpyPlugin.received), 1)
        name, ctx = _ShutdownSpyPlugin.received[0]
        self.assertEqual(name, "shutdown-spy")
        self.assertIsInstance(ctx, dict)
        self.assertEqual(ctx.get("app"), "stub")

    def test_t7_4_closeevent_isolates_plugin_exception(self):
        """A plugin that raises on shutdown must not block ``event.accept()``."""

        class _ExplodingPlugin(Plugin):
            @classmethod
            def metadata(cls):
                return PluginMetadata(name="bomb", version="1.0.0")

            def on_app_shutdown(self, context):
                raise RuntimeError("kaboom")

        manager = PluginManager()
        from modules.plugins.manager import _LoadedPlugin

        entry = _LoadedPlugin(
            instance=_ExplodingPlugin(),
            metadata=_ExplodingPlugin.metadata(),
            path=REPO_ROOT,
        )
        manager._loaded.append(entry)
        manager._by_name[entry.metadata.name] = entry
        ok, errs = manager.shutdown({"app": None})
        # ok=0 (plugin raised) but the call itself returned normally —
        # which is what closeEvent's try/except relies on.
        self.assertEqual(ok, 0)
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0][0], "bomb")

    def test_t7_5_closeevent_handles_none_plugin_manager(self):
        """closeEvent must not crash when MainWindow was constructed
        without a plugin_manager (legacy/test entry points). The source
        guard ``if self.plugin_manager is not None`` is the contract."""
        path = REPO_ROOT / "VeoSuite_V3" / "ui" / "main_window.py"
        text = path.read_text(encoding="utf-8")
        self.assertIn("self.plugin_manager is not None", text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main(verbosity=2)
