"""Analyse d'un média source (vidéo ou audio) pour le montage : plans, silences, énergie, mouvement, parole."""
from pathlib import Path

import numpy as np

from app.services import ffmpeg_service, transcription
from app.services.analysis import audio as audio_mod
from app.services.analysis import scenes as scenes_mod
from app.services.analysis.decode import analysis_size, gray, iter_frames, read_audio
from app.services.jobs import JobContext


def _speech_silences(y: np.ndarray, sr: int, min_dur: float = 0.35) -> list[list[float]]:
    """Silences relatifs à la parole (seuil adaptatif sur l'énergie)."""
    hop = int(sr * 0.02)
    n = len(y) // hop
    if n == 0:
        return []
    rms = np.sqrt((y[: n * hop].reshape(n, hop) ** 2).mean(1) + 1e-12)
    db = 20 * np.log10(rms)
    loud = np.percentile(db, 90)
    thr = max(-55.0, loud - 30)
    quiet = db < thr
    out, start = [], None
    for i, q in enumerate(np.append(quiet, False)):
        if q and start is None:
            start = i
        elif not q and start is not None:
            s, e = start * hop / sr, i * hop / sr
            if e - s >= min_dur:
                out.append([round(s, 2), round(e, 2)])
            start = None
    return out


def _energy_per_second(y: np.ndarray, sr: int) -> list[float]:
    n = len(y) // sr
    if n == 0:
        return []
    rms = np.sqrt((y[: n * sr].reshape(n, sr) ** 2).mean(1) + 1e-12)
    db = 20 * np.log10(rms)
    lo, hi = np.percentile(db, 5), np.percentile(db, 98)
    return [round(float(x), 3) for x in np.clip((db - lo) / (hi - lo + 1e-6), 0, 1)]


def analyze(ctx: JobContext, path: Path, category: str, transcribe: bool = True, language: str = "fr",
            progress_range: tuple[float, float] = (0.0, 1.0), label: str = "") -> tuple[dict, dict]:
    a, b = progress_range
    span = b - a
    probe = ffmpeg_service.probe(path)
    duration = probe.get("duration") or 0.0
    data: dict = {"duration": duration, "probe": probe}

    if category == "video" and probe.get("video"):
        v = probe["video"]
        fps = 10.0
        w, h = analysis_size(v["width"], v["height"], 64)
        change, luma, motion = [], [], []
        prev_g = prev_h = None
        expected = max(1, int(duration * fps))
        for i, f in enumerate(iter_frames(ctx, path, fps, w, h)):
            g = gray(f.astype(np.float32))
            hh = scenes_mod.hist(f)
            change.append(0.0 if prev_g is None else scenes_mod.frame_change(prev_g, g, prev_h, hh))
            motion.append(0.0 if prev_g is None else float(np.abs(g - prev_g).mean() / 255))
            luma.append(float(g.mean() / 255))
            prev_g, prev_h = g, hh
            if i % 20 == 0:
                ctx.progress(a + span * 0.35 * min(1, i / expected), f"Analyse des images {label}…")
        cuts = scenes_mod.detect_cuts(np.array(change), fps) if change else []
        bounds = [0.0] + [c / fps for c in cuts] + [duration]
        data["shots"] = [{"start": round(s, 3), "end": round(e, 3)} for s, e in zip(bounds[:-1], bounds[1:]) if e - s > 0.05]
        sec = int(fps)
        data["motion_per_second"] = [round(float(np.mean(motion[i:i + sec])), 4) for i in range(0, len(motion), sec)]
        data["black_ratio"] = round(float(np.mean(np.array(luma) < 0.05)), 3) if luma else 0.0

    transcript: dict = {}
    if probe.get("audio"):
        ctx.progress(a + span * 0.4, f"Lecture audio {label}…", force=True)
        y = read_audio(ctx, path, 16000)
        data["silences"] = _speech_silences(y, 16000)
        data["energy_per_second"] = _energy_per_second(y, 16000)
        env = audio_mod.onset_envelope(read_audio(ctx, path, audio_mod.SR)) if category == "audio" else None
        if env is not None:
            bpm, conf, phase = audio_mod.tempo(env)
            data["tempo_bpm"], data["tempo_confidence"], data["beat_phase_s"] = bpm, conf, phase
        if transcribe and transcription.installed():
            transcript = transcription.transcribe(ctx, y, 16000, language, (a + span * 0.45, b), label)
            data["speech_seconds"] = round(sum(s["end"] - s["start"] for s in transcript["segments"]), 2)
        elif transcribe:
            data["transcription_note"] = "Whisper non installé : transcription ignorée."
    return data, transcript
