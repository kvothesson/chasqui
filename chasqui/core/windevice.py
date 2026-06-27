"""Windows default audio output switcher via PowerShell AudioDeviceCmdlets."""

import sys
import subprocess
from typing import Optional

if sys.platform != "win32":
    def get_default_output_name() -> Optional[str]:
        return None

    def set_default_output(name_hint: str) -> bool:
        return False
else:
    def _ps(cmd: str, timeout: int = 8) -> Optional[str]:
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command", cmd],
                capture_output=True, text=True, timeout=timeout,
            )
            return r.stdout.strip() if r.returncode == 0 else None
        except Exception:
            return None

    def get_default_output_name() -> Optional[str]:
        out = _ps("(Get-AudioDevice -Playback).Name")
        return out or None

    def set_default_output(name_hint: str) -> bool:
        # Find the device index whose name contains name_hint, then set it.
        script = f"""
$dev = Get-AudioDevice -List | Where-Object {{
    $_.Type -eq 'Playback' -and $_.Name -like '*{name_hint}*'
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
