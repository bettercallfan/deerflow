from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.dataset import (
    DatasetRecordDetail,
    DatasetRecordListResponse,
    DatasetStatsResponse,
)
from app.services.dataset_service import DatasetService

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("/records", response_model=DatasetRecordListResponse)
def list_dataset_records(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None),
    result_type: str | None = Query(None),
    db: Session = Depends(get_db),
):
    service = DatasetService(db)
    return service.list_records(
        page=page,
        page_size=page_size,
        keyword=keyword,
        result_type=result_type,
    )


@router.get("/records/{record_id}", response_model=DatasetRecordDetail)
def get_dataset_record(
    record_id: int,
    db: Session = Depends(get_db),
):
    service = DatasetService(db)
    record = service.get_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Dataset record not found")
    return record


@router.get("/stats", response_model=DatasetStatsResponse)
def get_dataset_stats(
    db: Session = Depends(get_db),
):
    service = DatasetService(db)
    return service.get_stats()
