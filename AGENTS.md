# AGENTS.md — Chasqui

Chasqui is a real-time simultaneous translation CLI that streams audio through the
OpenAI Realtime API (WebSocket). It captures mic input, sends PCM16 audio to the
API, and plays back translated speech in near real-time.

---

## Architecture

```
chasqui/
  core/
    pipeline.py     ← WebSocket client + audio I/O loop (the heart of the system)
    audio.py        ← MicStream / SpeakerStream / LoopbackStream abstractions
    config.py       ← Config dataclass, loads chasqui.yaml
    session.py      ← Turn log + session export
    constants.py    ← LANG_NAMES, API endpoint URLs
    selftest.py     ← run_check(): TTS → pipeline round trip, no audio hardware
    firstrun.py     ← first-run checks: saved key, key verification, cable, switcher
    pricing.py      ← cost meter: rate table + estimate() over Pipeline.usage
    windevice.py    ← Windows default audio output switcher (PowerShell AudioDeviceCmdlets)
  adapters/
    __init__.py     ← adapter registry (ADAPTER_PATHS, build_adapter) — lazy imports
    base.py         ← BaseAdapter (all adapters inherit from this)
    text.py         ← Text-only demo adapter
    device.py       ← Single physical mic/speaker
    virtual_mic.py  ← Routes output to a virtual mic (VB-Audio Cable)
    media.py        ← System audio loopback translation (YouTube, videos); auto-switches Windows output
    bridge.py       ← Two-device LAN pair mode
    meet.py         ← Thin subclass of BridgeAdapter with Meet-specific instructions
    headset.py      ← Bidirectional via Stereo Mix / Hi-Fi Cable; auto-switches Windows default mic
  ui/
    runner.py       ← Session control for the GUI: worker thread + event queue (no tkinter)
    app.py          ← The Tk window
    icon.py         ← The icon, drawn in code: PNG/ICO written with stdlib only
    wizard.py       ← The setup window (Toplevel) over core/firstrun.py
packaging/
  build_windows.py  ← PyInstaller app folder + Inno Setup installer
  chasqui.iss       ← the installer script (per-user, no admin)
  cli.py            ← Click CLI: listen, ui, translate, check, devices, langs, init
```

**To add a new adapter**: subclass `BaseAdapter`, implement `run()`, call
`self._make_pipeline()` to get a configured `Pipeline`, then add the name to
`adapters/__init__.py > ADAPTER_PATHS` (plus `ADAPTER_LABELS` /
`UI_ADAPTER_NAMES` if it belongs in the GUI). The CLI's `--adapter` choices and
the UI's mode list both read from there.

---

## UI

`chasqui ui` opens a Tkinter window. Two rules keep it from fighting the audio
stack:

- **`ui/runner.py` never imports tkinter.** It owns the worker thread, captures
  stdout while a session runs and pushes `LogLine` / `TurnLine` / `StateChange`
  events onto a queue; `ui/app.py` drains that queue from Tk's main thread every
  100ms. Widgets are only ever touched from the main thread.
- **Stopping goes through `BaseAdapter.stop()`**, the same unwind path as
  Ctrl+C — pipelines stop, `run()` returns, and each adapter's `finally`
  restores the Windows default devices. Closing the window blocks (up to 15s)
  waiting for that, on purpose.

Transcripts reach the UI through `BaseAdapter.on_turn(event, direction)`, not by
parsing the printed log.

### Skin

