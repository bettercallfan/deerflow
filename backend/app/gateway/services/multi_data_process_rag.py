"""Controlled Elasticsearch ingestion for Multi Data Process RAG.

The multi-data-process platform writes one document per processed source record
to ``multi-data-process-documents``.  DeerFlow should not query that mutable
document shape directly: this module reads one completed dataset version,
creates deterministic text chunks, and stores them in the dedicated
``multi-data-process-rag-chunks`` index.

The implementation deliberately keeps the source and target index names under
server-side configuration.  API callers cannot select an arbitrary ES index.
Embeddings are optional: when no compatible OpenAI-style embedding endpoint is
configured (or it is temporarily unavailable), the chunk index still supports
BM25 retrieval through its ``content`` field.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterator

import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)

DEFAULT_SOURCE_INDEX = "multi-data-process-documents"
DEFAULT_CHUNKS_INDEX = "multi-data-process-rag-chunks"
_INDEX_NAME_RE = re.compile(r"^[a-z0-9._-]+$")
_TEXT_KEYS = ("content", "content_text", "text", "page_content", "markdown", "body")
_SKIP_TEXT_KEYS = {
    "embedding",
    "content_vector",
    "vector",
    "metadata",
    "raw_data",
    "source",
    "source_metadata",
}
_SCALAR_METADATA_KEYS = (
    "source_type",
    "source_title",
    "filename",
    "filetype",
    "language",
    "languages",
    "last_modified",
)


class MultiDataProcessRagError(RuntimeError):
    """Base error for the controlled RAG ingestion flow."""


class RagConfigurationError(MultiDataProcessRagError):
    """Raised when a mandatory server-side configuration value is absent."""


class ElasticsearchRequestError(MultiDataProcessRagError):
    """Raised for a failed Elasticsearch request without exposing credentials."""


class SourceVersionNotFound(MultiDataProcessRagError):
    """Raised when the requested successful source dataset version is absent."""


class NoIndexableContent(MultiDataProcessRagError):
    """Raised when a source version exists but has no usable text."""


@dataclass(frozen=True)
class MultiDataProcessRagSettings:
    """Server-side settings for the source, chunk, and optional embedding APIs."""

    es_url: str
    es_username: str | None
    es_password: str | None
    source_index: str
    chunks_index: str
    request_timeout_seconds: int
    source_page_size: int
    embedding_base_url: str | None
    embedding_model: str
    embedding_api_key: str | None
    embedding_batch_size: int
    verify_tls: bool

    @classmethod
    def from_environment(cls) -> "MultiDataProcessRagSettings":
        es_url = (
            os.getenv("MULTI_DATA_PROCESS_RAG_ES_URL")
            or os.getenv("ES_URL")
            or ""
        ).strip().rstrip("/")
        if not es_url:
            raise RagConfigurationError("MULTI_DATA_PROCESS_RAG_ES_URL or ES_URL is required")

        source_index = (os.getenv("MULTI_DATA_PROCESS_RAG_SOURCE_INDEX") or DEFAULT_SOURCE_INDEX).strip()
        chunks_index = (os.getenv("MULTI_DATA_PROCESS_RAG_CHUNKS_INDEX") or DEFAULT_CHUNKS_INDEX).strip()
        _validate_index_name(source_index, "source")
        _validate_index_name(chunks_index, "chunks")

        return cls(
            es_url=es_url,
            es_username=(
                os.getenv("MULTI_DATA_PROCESS_RAG_ES_USERNAME")
                or os.getenv("ES_USERNAME")
                or os.getenv("ES_USER")
                or None
            ),
            es_password=(
                os.getenv("MULTI_DATA_PROCESS_RAG_ES_PASSWORD")
                or os.getenv("ES_PASSWORD")
                or None
            ),
            source_index=source_index,
            chunks_index=chunks_index,
            request_timeout_seconds=_read_int("MULTI_DATA_PROCESS_RAG_TIMEOUT_SECONDS", 30, minimum=5, maximum=120),
            source_page_size=_read_int("MULTI_DATA_PROCESS_RAG_SOURCE_PAGE_SIZE", 250, minimum=1, maximum=1000),
            embedding_base_url=(
                os.getenv("MULTI_DATA_PROCESS_RAG_EMBEDDING_BASE_URL")
                or os.getenv("EMBEDDING_BASE_URL")
                or None
            ),
            embedding_model=(
                os.getenv("MULTI_DATA_PROCESS_RAG_EMBEDDING_MODEL")
                or os.getenv("EMBEDDING_MODEL")
                or "BAAI/bge-m3"
            ),
            embedding_api_key=(
                os.getenv("MULTI_DATA_PROCESS_RAG_EMBEDDING_API_KEY")
                or os.getenv("EMBEDDING_API_KEY")
                or None
            ),
            embedding_batch_size=_read_int("MULTI_DATA_PROCESS_RAG_EMBEDDING_BATCH_SIZE", 16, minimum=1, maximum=64),
            verify_tls=_read_bool("MULTI_DATA_PROCESS_RAG_VERIFY_TLS", True),
        )


@dataclass(frozen=True)
class SyncRequest:
    """A completed dataset version to materialise into the chunks index."""

    dataset_id: str
    dataset_version_id: str
    workflow_id: str | None = None
    job_id: str | None = None
    version_status: str = "ready"
    activate_current: bool = True
    visibility: str = "global"
    workspace_id: str | None = None
    chunk_size: int = 800
    chunk_overlap: int = 120

    def validate(self) -> None:
        _validate_identifier(self.dataset_id, "dataset_id")
        _validate_identifier(self.dataset_version_id, "dataset_version_id")
        if self.version_status not in {"ready", "success"}:
            raise MultiDataProcessRagError("only a ready or success dataset version can be synchronized")
        if self.visibility not in {"global", "workspace"}:
            raise MultiDataProcessRagError("visibility must be global or workspace")
        if self.visibility == "workspace" and not (self.workspace_id or "").strip():
            raise MultiDataProcessRagError("workspace_id is required when visibility is workspace")
        if not 200 <= self.chunk_size <= 4000:
            raise MultiDataProcessRagError("chunk_size must be between 200 and 4000")
        if not 0 <= self.chunk_overlap < self.chunk_size:
            raise MultiDataProcessRagError("chunk_overlap must be non-negative and smaller than chunk_size")


@dataclass(frozen=True)
class SyncResult:
    """Safe, serializable summary returned to the upstream workflow."""

    dataset_id: str
    dataset_version_id: str
    source_documents: int
    indexable_documents: int
    chunks_indexed: int
    chunks_index: str
    activated_current: bool
    embedding_status: str
    embedding_dimensions: int | None
    warnings: list[str]


@dataclass(frozen=True)
class SearchRequest:
    """A controlled, read-only retrieval request over materialised RAG chunks."""

    query: str
    top_k: int = 8
    dataset_id: str | None = None
    dataset_version_id: str | None = None
    workspace_id: str | None = None
    include_historical: bool = False

    def validate(self) -> None:
        if not self.query or not self.query.strip() or len(self.query.strip()) > 2000:
            raise MultiDataProcessRagError("query must be a non-empty value of at most 2000 characters")
        if not 1 <= self.top_k <= 20:
            raise MultiDataProcessRagError("top_k must be between 1 and 20")
        if self.dataset_id is not None:
            _validate_identifier(self.dataset_id, "dataset_id")
        if self.dataset_version_id is not None:
            _validate_identifier(self.dataset_version_id, "dataset_version_id")
        if self.workspace_id is not None:
            _validate_identifier(self.workspace_id, "workspace_id")


@dataclass(frozen=True)
class SearchResult:
    """Sanitised retrieval evidence returned by the Gateway and Skill script."""

    query: str
    retrieval_mode: str
    results: list[dict[str, Any]]


class ElasticsearchHttpClient:
    """Small, dependency-light wrapper around only the ES APIs this flow needs."""

    def __init__(self, settings: MultiDataProcessRagSettings) -> None:
        self.settings = settings
        self.auth = (
            HTTPBasicAuth(settings.es_username, settings.es_password)
            if settings.es_username and settings.es_password
            else None
        )

    def iter_source_documents(self, dataset_version_id: str) -> Iterator[dict[str, Any]]:
        """Yield all main-index documents belonging to one dataset version."""

        query = {
            "size": self.settings.source_page_size,
            "sort": ["_doc"],
            "track_total_hits": True,
            "query": {
                "bool": {
                    "filter": [
                        {
                            "bool": {
                                "should": [
                                    {"term": {"__mdp_version_id": dataset_version_id}},
                                    {"term": {"dataset_version_id": dataset_version_id}},
                                ],
                                "minimum_should_match": 1,
                            }
                        },
                        {"term": {"status": "ready"}},
                        {"term": {"is_current": True}},
                    ]
                }
            },
        }
        response = self._json_request(
            "POST",
            f"/{self.settings.source_index}/_search",
            params={"scroll": "1m"},
            json_body=query,
        )
        scroll_id = response.get("_scroll_id")
        try:
            while True:
                hits = response.get("hits", {}).get("hits", [])
                if not isinstance(hits, list) or not hits:
                    break
                for hit in hits:
                    if isinstance(hit, dict) and isinstance(hit.get("_source"), dict):
                        yield hit
                if not scroll_id:
                    break
                response = self._json_request(
                    "POST",
                    "/_search/scroll",
                    json_body={"scroll": "1m", "scroll_id": scroll_id},
                )
                scroll_id = response.get("_scroll_id") or scroll_id
        finally:
            if scroll_id:
                try:
                    self._json_request("DELETE", "/_search/scroll", json_body={"scroll_id": [scroll_id]})
                except ElasticsearchRequestError:
                    logger.warning("Unable to clear Elasticsearch scroll for multi-data-process RAG sync")

    def ensure_chunks_index(self, embedding_dimensions: int | None) -> None:
        """Create the chunks index lazily and add its vector field only when known."""

        response = self._request("HEAD", f"/{self.settings.chunks_index}", allow_statuses={404})
        if response.status_code == 404:
            self._json_request(
                "PUT",
                f"/{self.settings.chunks_index}",
                json_body=_chunks_mapping(embedding_dimensions),
            )
            return

        if embedding_dimensions is None:
            return

        mapping = self._json_request("GET", f"/{self.settings.chunks_index}/_mapping")
        properties = mapping.get(self.settings.chunks_index, {}).get("mappings", {}).get("properties", {})
        vector_mapping = properties.get("content_vector") if isinstance(properties, dict) else None
        if isinstance(vector_mapping, dict):
            existing_dims = vector_mapping.get("dims")
            if existing_dims is not None and int(existing_dims) != embedding_dimensions:
                raise ElasticsearchRequestError(
                    "existing content_vector dimensions do not match the configured embedding service"
                )
            return

        self._json_request(
            "PUT",
            f"/{self.settings.chunks_index}/_mapping",
            json_body={"properties": {"content_vector": _vector_mapping(embedding_dimensions)}},
        )

    def bulk_index(self, documents: list[dict[str, Any]]) -> None:
        """Bulk-index chunks using their deterministic chunk IDs as ES IDs."""

        for start in range(0, len(documents), 100):
            batch = documents[start : start + 100]
            lines: list[str] = []
            for document in batch:
                lines.append(json.dumps({"index": {"_index": self.settings.chunks_index, "_id": document["chunk_id"]}}, ensure_ascii=False))
                lines.append(json.dumps(document, ensure_ascii=False, separators=(",", ":")))
            payload = "\n".join(lines) + "\n"
            response = self._json_request(
                "POST",
                "/_bulk",
                params={"refresh": "wait_for"},
                data=payload,
                headers={"Content-Type": "application/x-ndjson"},
            )
            if response.get("errors"):
                raise ElasticsearchRequestError("Elasticsearch rejected one or more RAG chunk documents")

    def activate_version(self, dataset_id: str, dataset_version_id: str) -> None:
        """Expose the fully indexed version, then retire older chunks for its dataset."""

        current_query = {
            "term": {"dataset_id": dataset_id},
        }
        target_query = {
            "bool": {
                "filter": [
                    current_query,
                    {"term": {"dataset_version_id": dataset_version_id}},
                    {"term": {"version_status": "ready"}},
                ]
            }
        }
        self._update_by_query(target_query, "ctx._source.is_current = true")

        previous_query = {
            "bool": {
                "filter": [current_query],
                "must_not": [{"term": {"dataset_version_id": dataset_version_id}}],
            }
        }
        self._update_by_query(previous_query, "ctx._source.is_current = false")

    def delete_version(self, dataset_id: str, dataset_version_id: str) -> int:
        """Delete only a failed version's own chunks; never delete a whole dataset."""

        exists = self._request("HEAD", f"/{self.settings.chunks_index}", allow_statuses={404})
        if exists.status_code == 404:
            return 0

        response = self._json_request(
            "POST",
            f"/{self.settings.chunks_index}/_delete_by_query",
            params={"conflicts": "proceed", "refresh": "true"},
            json_body={
                "query": {
                    "bool": {
                        "filter": [
                            {"term": {"dataset_id": dataset_id}},
                            {"term": {"dataset_version_id": dataset_version_id}},
                        ]
                    }
                }
            },
        )
        return int(response.get("deleted", 0))

    def search_chunks(self, request: SearchRequest) -> list[dict[str, Any]]:
        """Run a fixed BM25 query over canonical, visible chunks only."""

        filters: list[dict[str, Any]] = [{"term": {"version_status": "ready"}}]
        if not request.include_historical:
            filters.append({"term": {"is_current": True}})
        if request.dataset_id:
            filters.append({"term": {"dataset_id": request.dataset_id}})
        if request.dataset_version_id:
            filters.append({"term": {"dataset_version_id": request.dataset_version_id}})
        if request.workspace_id:
            filters.append(
                {
                    "bool": {
                        "should": [
                            {"term": {"visibility": "global"}},
                            {
                                "bool": {
                                    "filter": [
                                        {"term": {"visibility": "workspace"}},
                                        {"term": {"workspace_id": request.workspace_id}},
                                    ]
                                }
                            },
                        ],
                        "minimum_should_match": 1,
                    }
                }
            )
        else:
            filters.append({"term": {"visibility": "global"}})

        response = self._json_request(
            "POST",
            f"/{self.settings.chunks_index}/_search",
            json_body={
                "size": request.top_k,
                "track_total_hits": False,
                "_source": [
                    "chunk_id",
                    "content",
                    "title",
                    "source_url",
                    "source_document_id",
                    "source_task_id",
                    "dataset_id",
                    "dataset_version_id",
                    "workflow_id",
                    "job_id",
                    "chunk_index",
                ],
                "query": {
                    "bool": {
                        "must": [
                            {
                                "multi_match": {
                                    "query": request.query.strip(),
                                    "fields": ["content^3", "title"],
                                    "type": "best_fields",
                                    "operator": "or",
                                }
                            }
                        ],
                        "filter": filters,
                    }
                },
            },
        )
        hits = response.get("hits", {}).get("hits", [])
        if not isinstance(hits, list):
            raise ElasticsearchRequestError("Elasticsearch returned an invalid RAG search response")
        return [hit for hit in hits if isinstance(hit, dict) and isinstance(hit.get("_source"), dict)]

    def _update_by_query(self, query: dict[str, Any], source: str) -> None:
        self._json_request(
            "POST",
            f"/{self.settings.chunks_index}/_update_by_query",
            params={"conflicts": "proceed", "refresh": "true"},
            json_body={"query": query, "script": {"lang": "painless", "source": source}},
        )

    def _json_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        data: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        response = self._request(method, path, params=params, json_body=json_body, data=data, headers=headers)
        try:
            parsed = response.json()
        except ValueError as exc:
            raise ElasticsearchRequestError(f"Elasticsearch returned invalid JSON for {method} {path}") from exc
        if not isinstance(parsed, dict):
            raise ElasticsearchRequestError(f"Elasticsearch returned an unexpected response for {method} {path}")
        return parsed

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        data: str | None = None,
        headers: dict[str, str] | None = None,
        allow_statuses: set[int] | None = None,
    ) -> requests.Response:
        url = f"{self.settings.es_url}/{path.lstrip('/')}"
        try:
            response = requests.request(
                method,
                url,
                params=params,
                json=json_body,
                data=data,
                headers=headers,
                auth=self.auth,
                timeout=self.settings.request_timeout_seconds,
                verify=self.settings.verify_tls,
            )
        except requests.RequestException as exc:
            raise ElasticsearchRequestError(f"Elasticsearch request failed: {type(exc).__name__}") from exc

        allowed = allow_statuses or set()
        if response.status_code >= 400 and response.status_code not in allowed:
            logger.warning("Elasticsearch request failed: method=%s path=%s status=%s", method, path, response.status_code)
            raise ElasticsearchRequestError(f"Elasticsearch request failed with HTTP {response.status_code}")
        return response


