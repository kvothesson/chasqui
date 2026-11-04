"""Adapter registry — the single place that maps adapter names to classes.

Imports stay lazy: `chasqui devices` and `chasqui langs` must not pay for
sounddevice/openai import time, and a missing optional dependency should only
blow up for the adapter that actually needs it.
"""

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..core.config import Config
    from .base import BaseAdapter

ADAPTER_PATHS: dict[str, str] = {
    "text":        "chasqui.adapters.text.TextAdapter",
    "device":      "chasqui.adapters.device.DeviceAdapter",
    "virtual-mic": "chasqui.adapters.virtual_mic.VirtualMicAdapter",
    "media":       "chasqui.adapters.media.MediaAdapter",
    "bridge":      "chasqui.adapters.bridge.BridgeAdapter",
    "meet":        "chasqui.adapters.meet.MeetAdapter",
    "headset":     "chasqui.adapters.headset.HeadsetAdapter",
}

ADAPTER_NAMES: list[str] = list(ADAPTER_PATHS)

# One-line descriptions of every adapter. The window words its three modes in
# ui/strings.py, in the user's language.
ADAPTER_LABELS: dict[str, str] = {
    "headset":     "Headset — bidirectional, any app (recommended)",
    "meet":        "Meet / Zoom / Teams — bidirectional, two cables",
    "bridge":      "Bridge — bidirectional, two cables",
    "virtual-mic": "Virtual mic — one way, your voice into any app",
    "media":       "Media — translate what your system is playing",
    "device":      "Device — physical mic + speaker pendant",
    "text":        "Text — keyboard in, terminal out",
}

# Adapters the GUI offers, in picker order: the three ways of using chasqui
# the landing promises. The text adapter is a blocking stdin REPL, so it has
# nothing to read from in a windowed session; bridge, virtual-mic and device
# are setups for people who already know their audio routing, and seven
# options was a question a newcomer could not answer. All stay in the CLI.
UI_ADAPTER_NAMES: list[str] = ["headset", "media", "meet"]


def get_adapter_class(name: str) -> type["BaseAdapter"]:
    """Resolve an adapter name to its class. Raises KeyError if unknown."""
    try:
        path = ADAPTER_PATHS[name]
    except KeyError:
        raise KeyError(
            f"Unknown adapter {name!r}. Available: {', '.join(ADAPTER_NAMES)}"
        ) from None

    module_path, class_name = path.rsplit(".", 1)
    return getattr(importlib.import_module(module_path), class_name)


def build_adapter(config: "Config") -> "BaseAdapter":
    """Instantiate the adapter named by `config.adapter`."""
    return get_adapter_class(config.adapter)(config)
