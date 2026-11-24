import copy
import json
import re
import shutil
import unicodedata
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import ROOT_DIR, settings
from app.core.database import get_db
from app.core.errors import AppError
from app.models.entities import MediaFile, ReferenceAnalysis, StyleProfile
from app.schemas.style import StyleCreate, StyleListItem, StyleOut, StyleUpdate
from app.services import style_builder

router = APIRouter(prefix="/api/styles", tags=["styles"])
EDITABLE = {"format", "rhythm", "transitions", "motion", "color", "subtitles", "audio", "sync"}


def _get(db: Session, style_id: int) -> StyleProfile:
    s = db.get(StyleProfile, style_id)
    if not s:
        raise AppError("Style introuvable.", 404, "not_found")
    return s


def _deep_merge(base: dict, patch: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _render(s: StyleProfile) -> None:
    s.markdown = style_builder.render_markdown(s.name, s.status, s.summary, s.config, s.user_notes)


def _slug(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:40] or "style"


@router.get("", response_model=list[StyleListItem])
def list_styles(db: Session = Depends(get_db)):
    return db.scalars(select(StyleProfile).order_by(StyleProfile.updated_at.desc())).all()


@router.post("", response_model=StyleOut, status_code=201)
def create_style(body: StyleCreate, db: Session = Depends(get_db)):
    analyses = []
    for mid in dict.fromkeys(body.reference_media_ids):
        m = db.get(MediaFile, mid)
        if not m or m.kind != "reference":
            raise AppError(f"Référence {mid} introuvable.", 404, "not_found")
        a = db.scalar(select(ReferenceAnalysis).where(ReferenceAnalysis.media_id == mid))
        if not a:
            raise AppError(f"La référence « {m.original_name} » doit d'abord être analysée.", 409, "not_analyzed")
        analyses.append(a.data)
    built = style_builder.build(analyses, body.name)
    s = StyleProfile(name=body.name, status="draft", reference_media_ids=list(dict.fromkeys(body.reference_media_ids)),
                     summary=built["summary"], config=built["config"], user_notes="")
    _render(s)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@router.get("/{style_id}", response_model=StyleOut)
def get_style(style_id: int, db: Session = Depends(get_db)):
    return _get(db, style_id)


@router.get("/{style_id}/guide.md", response_class=PlainTextResponse)
def get_guide(style_id: int, db: Session = Depends(get_db)):
    return _get(db, style_id).markdown


@router.patch("/{style_id}", response_model=StyleOut)
def update_style(style_id: int, body: StyleUpdate, db: Session = Depends(get_db)):
    s = _get(db, style_id)
    changed = False
    if body.name is not None and body.name != s.name:
        s.name, changed = body.name, True
        s.config = {**s.config, "name": body.name}
    if body.user_notes is not None and body.user_notes != s.user_notes:
        s.user_notes, changed = body.user_notes, True
    if body.config_patch:
        unknown = set(body.config_patch) - EDITABLE
        if unknown:
            raise AppError(f"Sections non modifiables : {', '.join(sorted(unknown))}", 422, "bad_patch")
        s.config = _deep_merge(s.config, body.config_patch)
        changed = True
    if changed and s.status != "draft":
        s.status, s.is_official, s.validated_at = "draft", False, None  # toute modification exige une nouvelle validation
    _render(s)
    db.commit()
    db.refresh(s)
    return s


@router.post("/{style_id}/validate", response_model=StyleOut)
def validate_style(style_id: int, db: Session = Depends(get_db)):
    s = _get(db, style_id)
    subs = s.config.get("subtitles", {})
    if subs.get("enabled") and not (subs.get("font") or {}).get("family"):
        raise AppError("Choisissez une police pour les sous-titres avant de valider (elle n'a pas pu être identifiée automatiquement).",
                       409, "font_required")
    db.execute(update(StyleProfile).values(is_official=False))
    s.status, s.is_official, s.validated_at = "validated", True, datetime.now(timezone.utc)
    _render(s)
    # écriture des fichiers du style officiel
    folder = settings.projects_dir / "styles" / f"style-{s.id}-{_slug(s.name)}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "style.json").write_text(json.dumps(s.config, ensure_ascii=False, indent=2), encoding="utf-8")
    (folder / "STYLE-GUIDE.md").write_text(s.markdown, encoding="utf-8")
    doc = ROOT_DIR / "documentation" / "STYLE-GUIDE.md"
    if settings.projects_dir.resolve() == (ROOT_DIR / "projects").resolve():  # pas en environnement de test
        shutil.copyfile(folder / "STYLE-GUIDE.md", doc)
    s.files_dir = str(folder.relative_to(settings.projects_dir.parent)) if folder.is_relative_to(settings.projects_dir.parent) else str(folder)
    db.commit()
    db.refresh(s)
    return s


@router.post("/{style_id}/reject", response_model=StyleOut)
def reject_style(style_id: int, db: Session = Depends(get_db)):
    s = _get(db, style_id)
    s.status, s.is_official, s.validated_at = "rejected", False, None
    _render(s)
    db.commit()
    db.refresh(s)
    return s
