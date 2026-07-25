"""The chasqui window: start/stop, languages, devices, check, live transcript.

Tkinter on purpose — it ships with Python, so the UI adds no dependency and
`chasqui ui` works on a fresh install. All the session logic lives in
`runner.py`; this module only draws and forwards clicks.
"""

import json
import sys
import time
from pathlib import Path
from typing import Optional

from ..adapters import ADAPTER_LABELS, UI_ADAPTER_NAMES
from ..core.config import Config, find_config, load_config
from ..core.constants import LANG_NAMES
from .runner import ACCENT, CheckDone, ERROR, INFO, LogLine, SessionRunner, StateChange, TurnLine, WARN

VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]

SETTINGS_PATH = Path.home() / ".chasqui" / "ui.json"

# Which device pickers matter per adapter — the rest are greyed out so the
# panel stops looking like four questions the user has to answer.
ADAPTER_DEVICES: dict[str, set[str]] = {
    "headset":     {"mic", "speaker", "earphone", "loopback"},
    "meet":        {"mic", "speaker", "earphone", "loopback"},
    "bridge":      {"mic", "speaker", "earphone", "loopback"},
    "virtual-mic": {"mic", "speaker", "earphone"},
    "media":       {"earphone", "loopback"},
    "device":      {"mic", "speaker", "earphone"},
}

# What the two language pickers MEAN, per mode. They are always
# (source_lang, target_lang) underneath, but "I speak" is a nonsense question
# in media mode — there the machine talks and you listen, so asking it that way
# gets the pair set backwards and the translation comes out in the language you
# already understand.
LANG_ROLES: dict[str, tuple[str, str]] = {
    "headset":     ("I speak", "They speak"),
    "meet":        ("I speak", "They speak"),
    "bridge":      ("I speak", "They speak"),
    "virtual-mic": ("I speak", "They hear"),
    "device":      ("I speak", "They hear"),
    "media":       ("Audio is in", "I hear"),
}
DEFAULT_ROLES = ("I speak", "They hear")

DEVICE_FIELDS = [
    ("mic",      "Microphone",   "Your voice goes in here",          "input"),
    ("speaker",  "App input",    "Virtual cable the app listens to",  "output"),
    ("earphone", "You hear",     "Where the translation reaches you", "output"),
    ("loopback", "App output",   "Capture of what the app is saying", "input"),
]

AUTO = "Auto"

# Palette. Dark on purpose: the log is the centre of the window and reads like
# a console, and the app is meant to sit next to a call, not compete with it.
C_BG      = "#15161a"
C_PANEL   = "#1d1f26"
C_BORDER  = "#2c2f39"
C_TEXT    = "#e9e9ee"
C_MUTED   = "#8b8e9b"
C_DISABLED = "#4c4f5c"
C_ACCENT  = "#e2683d"   # terracotta — the chasqui's road
C_OK      = "#4ec9a0"
C_WARN    = "#e2b33d"
C_ERROR   = "#e8615d"
C_IN      = "#6aa8f0"

LEVEL_COLORS = {INFO: C_TEXT, ACCENT: C_ACCENT, WARN: C_WARN, ERROR: C_ERROR}

STATE_COLORS = {
    "idle":     (C_MUTED,  "Idle"),
    "starting": (C_WARN,   "Starting..."),
    "running":  (C_OK,     "Running"),
    "stopping": (C_WARN,   "Stopping..."),
    "checking": (C_WARN,   "Checking..."),
    "error":    (C_ERROR,  "Error"),
}


def _lang_choices() -> list[str]:
    return [f"{name} ({code})" for code, name in sorted(LANG_NAMES.items(), key=lambda kv: kv[1])]


def _lang_label(code: str) -> str:
    return f"{LANG_NAMES.get(code, code)} ({code})"


def _lang_code(label: str) -> str:
    return label.rsplit("(", 1)[-1].rstrip(")") if "(" in label else label


def list_devices(kind: str) -> list[str]:
    """Unique device names of one kind, in PortAudio order.

    Names, never indices: every device shows up 3-4 times (MME/DirectSound/
    WASAPI/WDM-KS) and Windows renumbers indices whenever a default changes —
    `resolve_device()` maps a name to the right index at start time.
    """
    try:
        import sounddevice as sd
    except Exception:
        return []

    channel_key = "max_input_channels" if kind == "input" else "max_output_channels"
    seen: list[str] = []
    try:
        for device in sd.query_devices():
            name = device["name"].strip()
            if name and device[channel_key] > 0 and name not in seen:
                seen.append(name)
    except Exception:
        return []
    return seen


