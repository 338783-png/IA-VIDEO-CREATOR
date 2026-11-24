"""API du moteur de montage : analyse, storyboard, aperçu, validation, export."""
import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.core.errors import AppError
from app.models.entities import Export, Job, MediaAnalysis, MediaFile, Project, Storyboard, StyleProfile, VoiceTrack
from app.schemas.style import JobOut
from app.services import jobs as jobs_service
from app.services import media_analyzer, planner, renderer, storage_service, storyboard_service, subtitles_export, transcription

router = APIRouter(prefix="/api", tags=["montage"])
EXPORT_DIRS = {"tiktok": "tiktok", "reels": "reels", "shorts": "youtube", "youtube": "youtube"}


def _project(db: Session, pid: int) -> Project:
    p = db.get(Project, pid)
    if not p:
        raise AppError("Projet introuvable.", 404, "not_found")
    return p


def _media_dict(m: MediaFile) -> dict:
    return {"id": m.id, "kind": m.kind, "category": m.category, "original_name": m.original_name, "probe": m.probe}


def _project_media(db: Session, pid: int) -> list[MediaFile]:
    return db.scalars(select(MediaFile).where(MediaFile.project_id == pid, MediaFile.kind.in_(["video", "audio", "image"]))
                      .order_by(MediaFile.id)).all()


def _latest(db: Session, pid: int) -> Storyboard | None:
    return db.scalar(select(Storyboard).where(Storyboard.project_id == pid).order_by(Storyboard.version.desc()))


def _running(db: Session, jtype: str, target: int) -> Job | None:
    return db.scalar(select(Job).where(Job.type == jtype, Job.target_id == target, Job.status.in_(["queued", "running"])))


def _sb_out(sb: Storyboard) -> dict:
    return {"id": sb.id, "project_id": sb.project_id, "version": sb.version, "status": sb.status, "data": sb.data,
            "has_preview": bool(sb.preview_path) and sb.preview_version == sb.version, "created_at": sb.created_at}


# --------------------------------------------------------------------------- statut des moteurs
@router.get("/engine/status")
def engine_status():
    from app.services import ollama_service, ffmpeg_service
    return {"ffmpeg": ffmpeg_service.status(), "whisper": transcription.status(), "ollama": ollama_service.status()}


# --------------------------------------------------------------------------- analyse
class AnalyzeIn(BaseModel):
    force: bool = False
    transcribe: bool = True
    language: str = Field(default="fr", pattern=r"^[a-z]{2}$")


@router.post("/projects/{pid}/analyze", response_model=JobOut, status_code=202)
def analyze_project(pid: int, body: AnalyzeIn = AnalyzeIn(), db: Session = Depends(get_db)):
    _project(db, pid)
    if (j := _running(db, "project_analysis", pid)):
        return j
    media = [m for m in _project_media(db, pid) if m.category in ("video", "audio")]
    if not media:
        raise AppError("Aucune vidéo ni aucun audio à analyser dans ce projet.", 400, "no_media")
    done = {a.media_id for a in db.scalars(select(MediaAnalysis)).all()}
    todo = [(m.id, m.category, m.original_name, storage_service.resolve_media_path(m)) for m in media if body.force or m.id not in done]

    def work(ctx):
        for k, (mid, cat, name, path) in enumerate(todo):
            span = (k / len(todo), (k + 1) / len(todo))
            data, tr = media_analyzer.analyze(ctx, path, cat, body.transcribe, body.language, span, f"« {name} » — ")
            with SessionLocal() as s:
                row = s.scalar(select(MediaAnalysis).where(MediaAnalysis.media_id == mid))
                if row:
                    row.data, row.transcript = data, tr
                else:
                    s.add(MediaAnalysis(media_id=mid, data=data, transcript=tr))
                s.commit()
        return {"analyzed": len(todo)}

    return jobs_service.submit("project_analysis", pid, work)


@router.get("/projects/{pid}/analysis")
def project_analysis(pid: int, db: Session = Depends(get_db)):
    _project(db, pid)
    out = []
    for m in _project_media(db, pid):
        a = db.scalar(select(MediaAnalysis).where(MediaAnalysis.media_id == m.id))
        out.append({"media": _media_dict(m), "analyzed": a is not None,
                    "data": {k: v for k, v in (a.data if a else {}).items() if k not in ("probe", "motion_per_second", "energy_per_second")},
                    "transcript": {"text": " ".join(s["text"] for s in a.transcript.get("segments", [])),
                                   "segments": [{k: s[k] for k in ("start", "end", "text")} for s in a.transcript.get("segments", [])],
                                   "language": a.transcript.get("language")} if a and a.transcript else None})
    return out


