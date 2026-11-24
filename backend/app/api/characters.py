"""Bibliothèque de personnages (communs 2D/3D) et scénarios dialogués des projets animés."""
import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.core.errors import AppError
from app.models.entities import Character, Job, Project, Scenario
from app.schemas.style import JobOut
from app.services import jobs as jobs_service
from app.services import scenario as scenario_service
from app.services import tts

router = APIRouter(prefix="/api", tags=["personnages"])


# --------------------------------------------------------------------------- personnages
class VoiceIn(BaseModel):
    voice_id: str = Field(min_length=1, max_length=100)
    speaker: str | None = Field(default=None, max_length=100)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


class CharacterIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: str = Field(default="2d", pattern=r"^(2d|3d)$")
    description: str = Field(default="", max_length=1000)
    appearance: dict = Field(default_factory=dict)
    voice: VoiceIn | None = None
    settings: dict = Field(default_factory=dict)


class CharacterPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    appearance: dict | None = None
    voice: VoiceIn | None = None
    settings: dict | None = None


def _check_blob(d: dict, what: str) -> dict:
    if len(json.dumps(d)) > 20000:
        raise AppError(f"{what} : données trop volumineuses.", 422, "too_large")
    return d


def _check_voice(v: VoiceIn | None) -> dict:
    if v is None:
        return {}
    voices = {x["id"]: x for x in tts.list_voices()}
    if v.voice_id not in voices:
        raise AppError(f"Voix « {v.voice_id} » non installée.", 422, "voice_missing")
    if voices[v.voice_id]["excluded"]:
        raise AppError("Licence de voix incompatible avec une diffusion publique.", 422, "voice_license")
    spk = [s["id"] for s in voices[v.voice_id]["speakers"]]
    if spk and v.speaker not in spk:
        raise AppError("Locuteur inconnu pour cette voix.", 422, "bad_speaker")
    return v.model_dump()


def _out(c: Character) -> dict:
    return {"id": c.id, "name": c.name, "kind": c.kind, "description": c.description, "appearance": c.appearance,
            "voice": c.voice, "settings": c.settings, "created_at": c.created_at, "updated_at": c.updated_at}


def _char(db: Session, cid: int) -> Character:
    c = db.get(Character, cid)
    if not c or c.archived:
        raise AppError("Personnage introuvable.", 404, "not_found")
    return c


@router.get("/characters")
def list_characters(kind: str | None = None, db: Session = Depends(get_db)):
    q = select(Character).where(Character.archived.is_(False)).order_by(Character.name)
    if kind:
        q = q.where(Character.kind == kind)
    return [_out(c) for c in db.scalars(q).all()]


@router.post("/characters", status_code=201)
def create_character(body: CharacterIn, db: Session = Depends(get_db)):
    c = Character(name=body.name.strip(), kind=body.kind, description=body.description, settings=_check_blob(body.settings, "Paramètres"),
                  appearance=_check_blob(body.appearance, "Apparence"), voice=_check_voice(body.voice))
    db.add(c)
    db.commit()
    db.refresh(c)
    return _out(c)


@router.get("/characters/{cid}")
def get_character(cid: int, db: Session = Depends(get_db)):
    return _out(_char(db, cid))


@router.patch("/characters/{cid}")
def update_character(cid: int, body: CharacterPatch, db: Session = Depends(get_db)):
    c = _char(db, cid)
    if body.name is not None:
        c.name = body.name.strip()
    if body.description is not None:
        c.description = body.description
    if body.appearance is not None:
        c.appearance = _check_blob(body.appearance, "Apparence")
    if body.settings is not None:
        c.settings = _check_blob(body.settings, "Paramètres")
    if body.voice is not None:
        c.voice = _check_voice(body.voice)
    db.commit()
    db.refresh(c)
    return _out(c)


@router.post("/characters/{cid}/duplicate", status_code=201)
def duplicate_character(cid: int, db: Session = Depends(get_db)):
    c = _char(db, cid)
    copy = Character(name=f"{c.name} (copie)"[:100], kind=c.kind, description=c.description, appearance=dict(c.appearance),
                     voice=dict(c.voice), settings=dict(c.settings))
    db.add(copy)
    db.commit()
    db.refresh(copy)
    return _out(copy)


