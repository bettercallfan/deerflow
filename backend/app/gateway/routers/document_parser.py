import os
from typing import Optional

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response, JSONResponse


DOCUMENT_PARSE_BACKEND_URL = os.getenv(
    "DOCUMENT_PARSE_BACKEND_URL",
    "http://document-parser-backend:8010",
).rstrip("/")


router = APIRouter(
    prefix="/api/data-center/document-parser",
    tags=["data-center-document-parser"],
)


def _proxy_response(resp: httpx.Response) -> Response:
    content_type = resp.headers.get("content-type", "application/json")

    headers = {}
    content_disposition = resp.headers.get("content-disposition")
    if content_disposition:
        headers["content-disposition"] = content_disposition

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=content_type,
        headers=headers,
    )

def _rewrite_document_parser_urls(payload: dict) -> dict:
    """
    Rewrite document-parser-backend internal URLs to Gateway URLs.
    """
    job_id = payload.get("jobId")

    if job_id:
        payload["markdownDownloadUrl"] = (
            f"/api/data-center/document-parser/download-md/{job_id}"
        )

    processed_image_url = payload.get("processedImageUrl")
    if isinstance(processed_image_url, str) and processed_image_url.startswith(
        "/api/result-file/"
    ):
        payload["processedImageUrl"] = processed_image_url.replace(
            "/api/result-file/",
            "/api/data-center/document-parser/result-file/",
            1,
        )

    return payload

@router.get("/health")
async def health():
    """
    Check document parser backend health.
    Gateway path:
      GET /api/data-center/document-parser/health

    Backend path:
      GET /api/health
    """
    try:
        async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
            resp = await client.get(f"{DOCUMENT_PARSE_BACKEND_URL}/api/health")
        return _proxy_response(resp)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Document parser backend unavailable: {exc}",
        )


@router.post("/parse")
async def parse_document(
    file: UploadFile = File(...),
    preprocess: bool = Form(False),
):
    """
    Parse image or PDF document.

    Gateway path:
      POST /api/data-center/document-parser/parse

    Backend path:
      POST /api/parse
    """
    try:
        file_bytes = await file.read()

        files = {
            "file": (
                file.filename,
                file_bytes,
                file.content_type or "application/octet-stream",
            )
        }

        data = {
            "preprocess": "true" if preprocess else "false",
        }

        timeout = httpx.Timeout(
            connect=30.0,
            read=1800.0,
            write=1800.0,
            pool=30.0,
        )

        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            resp = await client.post(
                f"{DOCUMENT_PARSE_BACKEND_URL}/api/parse",
                files=files,
                data=data,
            )

        if resp.status_code >= 400:
            return _proxy_response(resp)

        try:
            payload = resp.json()
        except Exception:
            return _proxy_response(resp)

        if isinstance(payload, dict):
            payload = _rewrite_document_parser_urls(payload)

        return JSONResponse(
            content=payload,
            status_code=resp.status_code,
        )

        return _proxy_response(resp)

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Document parser backend request failed: {exc}",
        )


@router.get("/download-md/{job_id}")
async def download_markdown(job_id: str):
    """
    Download generated markdown file.

    Gateway path:
      GET /api/data-center/document-parser/download-md/{job_id}

    Backend path:
      GET /api/download-md/{job_id}
    """
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(
                f"{DOCUMENT_PARSE_BACKEND_URL}/api/download-md/{job_id}"
            )
        return _proxy_response(resp)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Document parser backend request failed: {exc}",
        )


@router.get("/result-file/{job_id}/{section}/{filename:path}")
async def get_result_file(
    job_id: str,
    section: str,
    filename: str,
):
    """
    Proxy result files, such as processed image or markdown assets.

    Gateway path:
      GET /api/data-center/document-parser/result-file/{job_id}/{section}/{filename}

    Backend path:
      GET /api/result-file/{job_id}/{section}/{filename}
    """
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(
                f"{DOCUMENT_PARSE_BACKEND_URL}/api/result-file/"
                f"{job_id}/{section}/{filename}"
            )
        return _proxy_response(resp)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Document parser backend request failed: {exc}",
        )