# --------------------------------------------------------------------------- storyboard
class GenerateIn(BaseModel):
    instruction: str | None = Field(default=None, max_length=5000)
    style_id: int | None = None
    target_duration: float | None = Field(default=None, gt=3, le=600)
    platform: str | None = Field(default=None, pattern=r"^(tiktok|reels|shorts|youtube)$")
    use_llm: bool = True


@router.post("/projects/{pid}/storyboard/generate", response_model=JobOut, status_code=202)
def generate_storyboard(pid: int, body: GenerateIn = GenerateIn(), db: Session = Depends(get_db)):
    p = _project(db, pid)
    if (j := _running(db, "storyboard_generation", pid)):
        return j
    instruction = body.instruction if body.instruction is not None else p.instruction
    if body.instruction is not None and body.instruction != p.instruction:
        p.instruction = body.instruction
        db.commit()
    media = _project_media(db, pid)
    need = [m for m in media if m.category in ("video", "audio")]
    analyses = {a.media_id: a for a in db.scalars(select(MediaAnalysis).where(MediaAnalysis.media_id.in_([m.id for m in need]))).all()}
    missing = [m.original_name for m in need if m.id not in analyses]
    if missing:
        raise AppError(f"Analysez d'abord le projet (non analysé : {', '.join(missing[:3])}).", 409, "not_analyzed")
    style = db.get(StyleProfile, body.style_id) if body.style_id else db.scalar(select(StyleProfile).where(StyleProfile.is_official.is_(True)))
    if body.style_id and (not style or style.status != "validated"):
        raise AppError("Le style choisi n'est pas validé.", 409, "style_not_validated")
    style_cfg = style.config if style else None
    style_meta = {"id": style.id, "name": style.name,
                  "zoom_max_scale": style.config.get("motion", {}).get("zoom", {}).get("max_scale")} if style else {"id": None, "name": "Style par défaut"}
    project = {"id": p.id, "target_format": p.target_format}
    media_d = [_media_dict(m) for m in media]
    an_d = {k: v.data for k, v in analyses.items()}
    tr_d = {k: v.transcript for k, v in analyses.items()}
    overrides = {"platform": body.platform, "target_duration": body.target_duration}

    def work(ctx):
        ctx.progress(0.1, "Interprétation de la consigne et sélection des passages…", force=True)
        data = planner.build(project, media_d, an_d, tr_d, style_cfg, style_meta, instruction, overrides, body.use_llm)
        ctx.progress(0.9, "Enregistrement du storyboard…", force=True)
        with SessionLocal() as s:
            last = s.scalar(select(Storyboard).where(Storyboard.project_id == pid).order_by(Storyboard.version.desc()))
            version = (last.version + 1) if last else 1
            data["version"] = version
            sb = Storyboard(project_id=pid, version=version, status="draft", data=data)
            s.add(sb)
            proj = s.get(Project, pid)
            proj.status = "storyboard"
            s.commit()
            storyboard_service.save_json(pid, version, data)
            return {"storyboard_id": sb.id, "version": version, "scenes": len(data["scenes"])}

    return jobs_service.submit("storyboard_generation", pid, work)


@router.get("/projects/{pid}/storyboard")
def get_storyboard(pid: int, version: int | None = None, db: Session = Depends(get_db)):
    _project(db, pid)
    q = select(Storyboard).where(Storyboard.project_id == pid)
    sb = db.scalar(q.where(Storyboard.version == version)) if version else _latest(db, pid)
    if not sb:
        raise AppError("Aucun storyboard pour ce projet.", 404, "no_storyboard")
    return _sb_out(sb)


@router.get("/projects/{pid}/storyboards")
def list_storyboards(pid: int, db: Session = Depends(get_db)):
    _project(db, pid)
    rows = db.scalars(select(Storyboard).where(Storyboard.project_id == pid).order_by(Storyboard.version.desc())).all()
    return [{"version": r.version, "status": r.status, "scenes": len(r.data.get("scenes", [])),
             "duration": r.data.get("total_duration"), "created_at": r.created_at} for r in rows]


