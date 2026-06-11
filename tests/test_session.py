"""Session tracking and export."""

import json

from chasqui.core.session import Session


def test_add_turn_and_avg_latency():
    s = Session(source_lang="es", target_lang="ja")
    s.add_turn("hola", "こんにちは", latency_ms=100)
    s.add_turn("gracias", "ありがとう", latency_ms=300)
    assert len(s.turns) == 2
    assert s.avg_latency_ms == 200


def test_save_writes_json(tmp_path):
    s = Session(source_lang="es", target_lang="ja")
    s.add_turn("hola", "こんにちは", latency_ms=100)
    path = s.save(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["source_lang"] == "es"
    assert data["turns"][0]["target_text"] == "こんにちは"
