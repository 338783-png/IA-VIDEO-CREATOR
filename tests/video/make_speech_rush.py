"""Génère un « rush » parlé en français (voix Piper locale) avec défauts connus, pour tester Whisper et le planificateur.

Contenu (dans l'ordre) :
  1. prise ratée  : « Aujourd'hui je vais vous montrer trois astuces. »
  2. reprise      : « Aujourd'hui je vais vous montrer trois astuces simples pour mieux apprendre. »
  3. hésitation   : « Euh... »
  4. silence de 2,5 s
  5. « Première astuce : relisez vos notes le soir même. »
  6. « Deuxième astuce : expliquez la leçon à quelqu'un d'autre. »
  7. « Troisième astuce : faites des pauses régulières. »
"""
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VOICE = ROOT / "ai" / "models" / "piper" / "fr_FR-siwis-medium.onnx"
LINES = [
    ("Aujourd'hui je vais vous montrer trois astuces.", 0.6),
    ("Aujourd'hui je vais vous montrer trois astuces simples pour mieux apprendre.", 0.7),
    ("Euh...", 0.4),
    (None, 2.5),
    ("Première astuce : relisez vos notes le soir même.", 0.6),
    ("Deuxième astuce : expliquez la leçon à quelqu'un d'autre.", 0.6),
    ("Troisième astuce : faites des pauses régulières.", 0.8),
]


def synth(out_wav: Path) -> float:
    from piper import PiperVoice
    voice = PiperVoice.load(str(VOICE))
    sr = voice.config.sample_rate
    frames = b""
    for text, pause in LINES:
        if text:
            for chunk in voice.synthesize(text):
                frames += chunk.audio_int16_bytes
        frames += b"\x00\x00" * int(sr * pause)
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(frames)
    return len(frames) / 2 / sr


def make(out_mp4: Path) -> Path:
    tmp = Path(tempfile.mkdtemp())
    wav = tmp / "voix.wav"
    dur = synth(wav)
    # vidéo « face caméra » simulée : fond animé 1920x1080 (paysage, comme un rush de téléphone tenu à l'horizontale)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc2=s=1920x1080:r=30:d={dur:.2f}", "-i", str(wav),
                    "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out_mp4)], check=True)
    return out_mp4


if __name__ == "__main__":
    print(make(Path(sys.argv[1] if len(sys.argv) > 1 else "rush_parole.mp4")))