class OpenAICompatibleEmbeddingClient:
    """Optional embedding client with no assumed model dimension."""

    def __init__(self, settings: MultiDataProcessRagSettings) -> None:
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(self.settings.embedding_base_url)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.configured:
            raise RagConfigurationError("embedding endpoint is not configured")
        endpoint = f"{str(self.settings.embedding_base_url).rstrip('/')}/embeddings"
        headers = {"Content-Type": "application/json"}
        if self.settings.embedding_api_key:
            headers["Authorization"] = f"Bearer {self.settings.embedding_api_key}"

        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.settings.embedding_batch_size):
            batch = texts[start : start + self.settings.embedding_batch_size]
            try:
                response = requests.post(
                    endpoint,
                    headers=headers,
                    json={"model": self.settings.embedding_model, "input": batch},
                    timeout=self.settings.request_timeout_seconds,
                    verify=self.settings.verify_tls,
                )
                response.raise_for_status()
                payload = response.json()
            except (requests.RequestException, ValueError) as exc:
                raise ElasticsearchRequestError(f"embedding request failed: {type(exc).__name__}") from exc

            items = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(items, list) or len(items) != len(batch):
                raise ElasticsearchRequestError("embedding endpoint returned an unexpected item count")
            try:
                ordered = sorted(items, key=lambda item: int(item["index"]))
                batch_vectors = [item["embedding"] for item in ordered]
            except (KeyError, TypeError, ValueError) as exc:
                raise ElasticsearchRequestError("embedding endpoint returned an invalid response") from exc
            if any(not isinstance(vector, list) or not vector for vector in batch_vectors):
                raise ElasticsearchRequestError("embedding endpoint returned an empty vector")
            vectors.extend([[float(value) for value in vector] for vector in batch_vectors])

        dimensions = {len(vector) for vector in vectors}
        if len(dimensions) != 1:
            raise ElasticsearchRequestError("embedding endpoint returned inconsistent vector dimensions")
        return vectors


