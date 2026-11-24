from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.errors import AppError
from app.models.entities import MediaFile, Project
from app.schemas.project import MediaOut
from app.services import storage_service

router = APIRouter(prefix="/api/media", tags=["media"])

MIME = {".mp4": "video/mp4", ".mov": "video/quicktime", ".avi": "video/x-msvideo", ".mp3": "audio/mpeg",
        ".wav": "audio/wav", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".txt": "text/plain; charset=utf-8", ".md": "text/plain; charset=utf-8", ".srt": "text/plain; charset=utf-8"}


@router.post("/upload", response_model=list[MediaOut], status_code=201)
async def upload(files: list[UploadFile] = File(...), kind: str = Form(...), project_id: int | None = Form(None),
                 db: Session = Depends(get_db)):
    if project_id is not None and not db.get(Project, project_id):
        raise AppError("Projet introuvable.", 404, "not_found")
    return [await storage_service.save_upload(db, f, kind, project_id) for f in files]


@router.get("", response_model=list[MediaOut])
def list_media(project_id: int | None = None, kind: str | None = None, db: Session = Depends(get_db)):
    q = select(MediaFile).order_by(MediaFile.created_at.desc())
    if project_id is not None:
        q = q.where(MediaFile.project_id == project_id)
    if kind:
        q = q.where(MediaFile.kind == kind)
    return db.scalars(q).all()


def _media(db: Session, media_id: int) -> MediaFile:
    m = db.get(MediaFile, media_id)
    if not m:
        raise AppError("Média introuvable.", 404, "not_found")
    return m


@router.get("/{media_id}/file")
def media_file(media_id: int, db: Session = Depends(get_db)):
    m = _media(db, media_id)
    path = storage_service.resolve_media_path(m)
    if not path.exists():
        raise AppError("Fichier absent du stockage.", 410, "file_missing")
    # Servi en lecture uniquement : type imposé, jamais interprété comme une page (nosniff + CSP stricte).
    return FileResponse(path, media_type=MIME.get(path.suffix.lower(), "application/octet-stream"),
                        headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'; media-src 'self'; img-src 'self'"})


@router.get("/{media_id}/thumbnail")
def media_thumbnail(media_id: int, db: Session = Depends(get_db)):
    m = _media(db, media_id)
    if m.category == "image":
        return media_file(media_id, db)
    thumb = settings.storage_dir / "thumbnails" / (Path(m.stored_path).stem + ".jpg")
    if not thumb.exists():
        raise AppError("Miniature indisponible.", 404, "no_thumbnail")
    return FileResponse(thumb, media_type="image/jpeg")
