"""Build the Windows app (PyInstaller) and, if Inno Setup is there, its installer.

    python packaging/build_windows.py

Output:
    dist/chasqui/chasqui.exe              the app folder (runs as is)
    dist/chasqui-setup-<version>.exe      the installer, when ISCC is found

Run it from a clean virtualenv with `pip install -e . pyinstaller`: PyInstaller
packs whatever the interpreter can import, and a crowded site-packages makes a
fat app. The PowerShell module AudioDeviceCmdlets must be installed on the
build machine (Install-Module AudioDeviceCmdlets -Scope CurrentUser); it is
copied into the app so users never install it themselves.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build" / "windows"
DIST = ROOT / "dist"
APP_NAME = "chasqui"

sys.path.insert(0, str(ROOT))


def version() -> str:
    from chasqui import __version__
    return __version__


def write_icon() -> Path:
    from chasqui.ui.icon import write_ico
    return write_ico(BUILD / "chasqui.ico")


def stage_switcher() -> Path:
    """Copy AudioDeviceCmdlets (dll + manifest) next to its license."""
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-Module -ListAvailable AudioDeviceCmdlets | "
         "Sort-Object Version -Descending | Select-Object -First 1).ModuleBase"],
        capture_output=True, text=True,
    ).stdout.strip()
    if not out:
        sys.exit("AudioDeviceCmdlets is not installed here. Run in PowerShell:\n"
                 "  Install-Module AudioDeviceCmdlets -Scope CurrentUser")
    source = Path(out)
    target = BUILD / "AudioDeviceCmdlets"
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    for name in ("AudioDeviceCmdlets.dll", "AudioDeviceCmdlets.psd1"):
        shutil.copy2(source / name, target / name)
    shutil.copy2(ROOT / "packaging" / "third_party" / "AudioDeviceCmdlets-LICENSE.txt",
                 target / "LICENSE.txt")
    return target


def freeze(icon: Path, switcher: Path) -> Path:
    subprocess.run([
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--windowed",                 # no console behind the window
        "--onedir",                   # starts fast; the installer packs the folder
        "--name", APP_NAME,
        "--icon", str(icon),
        "--add-data", f"{switcher}{os.pathsep}AudioDeviceCmdlets",
        "--distpath", str(DIST),
        "--workpath", str(BUILD / "pyinstaller"),
        "--specpath", str(BUILD),
        str(ROOT / "packaging" / "chasqui_ui.py"),
    ], check=True, cwd=ROOT)
    app = DIST / APP_NAME
    shutil.copy2(ROOT / "LICENSE", app / "LICENSE.txt")
    return app


def find_iscc() -> Path | None:
    found = shutil.which("ISCC")
    if found:
        return Path(found)
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")):
        if base and (candidate := Path(base) / "Inno Setup 6" / "ISCC.exe").exists():
            return candidate
    return None


def installer(app: Path, icon: Path) -> Path | None:
    iscc = find_iscc()
    if not iscc:
        print("Inno Setup (ISCC.exe) not found: skipping the installer. "
              f"The app folder works on its own: {app}")
        return None
    v = version()
    subprocess.run([
        str(iscc), "/Qp",
        f"/DAppVersion={v}", f"/DAppDir={app}", f"/DAppIcon={icon}", f"/DOutDir={DIST}",
        str(ROOT / "packaging" / "chasqui.iss"),
    ], check=True)
    return DIST / f"chasqui-setup-{v}.exe"


def main() -> None:
    if sys.platform != "win32":
        sys.exit("The Windows build runs on Windows.")
    BUILD.mkdir(parents=True, exist_ok=True)
    icon = write_icon()
    switcher = stage_switcher()
    app = freeze(icon, switcher)
    print(f"App: {app / (APP_NAME + '.exe')}")
    setup = installer(app, icon)
    if setup:
        print(f"Installer: {setup}")


if __name__ == "__main__":
    main()
