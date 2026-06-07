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

## 2. Naming

| Nombre | Qué es |
|---|---|
| **averroes** | El core open source. La librería. El engine. Cualquiera lo instala. |
| **nyx** | El dispositivo físico (el medallón). Usa el adapter `device` de averroes. |

Nyx en el universo Kvothesson: unidad de suspensión, infiltración, sigilo, manipulación de entornos. Exactamente lo que hace — se infiltra en una conversación en un idioma ajeno y la hace funcionar.

Cuando alguien lo compra en MercadoLibre compra un **Nyx**.  
Cuando alguien lo buildea desde cero clona **averroes**.

---

## 3. Modelo y Costo

**Modelo:** `gpt-realtime-translate` (mayo 2026)
- Endpoint: `wss://api.openai.com/v1/realtime/translations`
- Precio: **$0.034/minuto** de audio
- 70+ idiomas de entrada, detección automática
- Sin prompting personalizado, sin selección de voz
- Costo estimado viaje 14 días Japón (30 min/día): **~$14 total**

**Fallback:** `gpt-realtime` (general)
- Endpoint: `wss://api.openai.com/v1/realtime`
- Precio: $0.18–0.46/minuto
- Soporta instrucciones personalizadas y selección de voz

**Detección automática de idioma:**
El modelo detecta el idioma de entrada automáticamente. Si el input ya está en el idioma destino (ej: dos personas con Nyx hablando español), el modelo hace pass-through sin traducción real. Costo idéntico — no vale la pena optimizar.

---

## 4. Principios de Diseño

- **Core agnóstico**: el núcleo no sabe de dónde viene el audio ni adónde va
- **Adapters como ciudadanos de primera clase**: cada superficie es un adapter intercambiable
- **Latencia sobre calidad**: 300ms con voz aceptable > 2s con voz perfecta
- **Open source sin fricción**: una API key y funciona; sin servidores propios requeridos
- **Combinable**: los adapters se pueden componer y correr en paralelo
- **Bidireccional por defecto**: toda conversación real es en dos direcciones

---

## 5. Arquitectura

```
┌─────────────────────────────────────────────────────────┐
│                    INTERFACE LAYER                      │
│                                                         │
│  device │ virtual-mic │ media │ meet │ text             │
│                                                         │
│  Input Sources          Output Destinations             │
│  - Throat mic           - Physical speaker (outward)    │
│  - Ambient mic          - Virtual mic (VB-Cable)        │
│  - System audio         - Bone conduction (private)     │
│  - Text / stdin         - Text / stdout                 │
└──────────────────────────┬──────────────────────────────┘
                           │  AudioStream (abstract)
┌──────────────────────────▼──────────────────────────────┐
│                      CORE                               │
│                                                         │
│   AudioInput ──► Pipeline ──► AudioOutput               │
│                     │                                   │
│              gpt-realtime-translate                     │
│              WebSocket session                          │
│                                                         │
│   - Language pair (source detectado, target configurado)│
│   - Voice Activity Detection (server-side VAD)          │
│   - SpeakerStream: background thread + queue            │
└─────────────────────────────────────────────────────────┘
```

---

## 6. Adapters

### 6.1 `text` — Teclado → Terminal
Usa Chat Completions (no Realtime). Para testing, modo silencioso, piping.
```bash
averroes translate "¿Dónde está el baño?"
echo "gracias" | averroes translate --from es --to ja
```
**Estado: ✅ funciona**

---

### 6.2 `virtual-mic` — Google Meet / Zoom / Teams (unidireccional)
```
tu mic real → pipeline ES→JA → CABLE Input → Meet transmite japonés
```
Requiere VB-Audio Cable (Windows) o BlackHole (macOS).  
**Estado: ✅ funciona**

---

### 6.3 `meet` — Google Meet bidireccional ⏳
Dos pipelines corriendo en paralelo:
```
pipeline OUT: tu mic real   → ES→JA → CABLE Input    (ellos te escuchan en japonés)
pipeline IN:  audio de Meet → JA→ES → bone conduction (vos escuchás en español)
```
El audio de Meet se captura por loopback del sistema.  
**Estado: por implementar**

---

### 6.4 `media` — YouTube / Videos / Streams
```
audio del sistema (loopback) → pipeline JA→ES → auriculares
```
Modos: `dub` | `subtitle` | `both`  
**Estado: implementado, no probado**

---

### 6.5 `device` — Hardware físico Nyx (bidireccional)

El pendant tiene **dos micrófonos y dos salidas**:

```
PENDANT (Nyx)
├── throat mic  → pipeline ES→JA → speaker outward    (japonés escucha)
└── ambient mic → pipeline JA→ES → bone conduction    (vos escuchás)
```

