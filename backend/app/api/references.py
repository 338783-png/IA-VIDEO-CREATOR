import re

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.core.errors import AppError
from app.core.security import ensure_inside
from app.models.entities import Job, MediaFile, ReferenceAnalysis
from app.schemas.style import JobOut
from app.services import jobs as jobs_service
from app.services import storage_service
from app.services.analysis import reference_analyzer

router = APIRouter(prefix="/api/references", tags=["references"])
KEYFRAME_RE = re.compile(r"^scene_\d{2,3}\.jpg$")


def _ref(db: Session, media_id: int) -> MediaFile:
    m = db.get(MediaFile, media_id)
    if not m or m.kind != "reference":
        raise AppError("Vidéo de référence introuvable.", 404, "not_found")
    return m


@router.get("")
def list_references(db: Session = Depends(get_db)):
    refs = db.scalars(select(MediaFile).where(MediaFile.kind == "reference").order_by(MediaFile.created_at.desc())).all()
    analyses = {a.media_id: a for a in db.scalars(select(ReferenceAnalysis)).all()}
    jobs = {}
    for j in db.scalars(select(Job).where(Job.type == "reference_analysis").order_by(Job.id)).all():
        jobs[j.target_id] = j  # dernière tâche par référence
    out = []
    for m in refs:
        a, j = analyses.get(m.id), jobs.get(m.id)
        out.append({
            "id": m.id, "original_name": m.original_name, "size_bytes": m.size_bytes, "probe": m.probe, "created_at": m.created_at,
            "analyzed": a is not None, "analyzed_at": a.updated_at if a else None,
            "summary": {"shots": a.data["rhythm"]["shot_count"], "pace": a.data["rhythm"]["pace"], "aspect": a.data["format"]["aspect"],
                        "captions": a.data["captions"].get("detected"), "bpm": a.data["audio"].get("tempo_bpm")} if a else None,
            "last_job": JobOut.model_validate(j).model_dump() if j else None,
        })
    return out


@router.post("/{media_id}/analyze", response_model=JobOut, status_code=202)
def analyze_reference(media_id: int, db: Session = Depends(get_db)):
    m = _ref(db, media_id)
    running = db.scalar(select(Job).where(Job.type == "reference_analysis", Job.target_id == media_id, Job.status.in_(["queued", "running"])))
    if running:
        return running
    path = storage_service.resolve_media_path(m)
    name = m.original_name

    def work(ctx):
        data = reference_analyzer.analyze(ctx, path, media_id, name)
        ctx.progress(0.98, "Enregistrement…", force=True)
        with SessionLocal() as s:
            row = s.scalar(select(ReferenceAnalysis).where(ReferenceAnalysis.media_id == media_id))
            if row:
                row.data = data
            else:
                s.add(ReferenceAnalysis(media_id=media_id, data=data))
            s.commit()
        return {"media_id": media_id, "shots": data["rhythm"]["shot_count"]}

    return jobs_service.submit("reference_analysis", media_id, work)


@router.get("/{media_id}/analysis")
def get_analysis(media_id: int, db: Session = Depends(get_db)):
    _ref(db, media_id)
    a = db.scalar(select(ReferenceAnalysis).where(ReferenceAnalysis.media_id == media_id))
    if not a:
        raise AppError("Cette référence n'a pas encore été analysée.", 404, "not_analyzed")
    return a.data


@router.get("/{media_id}/keyframes/{name}")
def keyframe(media_id: int, name: str, db: Session = Depends(get_db)):
    _ref(db, media_id)
    if not KEYFRAME_RE.match(name):
        raise AppError("Nom d'image invalide.", 400, "bad_name")
    base = reference_analyzer.keyframes_dir(media_id)
    path = ensure_inside(base, base / name)
    if not path.exists():
        raise AppError("Image introuvable.", 404, "not_found")
    return FileResponse(path, media_type="image/jpeg")