Dark, blue-cast night with one ice accent (`C_ACCENT = #5ec5e2`, "the cold road
the chasqui runs"), amber for warnings and violet for inbound turns. Mono is the
machine's voice — wordmark, state, buttons, captions; the proportional face is
for what the user picked, above all device names.

Things that are the way they are for a reason:

- **The hexagon is shared.** `hex_points()` in `app.py` and `_in_hexagon()` in
  `icon.py` draw the same silhouette; the status light, the pin glyph (⬢/⬡) and
  the taskbar tile are meant to read as one object. `icon.py > SMALL_ARROW_*` is
  fitted to the hexagon's half-width — `test_arrows_stay_inside_the_hexagon`
  fails if a vertex drifts outside and would be sliced flat.
- **Bump `ICON_VERSION` when the artwork changes**, or every existing user keeps
  the cached `.ico` forever.
- **`ttk.Checkbutton` is not usable here.** Clam draws a white indicator box
  that `indicatorbackground` does not darken; the devices toggle is a
  `PanelLink.TButton` that flips its own `BooleanVar` in `_toggle_devices`.
- **The dark title bar is a DWM call** (`_dark_titlebar`), not a Tk option, and
  it only takes after `update_idletasks()` has given the window a real HWND.
- **Panels are wrappers.** `_panel()` returns `(wrapper, inner)` — grid the
  wrapper (`extras_wrap`, `devices_wrap`), fill the inner. Gridding the inner
  frame directly puts it in the wrong parent and it silently never appears.

---

## Setup

```bash
pip install -e ".[dev]"
export OPENAI_API_KEY=sk-...
```

Config is loaded from `chasqui.yaml` in the working directory (or nearest parent).
Generate a starter file with:

```bash
chasqui init
```

---

## Running

```bash
chasqui listen                              # text adapter, es→ja
chasqui listen --from es --to ja --adapter device
chasqui listen --adapter meet               # bidirectional (needs VB-Audio Cable)
chasqui translate "dónde está el baño"      # one-shot text translation
chasqui devices                             # list audio devices + detect virtual mics
chasqui langs                               # list supported language codes
```

---

## Models

Two API endpoints are supported, selected automatically by model name:

| Model | Endpoint | Notes |
|---|---|---|
| `gpt-realtime-translate` | `/v1/realtime/translate` | Purpose-built, cheaper, no `voice` param |
| `gpt-realtime` / others | `/v1/realtime` | General realtime, uses `instructions` for translation |

The `Pipeline` class detects which mode to use: `"translate" in model`.

---

## Audio format

All streams use **PCM16, mono, 24 kHz** (OpenAI Realtime API requirement).
Audio is base64-encoded before being sent over WebSocket.

---

## Meet adapter (bidirectional)

Requires **VB-Audio Cable** installed:

1. `CABLE Input` → used as the virtual mic in Meet/Zoom (your voice, translated)
2. `CABLE Output` → loopback captures their audio for translation to your earphones

The adapter runs two `Pipeline` instances in parallel threads — one for each direction.
If CABLE devices are not detected automatically, set `device.speaker` in `chasqui.yaml`.

---

## Key gotchas

- **Windows + CJK output**: `cli.py` forces UTF-8 on stdout/stderr at startup. Don't
  remove this — Japanese characters will crash on default Windows consoles.
- **Session events differ by model**: `gpt-realtime-translate` prefixes all events with
  `session.` (e.g. `session.output_audio.delta`). `gpt-realtime` does not. Both are
  handled in `Pipeline._recv_audio`.
- **`pipeline.stop()` is non-blocking**: it sets a `threading.Event`. Callers must join
  threads before exiting or audio devices may not close cleanly.
- **The translate endpoint streams output audio continuously** (silence included) and
  **never emits "done"/completion events**. Utterance boundaries are inferred by a
  watchdog in `Pipeline._recv_audio` from *transcript* delta inactivity (1.2s when the
  source/target pair is complete, up to 5s waiting for the missing side). Do NOT use
  audio deltas as an activity signal.
- **Output transcripts lag input transcripts** by several seconds on the translate
  endpoint — that's why pairing waits for both sides before firing `on_translation`.
- **Conversational drift**: `gpt-realtime-translate` takes no instructions, and with an
  always-on mic it sometimes *answers* instead of translating (e.g. adds 元気だよ to a
  reply). `gpt-realtime` with the built-in interpreter instructions is the
  higher-quality/higher-cost alternative (`api.model` in chasqui.yaml).
  `api.isolate_turns` (gpt-realtime only) goes further: automatic responses
  are off, and each finished transcript is translated by an out-of-band
  `response.create` (`conversation: "none"`, the words quoted as the only
  input), one at a time. On by default. Measured 2026-10-20 with
  `examples/drift_check.py` (10 trap phrases × 3 runs, read by hand): wrong
  turns were translate 5/30 (it merges utterances and drops one), gpt-realtime
  4/30 (one real reply: «¿Llegaste bien?» → うん、大丈夫だよ; "mate" heard as
  待って), isolated 1/30, for ~0.5s more per short turn. Its one failure mode:
  it translates the *transcript*, so a whisper mishearing ("ciste" for
  "chiste") is translated faithfully. The script's text-model judge is a
  helper, not the measure; it still mislabels some turns.
- **`CHASQUI_DEBUG=1`** prints every server event type, audio delta counts, and flush
  decisions — first thing to reach for when audio flows but transcripts don't.
- **Windows device names come in two lengths**: PowerShell/AudioDeviceCmdlets report
  full names ("CABLE Output (VB-Audio Virtual Cable)") but PortAudio truncates to
  ~31 chars on MME. Pass names through `core.audio.resolve_device()` before giving
  them to `MicStream`/`SpeakerStream`, or the lookup silently fails.
- **Raw name strings crash sounddevice**: every device exists 3-4× (MME/DirectSound/
  WASAPI/WDM-KS), so `sd.InputStream(device="Micrófono (HyperX ...)")` dies with
  "Multiple input devices found". `resolve_device()` returns a single index —
  ALL user-provided device values (`--mic`, `--earphone`, `--loopback`,
  chasqui.yaml) must go through it.
- **Never pin device indices in chasqui.yaml** — Windows MME reorders indices when
  the default device changes (the default jumps to the first slot of its type), and
  chasqui's own adapters switch defaults at startup (media: output, headset: input).
  Use names; `resolve_device()` maps them at start.
- **The renumbering happens LIVE, mid-process** — waveIn/waveOut IDs shift the
  moment the default changes, but PortAudio keeps its stale snapshot, so an index
  resolved *before* a switch opens a *different* device after it (verified: the
  headset adapter's real-mic index pointed at CABLE Output post-switch → chasqui
  listened to its own output and heard nothing). Rule: **switch the default first,
  then `refresh_devices()` (re-inits PortAudio), then resolve names to indices.**
  Never call `refresh_devices()` while streams are open.
- **PowerShell output must be decoded as UTF-8** (`core/windevice.py` forces it on
  both sides). With the default cp1252 decode, "Micrófono" came back as
  "MicrÃ³fono", which made the default-mic *restore* silently no-op (the `-like`
  match found nothing) and broke `resolve_device()` on the default-mic name.
- **MME capture of CABLE Output can read pure noise while other streams are open**
  (seen with 4+ concurrent streams in one process). Real apps capture via
  WASAPI/DirectSound and hear the audio fine — verify with a DirectSound-index
  capture before concluding the cable is silent.
- **gpt-realtime (GA) rejects the old beta session fields** ("Unknown parameter:
  'session.modalities'"): voice/formats/turn_detection now live under
  `output_modalities` + `audio.input`/`audio.output` (see
  `Pipeline._build_realtime_session`).
- **`gpt-realtime-translate` is billed by DURATION, not tokens** ($0.034/min as
  of 2026-07-25). That is *why* it never sends `response.done` — that event
  carries the `usage` object, and there is nothing to report per response when
  the meter is a clock. So the cost meter counts the audio bytes chasqui
  streams (`Pipeline.usage`), and only reads `usage` events for `gpt-realtime`,
  which does bill by tokens. **Bidirectional modes run two pipelines = two
  billed streams**; anything summing cost must add both or it reports half.
  The `gpt-realtime-whisper` input transcription ($0.017/min) **stacks on
  top** (measured 2026-10-21: a timed session billed as two dashboard line
  items), so the real price is **$0.051/min per direction, $0.102 two-way**.
  It cannot be dropped to save money: the transcript is what the UI shows
  and what the utterance watchdog listens to.
- **The translate endpoint needs ~3s of trailing audio to finish a sentence.**
  It releases the end of a translation only while input keeps arriving. The
  silence gate (`core/gate.py`) therefore holds open 3s after the last sound:
  with 1.5-2s the last words of each turn came out at the start of the next
  one. Measured with `examples/gate_check.py` (2026-10-20): 3s hold kept all
  turns complete and streamed ~52% fewer minutes on a call-like pattern.
- **There is no OpenAI endpoint for remaining credit balance.** `/v1/organization/costs`
  gives spend (not balance) and needs an *admin* key, which does not belong in
  a chasqui.yaml. "Remaining" in the UI is the user's own `pricing.budget`.
- **Never set `iconphoto` AND `iconbitmap` on the same Tk window.** Each works
  alone; together Tk falls back to its own default icon with no error and no
  warning — you just get the wrong picture (verified on Tk 8.6.15, Windows).
  `ui/app.py > _apply_icon` picks exactly one: the `.ico` on Windows, the
  in-memory PhotoImage elsewhere.
- **`chasqui ui` is a console script and always opens a console** when launched
  by double-click (measured: 1 new `ConsoleWindowClass` window; from a terminal
  it reuses that one, which is why it looks fine in development). The windowed
  door is `chasqui-ui`, declared under `[project.gui-scripts]` — that is what
  the desktop shortcut points at. Removing that block silently brings the
  console back for every shortcut user.
- **`pythonw.exe` has no `sys.stdout` or `sys.stderr` at all** (the desktop
  shortcut launches the UI through it so no console tags along). Anything that
  touches a stream attribute at import time must guard for `None` — the
  unguarded `sys.stdout.encoding` in `cli.py` made double-clicking the desktop
  icon do nothing at all, with no console to show the traceback.
- **The UI redirects `sys.stdout` process-wide** while a session runs (adapters
  only communicate by printing). It is restored in a `finally`; if you add an
  early return there, every later print in the process disappears into a dead
  queue. It tees to the previous stdout, not `sys.__stdout__` — the raw one
  still dies on Japanese.
- **The distribution is `chasqui-translate`, not `chasqui`** — that name is
  taken on PyPI by an unrelated project. The import package and the `chasqui`
  console script keep the short name. Anything that looks the package up by
  distribution name (`click.version_option(package_name=...)`,
  `importlib.metadata`) must use `chasqui-translate`, or `chasqui --version`
  crashes with PackageNotFoundError.
- **The setup window saves the key to `~/.chasqui/config.yaml`** and
  `load_config()` reads it only as a last resort (after the yaml's own key and
  `OPENAI_API_KEY`). It never writes into a project `chasqui.yaml`: that file
  may live in a repo. `firstrun.check_api_key` hits `GET /v1/models/{model}`,
  which is free: 401 bad key, 404 key without access to that model.
- **`load_dotenv()` walks up from `core/config.py`, not from the cwd.** In a
  source checkout it finds the repo's `.env` wherever you run from, so a test
  of "no key" must clear `OPENAI_API_KEY` *after* importing chasqui.
- **The installed app bundles AudioDeviceCmdlets** (`packaging/build_windows.py`
  copies it from the build machine, MIT license alongside). `windevice` imports
  it from `sys._MEIPASS` when frozen; a pip install keeps using the user's own.
  Every PowerShell call passes `CREATE_NO_WINDOW`: from the windowed exe each
  call would otherwise flash a console.
- **AudioDeviceCmdlets params are `-Recording` / `-Playback`** (they return the
  *default* device of that type). `-RecordingDefault` does not exist — it fails with
  AmbiguousParameterSet, and a bare `except` made the headset mic auto-switch a
  silent no-op for weeks. Default-device switching lives in `core/windevice.py`; use
  it instead of inlining PowerShell.
- **The release installer is built by CI, not by hand** (`.github/workflows/windows.yml`,
  on release published). SignPath Foundation signing requires that, so do not
  attach a locally built `.exe` to a release. On the runner AudioDeviceCmdlets
  is installed `-Scope AllUsers`: the build step runs under pwsh 7, whose
  PSModulePath leaks into the `powershell` 5.1 that `build_windows.py` spawns
  and hides the CurrentUser module folder (first CI run failed on exactly that).
- **Download links never name a version.** The release job attaches the
  installer twice, `chasqui-setup-<version>.exe` and the same bytes as
  `chasqui-setup.exe`, and the landing and READMEs point at
  `releases/latest/download/chasqui-setup.exe`. The landing's JSON-LD reads
  `softwareVersion` from `chasqui/__init__.py`. (v0.3.0 got its copy by hand.)

---

## Testing / development

```bash
# Run a quick text translation (no mic needed)
chasqui listen --adapter text

# Check audio device indices before configuring chasqui.yaml
chasqui devices
```

Unit tests live in `tests/` (no network or audio hardware required):

```bash
pip install -e ".[dev]"
pytest
```

The `examples/` directory has standalone scripts for audio and virtual mic testing.
