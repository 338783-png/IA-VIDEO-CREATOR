"""Client minimal pour Ollama (LLM local). L'application reste utilisable si Ollama est absent."""
import httpx

from app.core.config import settings
from app.core.errors import AppError


def status() -> dict:
    try:
        r = httpx.get(f"{settings.ollama_url}/api/tags", timeout=3)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        return {"available": True, "url": settings.ollama_url, "models": models,
                "configured_model": settings.ollama_model, "model_ready": settings.ollama_model in models}
    except (httpx.HTTPError, ValueError):
        return {"available": False, "url": settings.ollama_url, "models": [],
                "configured_model": settings.ollama_model, "model_ready": False}


def generate(prompt: str, system: str | None = None, as_json: bool = False, timeout: float = 300,
             images: list[str] | None = None, model: str | None = None) -> str:
    payload: dict = {"model": model or settings.ollama_model, "prompt": prompt, "stream": False}
    if images:
        payload["images"] = images
    if system:
        payload["system"] = system
    if as_json:
        payload["format"] = "json"
    try:
        r = httpx.post(f"{settings.ollama_url}/api/generate", json=payload, timeout=timeout)
        r.raise_for_status()
    except httpx.ConnectError as e:
        raise AppError("Ollama n'est pas démarré ou pas installé.", 503, "ollama_unavailable") from e
    except httpx.HTTPStatusError as e:
        raise AppError(f"Ollama a renvoyé une erreur : {e.response.text[:200]}", 502, "ollama_error") from e
    return r.json().get("response", "")
