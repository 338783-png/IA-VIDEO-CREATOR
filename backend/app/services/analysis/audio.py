"""Analyse audio : volume, silences, attaques (onsets), tempo, synchronisation avec les coupes."""
import re
import subprocess
from pathlib import Path

import numpy as np

from app.core.config import settings

SR = 22050
HOP = 512


def loudness_lufs(path: Path) -> float | None:
    cmd = [settings.ffmpeg_bin, "-nostats", "-hide_banner", "-i", str(path), "-map", "0:a:0", "-af", "ebur128", "-f", "null", "-"]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    m = re.findall(r"I:\s+(-?\d+(?:\.\d+)?) LUFS", res.stderr)
    return float(m[-1]) if m else None


def onset_envelope(y: np.ndarray) -> np.ndarray:
    n_fft = 1024
    if len(y) < n_fft:
        return np.zeros(1)
    win = np.hanning(n_fft).astype(np.float32)
    frames = np.lib.stride_tricks.sliding_window_view(y, n_fft)[::HOP] * win
    mag = np.log1p(10 * np.abs(np.fft.rfft(frames, axis=1)))
    flux = np.maximum(0, np.diff(mag, axis=0)).sum(1)
    flux = np.concatenate([[0], flux])
    return flux / (flux.max() + 1e-9)


def pick_onsets(env: np.ndarray) -> np.ndarray:
    if len(env) < 8:
        return np.array([])
    thr = np.median(env) + 1.5 * env.std()
    peaks = [i for i in range(3, len(env) - 3) if env[i] >= thr and env[i] == env[i - 3:i + 4].max()]
    return np.array(peaks) * HOP / SR


def tempo(env: np.ndarray) -> tuple[float | None, float, float]:
    """Retourne (bpm, confiance 0..1, phase en s)."""
    fr = SR / HOP
    if len(env) < fr * 4:
        return None, 0.0, 0.0
    x = env - env.mean()
    ac = np.correlate(x, x, "full")[len(x) - 1:]
    if ac[0] <= 0:
        return None, 0.0, 0.0
    ac = ac / ac[0]
    lags = np.arange(len(ac))
    bpm = 60 * fr / np.maximum(lags, 1)
    valid = (bpm >= 60) & (bpm <= 190)
    weight = np.exp(-0.5 * (np.log2(np.maximum(bpm, 1) / 120) / 0.9) ** 2)  # préférence douce autour de 120
    score = np.where(valid, ac * weight, -1)
    lag = int(np.argmax(score))
    conf = float(ac[lag])
    # affinage parabolique
    if 1 <= lag < len(ac) - 1:
        a, b, c = ac[lag - 1], ac[lag], ac[lag + 1]
        off = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else 0
        lag_f = lag + off
    else:
        lag_f = lag
    period = lag_f / fr
    phases = np.linspace(0, period, 40, endpoint=False)
    t_env = np.arange(len(env)) / fr
    best_phase = max(phases, key=lambda p: env[np.clip(((np.arange(p, t_env[-1], period)) * fr).astype(int), 0, len(env) - 1)].sum())
    return float(round(60 / period, 1)), float(round(conf, 3)), float(best_phase)


def silences(y: np.ndarray, min_dur: float = 0.3) -> list[list[float]]:
    if not len(y):
        return []
    n = len(y) // HOP
    rms = np.sqrt((y[: n * HOP].reshape(n, HOP) ** 2).mean(1) + 1e-12)
    db = 20 * np.log10(rms)
    thr = max(-50.0, float(db.max()) - 40)
    quiet = db < thr
    out, start = [], None
    for i, q in enumerate(np.append(quiet, False)):
        if q and start is None:
            start = i
        elif not q and start is not None:
            s, e = start * HOP / SR, i * HOP / SR
            if e - s >= min_dur:
                out.append([round(s, 2), round(e, 2)])
            start = None
    return out


def analyze(y: np.ndarray, path: Path, cut_times: list[float], duration: float) -> dict:
    if len(y) < SR * 0.5:
        return {"has_audio": False}
    env = onset_envelope(y)
    onsets = pick_onsets(env)
    bpm, conf, phase = tempo(env)
    sil = silences(y)
    sil_ratio = sum(e - s for s, e in sil) / duration if duration else 0
    fr = SR / HOP
    tol = 0.08

    def near(t, arr):
        return len(arr) and np.min(np.abs(arr - t)) <= tol

    cuts_on_onset = sum(1 for c in cut_times if near(c, onsets))
    beat_grid = np.arange(phase, duration + 1, 60 / bpm) if bpm else np.array([])
    cuts_on_beat = sum(1 for c in cut_times if near(c, beat_grid)) if bpm and conf > 0.25 else 0
    # effets sonores probables : attaque forte exactement à la coupe
    strong = np.percentile(env, 95) if len(env) else 1
    sfx = 0
    for c in cut_times:
        i0, i1 = int((c - 0.06) * fr), int((c + 0.08) * fr) + 1
        if i1 > i0 >= 0 and env[i0:i1].max() >= strong:
            sfx += 1
    n_cuts = len(cut_times)
    rhythmic = bool(bpm and conf > 0.3)
    return {
        "has_audio": True,
        "loudness_lufs": loudness_lufs(path),
        "silences": sil[:50],
        "silence_ratio": round(sil_ratio, 3),
        "onsets_count": int(len(onsets)),
        "onsets_per_second": round(len(onsets) / duration, 2) if duration else 0,
        "tempo_bpm": bpm if rhythmic else None,
        "tempo_confidence": conf,
        "beat_phase_s": round(phase, 3) if rhythmic else None,
        "music": {
            "likely": rhythmic and sil_ratio < 0.25,
            "description": "fond musical rythmé probable" if rhythmic and sil_ratio < 0.25 else
                           "pas de pulsation régulière détectée (parole, ambiance ou musique libre)",
            "confidence": "moyenne" if conf > 0.5 else "faible",
            "note": "La distinction parole/musique sera affinée par Whisper (transcription).",
        },
        "sync": {
            "cuts": n_cuts,
            "cuts_on_onset_ratio": round(cuts_on_onset / n_cuts, 2) if n_cuts else None,
            "cuts_on_beat_ratio": round(cuts_on_beat / n_cuts, 2) if n_cuts and rhythmic else None,
            "tolerance_ms": int(tol * 1000),
        },
        "sound_effects": {
            "on_cuts_ratio": round(sfx / n_cuts, 2) if n_cuts else None,
            "description": "attaques sonores fortes alignées sur les coupes (whoosh/impact probables)" if n_cuts and sfx / n_cuts > 0.5 else
                           "pas d'effet sonore systématique détecté aux coupes",
            "confidence": "faible",
        },
    }
