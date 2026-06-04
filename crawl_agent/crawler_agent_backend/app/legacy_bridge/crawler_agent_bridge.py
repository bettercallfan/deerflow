from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
LEGACY_DIR = ROOT / "crawler_agent"
if str(LEGACY_DIR) not in sys.path:
    sys.path.insert(0, str(LEGACY_DIR))

from crawler_entrance import browse_page  # type: ignore


def _fallback_markdown_from_html(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    text = soup.get_text("\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n\n".join(lines)


def _fallback_json_extract(html: str, query: str) -> dict[str, Any]:
    soup = BeautifulSoup(html or "", "html.parser")
    text = " ".join(soup.get_text(" ").split())
    return {
        "query": query,
        "summary": text[:1200],
    }


async def collect_pages(
    query: str,
    portal_url: str,
    model_config: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    pages = await browse_page(query, portal_url, model_config=model_config)
    sanitized = []
    for page in pages:
        sanitized.append(
            {
                "url": page.get("url", ""),
                "title": page.get("title", ""),
                "html": page.get("html", ""),
            },
        )
    return sanitized


__all__ = ["collect_pages", "collect_pages_sync", "extract_html", "extract_markdown", "extract_json"]


def collect_pages_sync(
    query: str,
    portal_url: str,
    model_config: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    return asyncio.run(collect_pages(query=query, portal_url=portal_url, model_config=model_config))


def extract_html(url: str, html: str) -> dict[str, Any]:
    return {
        "result_type": "html",
        "result_html": html,
        "result_markdown": None,
        "result_markdown_ocr": None,
        "result_json": None,
    }


def extract_markdown(url: str, html: str) -> dict[str, Any]:
    try:
        from html_to_markdown.readerlm import convert_html_to_markdown_with_ocr

        result = convert_html_to_markdown_with_ocr(url=url, html=html)
        return {
            "result_type": "markdown",
            "result_markdown": result.get("markdown"),
            "result_markdown_ocr": result.get("markdown_with_ocr"),
            "result_json": None,
        }
    except Exception:
        fallback_md = _fallback_markdown_from_html(html)
        return {
            "result_type": "markdown",
            "result_markdown": fallback_md,
            "result_markdown_ocr": fallback_md,
            "result_json": None,
        }


def extract_json(
    url: str,
    html: str,
    query: str,
    model_config: dict[str, str] | None = None,
    json_schema: dict | list | None = None,
    position_paths: list[str] | None = None,
) -> dict[str, Any]:
    def _run_extraction(active_position_paths: list[str] | None = None) -> dict[str, Any]:
        from base.base import LLMClient
        from web_info_extract.recursive_acquisition import HTMLRecursiveExtractor

        runtime_cfg = model_config or {
            "api_key": os.environ.get("WCODE_API_KEY"),
            "model_name": os.environ.get("WCODE_MODEL_NAME", "qwen/qwen3.5-9b"),
            "base_url": os.environ.get("WCODE_BASE_URL", "https://wcode.net/api/gpt/v1"),
        }
        client = LLMClient(
            api_key=runtime_cfg.get("api_key"),
            model_name=runtime_cfg.get("model_name"),
            url=runtime_cfg.get("base_url"),
        )
        extractor = HTMLRecursiveExtractor(
            llm_client=client,
            urls=[url],
            htmls=[html],
            query=query,
            json_model=json_schema,
            cached_position_paths=[active_position_paths or []],
        )
        extracted = extractor.extract_from_html()
        data = extracted[0] if extracted else _fallback_json_extract(html, query)
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                data = {"text": data}
        return {
            "result_type": "json",
            "result_json": data,
            "result_markdown": None,
            "result_markdown_ocr": None,
            "position_paths": extractor.last_selected_paths_per_page[0] if extractor.last_selected_paths_per_page else [],
            "position_cache_used": (
                extractor.last_position_cache_used_per_page[0]
                if extractor.last_position_cache_used_per_page else False
            ),
        }

    try:
        return _run_extraction(position_paths)
    except Exception:
        if position_paths:
            try:
                return _run_extraction(None)
            except Exception:
                pass

        return {
            "result_type": "json",
            "result_json": _fallback_json_extract(html, query),
            "result_markdown": None,
            "result_markdown_ocr": None,
            "position_paths": [],
            "position_cache_used": False,
        }
