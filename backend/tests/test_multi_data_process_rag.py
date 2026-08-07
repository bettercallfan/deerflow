"""Unit tests for controlled Multi Data Process RAG ingestion and retrieval."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.gateway.routers.multi_data_process_rag import (
    SyncVersionPayload,
    _to_sync_request,
    _validate_callback_event,
)
from app.gateway.services.multi_data_process_rag import (
    ElasticsearchHttpClient,
    MultiDataProcessRagSearchService,
    MultiDataProcessRagSettings,
    MultiDataProcessRagSyncService,
    SearchRequest,
    SourceVersionNotFound,
    _chunks_mapping,
)


SETTINGS = MultiDataProcessRagSettings(
    es_url="http://example.invalid:9200",
    es_username=None,
    es_password=None,
    source_index="multi-data-process-documents",
    chunks_index="multi-data-process-rag-chunks",
    request_timeout_seconds=10,
    source_page_size=100,
    embedding_base_url=None,
    embedding_model="unused",
    embedding_api_key=None,
    embedding_batch_size=8,
    verify_tls=True,
)


def source_hit(
    *,
    dataset_id: int | str = 42,
    version_id: str = "v-1",
    status: str = "ready",
    is_current: bool = True,
    content: str = "Example Domain is a deliberately simple documentation website.",
) -> dict[str, Any]:
    return {
        "_id": "source-document-1",
        "_source": {
            "dataset_id": dataset_id,
            "dataset_version_id": version_id,
            "__mdp_dataset_id": dataset_id,
            "__mdp_version_id": version_id,
            "status": status,
            "is_current": is_current,
            "title": "Example Domain",
            "content": content,
            "source_url": "https://www.example.com/",
            "source_task_id": "crawl-task-1",
        },
    }


class FakeElasticsearch:
    def __init__(self, hits: list[dict[str, Any]]) -> None:
        self.hits = hits
        self.events: list[tuple[Any, ...]] = []
        self.documents: dict[str, dict[str, Any]] = {
            "other-version": {
                "chunk_id": "other-version",
                "dataset_id": "42",
                "dataset_version_id": "v-older",
            }
        }

    def iter_source_documents(self, dataset_version_id: str):
        self.events.append(("iter", dataset_version_id))
        yield from self.hits

    def ensure_chunks_index(self, dimensions: int | None) -> None:
        self.events.append(("ensure", dimensions))

    def delete_version(self, dataset_id: str, dataset_version_id: str) -> int:
        self.events.append(("delete", dataset_id, dataset_version_id))
        existing = list(self.documents.items())
        removed = 0
        for chunk_id, document in existing:
            if document.get("dataset_id") == dataset_id and document.get("dataset_version_id") == dataset_version_id:
                del self.documents[chunk_id]
                removed += 1
        return removed

    def bulk_index(self, documents: list[dict[str, Any]]) -> None:
        self.events.append(("bulk", len(documents)))
        for document in documents:
            self.documents[str(document["chunk_id"])] = dict(document)

    def activate_version(self, dataset_id: str, dataset_version_id: str) -> None:
        self.events.append(("activate", dataset_id, dataset_version_id))


class DisabledEmbeddingClient:
    configured = False


def sync_service(fake_es: FakeElasticsearch) -> MultiDataProcessRagSyncService:
    return MultiDataProcessRagSyncService(
        SETTINGS,
        es_client=fake_es,  # type: ignore[arg-type]
        embedding_client=DisabledEmbeddingClient(),  # type: ignore[arg-type]
    )


def sync_request() -> Any:
    return _to_sync_request(
        SyncVersionPayload(
            dataset_id=42,
            dataset_version_id="v-1",
            workflow_id=9,
            job_id="job-9",
            status="ready",
        )
    )


def test_sync_replay_replaces_only_the_exact_version_in_a_safe_order() -> None:
    fake_es = FakeElasticsearch([source_hit()])
    service = sync_service(fake_es)

    first = service.sync_version(sync_request())
    assert first.embedding_status == "not_configured"
    assert first.chunks_indexed == 1
    assert fake_es.events == [
        ("iter", "v-1"),
        ("ensure", None),
        ("delete", "42", "v-1"),
        ("bulk", 1),
        ("activate", "42", "v-1"),
    ]
    assert "other-version" in fake_es.documents
    first_chunk_ids = {chunk_id for chunk_id, document in fake_es.documents.items() if document.get("dataset_version_id") == "v-1"}
    assert len(first_chunk_ids) == 1

    # Replay is idempotent: it uses the same deterministic IDs and scopes cleanup
    # to (dataset_id, dataset_version_id), never the older version.
    second = service.sync_version(sync_request())
    assert second.chunks_indexed == 1
    second_chunk_ids = {chunk_id for chunk_id, document in fake_es.documents.items() if document.get("dataset_version_id") == "v-1"}
    assert second_chunk_ids == first_chunk_ids
    assert "other-version" in fake_es.documents
    assert fake_es.events[-4:] == [
        ("ensure", None),
        ("delete", "42", "v-1"),
        ("bulk", 1),
        ("activate", "42", "v-1"),
    ]


def test_failed_cleanup_is_idempotent_and_cannot_delete_another_version() -> None:
    fake_es = FakeElasticsearch([])
    fake_es.documents["failed-version"] = {
        "chunk_id": "failed-version",
        "dataset_id": "42",
        "dataset_version_id": "v-failed",
    }
    service = sync_service(fake_es)

    assert service.cleanup_failed_version("42", "v-failed") == 1
    assert "failed-version" not in fake_es.documents
    assert "other-version" in fake_es.documents
    assert service.cleanup_failed_version("42", "v-failed") == 0
    assert fake_es.events[-2:] == [("delete", "42", "v-failed"), ("delete", "42", "v-failed")]


def test_sync_rejects_noncanonical_writing_or_noncurrent_source_documents() -> None:
    for hit in [source_hit(status="writing"), source_hit(is_current=False)]:
        with pytest.raises(SourceVersionNotFound):
            sync_service(FakeElasticsearch([hit])).sync_version(sync_request())


def test_chunks_mapping_has_no_hardcoded_vector_dimension() -> None:
    lexical_mapping = _chunks_mapping(None)
    assert "content_vector" not in lexical_mapping["mappings"]["properties"]

    vector_mapping = _chunks_mapping(7)
    assert vector_mapping["mappings"]["properties"]["content_vector"]["dims"] == 7


def test_search_query_enforces_ready_current_and_visibility_filters() -> None:
    client = ElasticsearchHttpClient(SETTINGS)
    captured: dict[str, Any] = {}

    def fake_json_request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        captured.update({"method": method, "path": path, **kwargs})
        return {"hits": {"hits": []}}

    client._json_request = fake_json_request  # type: ignore[method-assign]
    client.search_chunks(SearchRequest(query="Example Domain", workspace_id="workspace-a"))

    filters = captured["json_body"]["query"]["bool"]["filter"]
    assert {"term": {"version_status": "ready"}} in filters
    assert {"term": {"is_current": True}} in filters
    visibility_filter = next(item for item in filters if "bool" in item)
    assert visibility_filter["bool"]["minimum_should_match"] == 1

    captured.clear()
    client.search_chunks(SearchRequest(query="Example Domain", include_historical=True))
    historical_filters = captured["json_body"]["query"]["bool"]["filter"]
    assert {"term": {"version_status": "ready"}} in historical_filters
    assert {"term": {"is_current": True}} not in historical_filters
    assert {"term": {"visibility": "global"}} in historical_filters


def test_cleanup_returns_zero_when_chunks_index_has_never_been_created() -> None:
    client = ElasticsearchHttpClient(SETTINGS)
    client._request = lambda *args, **kwargs: SimpleNamespace(status_code=404)  # type: ignore[method-assign]
    client._json_request = lambda *args, **kwargs: pytest.fail("delete-by-query must not run for a missing index")  # type: ignore[method-assign]
    assert client.delete_version("42", "v-failed") == 0


def test_search_service_returns_traceable_citations() -> None:
    class SearchFake:
        def search_chunks(self, request: SearchRequest) -> list[dict[str, Any]]:
            assert request.query == "Example Domain"
            return [
                {
                    "_id": "chunk-1",
                    "_score": 1.2,
                    "_source": {
                        "chunk_id": "chunk-1",
                        "chunk_index": 0,
                        "content": "Example Domain is for documentation examples.",
                        "title": "Example Domain",
                        "source_url": "https://www.example.com/",
                        "source_document_id": "source-1",
                        "dataset_id": "42",
                        "dataset_version_id": "v-1",
                    },
                }
            ]

    result = MultiDataProcessRagSearchService(SETTINGS, es_client=SearchFake()).search(  # type: ignore[arg-type]
        SearchRequest(query="Example Domain")
    )
    assert result.retrieval_mode == "bm25"
    assert result.results[0]["citation"] == "数据集 42 | 版本 v-1 | Example Domain | https://www.example.com/"


def test_mdp_callback_envelope_accepts_integer_dataset_id_and_validates_events() -> None:
    ready_payload = SyncVersionPayload(
        event="dataset_version.ready",
        schema_version="multi-data-process-rag-event-v1",
        dataset_id=42,
        dataset_version_id="v-1",
        workflow_id=9,
        status="success",
    )
    request = _to_sync_request(ready_payload)
    assert request.dataset_id == "42"
    assert request.dataset_version_id == "v-1"
    assert request.workflow_id == "9"
    _validate_callback_event(ready_payload, "dataset_version.ready")

    failed_payload = SyncVersionPayload(
        event="dataset_version.failed",
        dataset_id=42,
        dataset_version_id="v-failed",
        status="failed",
    )
    _validate_callback_event(failed_payload, "dataset_version.failed")
    with pytest.raises(Exception, match="failed event"):
        _validate_callback_event(SyncVersionPayload(event="dataset_version.failed", dataset_id=42, dataset_version_id="v-failed", status="ready"), "dataset_version.failed")


def test_skill_script_calls_controlled_gateway_and_preserves_returned_citations(monkeypatch: pytest.MonkeyPatch) -> None:
    project_root = Path(__file__).resolve().parents[2]
    script_path = project_root / "skills/custom/multi-data-process-rag/scripts/search_multi_data_process.py"
    spec = importlib.util.spec_from_file_location("multi_data_process_skill_script", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    observed: dict[str, Any] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args: Any) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "success": True,
                    "results": [
                        {
                            "content": "Example Domain result",
                            "citation": "数据集 42 | 版本 v-1 | Example Domain | https://www.example.com/",
                        }
                    ],
                }
            ).encode("utf-8")

    def fake_urlopen(request: Any, timeout: int) -> FakeResponse:
        observed["url"] = request.full_url
        observed["authorization"] = request.get_header("Authorization")
        observed["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setenv("MULTI_DATA_PROCESS_RAG_GATEWAY_URL", "http://gateway.internal:3318")
    monkeypatch.setenv("MULTI_DATA_PROCESS_RAG_SEARCH_TOKEN", "sandbox-only-token")
    monkeypatch.setattr(module, "urlopen", fake_urlopen)
    result = module.search(
        argparse.Namespace(
            query="Example Domain",
            top_k=3,
            dataset_id="42",
            dataset_version_id=None,
            workspace_id=None,
            include_historical=False,
            timeout=9,
            pretty=True,
        )
    )

    assert observed["url"] == "http://gateway.internal:3318/api/multi-data-process-rag/search"
    assert observed["authorization"] == "Bearer sandbox-only-token"
    assert observed["timeout"] == 9
    assert result["results"][0]["citation"].startswith("数据集 42 | 版本 v-1")
