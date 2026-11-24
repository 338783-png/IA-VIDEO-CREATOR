from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    instruction: Mapped[str] = mapped_column(Text, default="")
    target_format: Mapped[str] = mapped_column(String(20), default="tiktok")
    project_type: Mapped[str] = mapped_column(String(4), default="2d")  # 2d | 3d
    status: Mapped[str] = mapped_column(String(30), default="draft")
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    media: Mapped[list["MediaFile"]] = relationship(back_populates="project", cascade="save-update, merge")


class MediaFile(Base):
    __tablename__ = "media_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(20))  # video | audio | image | reference
    category: Mapped[str] = mapped_column(String(20))  # video | audio | image
    original_name: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(500))  # relatif à storage/
    size_bytes: Mapped[int] = mapped_column(Integer)
    probe: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    project: Mapped[Project | None] = relationship(back_populates="media")


class Job(Base):
    """Tâche longue (analyse, rendu...) avec progression et annulation."""
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(40))
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|running|done|failed|cancelled|interrupted
    progress: Mapped[float] = mapped_column(default=0.0)  # 0..1
    message: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class ReferenceAnalysis(Base):
    """Résultat d'analyse d'une vidéo de référence (métriques uniquement, aucune copie du contenu)."""
    __tablename__ = "reference_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    media_id: Mapped[int] = mapped_column(ForeignKey("media_files.id"), unique=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class StyleProfile(Base):
    __tablename__ = "style_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|validated|rejected
    reference_media_ids: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)  # obligatoire / facultatif / par scène
    config: Mapped[dict] = mapped_column(JSON, default=dict)  # configuration moteur
    markdown: Mapped[str] = mapped_column(Text, default="")
    user_notes: Mapped[str] = mapped_column(Text, default="")
    is_official: Mapped[bool] = mapped_column(Boolean, default=False)
    files_dir: Mapped[str] = mapped_column(String(500), default="")
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class MediaAnalysis(Base):
    """Analyse d'un média source : plans, silences, énergie, transcription."""
    __tablename__ = "media_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    media_id: Mapped[int] = mapped_column(ForeignKey("media_files.id"), unique=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    transcript: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Storyboard(Base):
    """Une version de storyboard. Chaque modification crée une nouvelle version (historique conservé)."""
    __tablename__ = "storyboards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|validated
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    preview_path: Mapped[str] = mapped_column(String(500), default="")
    preview_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Export(Base):
    __tablename__ = "exports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    storyboard_id: Mapped[int] = mapped_column(ForeignKey("storyboards.id"))
    storyboard_version: Mapped[int] = mapped_column(Integer)
    platform: Mapped[str] = mapped_column(String(20))
    path: Mapped[str] = mapped_column(String(500))
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    verification: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class VoiceTrack(Base):
    """Piste vocale générée (TTS) : paramètres + horaires des mots et phonèmes (sous-titres, synchronisation labiale)."""
    __tablename__ = "voice_tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    media_id: Mapped[int] = mapped_column(ForeignKey("media_files.id"), unique=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    voice_id: Mapped[str] = mapped_column(String(100))
    speaker: Mapped[str | None] = mapped_column(String(100), nullable=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    words: Mapped[list] = mapped_column(JSON, default=list)
    phonemes: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Character(Base):
    """Personnage réutilisable dans plusieurs projets (2D ou 3D) : apparence, voix, paramètres."""
    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(4), default="2d")  # 2d | 3d
    description: Mapped[str] = mapped_column(Text, default="")
    appearance: Mapped[dict] = mapped_column(JSON, default=dict)
    voice: Mapped[dict] = mapped_column(JSON, default=dict)  # voice_id, speaker, speed
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Scenario(Base):
    """Scénario dialogué d'un projet animé : scènes, répliques, personnages, émotions. Versionné."""
    __tablename__ = "scenarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | validated
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
