"""Session: tracks conversation state and history."""

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Literal

SessionState = Literal["idle", "listening", "translating", "speaking"]


@dataclass
class Turn:
    timestamp: float
    source_lang: str
    target_lang: str
    source_text: str
    target_text: str
    latency_ms: float = 0.0


@dataclass
class Session:
    source_lang: str
    target_lang: str
    context: str = ""
    state: SessionState = "idle"
    turns: List[Turn] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)

    def add_turn(self, source_text: str, target_text: str, latency_ms: float = 0.0) -> Turn:
        turn = Turn(
            timestamp=time.time(),
            source_lang=self.source_lang,
            target_lang=self.target_lang,
            source_text=source_text,
            target_text=target_text,
            latency_ms=latency_ms,
        )
        self.turns.append(turn)
        return turn

    def save(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        filename = f"session_{int(self.started_at)}.json"
        path = directory / filename
        data = {
            "source_lang": self.source_lang,
            "target_lang": self.target_lang,
            "context": self.context,
            "started_at": self.started_at,
            "turns": [asdict(t) for t in self.turns],
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    @property
    def avg_latency_ms(self) -> float:
        if not self.turns:
            return 0.0
        return sum(t.latency_ms for t in self.turns) / len(self.turns)

    def summary(self) -> str:
        duration = time.time() - self.started_at
        lines = [
            f"  {self.source_lang} → {self.target_lang}",
            f"  Turns   : {len(self.turns)}",
            f"  Duration: {duration:.0f}s",
            f"  Avg latency: {self.avg_latency_ms:.0f}ms",
        ]
        return "\n".join(lines)
