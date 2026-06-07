# Averroes — Functional Specification

> *"Averroes, encerrado en el ámbito del Islam, nunca pudo saber el significado de tragedia y comedia."*  
> — Jorge Luis Borges, La busca de Averroes
>
> Este dispositivo existe para que ese problema no vuelva a ocurrir.

---

## 1. Visión

**Averroes** es un sistema de traducción en tiempo real, de código abierto, que se comporta como un intérprete simultáneo personal.

El objetivo de experiencia es uno solo: **hablar en tu idioma con alguien que no lo habla, con la misma naturalidad que si hubiera un intérprete humano al lado.**

No es una app de traducción. No es un diccionario. Es una capa de lenguaje que se interpone entre dos personas y desaparece.

---

## 2. Principios de Diseño

- **Core agnóstico**: el núcleo no sabe de dónde viene el audio ni adónde va
- **Adapters como ciudadanos de primera clase**: cada superficie (dispositivo físico, meet, video, texto) es un adapter intercambiable
- **Latencia sobre calidad**: 300ms con voz aceptable > 2s con voz perfecta
- **Open source sin fricción**: una API key y funciona; sin servidores propios requeridos
- **Combinable**: los adapters se pueden componer (ej: capturar de YouTube y outputear al dispositivo físico simultáneamente)

---

## 3. Arquitectura

```
┌─────────────────────────────────────────────────────────┐
│                    INTERFACE LAYER                      │
│                                                         │
│  DeviceAdapter │ VirtualMicAdapter │ MediaAdapter │ ... │
│                                                         │
│  Input Sources          Output Destinations             │
│  - Throat mic           - Physical speaker              │
│  - System mic           - Virtual mic (VB-Cable)        │
│  - System audio         - Earphone / bone conduction    │
│  - Text / stdin         - Text / stdout                 │
│  - WebSocket stream     - File / recording              │
└──────────────────────────┬──────────────────────────────┘
                           │  AudioStream (abstract)
┌──────────────────────────▼──────────────────────────────┐
│                      CORE                               │
│                                                         │
│   AudioInput ──► Pipeline ──► AudioOutput               │
│                     │                                   │
│              GPT-4o Realtime                            │
│              WebSocket session                          │
│                                                         │
│   - Manages language pair (source → target)             │
│   - Manages conversation context                        │
│   - Handles turn detection                              │
│   - Streams audio bidirectionalmente                    │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Core

### 4.1 Pipeline

El `Pipeline` es la unidad central. Recibe un `AudioStream` de entrada y produce un `AudioStream` de salida.

```python
pipeline = Pipeline(
    source_lang="es",
    target_lang="ja",
    model="gpt-4o-realtime",
    api_key="...",
)

pipeline.run(input_stream, output_stream)
```

Internamente gestiona:
- La conexión WebSocket con GPT-4o Realtime
- El contexto de conversación (historial de la sesión)
- Voice Activity Detection (VAD) para saber cuándo habló alguien
- Turn-taking: bloquear el mic mientras habla el output para evitar feedback

### 4.2 AudioStream

Abstracción mínima sobre cualquier fuente o destino de audio.

```python
class AudioStream:
    def read(self, chunk_size: int) -> bytes: ...  # PCM 16-bit, 24kHz
    def write(self, data: bytes) -> None: ...
    def close(self) -> None: ...
