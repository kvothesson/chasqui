# averroes

> *"Averroes, encerrado en el ámbito del Islam, nunca pudo saber el significado de tragedia y comedia."*  
> — Borges

Real-time simultaneous translation. Speak your language. Be understood.

## Quick start

```bash
pip install averroes
export OPENAI_API_KEY=sk-...
averroes listen --from es --to ja
```

## Adapters

| Adapter | Use case |
|---|---|
| `device` | Physical pendant (mic + speaker) |
| `virtual-mic` | Google Meet, Zoom, Teams |
| `media` | YouTube, videos, any system audio |
| `text` | Silent mode, accessibility |

See [SPEC.md](SPEC.md) for full architecture.
