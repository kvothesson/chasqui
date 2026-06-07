"""Test: captura mic 3 segundos y reproduce por el output default.
Si escuchás tu propia voz, el audio I/O funciona.

Run: python examples/audio_test.py
"""
import sounddevice as sd
import numpy as np

SAMPLE_RATE = 24000
DURATION = 3

print("Dispositivos disponibles:")
for i, d in enumerate(sd.query_devices()):
    if d["max_input_channels"] > 0 or d["max_output_channels"] > 0:
        print(f"  [{i}] {d['name']}  in:{d['max_input_channels']} out:{d['max_output_channels']}")

print(f"\nGrabando {DURATION}s desde el mic default... hablá algo")
audio = sd.rec(SAMPLE_RATE * DURATION, samplerate=SAMPLE_RATE, channels=1, dtype='float32')
sd.wait()
print("Reproduciendo por el output default...")
sd.play(audio, samplerate=SAMPLE_RATE)
sd.wait()
print("Listo. ¿Lo escuchaste?")
