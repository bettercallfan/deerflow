"""Controlled ingestion and retrieval endpoints for Multi Data Process RAG."""

from __future__ import annotations

import os
import secrets
from typing import Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.gateway.services.multi_data_process_rag import (
    ElasticsearchRequestError,
    MultiDataProcessRagError,
    MultiDataProcessRagSearchService,
    MultiDataProcessRagSettings,
    MultiDataProcessRagSyncService,
    NoIndexableContent,
    RagConfigurationError,
    SearchRequest,
    SourceVersionNotFound,
    SyncRequest,
    SyncResult,
)

router = APIRouter(prefix="/api/multi-data-process-rag", tags=["multi_data_process_rag"])

_CALLBACK_SCHEMA_VERSION = "multi-data-process-rag-event-v1"
_READY_EVENT = "dataset_version.ready"
_FAILED_EVENT = "dataset_version.failed"


class SyncVersionPayload(BaseModel):
    """The allowlisted MDP callback contract; client-provided index names are ignored."""

    event: Literal["dataset_version.ready", "dataset_version.failed"] = _READY_EVENT
    schema_version: Literal["multi-data-process-rag-event-v1"] = _CALLBACK_SCHEMA_VERSION
    dataset_id: str | int
    dataset_version_id: str | int
    version_no: str | int | None = None
    # MDP persists workflow IDs as integers, while older callers may send
    # string identifiers. Normalize both forms before handing the value to
    # the internal request model.
    workflow_id: str | int | None = None
    job_id: str | None = None
    # Informational only: the Gateway always reads its configured source index.
    index: str | None = None
    record_count: int | None = Field(default=None, ge=0)
    status: Literal["ready", "success", "failed"] = "ready"
    visibility: Literal["global", "workspace"] = "global"
    workspace_id: str | None = None
    error_message: str | None = None
    activate_current: bool = True
    chunk_size: int = Field(default=800, ge=200, le=4000)
    chunk_overlap: int = Field(default=120, ge=0, le=800)


class SearchPayload(BaseModel):
    """Read-only retrieval request. It intentionally has no ES/index parameters."""

    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=8, ge=1, le=20)
    dataset_id: str | int | None = None
    dataset_version_id: str | int | None = None
    workspace_id: str | None = None
    include_historical: bool = False


class SyncVersionResponse(BaseModel):
    success: bool = True
    action: Literal["synced", "cleaned"] = "synced"
    dataset_id: str
    dataset_version_id: str
    source_documents: int = 0
    indexable_documents: int = 0
    chunks_indexed: int = 0
    chunks_deleted: int = 0
    chunks_index: str
    activated_current: bool = False
    embedding_status: str = "not_applicable"
    embedding_dimensions: int | None = None
    warnings: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    success: bool = True
    query: str
    retrieval_mode: Literal["bm25"] = "bm25"
    chunks_index: str
    results: list[dict]


class RagSyncStatusResponse(BaseModel):
    sync_enabled: bool
    source_index: str | None = None
    chunks_index: str | None = None
    embedding_configured: bool = False
    search_enabled: bool = False


def _expected_sync_token() -> str:
    return os.getenv("MULTI_DATA_PROCESS_RAG_SYNC_TOKEN", "").strip()


def _expected_search_token() -> str:
    return os.getenv("MULTI_DATA_PROCESS_RAG_SEARCH_TOKEN", "").strip()


def _supplied_token(x_mdp_sync_token: str | None, authorization: str | None) -> str:
    supplied = (x_mdp_sync_token or "").strip()
    if not supplied and authorization:
        scheme, _, credential = authorization.partition(" ")
        if scheme.lower() == "bearer":
            supplied = credential.strip()
    return supplied


def _authorize_token(expected: str, supplied: str, purpose: str) -> None:
    if not expected:
        raise HTTPException(status_code=503, detail=f"Multi Data Process RAG {purpose} is not configured")
    if not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail=f"Invalid Multi Data Process RAG {purpose} token")


