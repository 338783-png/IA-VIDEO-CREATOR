"""Scénarios dialogués (communs 2D/3D) : génération par le LLM local, validation stricte, édition manuelle."""
import json
import logging
import re

from app.core.config import ROOT_DIR
from app.core.errors import AppError
from app.services import ollama_service

log = logging.getLogger("scenario")
EMOTIONS = ["neutre", "joyeux", "enthousiaste", "surpris", "pensif", "triste", "inquiet", "en colère"]
CAMERAS = ["plan_moyen", "plan_rapproche", "plan_large", "zoom_avant", "zoom_arriere", "panoramique"]
MAX_SCENES, MAX_LINES, MAX_TEXT = 30, 200, 400
WORDS_PER_SECOND = 2.6  # débit d'une voix Piper à vitesse 1


def estimate_seconds(text: str, speed: float = 1.0) -> float:
    return round(len(re.findall(r"\w+", text)) / (WORDS_PER_SECOND * speed), 2)


def _clean(s, n) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()[:n]


def validate(data: dict, character_ids: set[int]) -> dict:
    """Vérifie et normalise un scénario (génération ou modification manuelle)."""
    if not isinstance(data, dict):
        raise AppError("Scénario invalide.", 422, "bad_scenario")
    scenes_in = data.get("scenes")
    if not isinstance(scenes_in, list) or not scenes_in:
        raise AppError("Le scénario doit contenir au moins une scène.", 422, "bad_scenario")
    if len(scenes_in) > MAX_SCENES:
        raise AppError(f"Trop de scènes ({MAX_SCENES} maximum).", 422, "bad_scenario")
    scenes, n_lines, total = [], 0, 0.0
    for si, sc in enumerate(scenes_in):
        lines = []
        for li, ln in enumerate(sc.get("lines") or []):
            text = _clean(ln.get("text"), MAX_TEXT)
            if not text:
                continue
            cid = ln.get("character_id")
            try:
                cid = int(cid)
            except (TypeError, ValueError) as e:
                raise AppError(f"Scène {si + 1}, réplique {li + 1} : personnage manquant.", 422, "bad_character") from e
            if cid not in character_ids:
                raise AppError(f"Scène {si + 1}, réplique {li + 1} : personnage {cid} inconnu.", 422, "bad_character")
            emotion = ln.get("emotion") if ln.get("emotion") in EMOTIONS else "neutre"
            pause = max(0.0, min(3.0, float(ln.get("pause_after", 0.3) or 0)))
            est = estimate_seconds(text)
            total += est + pause
            lines.append({"id": _clean(ln.get("id"), 20) or f"l{si + 1}_{li + 1}", "character_id": cid, "text": text,
                          "emotion": emotion, "intention": _clean(ln.get("intention"), 120), "pause_after": round(pause, 2),
                          "estimated_seconds": est})
        n_lines += len(lines)
        if not lines:
            raise AppError(f"La scène {si + 1} n'a aucune réplique.", 422, "empty_scene")
        camera = sc.get("camera") if sc.get("camera") in CAMERAS else "plan_moyen"
        scenes.append({"id": _clean(sc.get("id"), 20) or f"sc{si + 1}", "title": _clean(sc.get("title"), 120) or f"Scène {si + 1}",
                       "setting": _clean(sc.get("setting"), 200), "camera": camera, "lines": lines})
    if n_lines > MAX_LINES:
        raise AppError(f"Trop de répliques ({MAX_LINES} maximum).", 422, "bad_scenario")
    ids = [s["id"] for s in scenes]
    if len(set(ids)) != len(ids):
        raise AppError("Identifiants de scène en double.", 422, "duplicate_ids")
    return {"title": _clean(data.get("title"), 150) or "Sans titre", "topic": _clean(data.get("topic"), 300),
            "scenes": scenes, "estimated_seconds": round(total, 1), "lines_count": n_lines}


def generate(topic: str, characters: list[dict], target_seconds: float, tone: str, instructions: str = "") -> dict:
    """Demande au LLM local un scénario JSON, puis le valide. Lève une erreur claire si Ollama est absent."""
    if not ollama_service.status()["model_ready"]:
        raise AppError("Ollama n'est pas démarré : écrivez le scénario à la main ou lancez « ollama serve ».", 503, "ollama_unavailable")
    tpl = (ROOT_DIR / "ai" / "prompts" / "scenario_dialogue.md").read_text(encoding="utf-8")
    cast = "\n".join(f"- id {c['id']} : {c['name']}" + (f" — {c['description']}" if c.get("description") else "") for c in characters)
    words = int(target_seconds * WORDS_PER_SECOND)
    prompt = (tpl.replace("{topic}", topic).replace("{cast}", cast).replace("{seconds}", str(int(target_seconds)))
              .replace("{words}", str(words)).replace("{tone}", tone or "pédagogique et chaleureux")
              .replace("{emotions}", ", ".join(EMOTIONS)).replace("{cameras}", ", ".join(CAMERAS))
              .replace("{instructions}", instructions or "aucune"))
    last_err = None
    for attempt in range(2):  # une seconde tentative si le JSON est inutilisable
        raw = ollama_service.generate(prompt, as_json=True, timeout=600)
        try:
            data = json.loads(raw)
            data["topic"] = topic
            return validate(data, {c["id"] for c in characters})
        except (json.JSONDecodeError, AppError) as e:
            last_err = e
            log.warning("Scénario LLM inutilisable (essai %d) : %s", attempt + 1, e)
    raise AppError(f"Le modèle n'a pas produit de scénario valide ({getattr(last_err, 'message', last_err)}). Réessayez ou écrivez-le à la main.",
                   502, "scenario_invalid")
