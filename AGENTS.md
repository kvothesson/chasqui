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
  adapters/
    base.py         ← BaseAdapter (all adapters inherit from this)
    text.py         ← Text-only demo adapter
    device.py       ← Single physical mic/speaker
    virtual_mic.py  ← Routes output to a virtual mic (VB-Audio Cable)
    media.py        ← Translates a media file
    bridge.py       ← Two-device LAN pair mode
    meet.py         ← Bidirectional translation for Google Meet / Zoom
  cli.py            ← Click CLI: listen, translate, devices, langs, init
```

**To add a new adapter**: subclass `BaseAdapter`, implement `run()`, call
`self._make_pipeline()` to get a configured `Pipeline`, then register the name in
`cli.py > _run_adapter > adapter_map`.

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

---

## Testing / development

```bash
# Run a quick text translation (no mic needed)
chasqui listen --adapter text

# Check audio device indices before configuring chasqui.yaml
chasqui devices
```

There is no automated test suite yet. The `examples/` directory has standalone scripts
for audio and virtual mic testing.