class MultiDataProcessRagSyncService:
    """Synchronize one completed main-index version into deterministic chunks."""

    def __init__(
        self,
        settings: MultiDataProcessRagSettings,
        *,
        es_client: ElasticsearchHttpClient | None = None,
        embedding_client: OpenAICompatibleEmbeddingClient | None = None,
    ) -> None:
        self.settings = settings
        self.es = es_client or ElasticsearchHttpClient(settings)
        self.embedding_client = embedding_client or OpenAICompatibleEmbeddingClient(settings)

    def sync_version(self, request: SyncRequest) -> SyncResult:
        request.validate()

        source_hits = list(self.es.iter_source_documents(request.dataset_version_id))
        source_hits = [
            hit
            for hit in source_hits
            if _matches_dataset(hit.get("_source", {}), request.dataset_id)
            and _is_canonical_ready_source(hit.get("_source", {}))
        ]
        if not source_hits:
            raise SourceVersionNotFound(
                f"no source documents found for dataset {request.dataset_id} version {request.dataset_version_id}"
            )

        chunks, indexable_documents = build_chunk_documents(source_hits, request, self.settings.source_index)
        if not chunks:
            raise NoIndexableContent("the source version contains no indexable processed text")

        warnings: list[str] = []
        embedding_status = "not_configured"
        embedding_dimensions: int | None = None
        if self.embedding_client.configured:
            try:
                vectors = self.embedding_client.embed([str(chunk["content"]) for chunk in chunks])
                if len(vectors) != len(chunks):
                    raise ElasticsearchRequestError("embedding endpoint did not return one vector per chunk")
                embedding_dimensions = len(vectors[0]) if vectors else None
                for chunk, vector in zip(chunks, vectors, strict=True):
                    chunk["content_vector"] = vector
                    chunk["embedding_status"] = "ready"
                embedding_status = "ready"
            except MultiDataProcessRagError as exc:
                logger.warning("RAG chunk sync will continue with BM25 only: %s", exc)
                warnings.append("embedding unavailable; synchronized BM25-only chunks and can be retried later")
                for chunk in chunks:
                    chunk["embedding_status"] = "degraded"
                embedding_status = "degraded"
        else:
            for chunk in chunks:
                chunk["embedding_status"] = "not_configured"

        self.es.ensure_chunks_index(embedding_dimensions)
        # A replay normally writes the same deterministic IDs.  Deleting only this
        # exact version first also removes stale chunks if its source payload changed
        # before the retry; it can never affect another dataset/version.
        self.es.delete_version(request.dataset_id, request.dataset_version_id)
        self.es.bulk_index(chunks)
        if request.activate_current:
            self.es.activate_version(request.dataset_id, request.dataset_version_id)

        return SyncResult(
            dataset_id=request.dataset_id,
            dataset_version_id=request.dataset_version_id,
            source_documents=len(source_hits),
            indexable_documents=indexable_documents,
            chunks_indexed=len(chunks),
            chunks_index=self.settings.chunks_index,
            activated_current=request.activate_current,
            embedding_status=embedding_status,
            embedding_dimensions=embedding_dimensions,
            warnings=warnings,
        )


    def cleanup_failed_version(self, dataset_id: str, dataset_version_id: str) -> int:
        """Idempotently remove only a failed version's already-materialised chunks."""

        _validate_identifier(dataset_id, "dataset_id")
        _validate_identifier(dataset_version_id, "dataset_version_id")
        return self.es.delete_version(dataset_id, dataset_version_id)