@router.delete("/characters/{cid}")
def delete_character(cid: int, db: Session = Depends(get_db)):
    """Retire le personnage de la bibliothèque (archivé : les projets qui l'utilisent restent intacts)."""
    c = _char(db, cid)
    c.archived = True
    db.commit()
    return {"id": cid, "archived": True}


# --------------------------------------------------------------------------- scénarios
def _project(db: Session, pid: int) -> Project:
    p = db.get(Project, pid)
    if not p:
        raise AppError("Projet introuvable.", 404, "not_found")
    return p


def _latest(db: Session, pid: int) -> Scenario | None:
    return db.scalar(select(Scenario).where(Scenario.project_id == pid).order_by(Scenario.version.desc()))


def _sc_out(s: Scenario) -> dict:
    return {"id": s.id, "project_id": s.project_id, "version": s.version, "status": s.status, "data": s.data, "created_at": s.created_at}


def _active_ids(db: Session) -> set[int]:
    return set(db.scalars(select(Character.id).where(Character.archived.is_(False))).all())


class GenerateIn(BaseModel):
    topic: str = Field(min_length=3, max_length=300)
    character_ids: list[int] = Field(min_length=1, max_length=6)
    target_seconds: float = Field(default=45, ge=10, le=300)
    tone: str = Field(default="pédagogique et chaleureux", max_length=100)
    instructions: str = Field(default="", max_length=1000)


@router.post("/projects/{pid}/scenario/generate", response_model=JobOut, status_code=202)
def generate_scenario(pid: int, body: GenerateIn, db: Session = Depends(get_db)):
    _project(db, pid)
    chars = [_out(_char(db, cid)) for cid in dict.fromkeys(body.character_ids)]
    running = db.scalar(select(Job).where(Job.type == "scenario_generation", Job.target_id == pid, Job.status.in_(["queued", "running"])))
    if running:
        return running

    def work(ctx):
        ctx.progress(0.1, "Écriture du scénario par l'IA locale (1 à 5 min)…", force=True)
        data = scenario_service.generate(body.topic, chars, body.target_seconds, body.tone, body.instructions)
        ctx.check()
        with SessionLocal() as s:
            last = s.scalar(select(Scenario).where(Scenario.project_id == pid).order_by(Scenario.version.desc()))
            sc = Scenario(project_id=pid, version=(last.version + 1) if last else 1, status="draft",
                          data=data | {"generated": True, "target_seconds": body.target_seconds})
            s.add(sc)
            s.commit()
            return {"version": sc.version, "scenes": len(data["scenes"]), "lines": data["lines_count"]}

    return jobs_service.submit("scenario_generation", pid, work)


@router.get("/projects/{pid}/scenario")
def get_scenario(pid: int, version: int | None = None, db: Session = Depends(get_db)):
    _project(db, pid)
    s = db.scalar(select(Scenario).where(Scenario.project_id == pid, Scenario.version == version)) if version else _latest(db, pid)
    if not s:
        raise AppError("Aucun scénario pour ce projet.", 404, "no_scenario")
    return _sc_out(s)


@router.put("/projects/{pid}/scenario")
def save_scenario(pid: int, body: dict, db: Session = Depends(get_db)):
    """Écriture ou modification manuelle : nouvelle version (brouillon), l'historique est conservé."""
    _project(db, pid)
    last = _latest(db, pid)
    if last and body.get("base_version") not in (None, last.version):
        raise AppError("Le scénario a été modifié entre-temps : rechargez la page.", 409, "version_conflict")
    data = scenario_service.validate(body, _active_ids(db))
    s = Scenario(project_id=pid, version=(last.version + 1) if last else 1, status="draft", data=data | {"generated": False})
    db.add(s)
    db.commit()
    db.refresh(s)
    return _sc_out(s)


class ValidateIn(BaseModel):
    version: int


@router.post("/projects/{pid}/scenario/validate")
def validate_scenario(pid: int, body: ValidateIn, db: Session = Depends(get_db)):
    last = _latest(db, pid)
    if not last or last.version != body.version:
        raise AppError("Seule la dernière version du scénario peut être validée.", 409, "version_conflict")
    scenario_service.validate(last.data, _active_ids(db))  # personnages toujours présents
    last.status = "validated"
    db.commit()
    return _sc_out(last)
