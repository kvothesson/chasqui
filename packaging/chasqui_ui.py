"""PyInstaller's entry point for the installed app: the window, nothing else.

A real file rather than `-m chasqui`, because PyInstaller freezes a script.
"""

from chasqui.cli import ui_entry

if __name__ == "__main__":
    ui_entry()
