import platform
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.services import ffmpeg_service, ollama_service

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "app": settings.app_name, "database": "ok"}


@router.get("/system/status")
def system_status(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    disk = shutil.disk_usage(settings.storage_dir)
    free = disk.free
    # Sous WSL, le disque Linux est un fichier extensible du disque Windows : c'est C: qui limite réellement.
    host = Path("/mnt/c")
    if platform.system() == "Linux" and "microsoft" in platform.release().lower() and host.exists():
        try:
            free = min(free, shutil.disk_usage(host).free)
        except OSError:
            pass
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "database": {"ok": True, "url": settings.database_url.split("///")[-1]},
        "ffmpeg": ffmpeg_service.status(),
        "ollama": ollama_service.status(),
        "disk_free_gb": round(free / 1e9, 1),
        "limits_mb": {"video": settings.max_video_mb, "audio": settings.max_audio_mb, "image": settings.max_image_mb},
    }


class AskIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)


@router.post("/ai/test")
def ai_test(body: AskIn):
    return {"model": settings.ollama_model, "response": ollama_service.generate(body.prompt, timeout=120)}
