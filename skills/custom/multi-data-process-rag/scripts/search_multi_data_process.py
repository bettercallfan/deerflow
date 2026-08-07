#!/usr/bin/env python3
"""Search materialised Multi Data Process chunks through the controlled Gateway."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search current Multi Data Process RAG evidence.")
    parser.add_argument("--query", required=True, help="User question or keywords")
    parser.add_argument("--top-k", type=int, default=5, choices=range(1, 21), metavar="1-20")
    parser.add_argument("--dataset-id", help="Optional logical dataset ID")
    parser.add_argument("--dataset-version-id", help="Optional version ID")
    parser.add_argument("--workspace-id", help="Optional workspace visibility scope")
    parser.add_argument("--include-historical", action="store_true", help="Include non-current successful versions")
    parser.add_argument("--timeout", type=int, default=20, choices=range(1, 121), metavar="1-120")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    return parser.parse_args()


def gateway_configuration() -> tuple[str, str]:
    gateway_url = os.getenv("MULTI_DATA_PROCESS_RAG_GATEWAY_URL", "").strip().rstrip("/")
    token = os.getenv("MULTI_DATA_PROCESS_RAG_SEARCH_TOKEN", "").strip()
    if not gateway_url:
        raise RuntimeError("MULTI_DATA_PROCESS_RAG_GATEWAY_URL is not configured in this sandbox")
    if not token:
        raise RuntimeError("MULTI_DATA_PROCESS_RAG_SEARCH_TOKEN is not configured in this sandbox")
    return gateway_url, token


def search(args: argparse.Namespace) -> dict[str, Any]:
    gateway_url, token = gateway_configuration()
    payload = {
        "query": args.query,
        "top_k": args.top_k,
        "dataset_id": args.dataset_id,
        "dataset_version_id": args.dataset_version_id,
        "workspace_id": args.workspace_id,
        "include_historical": args.include_historical,
    }
    request = Request(
        f"{gateway_url}/api/multi-data-process-rag/search",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=args.timeout) as response:  # noqa: S310 -- configured internal Gateway
            decoded = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"Gateway search failed with HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Gateway search is unreachable: {exc.reason}") from exc

    result = json.loads(decoded)
    if not isinstance(result, dict):
        raise RuntimeError("Gateway search returned an invalid JSON response")
    return result


def main() -> None:
    args = parse_args()
    try:
        result = search(args)
        print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
