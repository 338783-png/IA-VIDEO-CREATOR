from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    type: str
    target_id: int | None
    status: str
    progress: float
    message: str
    error: str
    result: dict
    created_at: datetime
    updated_at: datetime


class StyleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    reference_media_ids: list[int] = Field(min_length=1, max_length=20)


class StyleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    user_notes: str | None = Field(default=None, max_length=10000)
    config_patch: dict | None = None  # fusion partielle dans la configuration


class StyleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    status: str
    is_official: bool
    reference_media_ids: list
    summary: dict
    config: dict
    markdown: str
    user_notes: str
    files_dir: str
    validated_at: datetime | None
    created_at: datetime
    updated_at: datetime


class StyleListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    status: str
    is_official: bool
    reference_media_ids: list
    validated_at: datetime | None
    updated_at: datetime