```

### 4.3 Sesión

Una `Session` encapsula un intercambio completo (ej: una conversación en un restaurante). Tiene:
- Idiomas configurados
- Contexto acumulado (para que el modelo mantenga coherencia)
- Log de lo que se dijo en ambos idiomas
- Estado: `idle` | `listening` | `translating` | `speaking`

### 4.4 Pair Mode

Cuando hay dos dispositivos (ej: pareja de viajeros), la sesión soporta **dual-channel mode**:
- Device A habla → traduce hacia el japonés → speaker A
- Device B habla → traduce hacia el japonés → speaker B
- Cuando A está hablando, B silencia su mic por 500ms post-output para evitar capturar el speaker de A
- Coordinación por WebSocket local (LAN) o por canal dedicado en la sesión Realtime

---

## 5. Adapters

### 5.1 DeviceAdapter
Para el hardware físico (el medallón).

```python
adapter = DeviceAdapter(
    mic_device_id="throat_mic_usb",
    speaker_device_id="pendant_speaker",
    earphone_device_id="bone_conduction",
    ptt_gpio_pin=17,          # Push-to-talk button
)
```

- Input: micrófono de garganta USB
- Output A: speaker frontal (lo escucha el japonés)
- Output B: auricular de conducción ósea (lo escucha el usuario)
- PTT: botón físico activa la captura

### 5.2 VirtualMicAdapter
Para Google Meet, Zoom, Teams, cualquier app de videollamada.

```python
adapter = VirtualMicAdapter(
    real_mic_device_id="default",
    virtual_mic_device_id="CABLE Input (VB-Audio)",  # Windows
    # virtual_mic_device_id="BlackHole 2ch"          # macOS
    earphone_device_id="default_headphones",
)
```

Flujo:
1. Captura el micrófono real del usuario
2. Traduce ES → JA en tiempo real
3. Inyecta el audio traducido en el micrófono virtual
4. Google Meet transmite el audio traducido a los participantes
5. El audio de los participantes japoneses llega por los auriculares, traducido JA → ES

Requiere: VB-Audio Cable (Windows) o BlackHole (macOS) — gratuitos.

### 5.3 MediaAdapter
Para YouTube, Netflix, videos locales. Traduce lo que se escucha.

```python
adapter = MediaAdapter(
    system_audio_device="Stereo Mix",  # Windows
    # system_audio_device="BlackHole" # macOS (loopback)
    output_device="default_headphones",
    mode="subtitle",      # "subtitle" | "dub" | "both"
)
```

Modos:
- `subtitle`: genera texto en tiempo real (sin audio adicional)
- `dub`: reemplaza el audio con la traducción hablada
- `both`: texto + audio simultáneo

### 5.4 TextAdapter
Para uso silencioso, accesibilidad o testing.

```python
adapter = TextAdapter(
    input_mode="keyboard",   # "keyboard" | "stdin" | "file"
    output_mode="terminal",  # "terminal" | "stdout" | "file"
    show_both_langs=True,
)
```

### 5.5 CLIAdapter
Para pipes y scripting.

```bash
echo "hola, dónde está la estación?" | averroes translate --from es --to ja
averroes listen --adapter virtual-mic --from es --to ja
averroes run --config ./config.yaml
```

---

## 6. Configuración

Archivo `averroes.yaml` en el root del proyecto o en `~/.averroes/config.yaml`:

```yaml
api:
  provider: openai             # openai | anthropic (futuro)
  key: ${OPENAI_API_KEY}
  model: gpt-4o-realtime-preview

session:
  source_lang: es
  target_lang: ja
  context: |
    Somos turistas argentinos en Japón.
    El contexto es conversación cotidiana: restaurantes, transporte, compras.
    Traducir de manera natural, no literal.

adapter: device               # device | virtual-mic | media | text | cli

device:
  mic: "USB PnP Audio Device"
  speaker: "USB Audio"
  earphone: "Headphones"
  ptt_mode: hold              # hold | toggle | vad

pair_mode:
  enabled: false
  role: primary               # primary | secondary
  peer_address: "192.168.1.x:7373"

logging:
  save_session: true
  session_dir: ~/.averroes/sessions
  language: both              # source | target | both
```

---

## 7. Interfaces de Superficie (futura capa UI)

El core expone un servidor WebSocket local (`localhost:7373`) que cualquier interfaz puede consumir:

```json
// Evento: traducción completada
{
  "type": "translation",
  "source_lang": "es",
  "target_lang": "ja",
  "source_text": "¿Dónde está el baño?",
  "target_text": "トイレはどこですか？",
  "audio_url": "data:audio/pcm;base64,...",
  "latency_ms": 410
}
```

Esto permite:
- Una UI web (React) corriendo en el celu que muestra el texto en tiempo real
- Una extensión de Chrome que intercepta audio del browser
- Un overlay en el escritorio
- Una app mobile nativa

---

## 8. Stack Técnico

| Componente | Tecnología |
|---|---|
| Lenguaje core | Python 3.11+ |
| Realtime translation | OpenAI GPT-4o Realtime API (WebSocket) |
| Audio I/O | `sounddevice` + `PyAudio` |
| Virtual mic (Windows) | VB-Audio Cable |
| Virtual mic (macOS) | BlackHole |
| System audio capture | `soundcard` (loopback) |
| Config | YAML + env vars |
| CLI | `click` |
| Local server | `websockets` |
| Packaging | `uv` / `pip` |

---

## 9. Extensibilidad Futura

- **Otros providers**: Anthropic (cuando tenga Realtime), Gemini Live
- **Otros idiomas**: el adapter de configuración permite cualquier par de idiomas
- **Hardware alternativo**: cualquier mic + speaker USB funciona sin cambiar el core
- **Modo offline**: Whisper local + LLM local (Ollama) + TTS local (Coqui) — calidad menor, sin costo
- **Plugin system**: adapters como paquetes Python instalables (`averroes-adapter-chrome`, etc.)

---

## 10. Open Source

- **Licencia**: MIT
- **Hardware**: STL files + BOM incluidos en `/hardware`
- **API key**: el usuario provee la suya; no hay servidor intermedio
- **MercadoLibre**: venta de kits ensamblados usando exactamente este mismo código

---

## 11. Nombre y Referencia

**Averroes** (Ibn Rushd, 1126–1198) fue el filósofo árabe que intentó comentar a Aristóteles sin haber visto nunca una obra de teatro griega. No podía traducir "tragedia" ni "comedia" porque no existían en su mundo cultural.

Borges usó esa historia para hablar de los límites del lenguaje y la imposibilidad de la traducción perfecta.

Este proyecto lleva su nombre como recordatorio de que la traducción perfecta no existe — solo existe la comprensión suficiente para que dos personas se entiendan.
