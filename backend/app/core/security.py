"""Validation des fichiers importés et protection des chemins / originaux."""
import os
import re
import stat
import uuid
from pathlib import Path

from app.core.config import ALLOWED_EXTENSIONS, settings
from app.core.errors import AppError

# Signatures binaires (magic bytes) : on ne se fie pas qu'à l'extension.
def _sniff(head: bytes) -> str | None:
    if head[4:8] == b"ftyp":
        return "mp4/mov"
    if head[:4] == b"RIFF" and head[8:12] == b"AVI ":
        return "avi"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav"
    if head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return "mp3"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if head[:3] == b"\xff\xd8\xff":
        return "jpg"
    # QuickTime ancien : atome 'moov'/'mdat'/'wide' en tête
    if head[4:8] in (b"moov", b"mdat", b"wide", b"free"):
        return "mp4/mov"
    return None


EXPECTED_SIGNATURE = {
    ".mp4": "mp4/mov", ".mov": "mp4/mov", ".avi": "avi",
    ".mp3": "mp3", ".wav": "wav",
    ".png": "png", ".jpg": "jpg", ".jpeg": "jpg",
    ".txt": "text", ".md": "text", ".srt": "text",
}


def category_for(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    for cat, exts in ALLOWED_EXTENSIONS.items():
        if ext in exts:
            return cat
    allowed = ", ".join(sorted(e for s in ALLOWED_EXTENSIONS.values() for e in s))
    raise AppError(f"Format non supporté « {ext or '(aucune extension)'} ». Formats acceptés : {allowed}", 415, "unsupported_format")


def max_bytes_for(category: str) -> int:
    mb = {"video": settings.max_video_mb, "audio": settings.max_audio_mb, "image": settings.max_image_mb,
          "script": settings.max_script_mb}[category]
    return mb * 1024 * 1024


def check_text_file(path: Path) -> str:
    """Un script doit être du texte UTF-8 lisible (jamais exécuté)."""
    raw = path.read_bytes()
    if b"\x00" in raw:
        raise AppError("Le script contient des données binaires.", 415, "not_text")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            return raw.decode("cp1252")  # fichiers Bloc-notes Windows
        except UnicodeDecodeError as e:
            raise AppError("Encodage du script non reconnu (UTF-8 attendu).", 415, "bad_encoding") from e


def check_signature(filename: str, head: bytes) -> None:
    ext = Path(filename).suffix.lower()
    if EXPECTED_SIGNATURE[ext] == "text":
        return  # vérifié par check_text_file
    found = _sniff(head)
    if found != EXPECTED_SIGNATURE[ext]:
        raise AppError(f"Le contenu du fichier ne correspond pas à l'extension {ext} (fichier corrompu ou renommé).", 415, "signature_mismatch")


_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_stored_name(original: str) -> str:
    """Nom de stockage unique : jamais le nom fourni tel quel (pas de ../, pas d'écrasement)."""
    p = Path(original)
    stem = _SAFE.sub("_", p.stem)[:60].strip("._") or "file"
    return f"{uuid.uuid4().hex[:12]}_{stem}{p.suffix.lower()}"


def ensure_inside(base: Path, target: Path) -> Path:
    base_r, target_r = base.resolve(), target.resolve()
    if base_r != target_r and base_r not in target_r.parents:
        raise AppError("Chemin hors de la zone de stockage autorisée.", 400, "path_traversal")
    return target_r


def protect_original(path: Path) -> None:
    """Rend l'original en lecture seule et non exécutable."""
    os.chmod(path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