@router.put("/projects/{pid}/storyboard")
def update_storyboard(pid: int, body: dict, db: Session = Depends(get_db)):
    """Enregistre une modification manuelle -> nouvelle version (brouillon, aperçu à régénérer)."""
    _project(db, pid)
    last = _latest(db, pid)
    if not last:
        raise AppError("Générez d'abord un storyboard.", 404, "no_storyboard")
    if body.get("base_version") not in (None, last.version):
        raise AppError("Le storyboard a été modifié entre-temps : rechargez la page.", 409, "version_conflict")
    media = {m.id: _media_dict(m) for m in _project_media(db, pid)}
    # mots de la transcription pour recalculer les textes si l'utilisateur change les bornes
    analyses = {a.media_id: a for a in db.scalars(select(MediaAnalysis).where(MediaAnalysis.media_id.in_(list(media)))).all()}
    for s in body.get("scenes", []) or []:
        a = analyses.get(s.get("media_id"))
        if a and a.transcript:
            s["all_words"] = [{"word": w["word"], "start": w["start"], "end": w["end"]} for w in planner.merge_word_tokens(a.transcript.get("words", []))]
    data = storyboard_service.normalize(body, media, last.data)
    for sc in data["scenes"]:
        if sc["text_auto"] and sc["words"] and sc["kind"] == "video":
            sc["text"] = planner.join_words(sc["words"])
    attach_voiceover_words(db, data)
    data["version"] = last.version + 1
    data["edited_at"] = datetime.now().isoformat()
    sb = Storyboard(project_id=pid, version=last.version + 1, status="draft", data=data)
    db.add(sb)
    db.commit()
    db.refresh(sb)
    storyboard_service.save_json(pid, sb.version, data)
    return _sb_out(sb)


def attach_voiceover_words(db: Session, data: dict) -> None:
    """Horaires des mots de la voix off (TTS ou enregistrement transcrit) pour des sous-titres synchronisés."""
    au = data.get("audio") or {}
    vo = au.get("voiceover_media_id")
    words = []
    if vo:
        vt = db.scalar(select(VoiceTrack).where(VoiceTrack.media_id == vo))
        if vt:
            words = vt.words
        else:
            a = db.scalar(select(MediaAnalysis).where(MediaAnalysis.media_id == vo))
            if a and a.transcript:
                words = [{"word": w["word"], "start": w["start"], "end": w["end"]} for w in planner.merge_word_tokens(a.transcript.get("words", []))]
    au["voiceover_words"] = words
    sub = data.get("subtitles") or {}
    if words and sub.get("source") not in ("scenes", "voiceover"):
        sub["source"] = "voiceover"
    elif not words and sub.get("source") == "voiceover":
        sub["source"] = "scenes"
    data["audio"], data["subtitles"] = au, sub


# --------------------------------------------------------------------------- aperçu et validation
def _render_inputs(db: Session, data: dict) -> tuple[dict, dict]:
    ids = {s["media_id"] for s in data["scenes"]} | {x for x in (data.get("audio", {}).get("music_media_id"), data.get("audio", {}).get("voiceover_media_id")) if x}
    paths, has_audio = {}, {}
    for mid in ids:
        m = db.get(MediaFile, mid)
        if m:
            paths[mid] = storage_service.resolve_media_path(m)
            has_audio[mid] = bool((m.probe or {}).get("audio"))
    return paths, has_audio


@router.post("/projects/{pid}/storyboard/preview", response_model=JobOut, status_code=202)
def preview(pid: int, db: Session = Depends(get_db)):
    _project(db, pid)
    sb = _latest(db, pid)
    if not sb:
        raise AppError("Aucun storyboard.", 404, "no_storyboard")
    if (j := _running(db, "preview", pid)):
        return j
    data, sb_id, version = sb.data, sb.id, sb.version
    paths, has_audio = _render_inputs(db, data)
    out = settings.storage_dir / "previews" / f"project-{pid}" / f"preview_v{version:03d}.mp4"

    def work(ctx):
        info = renderer.render(ctx, data, paths, has_audio, out, mode="preview")
        with SessionLocal() as s:
            row = s.get(Storyboard, sb_id)
            row.preview_path, row.preview_version = str(out), version
            s.commit()
        return {"version": version, "duration": info["duration"], "warnings": info["warnings"]}

    return jobs_service.submit("preview", pid, work)


