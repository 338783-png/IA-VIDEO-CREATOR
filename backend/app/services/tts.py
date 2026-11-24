"""Synthèse vocale locale (Piper) : voix françaises, vitesse, pauses, volume, horaires des mots et phonèmes.

Les horaires de phonèmes (alignements Piper) servent aux sous-titres mot à mot et à la synchronisation labiale.
"""
import io
import json
import logging
import re
import threading
import wave
from pathlib import Path

import numpy as np

from app.core.config import settings
from app.core.errors import AppError

log = logging.getLogger("tts")
_cache: dict[str, object] = {}
_lock = threading.Lock()
EXCLUDED_LICENSES = ("agpl",)  # licences trop contraignantes pour une future diffusion publique


def voices_dir() -> Path:
    return settings.models_dir / "piper"


def installed() -> bool:
    try:
        import piper  # noqa: F401
        return True
    except ImportError:
        return False


def _card(onnx: Path) -> dict:
    card = onnx.parent / (onnx.name.replace(".onnx", "") + ".MODEL_CARD")
    out = {"license": None, "source": None}
    if card.exists():
        txt = card.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"License:\s*(.+)", txt)
        u = re.search(r"URL:\s*(\S+)", txt)
        lic = m.group(1).strip() if m else None
        cc = re.search(r"creativecommons\.org/licenses/([a-z\-]+)/([\d.]+)", lic or "")
        if cc:
            lic = f"CC-{cc.group(1).upper()} {cc.group(2)}"
        out = {"license": lic, "source": u.group(1).strip() if u else None}
    return out


def list_voices() -> list[dict]:
    out = []
    for onnx in sorted(voices_dir().glob("*.onnx")):
        cfg_path = onnx.with_name(onnx.name + ".json")
        if not cfg_path.exists():
            continue
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        vid = onnx.name[:-5]
        parts = vid.split("-")
        card = _card(onnx)
        lic = (card["license"] or "").lower()
        spk = cfg.get("speaker_id_map") or {}
        out.append({
            "id": vid, "language": cfg.get("language", {}).get("code") or parts[0],
            "name": parts[1] if len(parts) > 1 else vid, "quality": parts[2] if len(parts) > 2 else None,
            "sample_rate": cfg["audio"]["sample_rate"],
            "speakers": [{"id": str(k), "index": v} for k, v in sorted(spk.items(), key=lambda x: x[1])],
            "license": card["license"], "source": card["source"],
            "excluded": any(x in lic for x in EXCLUDED_LICENSES),
            "attribution": f"Voix Piper « {vid} » — {card['license'] or 'licence à vérifier'} — {card['source'] or ''}".strip(" —"),
        })
    return out


def _voice(voice_id: str):
    if not installed():
        raise AppError("Piper n'est pas installé (pip install piper-tts).", 503, "tts_missing")
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", voice_id):
        raise AppError("Identifiant de voix invalide.", 400, "bad_voice")
    path = voices_dir() / f"{voice_id}.onnx"
    if not path.exists():
        raise AppError(f"Voix « {voice_id} » non installée.", 404, "voice_missing")
    with _lock:
        if voice_id not in _cache:
            from piper import PiperVoice
            try:
                _cache[voice_id] = PiperVoice.load(str(path), include_alignments=True)
            except Exception:  # noqa: BLE001  (onnx absent : pas d'alignements, mais la voix fonctionne)
                log.warning("Alignements indisponibles pour %s", voice_id)
                _cache[voice_id] = PiperVoice.load(str(path))
        return _cache[voice_id]


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text.strip())
    parts = re.split(r"(?<=[.!?…])\s+|\n+", text)
    return [p.strip() for p in parts if p.strip()]


