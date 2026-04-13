"""Metadata tool — inspect local files and remote URLs without loading data."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import httpx

_FORMAT_MAP: dict[str, str] = {
    "csv": "csv",
    "tsv": "csv",
    "txt": "csv",
    "parquet": "parquet",
    "pq": "parquet",
    "json": "json",
    "jsonl": "json",
    "ndjson": "json",
}


async def get_file_metadata(file_path: str) -> dict:
    """Return format, size, and name for a local file."""
    path = Path(file_path)
    size_bytes = path.stat().st_size
    suffix = path.suffix.lower().lstrip(".")
    return {
        "format": _FORMAT_MAP.get(suffix, "csv"),
        "size_mb": round(size_bytes / (1024 * 1024), 3),
        "name": path.name,
    }


async def get_url_metadata(url: str) -> dict:
    """Return format, approximate size, and name for a remote URL."""
    parsed = urlparse(url)
    path_part = parsed.path.split("?")[0]
    suffix = Path(path_part).suffix.lower().lstrip(".")
    name = Path(path_part).name or "dataset"

    size_mb = 0.0
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.head(url)
            content_length = int(r.headers.get("content-length", 0))
            size_mb = round(content_length / (1024 * 1024), 3)
            # Try to detect format from Content-Type header
            ct = r.headers.get("content-type", "")
            if not suffix:
                if "parquet" in ct:
                    suffix = "parquet"
                elif "json" in ct:
                    suffix = "json"
    except Exception:
        pass

    return {
        "format": _FORMAT_MAP.get(suffix, "csv"),
        "size_mb": size_mb,
        "name": name,
    }
