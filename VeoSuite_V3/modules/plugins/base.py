"""Plugin base class + metadata schema.

These are pure data containers and an abstract interface — no Qt, no IO.
Plugin authors subclass :class:`Plugin` and override the hooks they care
about. The :class:`PluginManager` is the only consumer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Plugin name: lowercase letters, digits, hyphen, underscore. Forbids paths,
# spaces, and dotted attribute lookups so manifest names are safe to use as
# filesystem identifiers later (cache dirs, telemetry tags, …).
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}$")

# Semver-ish: MAJOR.MINOR.PATCH[-prerelease]. We do not need full PEP 440
# semantics — the manager only compares strings for display purposes and
# enforces presence + format here.
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?$")


@dataclass(frozen=True)
class PluginMetadata:
    """Identity card returned by ``Plugin.metadata()``.

    Frozen because the manager indexes plugins by ``(name, version)`` and
    uses metadata for log messages — accidental mutation after registration
    would break those invariants.
    """

    name: str
    version: str
    description: str = ""
    author: str = ""
    hooks: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not _NAME_RE.fullmatch(self.name):
            raise ValueError(f"Plugin name must match {_NAME_RE.pattern!r} (got {self.name!r})")
        if not isinstance(self.version, str) or not _VERSION_RE.fullmatch(self.version):
            raise ValueError(f"Plugin version must be MAJOR.MINOR.PATCH (got {self.version!r})")
        for hook in self.hooks:
            if hook not in {"on_app_start", "on_app_shutdown"}:
                raise ValueError(f"Unknown hook name: {hook!r}")


class Plugin:
    """Base class for Veo Suite plugins.

    Subclass and override :meth:`metadata` plus any lifecycle hook you
    want to react to. Hooks receive a *context* dict that the host may
    populate with things like ``{"app": QApplication, "db": ..., ...}``.

    The host MUST NOT pass live Qt objects to plugins running in a
    test context, so a plugin's hooks must remain side-effect free if
    the context is empty/missing keys.
    """

    @classmethod
    def metadata(cls) -> PluginMetadata:  # pragma: no cover - subclasses override
        raise NotImplementedError(f"{cls.__name__}.metadata() must return a PluginMetadata instance")

    def on_app_start(self, context: dict[str, Any]) -> None:
        """Called once after the host has finished initialising.

        Override to register callbacks, open caches, start timers, etc.
        Default: no-op. Exceptions are logged by the manager and do
        not propagate to the host.
        """

    def on_app_shutdown(self, context: dict[str, Any]) -> None:
        """Called once during host shutdown.

        Override to release resources. Exceptions are logged by the
        manager and do not propagate to the host (so a misbehaving
        plugin cannot block the app from exiting).
        """