- **Throat mic**: capta vibración ósea de tu voz, ignora el ambiente y el speaker outward
- **Ambient mic**: capta al japonés hablando, ignora tu voz (ya sale por el throat)
- **Speaker outward**: el japonés escucha la traducción sin auricular
- **Bone conduction**: vos escuchás la traducción sin bloquear el oído

Los dos pipelines corren en paralelo. El celu va en el bolsillo, no se toca.

**Pair mode (x2 dispositivos):**
- Device A habla → pipeline A traduce → speaker A
- Device B habla → pipeline B traduce → speaker B
- Coordinación: cuando A está outputeando, B silencia su ambient mic 500ms para evitar feedback

**Estado: implementado básico, falta bidireccional**

---

## 7. Hardware Nyx — Opción A (phone as brain)

El celu corre averroes. El pendant es periférico de audio.

### Componentes

| Componente | Función | Precio aprox |
|---|---|---|
| Throat mic USB | Captura voz del usuario | $20 USD |
| Mic ambiente pequeño | Captura voz del interlocutor | $5 USD |
| Speaker 8Ω 2W + PAM8403 amp | Salida outward | $8 USD |
| Bone conduction BT | Canal privado del usuario | $50 USD |
| USB-C hub con audio + PD | Conecta mic + speaker al celu | $25 USD |
| Enclosure 3D printed | El medallón | $15 USD |
| **Total** | | **~$123 USD** |

### Herramientas necesarias
- Soldador + estaño
- Pistola de silicona caliente
- Multímetro
- Cables dupont + termocontraíble

### Diseño del enclosure (Nyx)
- ~35mm × 12mm, aluminio negro mate
- Cristal hexagonal grabado (universo Kvothesson)
- Speaker grille honeycomb en frente
- Botón PTT lateral flush
- Runas nórdicas en la tapa trasera
- Cuelga de cadena titanio o cord negro

---

## 8. Stack Técnico

| Componente | Tecnología |
|---|---|
| Lenguaje | Python 3.11+ |
| Traducción Realtime | `gpt-realtime-translate` via WebSocket |
| Audio I/O | `sounddevice` + background thread queue |
| Virtual mic (Windows) | VB-Audio Cable |
| Virtual mic (macOS) | BlackHole |
| Config | YAML + env vars |
| CLI | `click` |
| Packaging | `pip` / `uv` |

---

## 9. CLI

```bash
averroes translate "¿Dónde está la estación?"   # texto, una frase
averroes listen --from es --to ja               # interactivo texto
averroes listen --adapter virtual-mic           # Meet unidireccional
averroes listen --adapter meet                  # Meet bidireccional
averroes listen --adapter device                # hardware Nyx
averroes listen --adapter media                 # YouTube/videos
averroes devices                                # listar dispositivos
averroes langs                                  # listar idiomas
averroes init                                   # generar config
```

---

## 10. Mercado

**Lo que existe en 2026:**
- Timekettle W4 Pro, Soundcore AeroFit 2, Kentfaith — auriculares de traducción
- Requieren auricular en el interlocutor, o celu en la mesa, o modo face-to-face
- Pendants AI (Meta/Limitless, Taya) — graban, no traducen

**Lo que no existe:** pendant autónomo con speaker outward + canal privado + throat mic donde ambas personas participan sin tocar nada y sin que el interlocutor use ningún dispositivo.

**Ventana:** `gpt-realtime-translate` es de mayo 2026. Los productos de hardware tienen ciclos de 2-3 años. Nadie lo tiene integrado todavía.

---

## 11. Open Source / Producto

- **Licencia**: MIT
- **GitHub**: averroes (core) — cualquiera lo fork, contribuye, adapta
- **Hardware**: STL files + BOM en `/hardware`
- **MercadoLibre**: venta de Nyx ensamblado usando este mismo código
- **Modelo de negocio**: hardware (Nyx) + opcional suscripción con API incluida

---

## 12. Nombre y Referencia

**Averroes** (Ibn Rushd, 1126–1198) intentó comentar a Aristóteles sin haber visto nunca una obra de teatro griega. No podía traducir "tragedia" ni "comedia" porque no existían en su mundo cultural. Borges lo usó para hablar de los límites del lenguaje.

Este proyecto lleva su nombre como recordatorio de que la traducción perfecta no existe — solo existe la comprensión suficiente para que dos personas se entiendan.

**Nyx** — unidad de suspensión del universo Kvothesson. Infiltración, sigilo, manipulación de entornos. Se infiltra en una conversación en un idioma ajeno y la hace funcionar. Asimétrica, fluida, núcleo expuesto.