class MultiDataProcessRagSearchService:
    """Expose safe lexical evidence without giving callers arbitrary ES access."""

    def __init__(
        self,
        settings: MultiDataProcessRagSettings,
        *,
        es_client: ElasticsearchHttpClient | None = None,
    ) -> None:
        self.es = es_client or ElasticsearchHttpClient(settings)

    def search(self, request: SearchRequest) -> SearchResult:
        request.validate()
        hits = self.es.search_chunks(request)
        results = [_to_search_evidence(hit, rank) for rank, hit in enumerate(hits, start=1)]
        return SearchResult(query=request.query.strip(), retrieval_mode="bm25", results=results)


def build_chunk_documents(
    source_hits: list[dict[str, Any]],
    request: SyncRequest,
    source_index: str,
) -> tuple[list[dict[str, Any]], int]:
    """Build deterministic, provenance-rich chunk documents from source hits."""

    now = datetime.now(UTC).isoformat()
    chunks: list[dict[str, Any]] = []
    indexable_documents = 0
    for hit in source_hits:
        source = hit.get("_source")
        if not isinstance(source, dict) or not _matches_dataset(source, request.dataset_id):
            continue
        text = extract_indexable_text(source)
        if not text:
            continue
        indexable_documents += 1
        source_doc_id = str(source.get("document_id") or hit.get("_id") or "unknown")
        for chunk_index, content in enumerate(chunk_text(text, request.chunk_size, request.chunk_overlap)):
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            chunk_id = deterministic_chunk_id(
                request.dataset_id,
                request.dataset_version_id,
                source_doc_id,
                chunk_index,
                content_hash,
            )
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "document_id": source_doc_id,
                    "source_document_id": source_doc_id,
                    "source_index": source_index,
                    "chunk_index": chunk_index,
                    "content": content,
                    "content_hash": content_hash,
                    "title": _source_title(source),
                    "source_url": _source_value(source, "source_url"),
                    "source_task_id": _source_value(source, "source_task_id"),
                    "source_record_id": _source_value(source, "source_record_id"),
                    "workflow_id": _source_value(source, "workflow_id") or request.workflow_id,
                    "job_id": _source_value(source, "job_id") or request.job_id,
                    "dataset_id": request.dataset_id,
                    "dataset_version_id": request.dataset_version_id,
                    "output_format": _source_value(source, "output_format") or _source_value(source, "format"),
                    "version_status": "ready",
                    "visibility": request.visibility,
                    "workspace_id": request.workspace_id,
                    "is_current": False,
                    "embedding_status": "pending",
                    "source_created_at": _source_value(source, "created_at"),
                    "synced_at": now,
                    "metadata": _source_metadata(source),
                }
            )
    return chunks, indexable_documents


