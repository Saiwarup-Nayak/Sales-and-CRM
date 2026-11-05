"""Download the source datasets from GitHub and cache them locally.

Files are fetched from raw.githubusercontent.com URLs into ``data/raw``. A
manifest records the source URL, download time, size and SHA-256 of each file
so a run can be traced back to the exact bytes it used. Subsequent runs read
the cache unless ``refresh=True`` is passed.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from src import config


class DataLoadError(RuntimeError):
    """Raised when a source file cannot be downloaded and no cached copy exists."""


@dataclass
class FetchResult:
    name: str
    path: Path
    url: str
    from_cache: bool
    warning: str | None = None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_manifest() -> dict:
    if config.MANIFEST_PATH.exists():
        try:
            return json.loads(config.MANIFEST_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _write_manifest(manifest: dict) -> None:
    config.MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def fetch_file(name: str, url: str, dest: Path, refresh: bool = False,
               session: requests.Session | None = None) -> FetchResult:
    """Download ``url`` to ``dest`` unless a cached copy exists and refresh is False.

    On a network/HTTP failure the cached copy is used if available (with a
    warning); otherwise a ``DataLoadError`` with an actionable message is raised.
    """
    if dest.exists() and not refresh:
        return FetchResult(name, dest, url, from_cache=True)

    http = session or requests
    try:
        resp = http.get(url, timeout=config.REQUEST_TIMEOUT_S)
        resp.raise_for_status()
        if not resp.content.strip():
            raise DataLoadError(f"Downloaded file '{name}' from {url} is empty.")
    except (requests.RequestException, DataLoadError) as exc:
        if dest.exists():
            return FetchResult(name, dest, url, from_cache=True,
                               warning=f"Could not refresh '{name}' ({exc}); using cached copy.")
        raise DataLoadError(
            f"Could not download '{name}' from {url}: {exc}. "
            "Check your internet connection or whether the GitHub repository/file "
            "still exists, then use 'Refresh data' to retry."
        ) from exc

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(resp.content)
    tmp.replace(dest)

    manifest = _read_manifest()
    manifest[name] = {
        "url": url,
        "file": dest.name,
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bytes": dest.stat().st_size,
        "sha256": _sha256(dest),
    }
    _write_manifest(manifest)
    return FetchResult(name, dest, url, from_cache=False)


def download_crm_data(refresh: bool = False) -> list[FetchResult]:
    """Fetch all CRM Sales Opportunities files into ``data/raw/crm``."""
    with requests.Session() as s:
        return [
            fetch_file(f"crm/{key}", f"{config.CRM_RAW_BASE}/{fname}",
                       config.RAW_DIR / "crm" / fname, refresh=refresh, session=s)
            for key, fname in config.CRM_FILES.items()
        ]


def download_leadforge_data(refresh: bool = False) -> list[FetchResult]:
    """Fetch the LeadForge lead-scoring bundle files into ``data/raw/leadforge``."""
    with requests.Session() as s:
        return [
            fetch_file(f"leadforge/{key}", f"{config.LEADFORGE_RAW_BASE}/{fname}",
                       config.RAW_DIR / "leadforge" / fname, refresh=refresh, session=s)
            for key, fname in config.LEADFORGE_FILES.items()
        ]


def load_crm_raw(refresh: bool = False) -> tuple[dict[str, pd.DataFrame], list[FetchResult]]:
    """Return the raw CRM tables (unmodified) keyed by table name."""
    results = download_crm_data(refresh=refresh)
    tables: dict[str, pd.DataFrame] = {}
    for key, fname in config.CRM_FILES.items():
        path = config.RAW_DIR / "crm" / fname
        try:
            tables[key] = pd.read_csv(path)
        except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as exc:
            raise DataLoadError(f"File '{fname}' could not be parsed as CSV: {exc}") from exc
    return tables, results


def load_leadforge_raw(refresh: bool = False) -> tuple[dict[str, pd.DataFrame], list[FetchResult]]:
    """Return the raw LeadForge flat lead table and its feature dictionary."""
    results = download_leadforge_data(refresh=refresh)
    tables = {}
    for key, fname in config.LEADFORGE_FILES.items():
        path = config.RAW_DIR / "leadforge" / fname
        try:
            tables[key] = pd.read_csv(path)
        except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as exc:
            raise DataLoadError(f"File '{fname}' could not be parsed as CSV: {exc}") from exc
    return tables, results


def manifest() -> dict:
    """Return provenance information for every cached file."""
    return _read_manifest()