@router.get("/projects/{pid}/preview.mp4")
def preview_file(pid: int, version: int | None = None, db: Session = Depends(get_db)):
    sb = db.scalar(select(Storyboard).where(Storyboard.project_id == pid, Storyboard.version == version)) if version else _latest(db, pid)
    if not sb or not sb.preview_path or not Path(sb.preview_path).exists():
        raise AppError("Aucun aperçu disponible.", 404, "no_preview")
    return FileResponse(sb.preview_path, media_type="video/mp4")


class ValidateIn(BaseModel):
    version: int


@router.post("/projects/{pid}/storyboard/validate")
def validate(pid: int, body: ValidateIn, db: Session = Depends(get_db)):
    sb = _latest(db, pid)
    if not sb or sb.version != body.version:
        raise AppError("Seule la dernière version du storyboard peut être validée.", 409, "version_conflict")
    if not (sb.preview_path and sb.preview_version == sb.version):
        raise AppError("Visionnez d'abord l'aperçu de cette version avant de valider.", 409, "preview_required")
    sb.status = "validated"
    db.get(Project, pid).status = "validated"
    db.commit()
    return _sb_out(sb)


# --------------------------------------------------------------------------- sous-titres
@router.get("/projects/{pid}/subtitles")
def subtitles(pid: int, format: str = "json", version: int | None = None, db: Session = Depends(get_db)):
    _project(db, pid)
    sb = db.scalar(select(Storyboard).where(Storyboard.project_id == pid, Storyboard.version == version)) if version else _latest(db, pid)
    if not sb:
        raise AppError("Aucun storyboard.", 404, "no_storyboard")
    cs = subtitles_export.cues(sb.data)
    name = f"sous-titres_v{sb.version}"
    if format == "srt":
        return PlainTextResponse(subtitles_export.to_srt(cs), media_type="application/x-subrip; charset=utf-8",
                                 headers={"Content-Disposition": f'attachment; filename="{name}.srt"'})
    if format == "vtt":
        return PlainTextResponse(subtitles_export.to_vtt(cs), media_type="text/vtt; charset=utf-8",
                                 headers={"Content-Disposition": f'attachment; filename="{name}.vtt"'})
    if format != "json":
        raise AppError("Format attendu : json, srt ou vtt.", 400, "bad_format")
    return {"version": sb.version, "manual": bool(sb.data.get("subtitles", {}).get("manual_cues")), "cues": cs,
            "sync": subtitles_export.sync_report(sb.data)}


# --------------------------------------------------------------------------- export
class ExportIn(BaseModel):
    platform: str = Field(pattern=r"^(tiktok|reels|shorts|youtube)$")
    quality: str = Field(default="standard", pattern=r"^(haute|standard|rapide)$")
    fps: int = 30
    confirm: bool = False


