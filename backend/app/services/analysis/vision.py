"""Analyse visuelle complémentaire par un modèle de vision local (Ollama), si disponible."""
import base64
import json
import logging
from pathlib import Path

from app.core.config import ROOT_DIR
from app.services import ollama_service

log = logging.getLogger("vision")
VISION_HINTS = ("llava", "vision", "moondream", "bakllava", "minicpm-v", "qwen2.5vl", "qwen2-vl", "qwen3-vl", "gemma3", "granite3.2-vision")
PROMPT_FILE = ROOT_DIR / "ai" / "prompts" / "vision_style.md"


def find_model() -> str | None:
    st = ollama_service.status()
    if not st["available"]:
        return None
    for m in st["models"]:
        if any(h in m.lower() for h in VISION_HINTS):
            return m
    return None


def analyze(keyframes: list[Path]) -> dict:
    model = find_model()
    if not model:
        return {"available": False, "note": "Aucun modèle de vision local installé (ex. : gemma3:4b, llava:7b, moondream). Analyse visuelle par heuristiques uniquement."}
    prompt = PROMPT_FILE.read_text(encoding="utf-8")
    results = []
    for kf in keyframes[:6]:
        img = base64.b64encode(kf.read_bytes()).decode()
        try:
            raw = ollama_service.generate(prompt, images=[img], model=model, as_json=True, timeout=240)
            results.append(json.loads(raw))
        except Exception as e:  # noqa: BLE001
            log.warning("Vision échouée sur %s : %s", kf.name, e)
            results.append({"error": str(e)[:200]})
    return {"available": True, "model": model, "frames": results,
            "note": "Descriptions générées par un modèle local : à vérifier, peuvent être imprécises."}
