from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import ModelConfigTarget


class ModelConfigUpsert(BaseModel):
    api_key: str | None = Field(default=None, description="留空表示沿用已保存的 API Key")
    base_url: str = Field(min_length=1)
    model_name: str = Field(min_length=1)


class ModelConfigRead(BaseModel):
    target: ModelConfigTarget
    label: str
    has_api_key: bool = False
    base_url: str | None = None
    model_name: str | None = None
    is_configured: bool
    missing_fields: list[str]
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ModelConfigListResponse(BaseModel):
    items: list[ModelConfigRead]