def _words_from_alignment(sentence: str, phons: list[tuple[str, float, float]], t0: float) -> list[dict]:
    """Associe les phonèmes aux mots : les espaces phonétiques séparent les mots."""
    words = [w for w in re.findall(r"[\w'’\-]+[^\s\w]*", sentence) if re.search(r"\w", w)]
    groups, cur = [], []
    for p, s, e in phons:
        if p == " ":
            if cur:
                groups.append(cur)
                cur = []
        elif p not in ("^", "$", "_") and not re.fullmatch(r"[,.;:!?…«»\"()\-]+", p):
            cur.append((p, s, e))
    if cur:
        groups.append(cur)
    if words and len(groups) == len(words):
        return [{"word": w, "start": round(float(t0 + g[0][1]), 3), "end": round(float(t0 + g[-1][2]), 3)} for w, g in zip(words, groups)]
    # repli : répartition proportionnelle à la longueur des mots sur la durée parlée
    if not phons or not words:
        return []
    speech = [x for x in phons if x[0] not in ("^", "$", "_", " ")]
    s0, s1 = (speech[0][1], speech[-1][2]) if speech else (phons[0][1], phons[-1][2])
    total = sum(len(w) for w in words)
    out, t = [], s0
    for w in words:
        d = (s1 - s0) * len(w) / total
        out.append({"word": w, "start": round(float(t0 + t), 3), "end": round(float(t0 + t + d), 3)})
        t += d
    return out


def synthesize(text: str, voice_id: str, speaker: str | None = None, speed: float = 1.0, pause_s: float = 0.35,
               volume_db: float = 0.0, max_chars: int = 20000) -> dict:
    """Retourne {wav_bytes, duration, words, phonemes, sample_rate}."""
    text = (text or "").strip()
    if not text:
        raise AppError("Texte vide.", 400, "empty_text")
    if len(text) > max_chars:
        raise AppError(f"Texte trop long ({len(text)} caractères, max {max_chars}).", 413, "text_too_long")
    speed = max(0.5, min(2.0, float(speed)))
    pause_s = max(0.0, min(3.0, float(pause_s)))
    voice = _voice(voice_id)
    from piper import SynthesisConfig
    spk_map = getattr(voice.config, "speaker_id_map", None) or {}
    spk_idx = None
    if spk_map:
        spk_idx = spk_map.get(speaker) if speaker is not None else next(iter(spk_map.values()))
        if spk_idx is None:
            raise AppError(f"Locuteur « {speaker} » inconnu pour cette voix.", 400, "bad_speaker")
    cfg = SynthesisConfig(speaker_id=spk_idx, length_scale=1.0 / speed, volume=1.0, normalize_audio=True)
    sr = voice.config.sample_rate
    gain = 10 ** (max(-30.0, min(12.0, float(volume_db))) / 20)
    chunks: list[np.ndarray] = []
    words: list[dict] = []
    phonemes: list[dict] = []
    t = 0.0
    for sent in split_sentences(text):
        for ch in voice.synthesize(sent, syn_config=cfg, include_alignments=True):
            audio = ch.audio_float_array.astype(np.float32)
            phons = []
            if ch.phoneme_alignments:
                pos = 0
                for al in ch.phoneme_alignments:
                    s, e = pos / sr, (pos + al.num_samples) / sr
                    phons.append((al.phoneme, s, e))
                    pos += al.num_samples
            else:  # sans alignements : phonèmes répartis uniformément
                n = max(1, len(ch.phonemes))
                d = len(audio) / sr / n
                phons = [(p, i * d, (i + 1) * d) for i, p in enumerate(ch.phonemes)]
            words += _words_from_alignment(sent, phons, t)
            phonemes += [{"p": p, "start": round(float(t + s), 3), "end": round(float(t + e), 3)} for p, s, e in phons if p not in ("^", "$", "_")]
            chunks.append(audio)
            t += float(len(audio) / sr)
        if pause_s:
            chunks.append(np.zeros(int(sr * pause_s), np.float32))
            t += pause_s
    pcm = np.clip(np.concatenate(chunks) * gain, -1, 1)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((pcm * 32767).astype(np.int16).tobytes())
    return {"wav_bytes": buf.getvalue(), "duration": round(len(pcm) / sr, 3), "words": words, "phonemes": phonemes, "sample_rate": sr}
