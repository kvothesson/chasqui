# chasqui

> *"El chasqui corría cientos de kilómetros llevando un mensaje que no podía leer.*
> *Transmitía sin entender. Conectaba sin pertenecer."*

Real-time simultaneous translation. Speak your language. Be understood.

## Quick start

Not on PyPI yet (the name `chasqui` there belongs to an unrelated project), so
install from source:

```bash
git clone https://github.com/kvothesson/chasqui && cd chasqui
pip install -e .
export OPENAI_API_KEY=sk-...
chasqui ui           # desktop interface
chasqui listen --from es --to ja    # or straight to the CLI
```

## Interface

`chasqui ui` opens a window: pick the two languages and a mode, press Start,
and watch the conversation land in the transcript as it happens. Check runs the
same smoke test as `chasqui check` — no mic, no speakers, just "is the pipeline
alive". Audio devices stay on **Auto**; open the devices panel only if
autodetection picks the wrong cable.

Stopping matters more than it looks: the headset and media modes take over your
Windows default mic and output while they run and hand them back on exit, so use
Stop (or just close the window — it waits for the handover) instead of killing
the process.

The footer keeps a running cost. `gpt-realtime-translate` bills by the minute,
so chasqui counts the audio it streams and prices it — and a bidirectional
session pays for two directions at once, which is worth seeing before a long
call. Set `pricing.budget` in chasqui.yaml to get "$X left" alongside it.

> OpenAI exposes no API for your remaining credit balance, so that budget is
> your own number, tracked locally — not a reading of your account.

Tkinter ships with Python, so the UI adds no dependency. On Debian/Ubuntu it
lives in a separate package: `sudo apt install python3-tk`.

## Adapters

| Adapter | Use case | Status |
|---|---|---|
| `text` | Keyboard in, terminal out — silent mode, accessibility, testing | ✅ Working |
| `virtual-mic` | Google Meet, Zoom, Teams, ChatGPT Voice (one-way: your voice, translated) | ✅ Working — validated end-to-end with ChatGPT Voice |
| `bridge` / `meet` | Bidirectional translation for any voice app (needs VB-Audio Cable) | OUT ✅ / IN ✅ (same plumbing as headset, validated there) |
| `headset` | Bidirectional for any app — Stereo Mix or Hi-Fi Cable for IN capture | ✅ **Validated end-to-end with ChatGPT Voice (2026-07-05), both directions.** Auto-switches default mic, restores on exit; separate mic/headphone via `--mic` / `--earphone` |
| `media` | YouTube, videos, any system audio → your language | ✅ Working — auto-switches Windows audio output to VB-Cable on start, restores on exit |
| `device` | Physical pendant (mic + speaker) — the **eco** hardware | Awaiting hardware |

## Commands

```bash
chasqui ui                                     # desktop interface
chasqui translate "¿Dónde está la estación?"   # one-shot text translation
chasqui listen --adapter device                # live audio translation
chasqui listen --adapter headset --mic "USB Micro" --earphone "Auriculares"
                                               # separate mic + headphones
chasqui devices                                # list audio devices, detect virtual mics
chasqui langs                                  # supported language codes
chasqui init                                   # generate chasqui.yaml starter config
```

## Configuration

Generate a starter config with `chasqui init`. Models are configurable per mode:

```yaml
api:
  key: ${OPENAI_API_KEY}
  model: gpt-realtime-translate   # realtime model for audio adapters
  text_model: gpt-4o-mini         # chat model for the text adapter
```

> **403 `model_not_found`?** Your OpenAI project doesn't have access to the
> configured model. Check which models are enabled for your project at
> [platform.openai.com](https://platform.openai.com/settings) and set
> `api.model` / `api.text_model` accordingly.

## Development

```bash
pip install -e ".[dev]"
pytest
```

See [SPEC.md](SPEC.md) for full architecture and [AGENTS.md](AGENTS.md) for contributor/agent notes.

## License

MIT
