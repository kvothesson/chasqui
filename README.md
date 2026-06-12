# chasqui

> *"El chasqui corría cientos de kilómetros llevando un mensaje que no podía leer.*
> *Transmitía sin entender. Conectaba sin pertenecer."*

Real-time simultaneous translation. Speak your language. Be understood.

## Quick start

```bash
pip install chasqui
export OPENAI_API_KEY=sk-...
chasqui listen --from es --to ja
```

## Adapters

| Adapter | Use case | Status |
|---|---|---|
| `text` | Keyboard in, terminal out — silent mode, accessibility, testing | ✅ Working |
| `virtual-mic` | Google Meet, Zoom, Teams, ChatGPT Voice (one-way: your voice, translated) | ✅ Working — validated end-to-end with ChatGPT Voice |
| `bridge` / `meet` | Bidirectional translation for any voice app (needs VB-Audio Cable) | OUT ✅ / IN in progress |
| `media` | YouTube, videos, any system audio → your language | Implemented, untested |
| `device` | Physical pendant (mic + speaker) — the **eco** hardware | Awaiting hardware |

## Commands

```bash
chasqui translate "¿Dónde está la estación?"   # one-shot text translation
chasqui listen --adapter device                # live audio translation
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
