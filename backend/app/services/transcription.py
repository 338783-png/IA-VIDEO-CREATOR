"""Transcription locale avec faster-whisper (modèles Whisper, sans PyTorch)."""
import logging
import os
import threading
from pathlib import Path

import numpy as np

from app.core.config import settings
from app.core.errors import AppError
from app.services.jobs import JobContext

log = logging.getLogger("whisper")
_model = None
_model_name = None
_lock = threading.Lock()

MODEL_SIZES_MB = {"tiny": 75, "base": 145, "small": 485, "medium": 1530, "large-v3": 3100}


def model_dir() -> Path:
    return settings.models_dir / "whisper"


def installed() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def status() -> dict:
    name = settings.whisper_model
    local = model_dir() / f"models--Systran--faster-whisper-{name}"
    return {"library": installed(), "model": name, "downloaded": local.exists() and any(local.rglob("model.bin")),
            "approx_size_mb": MODEL_SIZES_MB.get(name), "path": str(model_dir())}


def _load():
    global _model, _model_name
    if not installed():
        raise AppError("faster-whisper n'est pas installé (pip install faster-whisper).", 503, "whisper_missing")
    with _lock:
        if _model is None or _model_name != settings.whisper_model:
            from faster_whisper import WhisperModel
            model_dir().mkdir(parents=True, exist_ok=True)
            threads = settings.whisper_threads or max(1, (os.cpu_count() or 4) - 2)
            log.info("Chargement du modèle Whisper %s", settings.whisper_model)
            _model = WhisperModel(settings.whisper_model, device="cpu", compute_type=settings.whisper_compute_type,
                                  cpu_threads=threads, download_root=str(model_dir()))
            _model_name = settings.whisper_model
    return _model


def transcribe(ctx: JobContext | None, audio: np.ndarray, sr: int = 16000, language: str | None = "fr",
               progress_range: tuple[float, float] = (0.0, 1.0), label: str = "") -> dict:
    """audio : mono float32 à 16 kHz. Retourne segments + mots horodatés."""
    duration = len(audio) / sr
    if duration < 0.3:
        return {"language": language, "segments": [], "words": [], "duration": duration}
    if ctx:
        ctx.progress(progress_range[0], f"Chargement du modèle Whisper « {settings.whisper_model} »…", force=True)
    model = _load()
    segs_iter, info = model.transcribe(audio, language=language, word_timestamps=True, vad_filter=True,
                                       vad_parameters={"min_silence_duration_ms": 400}, beam_size=5,
                                       condition_on_previous_text=False)
    segments, words = [], []
    a, b = progress_range
    for seg in segs_iter:
        if ctx:
            ctx.progress(a + (b - a) * min(1.0, seg.end / duration), f"Transcription {label}{seg.end:.0f}/{duration:.0f} s…")
        ws = [{"word": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3), "prob": round(w.probability, 3)}
              for w in (seg.words or []) if w.word.strip()]
        words.extend(ws)
        segments.append({"id": len(segments), "start": round(seg.start, 3), "end": round(seg.end, 3), "text": seg.text.strip(),
                         "avg_logprob": round(seg.avg_logprob, 3), "no_speech_prob": round(seg.no_speech_prob, 3), "words": ws})
    return {"language": info.language, "language_probability": round(info.language_probability, 3),
            "segments": segments, "words": words, "duration": round(duration, 3), "model": settings.whisper_model}
