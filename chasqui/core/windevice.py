"""Windows default audio device switcher via PowerShell AudioDeviceCmdlets."""

import sys
import subprocess
from typing import Optional

if sys.platform != "win32":
    def get_default_output_name() -> Optional[str]:
        return None

    def set_default_output(name_hint: str) -> bool:
        return False

    def get_default_input_name() -> Optional[str]:
        return None

    def set_default_input(name_hint: str) -> bool:
        return False
else:
    # Force UTF-8 on the PowerShell side and decode as UTF-8 here. Without
    # this, non-ASCII device names ("Micrófono ...") come back mojibake
    # ("MicrÃ³fono ..."), which silently breaks both the restore -like match
    # and resolve_device() lookups downstream.
    _UTF8 = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "

    def _ps(cmd: str, timeout: int = 8) -> Optional[str]:
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command", _UTF8 + cmd],
                capture_output=True, timeout=timeout,
                encoding="utf-8", errors="replace",
            )
            return r.stdout.strip() if r.returncode == 0 else None
        except Exception:
            return None

    def get_default_output_name() -> Optional[str]:
        out = _ps("(Get-AudioDevice -Playback).Name")
        return out or None

    def _set_default(device_type: str, name_hint: str) -> bool:
        # Find the device index whose name contains name_hint, then set it.
        name_hint = name_hint.replace("'", "''")
        script = f"""
$dev = Get-AudioDevice -List | Where-Object {{
    $_.Type -eq '{device_type}' -and $_.Name -like '*{name_hint}*'
}} | Select-Object -First 1
if ($dev) {{ Set-AudioDevice -Index $dev.Index | Out-Null; exit 0 }}
exit 1
"""
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True, timeout=8,
            )
            return r.returncode == 0
        except Exception:
            return False

    def set_default_output(name_hint: str) -> bool:
        return _set_default("Playback", name_hint)

    def get_default_input_name() -> Optional[str]:
        out = _ps("(Get-AudioDevice -Recording).Name")
        return out or None

    def set_default_input(name_hint: str) -> bool:
        return _set_default("Recording", name_hint)
