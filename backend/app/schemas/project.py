from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TargetFormat = Literal["tiktok", "reels", "shorts", "youtube"]
ProjectType = Literal["2d", "3d"]


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    instruction: str = Field(default="", max_length=5000)
    target_format: TargetFormat = "tiktok"
    project_type: ProjectType = "2d"


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    instruction: str | None = Field(default=None, max_length=5000)
    target_format: TargetFormat | None = None
    status: str | None = None
    settings: dict | None = None


class MediaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int | None
    kind: str
    category: str
    original_name: str
    stored_path: str
    size_bytes: int
    probe: dict
    created_at: datetime


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str
    instruction: str
    target_format: str
    project_type: str = "2d"
    status: str
    settings: dict
    archived: bool
    created_at: datetime
    updated_at: datetime


class ProjectCard(ProjectOut):
    thumbnail_media_id: int | None = None
    media_count: int = 0
    storyboard_version: int | None = None
    storyboard_status: str | None = None
    exports_count: int = 0


class ProjectDetail(ProjectOut):
    media: list[MediaOut] = []
