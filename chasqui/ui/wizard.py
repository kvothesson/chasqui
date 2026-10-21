"""The first-run window: key, cable, switcher, then a ping.

Opens over the main window whenever there is no API key, and from the SETUP
link at any time after. Three rows, each answering "is this ready?" with a
light and one line of words; only the key blocks, because without it nothing
works, while the cable and the switcher only matter for some modes.

Network and device checks run on worker threads and report back through
`root.after`, the same rule as the rest of the UI: widgets are only touched
from Tk's main thread.
"""

import threading
import webbrowser
from typing import Callable

from ..core import firstrun
from . import app as skin

# Same wording as the button that opens it, so the link and the window read
# as one thing.
TITLE = "chasqui · setup"


class SetupWizard:
    def __init__(self, owner, model: str, on_done: Callable[[bool], None]):
        """`on_done(ping)` runs once, when the window closes; ping is True on DONE."""
        self.owner = owner
        self.tk = owner.tk
        self.model = model
        self.on_done = on_done
        self.key_saved = False
        self._closed = False

        root = owner.root
        self.win = self.tk.Toplevel(root)
        self.win.title(TITLE)
        self.win.configure(bg=skin.C_BG)
        self.win.transient(root)
        self.win.resizable(False, False)
        self.win.protocol("WM_DELETE_WINDOW", self._close)
        # Above the main window, which is itself usually pinned on top.
        self.win.attributes("-topmost", True)

        self._style()
        self._build()
        owner._dark_titlebar(self.win)
        self.win.geometry(f"+{root.winfo_rootx() + 24}+{root.winfo_rooty() + 24}")
        self.win.grab_set()
        self.entry.focus_set()
        self._recheck_machine()

    # ------------------------------------------------------------------

    def _style(self) -> None:
        from tkinter import ttk

        style = ttk.Style(self.win)
        # The only text field in the app, so its look lives here.
        style.configure(
            "Key.TEntry", fieldbackground=skin.C_PANEL, foreground=skin.C_TEXT,
            insertcolor=skin.C_ACCENT, bordercolor=skin.C_BORDER,
            lightcolor=skin.C_PANEL, darkcolor=skin.C_PANEL, padding=5,
        )
        style.map("Key.TEntry", bordercolor=[("focus", skin.C_ACCENT)])
        style.configure("Body.TLabel", background=skin.C_PANEL, foreground=skin.C_MUTED,
                        font=("Segoe UI", 8))

    def _row(self, parent, row: int, title: str):
        """One numbered panel with a status light. Returns (inner, light, note)."""
        from tkinter import ttk

        wrap, inner = self.owner._panel(parent)
        wrap.grid(row=row, column=0, sticky="ew", pady=(8, 0))
        inner.columnconfigure(1, weight=1)

        light = self.tk.Canvas(inner, width=13, height=13, bg=skin.C_PANEL, highlightthickness=0)
        light.grid(row=0, column=0, padx=(0, 6))
        light.create_polygon(skin.hex_points(6.5, 6.5, 6), fill=skin.C_MUTED, outline="",
                             tags="dot")
        ttk.Label(inner, text=title, style="Role.TLabel").grid(row=0, column=1, sticky="w")
        note = ttk.Label(inner, text="", style="Body.TLabel", wraplength=330, justify="left")
        note.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))
        return inner, light, note

    def _build(self) -> None:
        from tkinter import ttk

        outer = ttk.Frame(self.win, padding=(12, 10, 12, 12))
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)

        ttk.Label(outer, text="F I R S T   R U N", style="Title.TLabel").grid(
            row=0, column=0, sticky="w")
        ttk.Label(outer, text="three things, once", style="Tag.TLabel").grid(
            row=1, column=0, sticky="w")

        # 1 · the key ----------------------------------------------------
        key_box, self.key_light, self.key_note = self._row(outer, 2, "1 · OPENAI KEY")
        self.key_note.configure(text=(
            "chasqui uses your own OpenAI key; OpenAI bills you directly, "
            "about USD 2 an hour of translation. The key stays on this computer."))
        self.var_key = self.tk.StringVar()
        self.entry = ttk.Entry(key_box, textvariable=self.var_key, show="•", style="Key.TEntry")
        self.entry.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        self.entry.bind("<Return>", lambda _e: self._verify())

        keys = ttk.Frame(key_box, style="Panel.TFrame")
        keys.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        keys.columnconfigure(0, weight=1)
        ttk.Button(keys, text="GET A KEY ↗", style="PanelLink.TButton",
                   command=lambda: webbrowser.open(firstrun.KEYS_URL)).grid(
            row=0, column=0, sticky="w")
        self.btn_verify = ttk.Button(keys, text="VERIFY", style="Accent.TButton",
                                     command=self._verify)
        self.btn_verify.grid(row=0, column=1, sticky="e")

        # 2 · the cable --------------------------------------------------
        cable_box, self.cable_light, self.cable_note = self._row(outer, 3, "2 · VIRTUAL CABLE")
        self.cable_note.configure(text="Looking...")
        self.btn_cable = ttk.Button(
            cable_box, text="GET VB-CABLE ↗", style="PanelLink.TButton",
            command=lambda: webbrowser.open(firstrun.CABLE_URL))
        self.btn_cable.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

        # 3 · the switcher -----------------------------------------------
        sw_box, self.switch_light, self.switch_note = self._row(outer, 4, "3 · DEVICE SWITCHER")
        self.switch_note.configure(text="Looking...")
        self.btn_recheck = ttk.Button(sw_box, text="RECHECK", style="Inset.TButton",
                                      command=self._recheck_machine)
        self.btn_recheck.grid(row=2, column=2, sticky="e", pady=(6, 0))

        # done -------------------------------------------------------------
        self.btn_done = ttk.Button(outer, text="DONE · PING", style="Accent.TButton",
                                   command=self._finish, state="disabled")
        self.btn_done.grid(row=5, column=0, sticky="ew", pady=(12, 0))
        ttk.Button(outer, text="LATER", style="Link.TButton", command=self._close).grid(
            row=6, column=0, sticky="w", pady=(4, 0))

        # Someone reopening setup with a key already in place can finish
        # straight away; replacing it is optional.
        if self.owner.base_config.api_key:
            self._paint(self.key_light, skin.C_OK)
            self.key_note.configure(text="A key is already set. Paste another to replace it.")
            self.btn_done.configure(state="normal")

    # ------------------------------------------------------------------

    def _paint(self, light, color: str) -> None:
        light.itemconfigure("dot", fill=color)

    def _later(self, fn, *args) -> None:
        """Hand a worker thread's result to the Tk thread, if still open."""
        if not self._closed:
            self.win.after(0, lambda: None if self._closed else fn(*args))

    def _verify(self) -> None:
        key = self.var_key.get()
        self.btn_verify.configure(state="disabled", text="...")
        self._paint(self.key_light, skin.C_WARN)
        self.key_note.configure(text="Asking OpenAI...")

        def work():
            self._later(self._verified, key, firstrun.check_api_key(key, self.model))

        threading.Thread(target=work, daemon=True).start()

    def _verified(self, key: str, result: firstrun.KeyCheck) -> None:
        self.btn_verify.configure(state="normal", text="VERIFY")
        if not result.usable:
            self._paint(self.key_light, skin.C_ERROR)
            self.key_note.configure(text=result.message)
            return
        try:
            path = firstrun.save_api_key(key)
        except Exception as e:
            self._paint(self.key_light, skin.C_ERROR)
            self.key_note.configure(text=f"Could not save the key: {e}")
            return
        self.key_saved = True
        self.var_key.set("")
        ok = result.status == "ok"
        self._paint(self.key_light, skin.C_OK if ok else skin.C_WARN)
        self.key_note.configure(text=f"{result.message} Saved to {path}.")
        self.btn_done.configure(state="normal")

    def _recheck_machine(self) -> None:
        self.btn_recheck.configure(state="disabled")
        for light, note in ((self.cable_light, self.cable_note),
                            (self.switch_light, self.switch_note)):
            self._paint(light, skin.C_WARN)
            note.configure(text="Looking...")

        def work():
            cable = firstrun.has_virtual_cable()
            switcher = firstrun.has_device_switcher()
            self._later(self._machine_checked, cable, switcher)

        threading.Thread(target=work, daemon=True).start()

    def _machine_checked(self, cable: bool, switcher: bool) -> None:
        self.btn_recheck.configure(state="normal")
        # Amber, not red, when missing: neither blocks the app, only some modes.
        self._paint(self.cable_light, skin.C_OK if cable else skin.C_WARN)
        self.cable_note.configure(text=(
            "Found. Calls can hear your translated voice." if cable else
            "Not found. Calls (Headset) need it to carry your translated voice "
            "into Meet, Zoom or Discord. Install it, restart Windows, then RECHECK."))
        # The download link is only an answer while the cable is missing.
        if cable:
            self.btn_cable.grid_remove()
        else:
            self.btn_cable.grid()
        self._paint(self.switch_light, skin.C_OK if switcher else skin.C_WARN)
        self.switch_note.configure(text=(
            "Found. chasqui can switch your Windows mic and speakers, and put them back."
            if switcher else
            "Not found. Headset and media modes switch your Windows devices with it. "
            f"In PowerShell run: {firstrun.SWITCHER_INSTALL}"))

    def _finish(self) -> None:
        self._close(ping=True)

    def _close(self, ping: bool = False) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.win.grab_release()
        except Exception:
            pass
        self.win.destroy()
        self.on_done(ping)