def _slug(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()[:40] or "projet"


@router.post("/projects/{pid}/export", response_model=JobOut, status_code=202)
def export(pid: int, body: ExportIn, db: Session = Depends(get_db)):
    p = _project(db, pid)
    if not body.confirm:
        raise AppError("Confirmez l'exportation (confirm=true).", 400, "confirmation_required")
    if body.fps not in (24, 25, 30, 50, 60):
        raise AppError("Fréquence d'images autorisée : 24, 25, 30, 50 ou 60.", 422, "bad_fps")
    sb = _latest(db, pid)
    if not sb or sb.status != "validated":
        raise AppError("Validez le storyboard (après aperçu) avant d'exporter.", 409, "not_validated")
    if (j := _running(db, "export", pid)):
        return j
    W, H = planner.PLATFORM_FORMATS[body.platform]
    data = {**sb.data, "format": {**sb.data["format"], "platform": body.platform, "width": W, "height": H, "fps": body.fps}}
    paths, has_audio = _render_inputs(db, data)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = settings.exports_dir / EXPORT_DIRS[body.platform] / f"{_slug(p.name)}_{body.platform}_v{sb.version}_{stamp}.mp4"
    sb_id, version = sb.id, sb.version
    params = body.model_dump(exclude={"confirm"})

    def work(ctx):
        if out.exists():  # jamais d'écrasement
            raise AppError("Un export du même nom existe déjà.", 409, "exists")
        info = renderer.render(ctx, data, paths, has_audio, out, mode="final", quality=body.quality, fps=body.fps)
        ctx.progress(0.99, "Vérification du fichier exporté…", force=True)
        cs = subtitles_export.cues(data) if (data.get("subtitles") or {}).get("enabled") else []
        if cs:  # fichiers de sous-titres à côté de la vidéo
            out.with_suffix(".srt").write_text(subtitles_export.to_srt(cs), encoding="utf-8")
            out.with_suffix(".vtt").write_text(subtitles_export.to_vtt(cs), encoding="utf-8")
        ver = renderer.verify(out, {"width": W, "height": H, "fps": body.fps, "duration": info["expected_duration"]})
        with SessionLocal() as s:
            e = Export(project_id=pid, storyboard_id=sb_id, storyboard_version=version, platform=body.platform,
                       path=str(out.relative_to(settings.exports_dir.parent)) if out.is_relative_to(settings.exports_dir.parent) else str(out),
                       settings=params, verification={k: ver[k] for k in ("ok", "checks")} | {"warnings": info["warnings"]})
            s.add(e)
            proj = s.get(Project, pid)
            proj.status = "exported"
            proj.settings = {**(proj.settings or {}), "last_export": params}
            s.commit()
            return {"export_id": e.id, "path": e.path, "verification": ver["ok"], "checks": ver["checks"], "warnings": info["warnings"],
                    "subtitle_files": [p.name for p in (out.with_suffix(".srt"), out.with_suffix(".vtt")) if p.exists()]}

    return jobs_service.submit("export", pid, work)


@router.get("/projects/{pid}/exports")
def list_exports(pid: int, db: Session = Depends(get_db)):
    rows = db.scalars(select(Export).where(Export.project_id == pid).order_by(Export.id.desc())).all()
    return [{"id": e.id, "platform": e.platform, "path": e.path, "settings": e.settings, "verification": e.verification,
             "storyboard_version": e.storyboard_version, "created_at": e.created_at} for e in rows]


@router.get("/exports")
def all_exports(limit: int = 50, project_id: int | None = None, platform: str | None = None, db: Session = Depends(get_db)):
    q = select(Export).order_by(Export.id.desc()).limit(min(limit, 500))
    if project_id is not None:
        q = q.where(Export.project_id == project_id)
    if platform:
        q = q.where(Export.platform == platform)
    out = []
    for e in db.scalars(q).all():
        p = db.get(Project, e.project_id)
        path = (settings.exports_dir.parent / e.path) if not Path(e.path).is_absolute() else Path(e.path)
        out.append({"id": e.id, "project_id": e.project_id, "project_name": p.name if p else None, "platform": e.platform,
                    "path": e.path, "file_exists": path.exists(), "size_bytes": path.stat().st_size if path.exists() else None,
                    "settings": e.settings, "verification": e.verification, "storyboard_version": e.storyboard_version,
                    "created_at": e.created_at, "ok": e.verification.get("ok"),
                    "subtitle_files": [x.name for x in (path.with_suffix(".srt"), path.with_suffix(".vtt")) if x.exists()]})
    return out


@router.get("/storyboards")
def storyboards_overview(db: Session = Depends(get_db)):
    """Dernière version du storyboard de chaque projet (rubrique Storyboard du tableau de bord)."""
    out = []
    for p in db.scalars(select(Project).where(Project.archived.is_(False)).order_by(Project.updated_at.desc())).all():
        sb = _latest(db, p.id)
        if not sb:
            continue
        d = sb.data
        out.append({"project_id": p.id, "project_name": p.name, "project_type": p.project_type, "version": sb.version,
                    "status": sb.status, "scenes": len(d.get("scenes", [])), "duration": d.get("total_duration"),
                    "platform": d.get("format", {}).get("platform"), "style": (d.get("style") or {}).get("name"),
                    "has_preview": bool(sb.preview_path) and sb.preview_version == sb.version, "updated_at": sb.created_at})
    return out


@router.get("/exports/{eid}/file")
def export_file(eid: int, db: Session = Depends(get_db)):
    e = db.get(Export, eid)
    if not e:
        raise AppError("Export introuvable.", 404, "not_found")
    path = (settings.exports_dir.parent / e.path) if not Path(e.path).is_absolute() else Path(e.path)
    if not path.exists():
        raise AppError("Fichier d'export absent.", 410, "file_missing")
    return FileResponse(path, media_type="video/mp4", filename=path.name)