class ChasquiApp:
    """The main window."""

    def __init__(self, tk_module, config_path: Optional[str] = None):
        self.tk = tk_module
        self.config_path = config_path
        self.base_config = load_config(config_path)
        self.runner = SessionRunner()
        self.state = "idle"
        self.turns = 0
        self.latency_total = 0.0
        self._close_deadline = 0.0
        self._devices_loaded = False

        self.root = tk_module.Tk()
        self._build()
        self._load_settings()
        self._on_adapter_change()
        self._tick()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build(self) -> None:
        from tkinter import ttk

        root = self.root
        root.title("chasqui")
        root.configure(bg=C_BG)
        root.minsize(620, 560)
        root.geometry("720x680")
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        ui_font = "Segoe UI" if sys.platform == "win32" else "TkDefaultFont"
        mono_font = "Consolas" if sys.platform == "win32" else "TkFixedFont"
        self.mono = (mono_font, 10)

        style = ttk.Style(root)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(".", background=C_BG, foreground=C_TEXT, font=(ui_font, 10))
        style.configure("TFrame", background=C_BG)
        style.configure("Panel.TFrame", background=C_PANEL)
        style.configure("TLabel", background=C_BG, foreground=C_TEXT)
        style.configure("Panel.TLabel", background=C_PANEL, foreground=C_TEXT)
        style.configure("Muted.TLabel", background=C_BG, foreground=C_MUTED, font=(ui_font, 9))
        style.configure("PanelMuted.TLabel", background=C_PANEL, foreground=C_MUTED, font=(ui_font, 9))
        style.configure("Title.TLabel", background=C_BG, foreground=C_TEXT, font=(ui_font, 17, "bold"))
        style.configure("Role.TLabel", background=C_PANEL, foreground=C_ACCENT, font=(ui_font, 9, "bold"))
        style.configure("Status.TLabel", background=C_BG, foreground=C_MUTED, font=(ui_font, 10))

        style.configure(
            "TCombobox", fieldbackground=C_PANEL, background=C_PANEL, foreground=C_TEXT,
            arrowcolor=C_MUTED, bordercolor=C_BORDER, lightcolor=C_PANEL, darkcolor=C_PANEL,
            selectbackground=C_PANEL, selectforeground=C_TEXT, padding=5,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", C_PANEL), ("disabled", C_BG)],
            foreground=[("disabled", C_DISABLED)],
            arrowcolor=[("disabled", C_DISABLED)],
            bordercolor=[("focus", C_ACCENT)],
        )
        root.option_add("*TCombobox*Listbox.background", C_PANEL)
        root.option_add("*TCombobox*Listbox.foreground", C_TEXT)
        root.option_add("*TCombobox*Listbox.selectBackground", C_ACCENT)
        root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

        for name, bg, fg in (
            ("Accent.TButton", C_ACCENT, "#ffffff"),
            ("Stop.TButton", C_ERROR, "#ffffff"),
            ("Ghost.TButton", C_PANEL, C_TEXT),
            # Sits on a panel, so it needs to be lighter than one to read as a button.
            ("Inset.TButton", C_BORDER, C_TEXT),
        ):
            style.configure(
                name, background=bg, foreground=fg, bordercolor=C_BORDER,
                lightcolor=bg, darkcolor=bg, focuscolor=bg,
                font=(ui_font, 10, "bold"), padding=(16, 9), relief="flat",
            )
            style.map(
                name,
                background=[("active", bg), ("disabled", C_PANEL)],
                foreground=[("disabled", C_MUTED)],
            )

        style.configure(
            "Swap.TButton", background=C_PANEL, foreground=C_TEXT, bordercolor=C_BORDER,
            lightcolor=C_PANEL, darkcolor=C_PANEL, focuscolor=C_PANEL,
            padding=(6, 6), font=(ui_font, 11), relief="flat",
        )
        style.map(
            "Swap.TButton",
            background=[("active", C_BORDER), ("disabled", C_PANEL)],
            foreground=[("disabled", C_MUTED)],
        )
        style.configure(
            "TScrollbar", background=C_PANEL, troughcolor=C_BG, bordercolor=C_BORDER,
            arrowcolor=C_MUTED, lightcolor=C_PANEL, darkcolor=C_PANEL,
        )
        style.map("TScrollbar", background=[("active", C_BORDER)])

        style.configure(
            "Panel.TCheckbutton", background=C_PANEL, foreground=C_MUTED,
            focuscolor=C_PANEL, font=(ui_font, 9), padding=(0, 2),
            indicatorbackground=C_PANEL, indicatorforeground=C_ACCENT,
            bordercolor=C_BORDER, lightcolor=C_PANEL, darkcolor=C_PANEL,
        )
        style.map(
            "Panel.TCheckbutton",
            background=[("active", C_PANEL)],
            foreground=[("active", C_TEXT)],
            indicatorbackground=[("selected", C_PANEL), ("active", C_PANEL)],
        )

        outer = ttk.Frame(root, padding=(18, 16, 18, 14))
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)

        # --- header -------------------------------------------------
        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)

        ttk.Label(header, text="chasqui", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header, text="Speak your language. Be understood.", style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(1, 0))

        status = ttk.Frame(header)
        status.grid(row=0, column=2, rowspan=2, sticky="e")
        self.status_dot = self.tk.Canvas(
            status, width=10, height=10, bg=C_BG, highlightthickness=0,
        )
        self.status_dot.grid(row=0, column=0, padx=(0, 7))
        self._dot = self.status_dot.create_oval(1, 1, 9, 9, fill=C_MUTED, outline="")
        self.status_label = ttk.Label(status, text="Idle", style="Status.TLabel")
        self.status_label.grid(row=0, column=1)

        # --- settings -----------------------------------------------
        settings = ttk.Frame(outer, style="Panel.TFrame", padding=14)
        settings.grid(row=1, column=0, sticky="ew", pady=(16, 0))
        settings.columnconfigure(1, weight=1)
        settings.columnconfigure(3, weight=1)

        langs = _lang_choices()
        self.var_source = self.tk.StringVar(value=_lang_label(self.base_config.source_lang))
        self.var_target = self.tk.StringVar(value=_lang_label(self.base_config.target_lang))

        # Captions sit ABOVE the pickers and change with the mode: which box is
        # "yours" is the one thing a user must not have to guess.
        self.lbl_source_role = ttk.Label(settings, text="", style="Role.TLabel")
        self.lbl_source_role.grid(row=0, column=1, sticky="w", pady=(0, 3))
        self.lbl_target_role = ttk.Label(settings, text="", style="Role.TLabel")
        self.lbl_target_role.grid(row=0, column=3, sticky="w", pady=(0, 3))

        ttk.Label(settings, text="Languages", style="PanelMuted.TLabel").grid(
            row=1, column=0, sticky="w", padx=(0, 10))
        self.cmb_source = ttk.Combobox(
            settings, textvariable=self.var_source, values=langs, state="readonly", width=18)
        self.cmb_source.grid(row=1, column=1, sticky="ew")

        self.btn_swap = ttk.Button(
            settings, text="⇄", width=3, style="Swap.TButton", command=self._swap_langs)
        self.btn_swap.grid(row=1, column=2, padx=10)

        self.cmb_target = ttk.Combobox(
            settings, textvariable=self.var_target, values=langs, state="readonly", width=18)
        self.cmb_target.grid(row=1, column=3, sticky="ew")

        ttk.Label(settings, text="Mode", style="PanelMuted.TLabel").grid(
            row=2, column=0, sticky="w", pady=(12, 0))
        self.var_adapter = self.tk.StringVar()
        self.cmb_adapter = ttk.Combobox(
            settings, textvariable=self.var_adapter, state="readonly",
            values=[ADAPTER_LABELS[name] for name in UI_ADAPTER_NAMES])
        self.cmb_adapter.grid(row=2, column=1, columnspan=3, sticky="ew", pady=(12, 0))
        self.cmb_adapter.bind("<<ComboboxSelected>>", lambda _e: self._on_adapter_change())
        self.var_adapter.set(ADAPTER_LABELS.get(
            self.base_config.adapter if self.base_config.adapter in UI_ADAPTER_NAMES else "headset",
            ADAPTER_LABELS["headset"]))

        ttk.Label(settings, text="Voice", style="PanelMuted.TLabel").grid(
            row=3, column=0, sticky="w", pady=(12, 0))
        self.var_voice = self.tk.StringVar(value=self.base_config.voice)
        self.cmb_voice = ttk.Combobox(
            settings, textvariable=self.var_voice, values=VOICES, state="readonly", width=18)
        self.cmb_voice.grid(row=3, column=1, sticky="ew", pady=(12, 0))

        self.var_show_devices = self.tk.BooleanVar(value=False)
        ttk.Checkbutton(
            settings, text="Audio devices", variable=self.var_show_devices,
            command=self._toggle_devices, style="Panel.TCheckbutton",
        ).grid(row=3, column=3, sticky="e", pady=(12, 0), padx=(0, 2))

        # --- devices (collapsed) -------------------------------------
        self.devices_frame = ttk.Frame(outer, style="Panel.TFrame", padding=14)
        self.devices_frame.columnconfigure(1, weight=1)
        self.device_vars: dict[str, "object"] = {}
        self.device_widgets: dict[str, object] = {}

        for row, (key, label, hint, kind) in enumerate(DEVICE_FIELDS):
            ttk.Label(self.devices_frame, text=label, style="PanelMuted.TLabel").grid(
                row=row, column=0, sticky="w", pady=4, padx=(0, 10))
            var = self.tk.StringVar(value=AUTO)
            combo = ttk.Combobox(
                self.devices_frame, textvariable=var, values=[AUTO], state="readonly")
            combo.grid(row=row, column=1, sticky="ew", pady=4)
            ttk.Label(self.devices_frame, text=hint, style="PanelMuted.TLabel").grid(
                row=row, column=2, sticky="w", padx=(12, 0))
            self.device_vars[key] = var
            self.device_widgets[key] = combo

        ttk.Button(
            self.devices_frame, text="Refresh", style="Inset.TButton",
            command=lambda: self._load_device_lists(force=True),
        ).grid(row=len(DEVICE_FIELDS), column=1, sticky="w", pady=(10, 0))
        ttk.Label(
            self.devices_frame,
            text="Auto works for most setups — chasqui finds the cables itself.",
            style="PanelMuted.TLabel",
        ).grid(row=len(DEVICE_FIELDS), column=2, sticky="w", padx=(12, 0), pady=(10, 0))

        # --- actions --------------------------------------------------
        actions = ttk.Frame(outer)
        actions.grid(row=3, column=0, sticky="ew", pady=(16, 0))

        self.btn_start = ttk.Button(
            actions, text="Start", style="Accent.TButton", command=self._on_start_stop)
        self.btn_start.grid(row=0, column=0)

        self.btn_check = ttk.Button(
            actions, text="Check", style="Ghost.TButton", command=self._on_check)
        self.btn_check.grid(row=0, column=1, padx=(10, 0))

        self.btn_clear = ttk.Button(
            actions, text="Clear log", style="Ghost.TButton", command=self._clear_log)
        self.btn_clear.grid(row=0, column=2, padx=(10, 0))

        # --- log ------------------------------------------------------
        log_wrap = self.tk.Frame(outer, bg=C_BORDER, bd=0, highlightthickness=0)
        log_wrap.grid(row=4, column=0, sticky="nsew", pady=(16, 0))
        outer.rowconfigure(4, weight=1)

        self.log = self.tk.Text(
            log_wrap, bg=C_PANEL, fg=C_TEXT, insertbackground=C_TEXT, font=self.mono,
            wrap="word", relief="flat", padx=12, pady=10, height=12, state="disabled",
            selectbackground=C_ACCENT,
        )
        scroll = ttk.Scrollbar(log_wrap, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side="left", fill="both", expand=True, padx=1, pady=1)
        scroll.pack(side="right", fill="y")

        for level, color in LEVEL_COLORS.items():
            self.log.tag_configure(level, foreground=color)
        self.log.tag_configure("src", foreground=C_MUTED)
        self.log.tag_configure("out", foreground=C_TEXT, font=(mono_font, 11, "bold"))
        self.log.tag_configure("in", foreground=C_IN, font=(mono_font, 11, "bold"))
        self.log.tag_configure("meta", foreground=C_MUTED, font=(mono_font, 8))

        # --- footer ---------------------------------------------------
        self.footer = ttk.Label(outer, text="", style="Muted.TLabel")
        self.footer.grid(row=5, column=0, sticky="w", pady=(10, 0))
        self._update_footer()

        source = self.config_path or find_config()
        self._log(f"Config: {source or 'built-in defaults (no chasqui.yaml found)'}", INFO)
        if not self.base_config.api_key:
            self._log(
                "No API key. Set OPENAI_API_KEY, or api.key in chasqui.yaml, then reopen.",
                ERROR,
            )

    # ------------------------------------------------------------------
    # Settings persistence
    # ------------------------------------------------------------------

    def _load_settings(self) -> None:
        """Restore the last used selections. Absent or broken file → defaults."""
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return
        if code := data.get("source_lang"):
            self.var_source.set(_lang_label(code))
        if code := data.get("target_lang"):
            self.var_target.set(_lang_label(code))
        if (adapter := data.get("adapter")) in ADAPTER_LABELS:
            self.var_adapter.set(ADAPTER_LABELS[adapter])
        if (voice := data.get("voice")) in VOICES:
            self.var_voice.set(voice)
        for key, value in (data.get("devices") or {}).items():
            if key in self.device_vars and value:
                self.device_vars[key].set(value)
                widget = self.device_widgets[key]
                widget.configure(values=[AUTO, value])

    def _save_settings(self) -> None:
        data = {
            "source_lang": _lang_code(self.var_source.get()),
            "target_lang": _lang_code(self.var_target.get()),
            "adapter": self._adapter_name(),
            "voice": self.var_voice.get(),
            "devices": {
                key: var.get() for key, var in self.device_vars.items() if var.get() != AUTO
            },
        }
        try:
            SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass  # a UI preference is never worth failing a session over

    # ------------------------------------------------------------------
    # Widgets → config
    # ------------------------------------------------------------------

    def _adapter_name(self) -> str:
        label = self.var_adapter.get()
        for name, text in ADAPTER_LABELS.items():
            if text == label:
                return name
        return "headset"

    def _build_config(self) -> Config:
        """Fresh config from disk, with the window's selections on top."""
        cfg = load_config(self.config_path)
        cfg.source_lang = _lang_code(self.var_source.get())
        cfg.target_lang = _lang_code(self.var_target.get())
        cfg.adapter = self._adapter_name()
        cfg.voice = self.var_voice.get()

        active = ADAPTER_DEVICES.get(cfg.adapter, set())
        for key, var in self.device_vars.items():
            value = var.get()
            if key in active and value and value != AUTO:
                setattr(cfg.device, key, value)
        return cfg

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_adapter_change(self) -> None:
        adapter = self._adapter_name()

        source_role, target_role = LANG_ROLES.get(adapter, DEFAULT_ROLES)
        self.lbl_source_role.configure(text=source_role)
        self.lbl_target_role.configure(text=target_role)

        active = ADAPTER_DEVICES.get(adapter, set())
        for key, widget in self.device_widgets.items():
            widget.configure(state="readonly" if key in active else "disabled")

    def _toggle_devices(self) -> None:
        if self.var_show_devices.get():
            self.devices_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
            self._load_device_lists()
        else:
            self.devices_frame.grid_remove()

    def _load_device_lists(self, force: bool = False) -> None:
        if self._devices_loaded and not force:
            return
        self._devices_loaded = True
        by_kind = {"input": list_devices("input"), "output": list_devices("output")}
        for key, _label, _hint, kind in DEVICE_FIELDS:
            current = self.device_vars[key].get()
            values = [AUTO] + by_kind[kind]
            if current not in values:
                values.append(current)   # keep a saved name that is unplugged today
            self.device_widgets[key].configure(values=values)
        if not by_kind["input"] and not by_kind["output"]:
            self._log("No audio devices found — is sounddevice installed?", WARN)

    def _swap_langs(self) -> None:
        source, target = self.var_source.get(), self.var_target.get()
        self.var_source.set(target)
        self.var_target.set(source)

    def _on_start_stop(self) -> None:
        if self.runner.is_running:
            self.runner.stop()
            return

        source, target = _lang_code(self.var_source.get()), _lang_code(self.var_target.get())
        if source == target:
            self._log("Source and target language are the same — nothing to translate.", ERROR)
            return

        self._save_settings()
        try:
            self.runner.start(self._build_config())
        except ValueError as e:            # missing API key
            self._log(str(e), ERROR)
            self._set_state("error")
        except Exception as e:
            self._log(f"Could not start: {e}", ERROR)
            self._set_state("error")

    def _on_check(self) -> None:
        if self.runner.is_busy:
            return
        self._save_settings()
        cfg = self._build_config()
        self._log("")
        self._log(f"Check — {cfg.source_lang} → {cfg.target_lang} via {cfg.model}", ACCENT)
        try:
            self.runner.start_check(cfg)
            self._set_state("checking")
        except ValueError as e:
            self._log(str(e), ERROR)
            self._set_state("error")

    def _clear_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _on_close(self) -> None:
        if not self.runner.is_running:
            self._save_settings()
            self.root.destroy()
            return
        # Never kill a live session: the headset and media adapters put the
        # user's Windows default mic/output back on their way out, and skipping
        # that leaves the machine talking to a virtual cable after chasqui quits.
        self._set_state("stopping")
        self._log("Stopping — restoring your Windows audio devices...", ACCENT)
        self.runner.stop()
        self._close_deadline = time.time() + 15
        self._poll_close()

    def _poll_close(self) -> None:
        self._pump()
        if not self.runner.is_running or time.time() > self._close_deadline:
            self._save_settings()
            self.root.destroy()
        else:
            self.root.after(120, self._poll_close)

    # ------------------------------------------------------------------
    # Event pump
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        self._pump()
        self.root.after(100, self._tick)

    def _pump(self) -> None:
        for event in self.runner.drain():
            if isinstance(event, LogLine):
                if event.text.strip():
                    self._log(event.text, event.level)
            elif isinstance(event, TurnLine):
                self._log_turn(event)
            elif isinstance(event, CheckDone):
                self._log_check(event.result)
            elif isinstance(event, StateChange):
                self._on_state_event(event)

    def _on_state_event(self, event: StateChange) -> None:
        if event.state == "starting":
            self.turns = 0
            self.latency_total = 0.0
            self._set_state("starting")
        elif event.state in ("stopped", "check_done"):
            self._set_state("idle")
            if event.state == "stopped":
                self._log("Session ended.", ACCENT)
        elif event.state == "error":
            self._set_state("error")
            self._log(f"Session error: {event.detail}", ERROR)
        else:
            self._set_state(event.state)

    def _set_state(self, state: str) -> None:
        self.state = state
        color, text = STATE_COLORS.get(state, (C_MUTED, state.title()))
        self.status_dot.itemconfigure(self._dot, fill=color)
        self.status_label.configure(text=text, foreground=color)

        running = state in ("running", "starting", "stopping")
        self.btn_start.configure(
            text="Stop" if running else "Start",
            style="Stop.TButton" if running else "Accent.TButton",
            state="disabled" if state in ("stopping", "checking") else "normal",
        )
        self.btn_check.configure(state="disabled" if running or state == "checking" else "normal")

        locked = "disabled" if running or state == "checking" else "readonly"
        for widget in (self.cmb_source, self.cmb_target, self.cmb_adapter, self.cmb_voice):
            widget.configure(state=locked)
        self.btn_swap.configure(state="disabled" if running or state == "checking" else "normal")
        if locked == "disabled":
            for widget in self.device_widgets.values():
                widget.configure(state="disabled")
        else:
            self._on_adapter_change()

    # ------------------------------------------------------------------
    # Log rendering
    # ------------------------------------------------------------------

    def _log(self, text: str, level: str = INFO) -> None:
        at_bottom = self.log.yview()[1] > 0.99
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n", level)
        self.log.configure(state="disabled")
        if at_bottom:
            self.log.see("end")

    def _log_turn(self, turn: TurnLine) -> None:
        self.turns += 1
        self.latency_total += turn.latency_ms

        arrow = "→" if turn.direction == "out" else "←"
        at_bottom = self.log.yview()[1] > 0.99
        self.log.configure(state="normal")
        self.log.insert("end", f"\n{arrow} {turn.source_text}\n", "src")
        self.log.insert("end", f"  {turn.target_text}\n", turn.direction)
        self.log.insert("end", f"  {turn.latency_ms:.0f}ms\n", "meta")
        self.log.configure(state="disabled")
        if at_bottom:
            self.log.see("end")
        self._update_footer()

    def _log_check(self, result) -> None:
        if result.ok:
            self._log(f"  {result.source_text}", INFO)
            self._log(f"  {result.target_text}", ACCENT)
            self._log(f"  PASS — {result.latency_ms:.0f}ms round trip", ACCENT)
        else:
            self._log(f"  FAIL — {result.error}", ERROR)

    def _update_footer(self) -> None:
        average = self.latency_total / self.turns if self.turns else 0.0
        self.footer.configure(
            text=f"{self.base_config.model}   ·   {self.turns} turns   ·   avg {average:.0f}ms"
        )

    # ------------------------------------------------------------------

    def run(self) -> None:
        self.root.mainloop()


def launch(config_path: Optional[str] = None) -> int:
    """Open the window. Returns a process exit code."""
    try:
        import tkinter
    except ImportError:
        print(
            "The chasqui UI needs tkinter, which is missing from this Python.\n"
            "  Windows/macOS: reinstall Python from python.org (tkinter is included)\n"
            "  Debian/Ubuntu: sudo apt install python3-tk",
            file=sys.stderr,
        )
        return 1

    ChasquiApp(tkinter, config_path=config_path).run()
    return 0
