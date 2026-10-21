# chasqui

> *"El chasqui corría cientos de kilómetros llevando un mensaje que no podía leer.*
> *Transmitía sin entender. Conectaba sin pertenecer."*

Traducción simultánea en tiempo real. Hablá tu idioma. Que te entiendan.

*[Read in English →](https://github.com/kvothesson/chasqui/blob/master/README.md)*

<p align="center">
  <img src="https://raw.githubusercontent.com/kvothesson/chasqui/master/docs/img/ui-gadget.png" alt="La ventana de chasqui: dos idiomas, un modo, y Start" width="402">
</p>

---

## Instalación

### Windows: el instalador

**[Descargar chasqui-setup-0.2.0.exe](https://github.com/kvothesson/chasqui/releases/download/v0.2.0/chasqui-setup-0.2.0.exe)** (27 MB, Windows 10/11, 64 bits).

Sin Python y sin pedir permisos de administrador. Se instala para tu usuario,
agrega una entrada en el menú Inicio y abre chasqui, que en el primer arranque
te guía para cargar la API key (ver
[Primer arranque](#primer-arranque-la-ventana-de-configuración)). Para las
llamadas también necesitás [VB-Audio Cable](https://vb-audio.com/Cable/); la
ventana de configuración te avisa si falta.

El instalador todavía no está firmado, así que Windows SmartScreen va a decir
"Windows protegió tu PC". Hacé clic en **Más información** y después en
**Ejecutar de todas formas**.

### Con Python

**Necesitás:** Python 3.11 o superior, una API key de OpenAI y, para los modos
que meten audio traducido dentro de otra app,
[VB-Audio Cable](https://vb-audio.com/Cable/) en Windows.

```bash
pip install chasqui-translate
```

El paquete se llama `chasqui-translate` porque `chasqui` a secas lo tiene en
PyPI otro proyecto sin relación; el comando sigue siendo `chasqui`. Para
correrlo desde el código:

```bash
git clone https://github.com/kvothesson/chasqui && cd chasqui
pip install -e .
```

Pasale la key, como variable de entorno:

```bash
export OPENAI_API_KEY=sk-...          # en Windows: setx OPENAI_API_KEY sk-...
```

...o en un `chasqui.yaml` al lado de tu proyecto (`chasqui init` te genera uno
de arranque). Después abrís la ventana:

```bash
chasqui ui
```

### Acceso directo en el escritorio

```bash
chasqui icon --shortcut
```

Eso escribe el ícono (está dibujado en código, no hay ninguna imagen en el
repo) y te deja un acceso directo en el escritorio. El acceso directo ejecuta
`chasqui-ui`, un lanzador sin consola. `chasqui ui` hace lo mismo pero es un
script de consola: perfecto desde una terminal, y desde un doble clic te deja
una ventana negra de consola atrás de la app durante toda la sesión.

### Nota para Linux

Tkinter viene con Python, así que la interfaz no agrega ninguna dependencia. En
Debian y Ubuntu está en un paquete aparte:

```bash
sudo apt install python3-tk
```

Los adaptadores de audio son Windows primero y no lo disimulan: `headset` y
`media` cambian tus dispositivos por defecto de Windows vía PowerShell. El
adaptador `text` corre en cualquier lado.

---

## Cómo se usa la interfaz

La ventana tiene dos formas. La de arriba es la que viene por defecto: chica
como para dejarla al lado de una llamada, y muestra solo lo que necesitás en el
medio de una conversación.

### Los dos selectores de idioma

**Tu idioma siempre es el de la izquierda.** Las etiquetas de arriba cambian
según el modo y te dicen de quién es cada caja, así no tenés que deducirlo:

| Modo | Caja izquierda | Caja derecha |
|---|---|---|
| `headset`, `meet`, `bridge` | I SPEAK (yo hablo) | THEY SPEAK (ellos hablan) |
| `virtual-mic`, `device` | I SPEAK (yo hablo) | THEY HEAR (ellos escuchan) |
| `media` | I HEAR (yo escucho) | THEY SPEAK (ellos hablan) |

La flecha del medio te dice para dónde viaja la traducción: **⇄** en los modos
bidireccionales, **→** cuando te están transmitiendo en un solo sentido, **←**
en modo media cuando el audio viene hacia vos. Si la tocás, invierte los dos
idiomas.

Abajo está el selector de modo. `Headset — bidirectional, any app` es el que
conviene probar primero.

### Primer arranque: la ventana de configuración

Si no hay API key en ningún lado, la ventana abre encima una ventanita de
configuración que revisa tres cosas y dice si cada una está lista:

1. **Tu key de OpenAI.** La pegás y apretás VERIFY: chasqui le pregunta a
   OpenAI si esa key puede usar el modelo que va a correr, y la guarda en
   `~/.chasqui/config.yaml`. Una key en `OPENAI_API_KEY` o en un
   `chasqui.yaml` sigue ganándole a la guardada.
2. **VB-Audio Cable**, que necesitan los modos de llamada. Con un link si falta.
3. **El cambiador de dispositivos** (el módulo de PowerShell AudioDeviceCmdlets),
   con el que los modos headset y media mueven tus dispositivos de Windows.

**DONE · PING** la cierra y corre un ping, así lo primero que ves es una
traducción. **SETUP**, debajo de START, la vuelve a abrir.

### Start, Ping y la luz de estado

**START** abre la sesión. **PING** corre la misma prueba de ida y vuelta que
`chasqui check`: sin micrófono ni parlantes, solo "el pipeline está vivo". El
hexágono del encabezado es el estado del nodo:

| Luz | Qué está pasando |
|---|---|
| `LATENT` | En reposo. No hay nada corriendo. |
| `COMPILING` | Arrancando: abriendo el socket, tomando tus dispositivos por defecto. |
| `ON ROUTE` | En vivo. El audio se está traduciendo, en los dos sentidos si el modo es bidireccional. |
| `UNWINDING` | Frenando, y devolviéndote los dispositivos de Windows. |
| `PING` | Corriendo la prueba de ida y vuelta. |
| `GLITCH` | Algo falló. Abrí BUFFER, el motivo está ahí adentro. |

**Frenar importa más de lo que parece.** Los modos `headset` y `media` te toman
el micrófono y la salida por defecto de Windows mientras corren, y te los
devuelven al salir. Usá STOP, o cerrá la ventana directamente (espera hasta 15
segundos a que termine la devolución), en vez de matar el proceso.

El hexágono de arriba a la derecha (**⬢** / **⬡**) mantiene la ventana por
encima de todo lo demás. Lleno significa fijada arriba, que es lo que querés al
lado de una llamada.

### Cuánto te está costando

La línea debajo de los botones es un contador de gasto, y queda a la vista
incluso en la forma chica, a propósito. `gpt-realtime-translate` se cobra por
minuto, así que chasqui cuenta el audio que transmite y lo tarifa. Una sesión
bidireccional paga dos direcciones al mismo tiempo, cosa que conviene ver antes
de una llamada larga. Poné `pricing.budget` en `chasqui.yaml` y al lado te
aparece cuánto te queda.

> OpenAI no expone ninguna API para consultar tu saldo, así que ese presupuesto
> es un número tuyo, guardado localmente, y no una lectura de tu cuenta. El `~`
> adelante de la cifra está puesto a propósito: en `core/pricing.py` está qué
> se mide y qué se asume.

### BUFFER, el panel completo

Tocá **▸ BUFFER** y la ventana crece a la segunda forma: el selector de voz,
los dispositivos de audio y el log.

<p align="center">
  <img src="https://raw.githubusercontent.com/kvothesson/chasqui/master/docs/img/ui-transcript.png" alt="La ventana expandida con una transcripción en vivo" width="402">
</p>

El log es donde va cayendo la conversación mientras pasa. Cada turno muestra la
línea original en gris, la traducción abajo, y la latencia de ida y vuelta:
**hielo para lo que sale, violeta para lo que vuelve**, así en una llamada
bidireccional ves de un vistazo para qué lado viajó cada línea. También guarda
las líneas de arranque, la tarifa con la que chasqui te está midiendo el gasto,
y cualquier cosa que haya fallado.

Las líneas se acumulan tengas el panel abierto o cerrado, así que si lo abrís
después de un error vas a ver todo desde el principio. **FLUSH** lo limpia. El
pie muestra el modelo, la cantidad de turnos y la latencia promedio.

### Dispositivos de audio

Los dispositivos quedan en **Auto**, y Auto acierta casi siempre. Abrí
**▸ AUDIO DEVICES** solo cuando la detección automática elige el cable
equivocado.

<p align="center">
  <img src="https://raw.githubusercontent.com/kvothesson/chasqui/master/docs/img/ui-devices.png" alt="El panel de dispositivos, cuatro selectores en Auto" width="402">
</p>

Cada campo nombra las dos puntas del cable, y los selectores que no hacen falta
en el modo actual quedan grises:

| Campo | Qué es |
|---|---|
| **Your mic** | Por dónde entra tu voz |
| **To the app** | El cable virtual que escucha Meet, Zoom o Discord |
| **You hear** | Por dónde te llega la traducción |
| **From the app** | La captura de lo que está diciendo la app |

**RESCAN** vuelve a leer la lista de dispositivos, tocalo después de enchufar
algo. Elegí siempre por nombre y nunca por índice: Windows renumera los índices
cada vez que cambia un dispositivo por defecto, y los propios adaptadores de
chasqui cambian esos valores al arrancar.

Tus idiomas, el modo, la voz, los dispositivos, la forma de la ventana y el
gasto acumulado quedan guardados en `~/.chasqui/ui.json`.

### Si del otro lado no escuchan nada

Meet y Teams pasan tu micrófono por un supresor de ruido, y en "Automático"
puede tomar la voz sintética como ruido y borrar la traducción: chasqui
muestra el turno en el log y del otro lado escuchan silencio. Ponelo en
**Bajo** o **Desactivado** (Meet: Configuración > Audio > Cancelación de
ruido; Teams: Configuración > Dispositivos > Supresión de ruido; Zoom:
Configuración > Audio > Suprimir ruido de fondo).

### Pagar menos por el silencio, sonar más a vos

Dos opciones en `chasqui.yaml`, las dos apagadas por defecto:

```yaml
silence_gate: true   # el audio en silencio no se manda, así que no se cobra
passthrough: 0.15    # tu voz real, bajita, debajo de la traducción
```

`gpt-realtime-translate` cobra cada minuto que chasqui manda, y en una llamada
cada dirección pasa mucho tiempo callada. El **silence gate** deja de mandar
audio después de 3 s de silencio y vuelve a mandar, con los 300 ms previos,
apenas alguien habla; la línea de costo cuenta solo lo enviado. En un lugar
ruidoso queda abierto (no ahorra, pero no pierde nada): si pasa, subí
`silence_gate_dbfs`. El **passthrough** mezcla tu voz original debajo de la
traducción que escucha el otro, así se conserva tu tono y alguien bilingüe
entiende el original. Desde la terminal:
`chasqui listen --adapter headset --silence-gate --passthrough 0.15`.

---

## Adaptadores

| Adaptador | Para qué sirve | Estado |
|---|---|---|
| `text` | Teclado adentro, terminal afuera: modo silencioso, accesibilidad, pruebas | ✅ Funcionando |
| `virtual-mic` | Google Meet, Zoom, Teams, ChatGPT Voice (un solo sentido: tu voz, traducida) | ✅ Funcionando, validado de punta a punta con ChatGPT Voice |
| `bridge` / `meet` | Traducción bidireccional para cualquier app de voz (necesita VB-Audio Cable) | SALIDA ✅ / ENTRADA ✅ (misma plomería que headset, validado ahí) |
| `headset` | Bidireccional para cualquier app, con Stereo Mix o Hi-Fi Cable para capturar la entrada | ✅ **Validado de punta a punta con ChatGPT Voice (2026-07-05), en los dos sentidos.** Cambia el micrófono por defecto y lo restaura al salir; micrófono y auriculares separados con `--mic` / `--earphone` |
| `media` | YouTube, videos, cualquier audio del sistema hacia tu idioma | ✅ Funcionando, cambia la salida de Windows a VB-Cable al arrancar y la restaura al salir |
| `device` | Colgante físico (micrófono + parlante), el hardware **eco** | Esperando el hardware |

## Comandos

```bash
chasqui ui                                     # interfaz de escritorio
chasqui icon --shortcut                        # acceso directo + ícono
chasqui translate "¿Dónde está la estación?"   # traducción de texto, una sola vez
chasqui listen --adapter device                # traducción de audio en vivo
chasqui listen --adapter headset --mic "USB Micro" --earphone "Auriculares"
                                               # micrófono y auriculares separados
chasqui devices                                # lista dispositivos, detecta micrófonos virtuales
chasqui langs                                  # códigos de idioma soportados
chasqui init                                   # genera un chasqui.yaml de arranque
```

## Configuración

Generá una config de arranque con `chasqui init`. Los modelos se configuran por
modo:

```yaml
api:
  key: ${OPENAI_API_KEY}
  model: gpt-realtime-translate   # modelo realtime para los adaptadores de audio
  text_model: gpt-4o-mini         # modelo de chat para el adaptador de texto
```

**Costo o calidad.** El modelo por defecto, `gpt-realtime-translate`, es el
barato: unos USD 2 por hora y por dirección. También se equivoca más: con un
set de frases trampa ("¿Llegaste bien?", "¿Me das un mate?") falló 5 de 30
turnos, casi siempre juntando dos frases y perdiendo una. Con
`model: gpt-realtime` falló 1 de 30, porque cada turno se traduce por separado
y una pregunta corta nunca se *responde*, pero cuesta entre 5 y 10 veces más.
Medilo vos con `examples/drift_check.py`.

> **¿403 `model_not_found`?** Tu proyecto de OpenAI no tiene acceso al modelo
> configurado. Mirá qué modelos están habilitados en
> [platform.openai.com](https://platform.openai.com/settings) y ajustá
> `api.model` / `api.text_model`.

## Desarrollo

```bash
pip install -e ".[dev]"
pytest
```

En [SPEC.md](https://github.com/kvothesson/chasqui/blob/master/SPEC.md) está la arquitectura completa y en [AGENTS.md](https://github.com/kvothesson/chasqui/blob/master/AGENTS.md)
las notas para quien contribuya.

## Licencia

MIT
