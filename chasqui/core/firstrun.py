"""What a fresh install needs before the first session: key, cable, switcher.

No tkinter here, same rule as ui/runner.py: the setup window in ui/wizard.py
only draws what these functions find, so every check is testable without a
display and usable from the CLI.

The key lives in ~/.chasqui/config.yaml, a file chasqui already looked for
(core.config.find_config). It is the user's file, not the project's: an
installed chasqui has no working directory worth writing into, and a
chasqui.yaml in a repo must never collect a secret behind the user's back.
"""

import json
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

USER_CONFIG_PATH = Path.home() / ".chasqui" / "config.yaml"

KEYS_URL = "https://platform.openai.com/api-keys"
CABLE_URL = "https://vb-audio.com/Cable/"
MODELS_URL = "https://api.openai.com/v1/models/"

# The switcher the headset and media modes use to move the Windows default
# devices (core/windevice.py). Not a Python package: a PowerShell module, so
# pip never installs it and a fresh machine does not have it.
SWITCHER_MODULE = "AudioDeviceCmdlets"
SWITCHER_INSTALL = f"Install-Module {SWITCHER_MODULE} -Scope CurrentUser"


# ---------------------------------------------------------------------------
# The key
# ---------------------------------------------------------------------------

def stored_api_key(path: Optional[Path] = None) -> str:
    """The key the setup window saved, or "" if there is none."""
    from .config import _resolve_env

    path = path or USER_CONFIG_PATH
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return ""
    api = data.get("api") if isinstance(data, dict) else None
    key = api.get("key", "") if isinstance(api, dict) else ""
    return _resolve_env(key or "")


def save_api_key(key: str, path: Optional[Path] = None) -> Path:
    """Write api.key into the user config, keeping everything else in it.

    Comments in that file do not survive the round trip; it is the one chasqui
    writes itself, so there should not be any.
    """
    path = path or USER_CONFIG_PATH
    data: dict = {}
    if path.exists():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = loaded
    api = data.get("api") if isinstance(data.get("api"), dict) else {}
    api["key"] = key.strip()
    data["api"] = api

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    tmp.replace(path)   # a crash mid-write must not leave half a config
    return path


@dataclass
class KeyCheck:
    status: str        # ok | invalid | no_model | offline
    message: str

    @property
    def usable(self) -> bool:
        """Worth saving: the key exists, even if this model is not on it."""
        return self.status in ("ok", "no_model")


def check_api_key(key: str, model: str, timeout: float = 10.0) -> KeyCheck:
    """Ask OpenAI whether this key can see the model chasqui is about to use.

    GET /v1/models/{model} costs nothing and answers both questions at once:
    401 is a bad key, 404 is a good key whose project cannot use the model,
    which otherwise only shows up as an opaque failure once a session starts.
    """
    key = key.strip()
    if not key:
        return KeyCheck("invalid", "Paste a key first.")
    if not key.startswith("sk-"):
        return KeyCheck("invalid", "That does not look like an OpenAI key (they start with sk-).")

    request = urllib.request.Request(
        MODELS_URL + model, headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            json.loads(response.read() or b"{}")
        return KeyCheck("ok", "Key works.")
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return KeyCheck("invalid", "OpenAI rejected this key.")
        if e.code == 404:
            return KeyCheck(
                "no_model",
                f"The key works, but its project cannot use {model}. "
                "Check the project's model access on platform.openai.com.",
            )
        if e.code == 429:
            # Rate limited or out of credit: the key itself is real.
            return KeyCheck("ok", "Key works (OpenAI says to slow down or add credit).")
        return KeyCheck("offline", f"OpenAI answered {e.code}; try again in a moment.")
    except Exception:
        return KeyCheck("offline", "Could not reach OpenAI. Check the connection and retry.")


# ---------------------------------------------------------------------------
# The machine
# ---------------------------------------------------------------------------

def has_virtual_cable(names: Optional[list[str]] = None) -> bool:
    """VB-Audio Cable present: both its ends, which is what the call modes use.

    Rescans PortAudio first: the window stays open while the user installs
    the cable, and a stale device list would keep saying it is missing.
    """
    if names is None:
        try:
            from .audio import refresh_devices
            import sounddevice as sd

            refresh_devices()
            names = [d["name"] for d in sd.query_devices()]
        except Exception:
            return False
    lowered = [n.lower() for n in names]
    return (any("cable input" in n for n in lowered)
            and any("cable output" in n for n in lowered))


def has_device_switcher() -> bool:
    """The PowerShell module windevice.py drives is installed for this user."""
    if sys.platform != "win32":
        return False
    from .windevice import bundled_module

    if bundled_module():
        return True
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"if (Get-Module -ListAvailable {SWITCHER_MODULE}) {{ exit 0 }} else {{ exit 1 }}"],
            capture_output=True, timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return r.returncode == 0
    except Exception:
        return False
