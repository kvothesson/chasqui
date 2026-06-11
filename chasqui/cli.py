"""Chasqui CLI — entry point for all commands."""

import sys
import io
from pathlib import Path
from typing import Optional

# Force UTF-8 output on Windows so Japanese/CJK characters don't crash
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import click

from .core.config import Config, find_config
from .core.constants import LANG_NAMES


def _load_config(config_path: Optional[str], **overrides) -> Config:
    """Load config from file (auto-detected or explicit), apply CLI overrides."""
    path = Path(config_path) if config_path else find_config()
    cfg = Config.from_yaml(path) if path else Config()

    for key, val in overrides.items():
        if val is not None:
            setattr(cfg, key, val)

    return cfg


def _run_adapter(cfg: Config) -> None:
    adapter_map = {
        "text":        "chasqui.adapters.text.TextAdapter",
        "device":      "chasqui.adapters.device.DeviceAdapter",
        "virtual-mic": "chasqui.adapters.virtual_mic.VirtualMicAdapter",
        "media":       "chasqui.adapters.media.MediaAdapter",
        "bridge":      "chasqui.adapters.bridge.BridgeAdapter",
        "meet":        "chasqui.adapters.meet.MeetAdapter",
    }

    module_path = adapter_map.get(cfg.adapter)
    if not module_path:
        click.echo(f"Unknown adapter: {cfg.adapter!r}", err=True)
        click.echo(f"Available: {', '.join(adapter_map)}", err=True)
        sys.exit(1)

    mod_name, cls_name = module_path.rsplit(".", 1)
    import importlib
    module = importlib.import_module(mod_name)
    adapter_class = getattr(module, cls_name)
    adapter_class(cfg).run()


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
@click.version_option(package_name="chasqui")
def cli():
    """Chasqui — Real-time simultaneous translation.

    \b
    Speak your language. Be understood.

    \b
    Quick start:
      export OPENAI_API_KEY=sk-...
      chasqui listen --from es --to ja
    """
    pass


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--from", "source_lang", default=None, metavar="LANG",
              help="Source language code (es, en, ja, fr, pt, ...)")
@click.option("--to", "target_lang", default=None, metavar="LANG",
              help="Target language code")
@click.option("--adapter", default=None,
              type=click.Choice(["text", "device", "virtual-mic", "media", "bridge", "meet"]),
              help="Input/output adapter (default: from config, else text)")
@click.option("--voice", default=None,
              type=click.Choice(["alloy", "echo", "fable", "onyx", "nova", "shimmer"]),
              help="GPT-4o voice for translated output")
@click.option("--context", default=None,
              help="Conversation context (e.g. 'Tourist in Japan, casual conversation')")
@click.option("--config", "config_path", default=None,
              help="Path to chasqui.yaml")
def listen(source_lang, target_lang, adapter, voice, context, config_path):
    """Start real-time audio translation.

    \b
    Examples:
      chasqui listen                          # es→ja, text adapter
      chasqui listen --from es --to ja --adapter virtual-mic
      chasqui listen --adapter device --voice nova
    """
    cfg = _load_config(
        config_path,
        source_lang=source_lang,
        target_lang=target_lang,
        adapter=adapter,
        voice=voice,
        context=context,
    )

    try:
        cfg.validate()
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    _run_adapter(cfg)


@cli.command()
@click.argument("text", required=False)
@click.option("--from", "source_lang", default=None)
@click.option("--to", "target_lang", default=None)
@click.option("--config", "config_path", default=None)
def translate(text, source_lang, target_lang, config_path):
    """Translate a single text (argument or stdin).

    \b
    Examples:
      chasqui translate "dónde está el baño"
      echo "gracias" | chasqui translate --from es --to ja
    """
    cfg = _load_config(
        config_path,
        source_lang=source_lang,
        target_lang=target_lang,
        adapter="text",
    )

    try:
        cfg.validate()
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if not text and not sys.stdin.isatty():
        text = sys.stdin.read().strip()

    from .adapters.text import TextAdapter
    adapter = TextAdapter(cfg)

    if text:
        click.echo(adapter.translate_once(text))
    else:
        adapter.run()


@cli.command()
def devices():
    """List available audio devices and detect virtual mics."""
    try:
        import sounddevice as sd
    except ImportError:
        click.echo("sounddevice not installed. Run: pip install sounddevice")
        sys.exit(1)

    click.echo("\nAvailable audio devices:\n")
    for i, d in enumerate(sd.query_devices()):
        name: str = d["name"]
        tags = []
        nl = name.lower()
        if any(h in nl for h in ["cable input", "vb-audio", "blackhole", "loopback"]):
            tags.append("virtual mic")
        if any(h in nl for h in ["stereo mix", "what u hear", "monitor"]):
            tags.append("loopback")

        tag_str = f"  << {', '.join(tags)}" if tags else ""
        ins = d["max_input_channels"]
        outs = d["max_output_channels"]
        click.echo(f"  [{i:2d}] {name}  (in:{ins} out:{outs}){tag_str}")

    click.echo()
    click.echo("Tip: use the device name or index in chasqui.yaml > device.mic / device.speaker")


@cli.command()
def langs():
    """List supported language codes."""
    click.echo("\nSupported languages:\n")
    for code, name in sorted(LANG_NAMES.items()):
        click.echo(f"  {code:4s}  {name}")
    click.echo()


@cli.command()
@click.option("--out", default="chasqui.yaml", help="Output path")
def init(out):
    """Generate a starter chasqui.yaml config file."""
    template = """\
api:
  key: ${OPENAI_API_KEY}
  model: gpt-4o-realtime-preview

session:
  source_lang: es
  target_lang: ja
  context: >
    Tourist in Japan for a honeymoon.
    Casual everyday conversations: restaurants, transport, shopping.
    Translate naturally, not literally.

adapter: text   # text | device | virtual-mic | media

voice: alloy    # alloy | echo | fable | onyx | nova | shimmer

# Uncomment and fill for physical device:
# device:
#   mic: "USB PnP Audio Device"
#   speaker: "USB Audio"
#   earphone: "Headphones"
#   ptt_mode: vad

# Uncomment for two-device pair mode:
# pair_mode:
#   enabled: false
#   role: primary
#   peer_address: "192.168.1.x:7373"

logging:
  save_session: true
  show_transcript: true
"""
    path = Path(out)
    if path.exists():
        click.confirm(f"{out} already exists. Overwrite?", abort=True)
    path.write_text(template, encoding="utf-8")
    click.echo(f"Created {out}")
    click.echo("Set your OPENAI_API_KEY env var and run: chasqui listen")
