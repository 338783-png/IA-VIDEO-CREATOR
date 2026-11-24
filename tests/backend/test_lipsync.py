"""Module 2D.2 — synchronisation labiale (commune 2D/3D)."""
import numpy as np
import pytest

from app.services import lipsync, tts

VOICE = "fr_FR-siwis-medium"
has_voice = any(v["id"] == VOICE for v in tts.list_voices())


def _check_track(tr):
    assert tr and all(s["viseme"] in lipsync.VISEMES for s in tr)
    assert all(abs(a["end"] - b["start"]) < 1e-3 for a, b in zip(tr, tr[1:]))  # aucun trou
    assert min(s["end"] - s["start"] for s in tr) >= lipsync.MIN_MBP - 1e-3  # pas de scintillement


def test_mapping_basics():
    assert [lipsync.viseme_of(p) for p in "pbm"] == ["MBP"] * 3
    assert lipsync.viseme_of("f") == lipsync.viseme_of("v") == "FV"
    assert lipsync.viseme_of("ɔ̃") == "O" and lipsync.viseme_of("ˈ") is None


def test_vowel_between_closures_is_kept():
    """Régression : le « a » de « m'appelle » (58 ms entre deux fermetures) ne doit pas disparaître."""
    ph = [{"p": "m", "start": 0.0, "end": 0.058}, {"p": "a", "start": 0.058, "end": 0.116}, {"p": "p", "start": 0.116, "end": 0.151},
          {"p": "ˈ", "start": 0.151, "end": 0.186}, {"p": "ɛ", "start": 0.186, "end": 0.221}, {"p": "l", "start": 0.221, "end": 0.291},
          {"p": " ", "start": 0.291, "end": 0.4}]
    tr = lipsync.track_from_phonemes(ph)
    assert [s["viseme"] for s in tr] == ["MBP", "A", "MBP", "E", "L", "rest"]
    _check_track(tr)


@pytest.mark.skipif(not has_voice, reason="voix Piper absente")
def test_real_piper_sentences():
    for text in ("Bonjour, je m'appelle Paul et j'aime beaucoup la musique.",
                 "Une intelligence artificielle apprend grâce à des millions d'exemples.",
                 "Le chat gris boit un bol de lait frais ; il ronronne doucement."):
        r = tts.synthesize(text, VOICE, pause_s=0.2)
        unknown = {p["p"] for p in r["phonemes"] if not lipsync.PAUSE.match(p["p"]) and lipsync.viseme_of(p["p"]) is None} - {"ˈ", "ˌ", "ː", "̃"}
        assert not unknown, unknown
        tr = lipsync.track_from_phonemes(r["phonemes"])
        _check_track(tr)
        assert tr[-1]["end"] <= r["duration"] + 0.01
        # chaque « m/b/p » prononcé ferme les lèvres à cet instant (à l'anticipation près)
        for ph in r["phonemes"]:
            if ph["p"] in ("m", "b", "p"):
                mid = (ph["start"] + ph["end"]) / 2 - lipsync.ANTICIPATION
                assert lipsync.viseme_at(tr, mid) == "MBP", (text, ph)


def test_from_words_and_audio_fallbacks():
    words = [{"word": "ma", "start": 0.0, "end": 0.3}, {"word": "pomme", "start": 0.6, "end": 1.0}]
    tr = lipsync.track_from_words(words, lambda w: {"ma": ["m", "a"], "pomme": ["p", "ɔ", "m"]}[w])
    assert [s["viseme"] for s in tr] == ["MBP", "A", "rest", "MBP", "O", "MBP"]
    sr = 16000
    t = np.arange(sr * 2) / sr
    audio = np.where(t < 1.0, 0.0005 * np.random.default_rng(0).standard_normal(len(t)), 0.5 * np.sin(2 * np.pi * 200 * t))
    tr = lipsync.track_from_audio(audio.astype(np.float32), sr)
    assert lipsync.viseme_at(tr, 0.5) == "rest" and lipsync.viseme_at(tr, 1.5) in ("A", "O")


def test_viseme_at_and_adapter():
    tr = [{"viseme": "A", "start": 0.0, "end": 0.1}, {"viseme": "MBP", "start": 0.1, "end": 0.2}]
    assert [lipsync.viseme_at(tr, t) for t in (0.0, 0.099, 0.1, 0.25, -1)] == ["A", "A", "MBP", "rest", "rest"]
    rig_vrm = ["rest", "A", "I", "U", "E", "O"]  # formes VRM classiques (pas de MBP/FV/L)
    assert lipsync.adapt("MBP", rig_vrm) == "rest" and lipsync.adapt("FV", rig_vrm) == "E" and lipsync.adapt("L", rig_vrm) == "E"
    assert lipsync.adapt("A", ["closed", "open"]) == "open"  # mâchoire simple
    assert lipsync.adapt("rest", ["closed", "open"]) == "closed"
