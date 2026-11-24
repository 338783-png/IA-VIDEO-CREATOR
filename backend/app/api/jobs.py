from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AppError
from app.models.entities import Job
from app.schemas.style import JobOut
from app.services import jobs as jobs_service

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("", response_model=list[JobOut])
def list_jobs(type: str | None = None, target_id: int | None = None, limit: int = 50, db: Session = Depends(get_db)):
    q = select(Job).order_by(Job.id.desc()).limit(min(limit, 200))
    if type:
        q = q.where(Job.type == type)
    if target_id is not None:
        q = q.where(Job.target_id == target_id)
    return db.scalars(q).all()


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if not j:
        raise AppError("Tâche introuvable.", 404, "not_found")
    return j


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: int, db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if not j:
        raise AppError("Tâche introuvable.", 404, "not_found")
    if j.status not in ("queued", "running"):
        raise AppError("Cette tâche n'est plus en cours.", 409, "not_running")
    jobs_service.cancel(job_id)
    db.refresh(j)
    return j