def extract_indexable_text(source: dict[str, Any]) -> str:
    """Extract the processed textual payload without indexing arbitrary metadata."""

    collected: list[str] = []
    for key in _TEXT_KEYS:
        if key in source:
            _collect_text(source[key], collected)
    if not collected and "processed_data" in source:
        _collect_text(source["processed_data"], collected)
    if not collected and "raw_data" in source:
        _collect_text(source["raw_data"], collected)

    unique: list[str] = []
    seen: set[str] = set()
    for item in collected:
        normalized = _normalize_text(item)
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique.append(normalized)
    return "\n\n".join(unique)


def chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Split text on a nearby natural boundary while guaranteeing forward progress."""

    normalized = _normalize_text(text)
    if not normalized:
        return []
    if len(normalized) <= chunk_size:
        return [normalized]

    chunks: list[str] = []
    start = 0
    text_length = len(normalized)
    while start < text_length:
        target_end = min(start + chunk_size, text_length)
        end = target_end
        if target_end < text_length:
            minimum_boundary = start + max(chunk_size // 2, 80)
            candidates = [
                normalized.rfind(marker, minimum_boundary, target_end)
                for marker in ("。", "！", "？", "\n", ". ", "; ")
            ]
            boundary = max(candidates)
            if boundary >= minimum_boundary:
                end = boundary + 1
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= text_length:
            break
        start = max(end - chunk_overlap, start + 1)
    return chunks


def deterministic_chunk_id(
    dataset_id: str,
    dataset_version_id: str,
    source_document_id: str,
    chunk_index: int,
    content_hash: str,
) -> str:
    material = "\x1f".join(
        (dataset_id, dataset_version_id, source_document_id, str(chunk_index), content_hash)
    )
    return f"mdp-rag-{hashlib.sha256(material.encode('utf-8')).hexdigest()}"


def _chunks_mapping(embedding_dimensions: int | None) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "chunk_id": {"type": "keyword"},
        "document_id": {"type": "keyword"},
        "source_document_id": {"type": "keyword"},
        "source_index": {"type": "keyword"},
        "chunk_index": {"type": "integer"},
        "content": {"type": "text"},
        "content_hash": {"type": "keyword"},
        "title": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
        "source_url": {"type": "keyword", "ignore_above": 2048},
        "source_task_id": {"type": "keyword"},
        "source_record_id": {"type": "keyword"},
        "workflow_id": {"type": "keyword"},
        "job_id": {"type": "keyword"},
        "dataset_id": {"type": "keyword"},
        "dataset_version_id": {"type": "keyword"},
        "output_format": {"type": "keyword"},
        "version_status": {"type": "keyword"},
        "visibility": {"type": "keyword"},
        "workspace_id": {"type": "keyword"},
        "is_current": {"type": "boolean"},
        "embedding_status": {"type": "keyword"},
        "source_created_at": {"type": "keyword"},
        "synced_at": {"type": "date"},
        "metadata": {"type": "flattened"},
    }
    if embedding_dimensions is not None:
        properties["content_vector"] = _vector_mapping(embedding_dimensions)
    return {
        "mappings": {
            "dynamic": False,
            "_meta": {"managed_by": "deerflow-multi-data-process-rag", "schema_version": 1},
            "properties": properties,
        }
    }


def _vector_mapping(dimensions: int) -> dict[str, Any]:
    if dimensions <= 0:
        raise ElasticsearchRequestError("embedding dimensions must be positive")
    return {"type": "dense_vector", "dims": dimensions, "index": True, "similarity": "cosine"}


def _collect_text(value: Any, collected: list[str], depth: int = 0) -> None:
    if depth > 6 or value is None:
        return
    if isinstance(value, str):
        text = value.strip()
        if text[:1] in {"{", "["}:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                collected.append(text)
            else:
                _collect_text(parsed, collected, depth + 1)
        else:
            collected.append(text)
        return
    if isinstance(value, list):
        for item in value:
            _collect_text(item, collected, depth + 1)
        return
    if isinstance(value, dict):
        found_priority = False
        for key in _TEXT_KEYS:
            if key in value:
                found_priority = True
                _collect_text(value[key], collected, depth + 1)
        if found_priority:
            return
        for key, child in value.items():
            if str(key).lower() not in _SKIP_TEXT_KEYS:
                _collect_text(child, collected, depth + 1)


def _source_metadata(source: dict[str, Any]) -> dict[str, Any]:
    raw_metadata = source.get("metadata")
    if isinstance(raw_metadata, str):
        try:
            raw_metadata = json.loads(raw_metadata)
        except json.JSONDecodeError:
            raw_metadata = {}

    metadata: dict[str, Any] = {}
    if isinstance(raw_metadata, dict):
        for key, value in raw_metadata.items():
            if str(key).lower() not in _SKIP_TEXT_KEYS:
                metadata[str(key)] = _metadata_value(value)
    for key in _SCALAR_METADATA_KEYS:
        value = source.get(key)
        if value is not None:
            metadata[key] = _metadata_value(value)
    return metadata


def _metadata_value(value: Any) -> Any:
    """Keep compact scalar/list metadata suitable for an ES flattened field."""

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_metadata_value(item) for item in value[:50]]
    if isinstance(value, dict):
        return {str(key): _metadata_value(item) for key, item in list(value.items())[:50]}
    return str(value)


def _source_value(source: dict[str, Any], key: str) -> str | None:
    """Read MDP provenance from canonical or compatibility field names."""

    aliases = (key, f"__mdp_{key}", f"mdp_{key}")
    for alias in aliases:
        value = source.get(alias)
        if value is not None and str(value).strip():
            return str(value).strip()

    raw_metadata = source.get("metadata")
    if isinstance(raw_metadata, str):
        try:
            raw_metadata = json.loads(raw_metadata)
        except json.JSONDecodeError:
            raw_metadata = None
    if isinstance(raw_metadata, dict):
        for alias in aliases:
            value = raw_metadata.get(alias)
            if value is not None and str(value).strip():
                return str(value).strip()
    return None


def _source_title(source: dict[str, Any]) -> str:
    return (
        _source_value(source, "source_title")
        or _source_value(source, "title")
        or _source_value(source, "filename")
        or "Multi Data Process document"
    )


def _to_search_evidence(hit: dict[str, Any], rank: int) -> dict[str, Any]:
    """Return only presentation-safe, provenance-rich fields for a chat citation."""

    source = hit.get("_source", {})
    content = str(source.get("content") or "").strip()
    title = str(source.get("title") or "Multi Data Process document").strip()
    dataset_id = str(source.get("dataset_id") or "").strip()
    dataset_version_id = str(source.get("dataset_version_id") or "").strip()
    source_url = str(source.get("source_url") or "").strip() or None
    citation_parts = [f"数据集 {dataset_id}", f"版本 {dataset_version_id}", title]
    if source_url:
        citation_parts.append(source_url)
    return {
        "rank": rank,
        "score": hit.get("_score"),
        "chunk_id": str(source.get("chunk_id") or hit.get("_id") or ""),
        "chunk_index": source.get("chunk_index"),
        "content": content[:5000],
        "title": title,
        "source_url": source_url,
        "source_document_id": source.get("source_document_id"),
        "source_task_id": source.get("source_task_id"),
        "dataset_id": dataset_id,
        "dataset_version_id": dataset_version_id,
        "workflow_id": source.get("workflow_id"),
        "job_id": source.get("job_id"),
        "citation": " | ".join(citation_parts),
    }


def _matches_dataset(source: dict[str, Any], dataset_id: str) -> bool:
    return _source_value(source, "dataset_id") == dataset_id


def _is_canonical_ready_source(source: dict[str, Any]) -> bool:
    """Accept only the ready/current documents that MDP promoted before callback."""

    status = _source_value(source, "status") or _source_value(source, "version_status")
    current = _source_value(source, "is_current") or _source_value(source, "current")
    return status == "ready" and str(current).lower() in {"true", "1"}


def _normalize_text(value: str) -> str:
    return re.sub(r"[ \t]+", " ", re.sub(r"\r\n?", "\n", value)).strip()


def _validate_index_name(value: str, label: str) -> None:
    if not value or not _INDEX_NAME_RE.fullmatch(value):
        raise RagConfigurationError(f"invalid {label} index name")
    if value.startswith((".", "_", "-")):
        raise RagConfigurationError(f"invalid {label} index name")


def _validate_identifier(value: str, label: str) -> None:
    normalized = value.strip()
    if not normalized or len(normalized) > 256:
        raise MultiDataProcessRagError(f"{label} must be a non-empty value of at most 256 characters")


def _read_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RagConfigurationError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise RagConfigurationError(f"{name} must be between {minimum} and {maximum}")
    return value


def _read_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RagConfigurationError(f"{name} must be a boolean")
