from __future__ import annotations

import re
from urllib.parse import urlsplit


NUMERIC_TOKEN_RE = re.compile(r"\d+")
OPTIONAL_PAGE_SUFFIX_RE = re.compile(r"([/_-])\d+(?=(?:\.html?|/)?$)")


def _normalize_optional_page_suffix(value: str) -> str:
    return OPTIONAL_PAGE_SUFFIX_RE.sub("", value)


def build_url_structure_key(url: str) -> str:
    parsed = urlsplit(url or "")
    comparable = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    if parsed.query:
        comparable = f"{comparable}?{parsed.query}"
    comparable = _normalize_optional_page_suffix(comparable)
    return NUMERIC_TOKEN_RE.sub("{num}", comparable)


def are_urls_same_structure(left_url: str, right_url: str) -> bool:
    if not left_url or not right_url:
        return False

    if left_url == right_url:
        return True

    left = urlsplit(left_url)
    right = urlsplit(right_url)
    if left.scheme != right.scheme or left.netloc != right.netloc:
        return False

    left_comparable = left.path + (f"?{left.query}" if left.query else "")
    right_comparable = right.path + (f"?{right.query}" if right.query else "")

    if _normalize_optional_page_suffix(left_comparable) == _normalize_optional_page_suffix(right_comparable):
        return True

    left_parts = re.split(r"(\d+)", left_comparable)
    right_parts = re.split(r"(\d+)", right_comparable)
    if len(left_parts) != len(right_parts):
        return False

    differing_numeric_groups = 0
    for left_part, right_part in zip(left_parts, right_parts):
        if left_part == right_part:
            continue
        if left_part.isdigit() and right_part.isdigit():
            differing_numeric_groups += 1
            continue
        return False

    return differing_numeric_groups == 1
