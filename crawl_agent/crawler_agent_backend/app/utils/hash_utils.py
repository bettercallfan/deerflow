from __future__ import annotations

import hashlib
import re
from bs4 import BeautifulSoup


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def build_raw_html_hash(url: str, html: str) -> str:
    return sha256_text(f"{url}\n{html}")


def normalize_html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator=" ")
    text = re.sub(r"https?://[^\s]*utm_[^\s]*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d{10,13}\b", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def build_normalized_content_hash(html: str) -> str:
    return sha256_text(normalize_html_to_text(html))


def build_site_quick_hash(
    portal_url: str,
    text_snapshot: str,
    etag: str | None = None,
    last_modified: str | None = None,
    strategy: str = "content_only",
) -> str:
    normalized = re.sub(r"\s+", " ", text_snapshot or "").strip()
    if strategy == "etag+content":
        payload = f"{portal_url}\n{etag or ''}\n{last_modified or ''}\n{normalized}"
    else:
        payload = f"{portal_url}\n{normalized}"
    return sha256_text(payload)
