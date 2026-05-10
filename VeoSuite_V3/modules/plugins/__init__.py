"""Plugin subsystem for Veo Suite V3.

A *plugin* is a Python module that exposes a ``Plugin`` subclass with a
``metadata()`` classmethod and optional lifecycle hooks
(``on_app_start`` / ``on_app_shutdown``).

The plugin manager discovers plugin modules in a user directory and a
project-level "builtin" directory, instantiates them, and dispatches
lifecycle events. Plugin failures are isolated — a crashing plugin must
never bring down the host application.

See :mod:`VeoSuite_V3.modules.plugins.manager` for the entry point.
"""

from .base import Plugin, PluginMetadata
from .manager import PluginLoadError, PluginManager

__all__ = [
    "Plugin",
    "PluginMetadata",
    "PluginManager",
    "PluginLoadError",
]
