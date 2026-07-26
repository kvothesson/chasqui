"""Console script vs windowed script.

Launched from a terminal, a console entry point reuses the terminal and looks
fine. Launched by double-click — a desktop shortcut, the Run box, Explorer —
it has no console to inherit, so Windows creates one: a black window that sits
behind the UI for as long as the session runs. Measured, not assumed: 1 new
ConsoleWindowClass window for chasqui.exe, 0 for chasqui-ui.exe.

The fix lives entirely in packaging metadata, which is exactly the kind of
thing that gets dropped in a refactor without anyone noticing until a user
says "there's a console again".
"""

import sys
import tomllib
from pathlib import Path

import pytest

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


@pytest.fixture(scope="module")
def metadata():
    with open(PYPROJECT, "rb") as handle:
        return tomllib.load(handle)["project"]


def test_windowed_entry_point_is_declared(metadata):
    gui_scripts = metadata.get("gui-scripts", {})
    assert "chasqui-ui" in gui_scripts, (
        "The [project.gui-scripts] entry is gone. Without it there is no "
        "windowed launcher, and every desktop shortcut opens a console "
        "window behind the UI. Console scripts cannot avoid that on Windows."
    )
    assert gui_scripts["chasqui-ui"] == "chasqui.cli:ui_entry"


def test_console_entry_point_still_exists(metadata):
    """The CLI is the primary interface; the windowed one is an addition."""
    assert metadata["scripts"]["chasqui"] == "chasqui.cli:cli"


def test_both_targets_are_importable():
    """A typo in either target builds a launcher that dies on double-click,
    with no console left to show the traceback."""
    from chasqui import cli

    assert callable(cli.cli)
    assert callable(cli.ui_entry)


def test_ui_entry_takes_no_arguments():
    """gui-scripts launchers call the target with no arguments at all."""
    import inspect

    from chasqui.cli import ui_entry

    required = [
        name for name, parameter in inspect.signature(ui_entry).parameters.items()
        if parameter.default is inspect.Parameter.empty
        and parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
    ]
    assert not required, (
        f"ui_entry requires {required}, but a gui-scripts launcher passes "
        "nothing. It would crash instantly, silently, with no console."
    )


@pytest.mark.skipif(sys.platform != "win32", reason="Windows launcher layout")
def test_shortcut_prefers_the_windowed_launcher():
    """`chasqui icon --shortcut` must never point at the console script."""
    source = (Path(__file__).resolve().parent.parent
              / "chasqui" / "cli.py").read_text(encoding="utf-8")
    assert 'shutil.which("chasqui-ui")' in source, (
        "The shortcut builder no longer looks for the windowed launcher. "
        "Pointing a desktop shortcut at chasqui.exe brings the console back."
    )
