from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import ModelConfigTarget
from app.schemas.model_config import ModelConfigListResponse, ModelConfigRead, ModelConfigUpsert
from app.services.model_config_service import ModelConfigService

router = APIRouter(prefix="/model-configs", tags=["model-configs"])


@router.get("", response_model=ModelConfigListResponse)
def list_model_configs(db: Session = Depends(get_db)):
    svc = ModelConfigService(db)
    return ModelConfigListResponse(
        items=[
            ModelConfigRead(**svc.to_read_model(ModelConfigTarget.CRAWLER_AGENT)),
            ModelConfigRead(**svc.to_read_model(ModelConfigTarget.RECURSIVE_ACQUISITION)),
        ],
    )


@router.put("/{target}", response_model=ModelConfigRead)
def upsert_model_config(target: ModelConfigTarget, payload: ModelConfigUpsert, db: Session = Depends(get_db)):
    svc = ModelConfigService(db)
    try:
        svc.upsert_config(target, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ModelConfigRead(**svc.to_read_model(target))
