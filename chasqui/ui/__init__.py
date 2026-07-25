"""Chasqui desktop UI — start/stop, languages, devices and live transcript.

`runner` holds the logic and imports nothing from tkinter, so it runs (and is
tested) headless. `app` is the Tk window on top of it.
"""

from .runner import LogLine, RunnerEvent, SessionRunner, StateChange, TurnLine

__all__ = ["SessionRunner", "RunnerEvent", "LogLine", "TurnLine", "StateChange"]