def _authorize_sync(x_mdp_sync_token: str | None, authorization: str | None) -> None:
    _authorize_token(_expected_sync_token(), _supplied_token(x_mdp_sync_token, authorization), "sync")


def _authorize_search(authorization: str | None) -> None:
    _authorize_token(_expected_search_token(), _supplied_token(None, authorization), "search")


def _normalise_identifier(value: str | int | None, label: str, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise MultiDataProcessRagError(f"{label} is required")
        return None
    normalized = str(value).strip()
    if not normalized or len(normalized) > 256:
        raise MultiDataProcessRagError(f"{label} must be a non-empty value of at most 256 characters")
    return normalized


def _validate_callback_event(payload: SyncVersionPayload, x_mdp_event: str | None) -> None:
    if x_mdp_event and not secrets.compare_digest(x_mdp_event.strip(), payload.event):
        raise MultiDataProcessRagError("X-MDP-Event does not match the callback event")
    if payload.event == _READY_EVENT and payload.status not in {"ready", "success"}:
        raise MultiDataProcessRagError("a ready event must have ready or success status")
    if payload.event == _FAILED_EVENT and payload.status != "failed":
        raise MultiDataProcessRagError("a failed event must have failed status")


def _to_sync_request(payload: SyncVersionPayload) -> SyncRequest:
    request = SyncRequest(
        dataset_id=_normalise_identifier(payload.dataset_id, "dataset_id", required=True) or "",
        dataset_version_id=_normalise_identifier(payload.dataset_version_id, "dataset_version_id", required=True) or "",
        workflow_id=_normalise_identifier(payload.workflow_id, "workflow_id"),
        job_id=_normalise_identifier(payload.job_id, "job_id"),
        version_status=payload.status,
        activate_current=payload.activate_current,
        visibility=payload.visibility,
        workspace_id=_normalise_identifier(payload.workspace_id, "workspace_id"),
        chunk_size=payload.chunk_size,
        chunk_overlap=payload.chunk_overlap,
    )
    request.validate()
    return request


def _to_response(result: SyncResult) -> SyncVersionResponse:
    return SyncVersionResponse(
        dataset_id=result.dataset_id,
        dataset_version_id=result.dataset_version_id,
        source_documents=result.source_documents,
        indexable_documents=result.indexable_documents,
        chunks_indexed=result.chunks_indexed,
        chunks_index=result.chunks_index,
        activated_current=result.activated_current,
        embedding_status=result.embedding_status,
        embedding_dimensions=result.embedding_dimensions,
        warnings=result.warnings,
    )


def _cleanup_response(payload: SyncVersionPayload, settings: MultiDataProcessRagSettings, deleted: int) -> SyncVersionResponse:
    return SyncVersionResponse(
        action="cleaned",
        dataset_id=_normalise_identifier(payload.dataset_id, "dataset_id", required=True) or "",
        dataset_version_id=_normalise_identifier(payload.dataset_version_id, "dataset_version_id", required=True) or "",
        chunks_deleted=deleted,
        chunks_index=settings.chunks_index,
        warnings=[] if deleted else ["no RAG chunks existed for this failed version"],
    )


def _raise_http_error(exc: Exception) -> None:
    if isinstance(exc, SourceVersionNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, NoIndexableContent):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if isinstance(exc, RagConfigurationError):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if isinstance(exc, ElasticsearchRequestError):
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if isinstance(exc, MultiDataProcessRagError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


@router.get("/status", response_model=RagSyncStatusResponse)
async def get_sync_status(
    x_mdp_sync_token: str | None = Header(default=None, alias="X-MDP-Sync-Token"),
    authorization: str | None = Header(default=None),
) -> RagSyncStatusResponse:
    """Return non-sensitive callback configuration after sync-token authentication."""

    _authorize_sync(x_mdp_sync_token, authorization)
    try:
        settings = MultiDataProcessRagSettings.from_environment()
    except RagConfigurationError:
        return RagSyncStatusResponse(sync_enabled=True, search_enabled=bool(_expected_search_token()))
    return RagSyncStatusResponse(
        sync_enabled=True,
        source_index=settings.source_index,
        chunks_index=settings.chunks_index,
        embedding_configured=bool(settings.embedding_base_url),
        search_enabled=bool(_expected_search_token()),
    )


@router.post("/sync", response_model=SyncVersionResponse)
async def sync_completed_dataset_version(
    payload: SyncVersionPayload,
    x_mdp_sync_token: str | None = Header(default=None, alias="X-MDP-Sync-Token"),
    x_mdp_event: str | None = Header(default=None, alias="X-MDP-Event"),
    authorization: str | None = Header(default=None),
) -> SyncVersionResponse:
    """Sync a ready version, or safely clean only the named failed version."""

    _authorize_sync(x_mdp_sync_token, authorization)
    try:
        _validate_callback_event(payload, x_mdp_event)
        settings = MultiDataProcessRagSettings.from_environment()
        service = MultiDataProcessRagSyncService(settings)
        if payload.event == _FAILED_EVENT:
            dataset_id = _normalise_identifier(payload.dataset_id, "dataset_id", required=True) or ""
            version_id = _normalise_identifier(payload.dataset_version_id, "dataset_version_id", required=True) or ""
            deleted = await run_in_threadpool(service.cleanup_failed_version, dataset_id, version_id)
            return _cleanup_response(payload, settings, deleted)
        result = await run_in_threadpool(service.sync_version, _to_sync_request(payload))
        return _to_response(result)
    except Exception as exc:
        _raise_http_error(exc)
        raise AssertionError("unreachable")


@router.post("/cleanup", response_model=SyncVersionResponse)
async def cleanup_failed_dataset_version(
    payload: SyncVersionPayload,
    x_mdp_sync_token: str | None = Header(default=None, alias="X-MDP-Sync-Token"),
    x_mdp_event: str | None = Header(default=None, alias="X-MDP-Event"),
    authorization: str | None = Header(default=None),
) -> SyncVersionResponse:
    """Explicit, idempotent cleanup endpoint for a failed dataset version only."""

    _authorize_sync(x_mdp_sync_token, authorization)
    try:
        _validate_callback_event(payload, x_mdp_event)
        if payload.event != _FAILED_EVENT:
            raise MultiDataProcessRagError("/cleanup accepts dataset_version.failed events only")
        settings = MultiDataProcessRagSettings.from_environment()
        service = MultiDataProcessRagSyncService(settings)
        dataset_id = _normalise_identifier(payload.dataset_id, "dataset_id", required=True) or ""
        version_id = _normalise_identifier(payload.dataset_version_id, "dataset_version_id", required=True) or ""
        deleted = await run_in_threadpool(service.cleanup_failed_version, dataset_id, version_id)
        return _cleanup_response(payload, settings, deleted)
    except Exception as exc:
        _raise_http_error(exc)
        raise AssertionError("unreachable")


@router.post("/search", response_model=SearchResponse)
async def search_materialised_chunks(
    payload: SearchPayload,
    authorization: str | None = Header(default=None),
) -> SearchResponse:
    """Return token-protected BM25 evidence for the chat Skill, never raw ES access."""

    _authorize_search(authorization)
    try:
        settings = MultiDataProcessRagSettings.from_environment()
        request = SearchRequest(
            query=payload.query,
            top_k=payload.top_k,
            dataset_id=_normalise_identifier(payload.dataset_id, "dataset_id"),
            dataset_version_id=_normalise_identifier(payload.dataset_version_id, "dataset_version_id"),
            workspace_id=_normalise_identifier(payload.workspace_id, "workspace_id"),
            include_historical=payload.include_historical,
        )
        result = await run_in_threadpool(MultiDataProcessRagSearchService(settings).search, request)
        return SearchResponse(
            query=result.query,
            retrieval_mode=result.retrieval_mode,
            chunks_index=settings.chunks_index,
            results=result.results,
        )
    except Exception as exc:
        _raise_http_error(exc)
        raise AssertionError("unreachable")
