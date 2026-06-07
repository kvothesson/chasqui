# chasqui — Functional Specification

> *"Averroes, encerrado en el ámbito del Islam, nunca pudo saber el significado de tragedia y comedia."*  
> — Jorge Luis Borges, La busca de Averroes
>
> Este proyecto existe para que ese problema no vuelva a ocurrir.

---

## 1. Visión

**chasqui** es un sistema de traducción en tiempo real, de código abierto, que se comporta como un intérprete simultáneo personal.

El objetivo de experiencia es uno solo: **hablar en tu idioma con alguien que no lo habla, con la misma naturalidad que si hubiera un intérprete humano al lado.**

No es una app de traducción. No es un diccionario. Es una capa de lenguaje que se interpone entre dos personas y desaparece.

---

## 2. Naming

| Nombre | Qué es |
|---|---|
| **chasqui** | El core open source. La librería. El engine. Cualquiera lo instala. |
| **eco** | El dispositivo físico (el medallón). Usa el adapter `device` de chasqui. |

**chasqui** — del universo Kvothesson / NODO_QUIPU. El mensajero que atraviesa todos los nodos, habla todos los idiomas para conectarlos. Técnico, veloz, invisible. No pertenece a ningún nodo — los conecta a todos.

**eco** — el sonido que vuelve traducido. Lo que decís en un idioma regresa en otro. El nombre más simple para lo que hace.

Cuando alguien lo compra en MercadoLibre compra un **eco**.  
Cuando alguien lo buildea desde cero clona **chasqui**.

```bash
chasqui listen --adapter eco
```

---

## 3. Modelo y Costo

**Modelo:** `gpt-realtime-translate` (mayo 2026)
- Endpoint: `wss://api.openai.com/v1/realtime/translations`
- Precio: **$0.034/minuto** de audio
- 70+ idiomas de entrada, detección automática de idioma
- Sin prompting personalizado, sin selección de voz
- Costo estimado viaje 14 días Japón (30 min/día): **~$14 total**

**Fallback:** `gpt-realtime` (general)
- Endpoint: `wss://api.openai.com/v1/realtime`
- Precio: $0.18–0.46/minuto
- Soporta instrucciones personalizadas y selección de voz

**Detección automática de idioma:**
El modelo detecta el idioma de entrada automáticamente. Si el input ya está en el idioma destino (ej: dos personas con eco hablando español), el modelo hace pass-through. Costo idéntico — no vale la pena optimizar.

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
│              WebSocket / translations endpoint          │
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
chasqui translate "¿Dónde está el baño?"
echo "gracias" | chasqui translate --from es --to ja
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

### 6.3 `meet` — Google Meet bidireccional
Dos pipelines corriendo en paralelo:
```
pipeline OUT: tu mic real   → ES→JA → CABLE Input     (ellos te escuchan en japonés)
pipeline IN:  audio de Meet → JA→ES → bone conduction  (vos escuchás en español)
```
**Estado: por implementar**

---

### 6.4 `media` — YouTube / Videos / Streams
```
audio del sistema (loopback) → pipeline JA→ES → auriculares
```
Modos: `dub` | `subtitle` | `both`  
**Estado: implementado, no probado**

---

### 6.5 `device` — Hardware físico eco (bidireccional)

El pendant tiene **dos micrófonos y dos salidas**:

```
ECO (pendant)
├── throat mic  → pipeline ES→JA → speaker outward    (interlocutor escucha)
└── ambient mic → pipeline JA→ES → bone conduction    (usuario escucha)
```

- **Throat mic**: capta vibración ósea de tu voz, ignora el ambiente y el speaker outward
- **Ambient mic**: capta al interlocutor hablando
- **Speaker outward**: el interlocutor escucha la traducción sin auricular
- **Bone conduction**: el usuario escucha la traducción sin bloquear el oído

Los dos pipelines corren en paralelo. El celu va en el bolsillo, no se toca.

**Pair mode (x2 dispositivos, pareja de viajeros):**
- eco A habla → pipeline A traduce → speaker A
- eco B habla → pipeline B traduce → speaker B
- Coordinación: cuando A outputea, B silencia su ambient mic 500ms para evitar feedback

**Estado: implementado básico, falta bidireccional**

---

## 7. Hardware eco — Opción A (phone as brain)

El celu corre chasqui. El pendant es periférico de audio.

### Componentes

| Componente | Función | Precio aprox |
|---|---|---|
| Throat mic USB | Captura voz del usuario | $20 USD |
| Mic ambiente pequeño | Captura voz del interlocutor | $5 USD |
| Speaker 8Ω 2W + PAM8403 amp | Salida outward | $8 USD |
| Bone conduction BT | Canal privado del usuario | $50 USD |
| USB-C hub con audio + PD | Conecta mic + speaker al celu | $25 USD |
| Enclosure 3D printed | El medallón eco | $15 USD |
| **Total** | | **~$123 USD** |

### Herramientas necesarias
- Soldador + estaño
- Pistola de silicona caliente
- Multímetro
- Cables dupont + termocontraíble

### Diseño del enclosure (eco)
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
chasqui translate "¿Dónde está la estación?"   # texto, una frase
chasqui listen --from es --to ja               # interactivo texto
chasqui listen --adapter virtual-mic           # Meet unidireccional
chasqui listen --adapter meet                  # Meet bidireccional
chasqui listen --adapter device                # hardware eco
chasqui listen --adapter media                 # YouTube/videos
chasqui devices                                # listar dispositivos
chasqui langs                                  # listar idiomas
chasqui init                                   # generar config
```

---

## 10. Mercado

**Lo que existe en 2026:**
- Timekettle W4 Pro, Soundcore AeroFit 2 — auriculares de traducción
- Requieren auricular en el interlocutor, o celu en la mesa
- Pendants AI (Meta/Limitless, Taya) — graban, no traducen

**Lo que no existe:** pendant autónomo con speaker outward + canal privado + throat mic donde ambas personas participan sin tocar nada y sin que el interlocutor use ningún dispositivo.

**Ventana:** `gpt-realtime-translate` es de mayo 2026. Los productos de hardware tienen ciclos de 2-3 años. Nadie lo tiene integrado todavía.

---

## 11. Open Source / Producto

- **Licencia**: MIT
- **GitHub**: chasqui (core) — cualquiera lo fork, contribuye, adapta
- **Hardware**: STL files + BOM en `/hardware`
- **MercadoLibre**: venta de eco ensamblado usando este mismo código
- **Modelo de negocio**: hardware (eco) + opcional suscripción con API incluida

---

## 12. Referencia

**chasqui** — en el universo Kvothesson / NODO_QUIPU, el mensajero que traversa todos los nodos de la red argentina. No pertenece a ningún idioma. Los conecta a todos.

**eco** — el sonido que vuelve. Lo que decís en un idioma regresa en otro, en tiempo real, desde el pendant que llevás al cuello.
