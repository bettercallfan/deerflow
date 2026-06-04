from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.common import APIMessage
from app.schemas.storage import (
    ConnectionTestResponse,
    MilvusConfigCreate,
    MySQLConfigCreate,
    StorageConfigRead,
)
from app.services.storage_service import StorageService, mask_conn_json

router = APIRouter(prefix="/storage", tags=["storage"])


def _to_storage_read(row):
    return StorageConfigRead(
        id=row.id,
        name=row.name,
        db_type=row.db_type,
        conn_json=mask_conn_json(row.db_type, row.conn_json),
        is_enabled=row.is_enabled,
        is_default=row.is_default,
        last_test_status=row.last_test_status,
        last_test_at=row.last_test_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("/configs/mysql", response_model=StorageConfigRead)
def create_mysql_config(payload: MySQLConfigCreate, db: Session = Depends(get_db)):
    svc = StorageService(db)
    row = svc.create_mysql_config(payload.model_dump())
    return _to_storage_read(row)


@router.post("/configs/milvus", response_model=StorageConfigRead)
def create_milvus_config(payload: MilvusConfigCreate, db: Session = Depends(get_db)):
    svc = StorageService(db)
    row = svc.create_milvus_config(payload.model_dump())
    return _to_storage_read(row)


@router.get("/configs", response_model=list[StorageConfigRead])
def list_configs(db: Session = Depends(get_db)):
    svc = StorageService(db)
    return [_to_storage_read(item) for item in svc.list_configs()]


@router.post("/configs/{config_id}/test", response_model=ConnectionTestResponse)
def test_config(config_id: str, db: Session = Depends(get_db)):
    svc = StorageService(db)
    ok, msg, latency = svc.test_connection(config_id)
    return ConnectionTestResponse(success=ok, message=msg, latency_ms=latency)


@router.delete("/configs/{config_id}", response_model=APIMessage)
def delete_config(config_id: str, db: Session = Depends(get_db)):
    svc = StorageService(db)
    ok = svc.delete_config(config_id)
    if not ok:
        raise HTTPException(status_code=404, detail="config not found")
    return APIMessage(message="config deleted")
