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

from .adapters import ADAPTER_NAMES, build_adapter
from .core.config import Config, load_config
from .core.constants import LANG_NAMES


def _load_config(config_path: Optional[str], **overrides) -> Config:
    """Load config from file (auto-detected or explicit), apply CLI overrides."""
    cfg = load_config(config_path)

    for key, val in overrides.items():
        if val is not None:
            setattr(cfg, key, val)

    return cfg


def _run_adapter(cfg: Config) -> None:
    try:
        adapter = build_adapter(cfg)
    except KeyError as e:
        click.echo(f"Error: {e.args[0]}", err=True)
        sys.exit(1)
    adapter.run()


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
              type=click.Choice(ADAPTER_NAMES),
              help="Input/output adapter (default: from config, else text)")
@click.option("--voice", default=None,
              type=click.Choice(["alloy", "echo", "fable", "onyx", "nova", "shimmer"]),
              help="GPT-4o voice for translated output")
@click.option("--context", default=None,
              help="Conversation context (e.g. 'Tourist in Japan, casual conversation')")
@click.option("--mic", default=None, metavar="DEVICE",
              help="Microphone device name or index — for separate mic/headphone "
                   "setups (see 'chasqui devices')")
@click.option("--earphone", default=None, metavar="DEVICE",
              help="Output device for the translated audio YOU hear "
                   "(default: system default output)")
@click.option("--loopback", default=None, metavar="DEVICE",
              help="Capture device for the other side's audio (bridge/meet/headset IN)")
@click.option("--config", "config_path", default=None,
              help="Path to chasqui.yaml")
def listen(source_lang, target_lang, adapter, voice, context, mic, earphone, loopback, config_path):
    """Start real-time audio translation.

    \b
    Examples:
      chasqui listen                          # es→ja, text adapter
      chasqui listen --from es --to ja --adapter virtual-mic
      chasqui listen --adapter device --voice nova
      chasqui listen --adapter headset --mic "USB Micro" --earphone "Auriculares"
    """
    cfg = _load_config(
        config_path,
        source_lang=source_lang,
        target_lang=target_lang,
        adapter=adapter,
        voice=voice,
        context=context,
    )
    if mic is not None:
        cfg.device.mic = mic
    if earphone is not None:
        cfg.device.earphone = earphone
    if loopback is not None:
        cfg.device.loopback = loopback

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
@click.option("--from", "source_lang", default=None, metavar="LANG",
              help="Source language (default: from config, else es)")
@click.option("--to", "target_lang", default=None, metavar="LANG",
              help="Target language (default: from config, else ja)")
@click.option("--config", "config_path", default=None)
def check(source_lang, target_lang, config_path):
    """Smoke-test the translation pipeline without mic or speakers.

    \b
    Synthesizes a phrase via TTS, runs it through the realtime pipeline,
    and prints PASS/FAIL with the translated transcript.
    No audio hardware required.
    """
    from .core.selftest import run_check, test_phrase_for

    cfg = _load_config(config_path, source_lang=source_lang, target_lang=target_lang)
    try:
        cfg.validate()
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    src_name = LANG_NAMES.get(cfg.source_lang, cfg.source_lang)
    tgt_name = LANG_NAMES.get(cfg.target_lang, cfg.target_lang)
    phrase = test_phrase_for(cfg.source_lang, src_name)

    click.echo(f"\nChasqui check — {src_name} → {tgt_name}")
    click.echo(f"  Model:  {cfg.model}")
    click.echo(f"  Phrase: {phrase!r}")
    click.echo()

    result = run_check(cfg, phrase=phrase, on_progress=lambda msg: click.echo(f"  {msg}"))

    if not result.ok:
        click.echo()
        click.echo(f"  FAIL: {result.error}", err=True)
        click.echo("  Tip:  CHASQUI_DEBUG=1 chasqui check", err=True)
        sys.exit(1)

    click.echo()
    click.echo("  Result:")
    click.echo(f"    {cfg.source_lang.upper()}: {result.source_text}")
    click.echo(f"    {cfg.target_lang.upper()}: {result.target_text}")
    click.echo(f"    {result.latency_ms:.0f} ms")
    click.echo()
    click.echo("  PASS")


@cli.command()
@click.option("--config", "config_path", default=None,
              help="Path to chasqui.yaml")
def ui(config_path):
    """Open the desktop interface.

    \b
    Start/stop a session, pick languages and mode, run the smoke test and
    watch the transcript live. Audio devices stay on Auto unless you open
    the devices panel and choose them.
    """
    from .ui.app import launch
    sys.exit(launch(config_path=config_path))


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
  model: gpt-realtime-translate   # or gpt-realtime (higher quality, higher cost)

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
