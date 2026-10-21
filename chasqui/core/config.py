"""Configuration loading from YAML + environment variables."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

load_dotenv()


@dataclass
class DeviceConfig:
    mic: Optional[str] = None        # microphone device name or index
    speaker: Optional[str] = None    # outward speaker (Japanese person hears this)
    earphone: Optional[str] = None   # earphone (user hears translation here)
    loopback: Optional[str] = None   # capture device for the other side's audio (bridge/meet IN)
    ptt_mode: str = "vad"            # vad | hold | toggle


@dataclass
class PairModeConfig:
    enabled: bool = False
    role: str = "primary"            # primary | secondary
    peer_address: Optional[str] = None   # "192.168.x.x:7373"


@dataclass
class PricingConfig:
    """Cost meter. Rates default to core.pricing; set them here when OpenAI
    changes a price, so it stays a config edit."""
    per_minute: Optional[float] = None              # duration-billed models
    transcription_per_minute: Optional[float] = None
    count_transcription: bool = True                # see core/pricing.py
    budget: Optional[float] = None                  # USD; enables "remaining"


@dataclass
class LoggingConfig:
    save_session: bool = False
    session_dir: Path = field(
        default_factory=lambda: Path.home() / ".chasqui" / "sessions"
    )
    show_transcript: bool = True


@dataclass
class Config:
    # API
    api_key: str = field(default_factory=lambda: os.environ.get("OPENAI_API_KEY", ""))
    model: str = "gpt-realtime-translate"
    text_model: str = "gpt-4o-mini"   # Chat Completions model for the text adapter
    isolate_turns: bool = True       # gpt-realtime: translate each turn with no history

    # Translation
    source_lang: str = "es"
    target_lang: str = "ja"
    context: str = ""

    # Adapter
    adapter: str = "text"            # text | device | virtual-mic | media

    # Voice (GPT-4o Realtime voices)
    voice: str = "alloy"             # alloy | echo | fable | onyx | nova | shimmer

    # Hardware
    device: DeviceConfig = field(default_factory=DeviceConfig)
    pair_mode: PairModeConfig = field(default_factory=PairModeConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    pricing: PricingConfig = field(default_factory=PricingConfig)

    # VAD tuning
    vad_threshold: float = 0.5
    vad_silence_ms: int = 600

    # ------------------------------------------------------------------

    @classmethod
    def from_yaml(cls, path: Path) -> "Config":
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, d: dict) -> "Config":
        cfg = cls()

        if api := d.get("api"):
            cfg.api_key = _resolve_env(api.get("key", cfg.api_key))
            cfg.model = api.get("model", cfg.model)
            cfg.text_model = api.get("text_model", cfg.text_model)
            cfg.isolate_turns = api.get("isolate_turns", cfg.isolate_turns)

        if session := d.get("session"):
            cfg.source_lang = session.get("source_lang", cfg.source_lang)
            cfg.target_lang = session.get("target_lang", cfg.target_lang)
            cfg.context = session.get("context", cfg.context)

        cfg.adapter = d.get("adapter", cfg.adapter)
        cfg.voice = d.get("voice", cfg.voice)
        cfg.vad_threshold = d.get("vad_threshold", cfg.vad_threshold)
        cfg.vad_silence_ms = d.get("vad_silence_ms", cfg.vad_silence_ms)

        if dev := d.get("device"):
            cfg.device = DeviceConfig(
                mic=dev.get("mic"),
                speaker=dev.get("speaker"),
                earphone=dev.get("earphone"),
                loopback=dev.get("loopback"),
                ptt_mode=dev.get("ptt_mode", "vad"),
            )

        if pair := d.get("pair_mode"):
            cfg.pair_mode = PairModeConfig(
                enabled=pair.get("enabled", False),
                role=pair.get("role", "primary"),
                peer_address=pair.get("peer_address"),
            )

        if price := d.get("pricing"):
            cfg.pricing = PricingConfig(
                per_minute=price.get("per_minute"),
                transcription_per_minute=price.get("transcription_per_minute"),
                count_transcription=price.get("count_transcription", True),
                budget=price.get("budget"),
            )

        if log := d.get("logging"):
            cfg.logging = LoggingConfig(
                save_session=log.get("save_session", False),
                session_dir=Path(log.get("session_dir", cfg.logging.session_dir)),
                show_transcript=log.get("show_transcript", True),
            )

        return cfg

    def validate(self) -> None:
        if not self.api_key:
            raise ValueError(
                "No API key found. Open the window (chasqui ui) to set one up, "
                "set the OPENAI_API_KEY env var, or add 'api.key' to your chasqui.yaml."
            )


def _resolve_env(value: str) -> str:
    """Resolve ${ENV_VAR} references in config values."""
    if value and value.startswith("${") and value.endswith("}"):
        env_name = value[2:-1]
        return os.environ.get(env_name, "")
    return value


def load_config(path: Optional[str | Path] = None) -> Config:
    """Load config from an explicit path, the auto-detected one, or defaults."""
    resolved = Path(path) if path else find_config()
    cfg = Config.from_yaml(resolved) if resolved else Config()
    if not cfg.api_key:
        # Last resort, after the yaml and OPENAI_API_KEY: the key the setup
        # window saved. A project chasqui.yaml with `key: ${OPENAI_API_KEY}`
        # and no env var would otherwise hide it from an installed chasqui.
        from .firstrun import stored_api_key
        cfg.api_key = stored_api_key()
    return cfg


def find_config() -> Optional[Path]:
    """Search for chasqui.yaml in cwd then home."""
    candidates = [
        Path("chasqui.yaml"),
        Path("chasqui.yml"),
        Path.home() / ".chasqui" / "config.yaml",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None
