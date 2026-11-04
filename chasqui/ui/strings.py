"""Every word the window says, in English and Spanish.

The window speaks the language Windows speaks: Spanish if the user's display
language is Spanish, English otherwise. CHASQUI_UI_LANG=es|en overrides it.

Plain words on purpose. The window used to name its states after the lore
(LATENT, ON ROUTE, GLITCH) and its buttons after the machine (PING, BUFFER,
FLUSH): someone about to translate a call could not tell what any of them did.
The brand lives in the wordmark; everything else says what it does.

The session log is not translated: it is the console, and it is what gets
pasted into bug reports.
"""

import locale
import os
import sys


def _detect() -> str:
    forced = os.environ.get("CHASQUI_UI_LANG", "").strip().lower()
    if forced in ("es", "en"):
        return forced
    if sys.platform == "win32":
        try:
            import ctypes

            # Primary language id 0x0A is Spanish, whatever the country.
            if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF == 0x0A:
                return "es"
            return "en"
        except Exception:
            pass
    try:
        name = locale.getlocale()[0] or ""
    except Exception:
        name = ""
    return "es" if name.lower().startswith(("es", "spanish")) else "en"


LANG = _detect()

_T: dict[str, tuple[str, str]] = {
    # header
    "tagline":        ("voice translator", "traductor de voz"),
    # states: one word each, different silhouettes
    "state.idle":     ("READY", "LISTO"),
    "state.starting": ("CONNECTING", "CONECTANDO"),
    "state.running":  ("TRANSLATING", "TRADUCIENDO"),
    "state.stopping": ("STOPPING", "FRENANDO"),
    "state.checking": ("TESTING", "PROBANDO"),
    "state.error":    ("ERROR", "ERROR"),
    # language roles
    "role.i_speak":   ("I speak", "Yo hablo"),
    "role.i_hear":    ("I hear", "Yo escucho"),
    "role.they_speak": ("They speak", "Ellos hablan"),
    "role.they_hear": ("They hear", "Ellos escuchan"),
    # modes
    "mode.headset":   ("Call, any app (recommended)",
                       "Llamada, cualquier app (recomendado)"),
    "mode.media":     ("Video or stream: what your PC plays",
                       "Video o stream: lo que suena en tu PC"),
    "mode.meet":      ("Call, cables picked by hand (advanced)",
                       "Llamada, cables elegidos a mano (avanzado)"),
    # buttons and links
    "start":          ("START", "EMPEZAR"),
    "stop":           ("STOP", "PARAR"),
    "test":           ("TEST", "PROBAR"),
    "details":        ("DETAILS", "DETALLES"),
    "setup":          ("SETUP", "CONFIGURAR"),
    "clear":          ("CLEAR", "LIMPIAR"),
    "devices":        ("AUDIO DEVICES", "DISPOSITIVOS"),
    "rescan":         ("SEARCH AGAIN", "BUSCAR DE NUEVO"),
    "voice":          ("Voice", "Voz"),
    "auto":           ("Auto", "Auto"),
    # device pickers
    "dev.mic":        ("Your mic", "Tu micrófono"),
    "dev.speaker":    ("To the app", "Hacia la app"),
    "dev.earphone":   ("You hear", "Escuchás en"),
    "dev.loopback":   ("From the app", "Desde la app"),
    # footer
    "no_spend":       ("nothing spent yet", "todavía sin gasto"),
    "minutes":        ("{n:.1f} min", "{n:.1f} min"),
    "left_of":        ("{left} left of {budget}", "quedan {left} de {budget}"),
    "over_budget":    ("over budget by {over}", "te pasaste {over} del presupuesto"),
    "meta":           ("{model}   ·   {turns} turns   ·   avg {avg:.0f}ms",
                       "{model}   ·   {turns} turnos   ·   promedio {avg:.0f}ms"),
    # messages the window writes itself
    "no_key":         ("No API key yet. Press SETUP to add one.",
                       "Falta la API key. Tocá CONFIGURAR para cargarla."),
    "same_lang":      ("Both languages are the same: nothing to translate.",
                       "Los dos idiomas son iguales: no hay nada que traducir."),
    "setup_saved":    ("Setup saved.", "Configuración guardada."),
    "session_ended":  ("Session ended.", "Sesión terminada."),
    "closing":        ("Stopping, and giving your Windows audio devices back...",
                       "Frenando y devolviéndote los dispositivos de audio de Windows..."),
    "test_ok":        ("  WORKS: {ms:.0f}ms round trip", "  ANDA: {ms:.0f}ms ida y vuelta"),
    "test_fail":      ("  FAILED: {error}", "  FALLÓ: {error}"),
    # setup window
    "w.title":        ("chasqui · setup", "chasqui · configuración"),
    "w.heading":      ("S E T U P", "C O N F I G U R A C I Ó N"),
    "w.tagline":      ("three things, once", "tres cosas, una sola vez"),
    "w.key":          ("1 · OPENAI KEY", "1 · KEY DE OPENAI"),
    "w.key_note":     ("chasqui uses your own OpenAI key; OpenAI bills you directly, "
                       "about USD 3 an hour of translation. The key stays on this computer.",
                       "chasqui usa tu propia key de OpenAI y OpenAI te cobra directo, "
                       "unos USD 3 por hora de traducción. La key queda en esta compu."),
    "w.key_set":      ("A key is already set. Paste another to replace it.",
                       "Ya hay una key cargada. Pegá otra si la querés cambiar."),
    "w.get_key":      ("GET A KEY ↗", "CONSEGUIR UNA KEY ↗"),
    "w.verify":       ("VERIFY", "VERIFICAR"),
    "w.asking":       ("Asking OpenAI...", "Preguntándole a OpenAI..."),
    "w.saved_to":     ("{message} Saved to {path}.", "{message} Guardada en {path}."),
    "w.save_failed":  ("Could not save the key: {error}", "No se pudo guardar la key: {error}"),
    "w.cable":        ("2 · VIRTUAL CABLE", "2 · CABLE VIRTUAL"),
    "w.get_cable":    ("GET VB-CABLE ↗", "BAJAR VB-CABLE ↗"),
    "w.cable_ok":     ("Found. Calls can hear your translated voice.",
                       "Encontrado. En las llamadas van a escuchar tu voz traducida."),
    "w.cable_missing": ("Not found. Calls need it to carry your translated voice "
                        "into Meet, Zoom or Discord. Install it, restart Windows, "
                        "then SEARCH AGAIN.",
                        "No está. Las llamadas lo necesitan para llevar tu voz traducida "
                        "a Meet, Zoom o Discord. Instalalo, reiniciá Windows y tocá "
                        "BUSCAR DE NUEVO."),
    "w.switcher":     ("3 · DEVICE SWITCHER", "3 · CAMBIADOR DE DISPOSITIVOS"),
    "w.switcher_ok":  ("Found. chasqui can switch your Windows mic and speakers, and put them back.",
                       "Encontrado. chasqui puede cambiar tu micrófono y tus parlantes de "
                       "Windows, y después devolverlos."),
    "w.switcher_missing": ("Not found. Calls and videos switch your Windows devices with it. "
                           "In PowerShell run: {command}",
                           "No está. Las llamadas y los videos cambian tus dispositivos de "
                           "Windows con él. En PowerShell corré: {command}"),
    "w.looking":      ("Looking...", "Buscando..."),
    "w.done":         ("DONE · TEST", "LISTO · PROBAR"),
    "w.later":        ("LATER", "DESPUÉS"),
}

