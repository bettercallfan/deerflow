from __future__ import annotations

import hashlib


def fake_embedding(text: str, dim: int = 1024) -> list[float]:
    """Deterministic lightweight embedding used for demo/runtime fallback."""
    if dim <= 0:
        return []
    digest = hashlib.sha256(text.encode("utf-8", errors="ignore")).digest()
    values = []
    for i in range(dim):
        b = digest[i % len(digest)]
        values.append((b / 255.0) * 2 - 1)
    return values


def chunk_text(text: str, chunk_size: int = 600, overlap: int = 120) -> list[str]:
    if not text:
        return []
    normalized = " ".join(text.split())
    if len(normalized) <= chunk_size:
        return [normalized]

    chunks = []
    start = 0
    while start < len(normalized):
        end = min(start + chunk_size, len(normalized))
        chunks.append(normalized[start:end])
        if end == len(normalized):
            break
        start = max(0, end - overlap)
    return chunks
