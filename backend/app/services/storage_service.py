"""Enregistrement sécurisé des fichiers importés. Les originaux ne sont jamais modifiés ni supprimés."""
import logging
import re
import shutil
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import KIND_DIRS, settings
from app.core.errors import AppError
from app.models.entities import MediaFile
from app.services import ffmpeg_service

log = logging.getLogger("storage")
CHUNK = 1024 * 1024


def ensure_dirs() -> None:
    for sub in [*KIND_DIRS.values(), "thumbnails", "tmp", "previews"]:
        (settings.storage_dir / sub).mkdir(parents=True, exist_ok=True)
    for sub in ["tiktok", "reels", "youtube"]:
        (settings.exports_dir / sub).mkdir(parents=True, exist_ok=True)


async def save_upload(db: Session, upload: UploadFile, kind: str, project_id: int | None) -> MediaFile:
    if kind not in KIND_DIRS:
        raise AppError(f"Type d'import inconnu : {kind}", 400, "bad_kind")
    original = Path(upload.filename or "").name
    if not original:
        raise AppError("Nom de fichier manquant.", 400, "no_filename")
    category = security.category_for(original)
    if kind in ("video", "audio", "image") and kind != category:
        raise AppError(f"Le fichier « {original} » n'est pas de type {kind}.", 415, "kind_mismatch")
    if kind == "reference" and category != "video":
        raise AppError("Une référence doit être une vidéo (MP4, MOV, AVI).", 415, "kind_mismatch")
    if kind == "script" and category != "script":
        raise AppError("Un script doit être un fichier .txt, .md ou .srt.", 415, "kind_mismatch")
    if category == "script" and kind != "script":
        raise AppError(f"Le fichier « {original} » est un script : importez-le comme script.", 415, "kind_mismatch")

    limit = security.max_bytes_for(category)
    target_dir = settings.storage_dir / KIND_DIRS[kind]
    final_path = security.ensure_inside(target_dir, target_dir / security.safe_stored_name(original))
    tmp_path = settings.tmp_dir / (final_path.name + ".part")

    # 1) écriture dans tmp/ en flux, avec limite de taille
    size = 0
    head = b""
    try:
        with open(tmp_path, "wb") as out:
            while chunk := await upload.read(CHUNK):
                if not head:
                    head = chunk[:32]
                size += len(chunk)
                if size > limit:
                    raise AppError(f"Fichier trop volumineux (max {limit // (1024*1024)} Mo pour {category}).", 413, "too_large")
                out.write(chunk)
        if size == 0:
            raise AppError("Fichier vide.", 400, "empty_file")
        # 2) vérifications du contenu
        security.check_signature(original, head)
        if category == "script":
            text = security.check_text_file(tmp_path)
            probe = {"chars": len(text), "words": len(re.findall(r"\w+(?:['’-]\w+)*", text)), "lines": text.count("\n") + 1}
        else:
            probe = ffmpeg_service.probe(tmp_path)
        if category == "video" and not probe.get("video"):
            raise AppError("Aucune piste vidéo détectée.", 422, "no_video_stream")
        if category == "audio" and not probe.get("audio"):
            raise AppError("Aucune piste audio détectée.", 422, "no_audio_stream")
    except Exception:
        tmp_path.unlink(missing_ok=True)  # seul le fichier temporaire est supprimé
        raise

    # 3) déplacement vers le stockage définitif + verrouillage lecture seule
    shutil.move(tmp_path, final_path)
    security.protect_original(final_path)

    if category == "video":
        ffmpeg_service.make_thumbnail(final_path, settings.storage_dir / "thumbnails" / (final_path.stem + ".jpg"))

    media = MediaFile(project_id=project_id, kind=kind, category=category, original_name=original,
                      stored_path=str(final_path.relative_to(settings.storage_dir.resolve())), size_bytes=size, probe=probe)
    db.add(media)
    db.commit()
    db.refresh(media)
    log.info("Import %s (%s, %d octets) -> %s", original, kind, size, media.stored_path)
    return media


def resolve_media_path(media: MediaFile) -> Path:
    return security.ensure_inside(settings.storage_dir, settings.storage_dir / media.stored_path)


def save_generated(db: Session, data: bytes, filename: str, kind: str, project_id: int | None) -> MediaFile:
    """Enregistre un fichier produit par l'application (ex. voix off TTS) comme un média du projet."""
    category = security.category_for(filename)
    target_dir = settings.storage_dir / KIND_DIRS[kind]
    final_path = security.ensure_inside(target_dir, target_dir / security.safe_stored_name(filename))
    tmp_path = settings.tmp_dir / (final_path.name + ".part")
    tmp_path.write_bytes(data)
    try:
        probe = ffmpeg_service.probe(tmp_path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    shutil.move(tmp_path, final_path)
    security.protect_original(final_path)
    media = MediaFile(project_id=project_id, kind=kind, category=category, original_name=filename,
                      stored_path=str(final_path.relative_to(settings.storage_dir.resolve())), size_bytes=len(data), probe=probe)
    db.add(media)
    db.commit()
    db.refresh(media)
    log.info("Fichier généré %s -> %s", filename, media.stored_path)
    return media