# What core/firstrun.py answers about a key. It stays English there, because
# the CLI prints it too; the window translates the fixed ones and shows the
# rest as they come.
_CORE_ES: dict[str, str] = {
    "Paste a key first.": "Primero pegá una key.",
    "That does not look like an OpenAI key (they start with sk-).":
        "Eso no parece una key de OpenAI (empiezan con sk-).",
    "Key works.": "La key anda.",
    "OpenAI rejected this key.": "OpenAI rechazó esta key.",
    "Key works (OpenAI says to slow down or add credit).":
        "La key anda (OpenAI pide ir más despacio o cargar crédito).",
    "Could not reach OpenAI. Check the connection and retry.":
        "No se pudo llegar a OpenAI. Revisá la conexión y probá de nuevo.",
}


# The pickers' language names. core/constants.py keeps the English ones,
# because the model's instructions are written with them.
_LANG_ES: dict[str, str] = {
    "es": "Español", "ja": "Japonés", "en": "Inglés", "fr": "Francés",
    "pt": "Portugués", "zh": "Chino mandarín", "de": "Alemán", "it": "Italiano",
    "ko": "Coreano", "ar": "Árabe", "ru": "Ruso", "hi": "Hindi",
}


def lang_name(code: str, english: str) -> str:
    """A language's name in the window's language; `english` when there is none."""
    return _LANG_ES.get(code, english) if LANG == "es" else english


def t(key: str, **fields) -> str:
    """The text for `key` in the window's language, with `fields` filled in."""
    en, es = _T[key]
    text = es if LANG == "es" else en
    return text.format(**fields) if fields else text


def core(message: str) -> str:
    """A message from core/, in the window's language when there is a translation."""
    return _CORE_ES.get(message, message) if LANG == "es" else message
