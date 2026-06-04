from datetime import datetime
from pydantic import BaseModel, Field

from app.models.enums import StorageConfigType


class MySQLConfigCreate(BaseModel):
    name: str = Field(min_length=1)
    host: str
    port: int = 3306
    username: str
    password: str
    database: str
    charset: str = "utf8mb4"


class MilvusConfigCreate(BaseModel):
    name: str = Field(min_length=1)
    uri: str
    token: str | None = None
    db_name: str = "default"
    collection_prefix: str = "crawler"
    dimension: int = 1024
    metric_type: str = "IP"
    index_type: str = "AUTOINDEX"


class StorageConfigRead(BaseModel):
    id: str
    name: str
    db_type: StorageConfigType
    conn_json: dict
    is_enabled: bool
    is_default: bool
    last_test_status: str | None
    last_test_at: datetime | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ConnectionTestResponse(BaseModel):
    success: bool
    message: str
    latency_ms: int | None = None
