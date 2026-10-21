"""Default-device switching: a device name is data, never PowerShell code.

Names come from drivers and from whatever the user called their headphones,
so they reach the script through an environment variable. The real-PowerShell
tests stub the AudioDeviceCmdlets functions, so no audio device changes.
"""

import shutil
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only switcher")

from chasqui.core import windevice  # noqa: E402

# Closes a '...' PowerShell string with a typographic quote, then runs code.
EVIL = "x’; Set-Content -Path $env:CHASQUI_TEST_PWNED -Value 1; ’"


def test_the_name_never_enters_the_script(monkeypatch):
    seen = {}

    def fake_run(args, **kwargs):
        seen["script"], seen["env"] = args[-1], kwargs["env"]
        return type("R", (), {"returncode": 0})()

    monkeypatch.setattr(windevice.subprocess, "run", fake_run)
    assert windevice.set_default_output(EVIL)
    assert EVIL not in seen["script"], "windevice._set_default: name pasted into the script"
    assert seen["env"]["CHASQUI_DEVICE_HINT"] == EVIL


@pytest.fixture
def stub_cmdlets(monkeypatch, tmp_path):
    """Fake Get/Set-AudioDevice; Set-AudioDevice writes the index it got."""
    if not shutil.which("powershell"):
        pytest.skip("no powershell")
    chosen = tmp_path / "chosen.txt"
    monkeypatch.setenv("CHASQUI_TEST_CHOSEN", str(chosen))
    monkeypatch.setenv("CHASQUI_TEST_PWNED", str(tmp_path / "pwned.txt"))
    stub = """
function Get-AudioDevice { param([switch]$List) @(
    [pscustomobject]@{ Type = 'Playback'; Name = 'Altavoces [Realtek]'; Index = 3 },
    [pscustomobject]@{ Type = 'Playback'; Name = "Juan$([char]0x2019)s AirPods"; Index = 5 }
) }
function Set-AudioDevice { param($Index) Set-Content -Path $env:CHASQUI_TEST_CHOSEN -Value $Index }
"""
    monkeypatch.setattr(windevice, "_import", lambda: stub)
    return tmp_path


@pytest.mark.parametrize("hint, index", [
    ("Juan’s AirPods", "5"),   # typographic apostrophe, as an iPhone writes it
    ("[realtek]", "3"),        # brackets are text, and the match ignores case
])
def test_real_powershell_matches_odd_names(stub_cmdlets, hint, index):
    assert windevice.set_default_output(hint)
    assert (stub_cmdlets / "chosen.txt").read_text().strip() == index


def test_real_powershell_does_not_run_a_name(stub_cmdlets):
    assert not windevice.set_default_output(EVIL)
    assert not (stub_cmdlets / "pwned.txt").exists(), "a device name ran as code"
