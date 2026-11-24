from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.errors import AppError
from app.models.entities import Export, MediaFile, Project, Storyboard
from app.schemas.project import ProjectCard, ProjectCreate, ProjectDetail, ProjectOut, ProjectUpdate

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _get(db: Session, project_id: int) -> Project:
    p = db.scalar(select(Project).options(selectinload(Project.media)).where(Project.id == project_id))
    if not p:
        raise AppError("Projet introuvable.", 404, "not_found")
    return p


@router.get("", response_model=list[ProjectCard])
def list_projects(include_archived: bool = False, db: Session = Depends(get_db)):
    """Projets avec les informations utiles aux cartes du tableau de bord."""
    q = select(Project).order_by(Project.updated_at.desc())
    if not include_archived:
        q = q.where(Project.archived.is_(False))
    out = []
    for p in db.scalars(q).all():
        media = db.scalars(select(MediaFile).where(MediaFile.project_id == p.id).order_by(MediaFile.id)).all()
        thumb = next((m.id for m in media if m.category == "video"), None) or next((m.id for m in media if m.category == "image"), None)
        sb = db.scalar(select(Storyboard).where(Storyboard.project_id == p.id).order_by(Storyboard.version.desc()))
        n_exp = len(db.scalars(select(Export.id).where(Export.project_id == p.id)).all())
        out.append(ProjectCard.model_validate(p).model_copy(update={
            "thumbnail_media_id": thumb, "media_count": len(media), "exports_count": n_exp,
            "storyboard_version": sb.version if sb else None, "storyboard_status": sb.status if sb else None}))
    return out


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    p = Project(**body.model_dump(), settings={})
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project(project_id: int, db: Session = Depends(get_db)):
    return _get(db, project_id)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(project_id: int, body: ProjectUpdate, db: Session = Depends(get_db)):
    p = _get(db, project_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return p


@router.delete("/{project_id}", response_model=ProjectOut)
def archive_project(project_id: int, db: Session = Depends(get_db)):
    """Archive le projet. Aucun fichier (original ou export) n'est supprimé."""
    p = _get(db, project_id)
    p.archived = True
    db.commit()
    db.refresh(p)
    return p
