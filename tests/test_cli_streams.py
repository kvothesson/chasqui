"""Importing the CLI when there are no standard streams.

A desktop shortcut launches the UI through pythonw.exe so no console window
tags along. pythonw gives the process no stdout and no stderr at all — and the
UTF-8 forcing at the top of cli.py read sys.stdout.encoding unconditionally,
so the import died with AttributeError before anything existed to report it.
From the desktop that looked like double-clicking the icon and nothing
happening, forever.
"""

import importlib
import io
import sys

import chasqui.cli


def test_force_utf8_survives_missing_streams(monkeypatch):
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    chasqui.cli._force_utf8()   # must not raise

    assert sys.stdout is None, (
        "With no streams there is nothing to wrap — _force_utf8 must leave "
        "them alone rather than invent a wrapper around None."
    )


def test_force_utf8_survives_streams_without_a_buffer(monkeypatch):
    """StringIO and friends have .encoding but no .buffer — pytest's own
    capture puts one in place, so this path runs in CI constantly."""
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    chasqui.cli._force_utf8()


def test_force_utf8_wraps_a_non_utf8_console(monkeypatch):
    """The behaviour this guard must not lose: a cp1252 console gets wrapped,
    or Japanese output crashes the CLI on Windows."""
    class Cp1252Stream:
        encoding = "cp1252"
        buffer = io.BytesIO()

    monkeypatch.setattr(sys, "stdout", Cp1252Stream())
    monkeypatch.setattr(sys, "stderr", Cp1252Stream())

    chasqui.cli._force_utf8()

    assert sys.stdout.encoding == "utf-8", (
        "A non-UTF-8 console must still be re-wrapped. If this fails, CJK "
        "transcripts crash the CLI on a default Windows console."
    )


def test_module_imports_with_no_streams(monkeypatch):
    """The whole failure, end to end: `pythonw -m chasqui ui` re-imports the
    module from scratch with both streams already None."""
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    monkeypatch.delitem(sys.modules, "chasqui.cli", raising=False)

    importlib.import_module("chasqui.cli")   # must not raise
