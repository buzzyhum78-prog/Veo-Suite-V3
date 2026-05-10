"""Plugin manager — discovery, loading, lifecycle dispatch.

Pure-Python; safe to use under offscreen pytest.

Discovery: any ``*.py`` file in one of the configured plugin directories
that defines a subclass of :class:`Plugin` (other than ``Plugin`` itself)
becomes a plugin instance. Modules are imported via
:mod:`importlib.util` so they don't pollute ``sys.modules`` with names
that could collide with the host application.

Lifecycle: ``start(context)`` invokes ``on_app_start`` on every plugin;
``shutdown(context)`` invokes ``on_app_shutdown`` on every plugin in
reverse load order. Both methods isolate exceptions per-plugin and
return a tuple of ``(ok_count, errors)`` so the caller can surface a
warning without aborting.
"""

from __future__ import annotations

import importlib.util
import inspect
import logging
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .base import Plugin, PluginMetadata

logger = logging.getLogger("VeoSuite.Plugins")


class PluginLoadError(Exception):
    """Raised when a plugin module fails to load (import error, no
    Plugin subclass, duplicate name, invalid metadata)."""


class _LoadedPlugin:
    """Lightweight container — keeps the instance + its file path for
    debugging and unload, without exposing them as public attributes
    of the manager."""

    __slots__ = ("instance", "metadata", "path")

    def __init__(self, instance: Plugin, metadata: PluginMetadata, path: Path):
        self.instance = instance
        self.metadata = metadata
        self.path = path


class PluginManager:
    """Discover, load, and orchestrate Veo Suite plugins.

    The manager is stateful but cheap to recreate, so tests construct
    a fresh manager per case rather than relying on a singleton.
    """

    def __init__(self, plugin_dirs: Iterable[Path | str] | None = None):
        self._dirs: list[Path] = [Path(p) for p in (plugin_dirs or [])]
        self._loaded: list[_LoadedPlugin] = []
        self._by_name: dict[str, _LoadedPlugin] = {}

    # ------------------------------------------------------------------ dirs

    @property
    def plugin_dirs(self) -> list[Path]:
        return list(self._dirs)

    def add_dir(self, directory: Path | str) -> None:
        path = Path(directory)
        if path not in self._dirs:
            self._dirs.append(path)

    # -------------------------------------------------------------- discovery

    def discover(self) -> list[Path]:
        """Return every ``*.py`` file in the configured directories,
        sorted for deterministic load order. Ignores ``__*__`` files."""
        found: list[Path] = []
        for d in self._dirs:
            if not d.is_dir():
                continue
            for entry in sorted(d.iterdir()):
                if entry.is_file() and entry.suffix == ".py" and not entry.name.startswith("__"):
                    found.append(entry)
        return found

    def load_all(self) -> tuple[int, list[tuple[Path, str]]]:
        """Load every discovered plugin file.

        Returns ``(loaded_count, errors)`` where ``errors`` is a list of
        ``(path, message)`` pairs. Already-loaded plugins are skipped.
        """
        errors: list[tuple[Path, str]] = []
        loaded = 0
        for path in self.discover():
            try:
                self.load(path)
            except PluginLoadError as exc:
                logger.warning("Plugin %s failed to load: %s", path, exc)
                errors.append((path, str(exc)))
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("Unexpected error loading %s", path)
                errors.append((path, repr(exc)))
            else:
                loaded += 1
        return loaded, errors

    def load(self, path: Path | str) -> _LoadedPlugin:
        """Load a single plugin file. Raises :class:`PluginLoadError`."""
        path = Path(path)
        if not path.is_file():
            raise PluginLoadError(f"Not a file: {path}")

        module_name = f"_veo_plugin_{path.stem}_{id(self)}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise PluginLoadError(f"Cannot build import spec for {path}")
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            raise PluginLoadError(f"Import failed: {exc!r}") from exc

        # Find the first Plugin subclass *defined* in this module (skip
        # re-imports of the base class itself).
        candidates = [
            obj
            for _name, obj in inspect.getmembers(module, inspect.isclass)
            if issubclass(obj, Plugin) and obj is not Plugin and obj.__module__ == module.__name__
        ]
        if not candidates:
            raise PluginLoadError(f"No Plugin subclass found in {path}")
        if len(candidates) > 1:
            raise PluginLoadError(
                f"More than one Plugin subclass in {path}: {[c.__name__ for c in candidates]}"
            )

        cls = candidates[0]
        try:
            meta = cls.metadata()
        except Exception as exc:
            raise PluginLoadError(f"{cls.__name__}.metadata() raised {exc!r}") from exc
        if not isinstance(meta, PluginMetadata):
            raise PluginLoadError(
                f"{cls.__name__}.metadata() must return PluginMetadata (got {type(meta).__name__})"
            )

        if meta.name in self._by_name:
            raise PluginLoadError(
                f"Duplicate plugin name {meta.name!r} (also defined in {self._by_name[meta.name].path})"
            )

        try:
            instance = cls()
        except Exception as exc:
            raise PluginLoadError(f"{cls.__name__}() raised {exc!r}") from exc

        entry = _LoadedPlugin(instance=instance, metadata=meta, path=path)
        self._loaded.append(entry)
        self._by_name[meta.name] = entry
        # Keep module alive so closures/threads survive — but use a
        # namespaced key so we cannot collide with host modules.
        sys.modules[module_name] = module
        logger.info("Loaded plugin %s v%s from %s", meta.name, meta.version, path)
        return entry

    # ---------------------------------------------------------------- access

    def loaded_plugins(self) -> list[Plugin]:
        return [entry.instance for entry in self._loaded]

    def metadata_list(self) -> list[PluginMetadata]:
        return [entry.metadata for entry in self._loaded]

    def get(self, name: str) -> Plugin | None:
        entry = self._by_name.get(name)
        return entry.instance if entry else None

    # ------------------------------------------------------------- lifecycle

    def start(self, context: dict[str, Any] | None = None) -> tuple[int, list[tuple[str, str]]]:
        """Dispatch ``on_app_start`` to every plugin. Returns ``(ok_count, errors)``."""
        return self._dispatch("on_app_start", context or {}, reverse=False)

    def shutdown(self, context: dict[str, Any] | None = None) -> tuple[int, list[tuple[str, str]]]:
        """Dispatch ``on_app_shutdown`` to every plugin in reverse load order."""
        return self._dispatch("on_app_shutdown", context or {}, reverse=True)

    def _dispatch(
        self, hook: str, context: dict[str, Any], *, reverse: bool
    ) -> tuple[int, list[tuple[str, str]]]:
        errors: list[tuple[str, str]] = []
        ok = 0
        entries = list(reversed(self._loaded)) if reverse else list(self._loaded)
        for entry in entries:
            method = getattr(entry.instance, hook, None)
            if method is None or not callable(method):
                continue
            try:
                method(context)
            except Exception as exc:
                logger.exception("Plugin %s.%s raised", entry.metadata.name, hook)
                errors.append((entry.metadata.name, repr(exc)))
            else:
                ok += 1
        return ok, errors
