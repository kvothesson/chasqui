"""Base adapter class."""

import abc

from ..core.config import Config
from ..core.constants import LANG_NAMES
from ..core.pipeline import Pipeline, TranslationEvent
from ..core.session import Session


class BaseAdapter(abc.ABC):
    """All adapters inherit from this.

    Subclasses implement `run()` to set up their audio sources/sinks
    and call `self._make_pipeline()` to get a configured pipeline.
    """

    def __init__(self, config: Config):
        self.config = config
        self._session = Session(
            source_lang=config.source_lang,
            target_lang=config.target_lang,
            context=config.context,
        )

    @abc.abstractmethod
    def run(self) -> None:
        """Start the adapter. Blocks until stopped or KeyboardInterrupt."""
        ...

    def _make_pipeline(self, on_translation=None) -> Pipeline:
        def _combined(event: TranslationEvent):
            self._session.add_turn(
                source_text=event.source_text,
                target_text=event.target_text,
                latency_ms=event.latency_ms,
            )
            if self.config.logging.show_transcript:
                self._print_event(event)
            if on_translation:
                on_translation(event)

        return Pipeline(
            source_lang=self.config.source_lang,
            target_lang=self.config.target_lang,
            api_key=self.config.api_key,
            model=self.config.model,
            context=self.config.context,
            voice=self.config.voice,
            on_translation=_combined,
            vad_threshold=self.config.vad_threshold,
            vad_silence_ms=self.config.vad_silence_ms,
        )

    def _print_event(self, event: TranslationEvent) -> None:
        src = self.config.source_lang.upper()
        tgt = self.config.target_lang.upper()
        print(f"\n  [{src}] {event.source_text}")
        print(f"  [{tgt}] {event.target_text}")
        print(f"        {event.latency_ms:.0f}ms")

    def _print_header(self, adapter_name: str) -> None:
        src = LANG_NAMES.get(self.config.source_lang, self.config.source_lang)
        tgt = LANG_NAMES.get(self.config.target_lang, self.config.target_lang)
        print(f"\nAverroes — {adapter_name}")
        print(f"  {src} → {tgt}")
        print(f"  Voice: {self.config.voice}")
        print()

    def _save_session_if_needed(self) -> None:
        if self.config.logging.save_session and self._session.turns:
            path = self._session.save(self.config.logging.session_dir)
            print(f"\nSession saved: {path}")
        print(f"\nSession summary:\n{self._session.summary()}")
