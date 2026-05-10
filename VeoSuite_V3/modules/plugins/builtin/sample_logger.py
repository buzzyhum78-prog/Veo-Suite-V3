"""Minimal built-in plugin — logs lifecycle hooks for visibility.

Acts as both a smoke test for the plugin pipeline and a copy-pasteable
example. The host's plugin manager will pick this file up if its
directory is added to the search path.
"""

from __future__ import annotations

import logging
from typing import Any

try:
    from modules.plugins import Plugin, PluginMetadata
except ImportError:  # pragma: no cover - fallback for direct-folder execution
    from VeoSuite_V3.modules.plugins import Plugin, PluginMetadata  # type: ignore

logger = logging.getLogger("VeoSuite.Plugins.SampleLogger")


class SampleLoggerPlugin(Plugin):
    """Logs ``on_app_start`` / ``on_app_shutdown`` to the standard
    logger so operators can confirm the plugin pipeline ran."""

    @classmethod
    def metadata(cls) -> PluginMetadata:
        return PluginMetadata(
            name="sample-logger",
            version="1.0.0",
            description="Logs lifecycle events. Safe to leave enabled.",
            author="Veo Suite",
            hooks=("on_app_start", "on_app_shutdown"),
        )

    def on_app_start(self, context: dict[str, Any]) -> None:
        logger.info("sample-logger: app start (context keys=%s)", sorted(context))

    def on_app_shutdown(self, context: dict[str, Any]) -> None:
        logger.info("sample-logger: app shutdown")
