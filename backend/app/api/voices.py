"""Voix off locale (Piper) : liste des voix, écoute d'un extrait, génération, réutilisation dans le montage."""
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.core.errors import AppError
from app.models.entities import Job, MediaAnalysis, MediaFile, Project, VoiceTrack
from app.schemas.style import JobOut
from app.services import jobs as jobs_service
from app.services import storage_service, tts

router = APIRouter(prefix="/api", tags=["voix"])


class VoiceParams(BaseModel):
    voice_id: str = Field(min_length=1, max_length=100)
    speaker: str | None = Field(default=None, max_length=100)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    pause_s: float = Field(default=0.35, ge=0.0, le=3.0)
    volume_db: float = Field(default=0.0, ge=-30, le=12)


class PreviewIn(VoiceParams):
    text: str = Field(min_length=1, max_length=400)


class GenerateIn(VoiceParams):
    text: str = Field(min_length=1, max_length=20000)
    name: str | None = Field(default=None, max_length=80)


@router.get("/voices")
def list_voices():
    return {"installed": tts.installed(), "voices": tts.list_voices()}


@router.post("/voices/preview")
def preview(body: PreviewIn):
    """Extrait court à écouter avant de générer (rien n'est enregistré)."""
    r = tts.synthesize(body.text, body.voice_id, body.speaker, body.speed, body.pause_s, body.volume_db, max_chars=400)
    return Response(r["wav_bytes"], media_type="audio/wav", headers={"Cache-Control": "no-store"})


@router.post("/projects/{pid}/voiceover", response_model=JobOut, status_code=202)
def generate(pid: int, body: GenerateIn, db: Session = Depends(get_db)):
    if not db.get(Project, pid):
        raise AppError("Projet introuvable.", 404, "not_found")
    if any(v["id"] == body.voice_id and v["excluded"] for v in tts.list_voices()):
        raise AppError("Cette voix a une licence incompatible avec une diffusion publique ; choisissez-en une autre.", 409, "voice_license")
    running = db.scalar(select(Job).where(Job.type == "voiceover", Job.target_id == pid, Job.status.in_(["queued", "running"])))
    if running:
        return running
    params = body.model_dump(exclude={"text", "name"})

    def work(ctx):
        ctx.progress(0.1, "Synthèse vocale…", force=True)
        r = tts.synthesize(body.text, body.voice_id, body.speaker, body.speed, body.pause_s, body.volume_db)
        ctx.check()
        ctx.progress(0.85, "Enregistrement du fichier audio…", force=True)
        label = (body.name or "voix-off").strip() or "voix-off"
        with SessionLocal() as s:
            m = storage_service.save_generated(s, r["wav_bytes"], f"{label}.wav", "audio", pid)
            s.add(VoiceTrack(media_id=m.id, project_id=pid, text=body.text, voice_id=body.voice_id, speaker=body.speaker,
                             params=params, words=r["words"], phonemes=r["phonemes"]))
            s.add(MediaAnalysis(media_id=m.id, data={"duration": r["duration"], "probe": m.probe, "silences": [],
                                                     "speech_seconds": r["duration"], "generated": "tts"},
                                transcript={"language": "fr", "words": [{**w, "prob": 1.0} for w in r["words"]],
                                            "segments": [{"start": r["words"][0]["start"] if r["words"] else 0, "end": r["duration"],
                                                          "text": body.text}], "duration": r["duration"], "model": "piper"}))
            s.commit()
            return {"media_id": m.id, "duration": r["duration"], "words": len(r["words"])}

    return jobs_service.submit("voiceover", pid, work)


@router.get("/voice-tracks/{media_id}")
def get_track(media_id: int, db: Session = Depends(get_db)):
    vt = db.scalar(select(VoiceTrack).where(VoiceTrack.media_id == media_id))
    if not vt:
        raise AppError("Piste vocale introuvable.", 404, "not_found")
    m = db.get(MediaFile, media_id)
    return {"media_id": media_id, "name": m.original_name if m else None, "text": vt.text, "voice_id": vt.voice_id,
            "speaker": vt.speaker, "params": vt.params, "words": vt.words, "phonemes_count": len(vt.phonemes),
            "duration": (m.probe or {}).get("duration") if m else None}


@router.get("/projects/{pid}/voice-tracks")
def list_tracks(pid: int, db: Session = Depends(get_db)):
    rows = db.scalars(select(VoiceTrack).where(VoiceTrack.project_id == pid).order_by(VoiceTrack.id.desc())).all()
    out = []
    for vt in rows:
        m = db.get(MediaFile, vt.media_id)
        out.append({"media_id": vt.media_id, "name": m.original_name if m else None, "text": vt.text[:200], "voice_id": vt.voice_id,
                    "speaker": vt.speaker, "params": vt.params, "duration": (m.probe or {}).get("duration") if m else None})
    return out
