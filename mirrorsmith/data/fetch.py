"""Cached downloader for pinned Layer-1 data.

Files are pulled from an immutable commit URL, so once cached they never go stale
under us — the cache is keyed by the pinned data version. Deleting the cache and
re-fetching always reproduces the same bytes for a given pin. Standard library
only, so this runs with zero install.
"""

from __future__ import annotations

import json
import shutil
import urllib.request
from pathlib import Path
from typing import Any

from . import sources

# Repo root = three levels up from this file (mirrorsmith/data/fetch.py).
_REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_ROOT = _REPO_ROOT / "data" / "cache"

_USER_AGENT = "mirrorsmith/0.0.1 (+https://github.com/bobbyroylee/mirrorsmith)"


def cache_dir() -> Path:
    """Version-scoped cache directory (e.g. .../data/cache/3.28.0.16/)."""
    return CACHE_ROOT / sources.REPOE_VERSION


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(req, timeout=120) as resp, tmp.open("wb") as fh:
        shutil.copyfileobj(resp, fh)
    tmp.replace(dest)  # atomic: a half-written file never looks complete


def get(name: str, *, force: bool = False) -> Path:
    """Return the local path to data file ``name``, downloading if not cached.

    ``name`` is a logical key from ``sources.DATA_FILES`` (e.g. "tree", "gems").
    """
    if name not in sources.DATA_FILES:
        raise KeyError(
            f"unknown data file {name!r}; known: {sorted(sources.DATA_FILES)}"
        )
    rel = sources.DATA_FILES[name]
    dest = cache_dir() / Path(rel).name
    if force or not dest.exists():
        _download(sources.repoe_url(rel), dest)
    return dest


def load_json(name: str, *, force: bool = False) -> Any:
    """Fetch (if needed) and parse a data file as JSON."""
    with get(name, force=force).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def refresh(names: list[str] | None = None, *, force: bool = False) -> list[Path]:
    """Download a set of data files. Defaults to the eager (small/central) set."""
    names = list(names) if names is not None else list(sources.EAGER_FILES)
    return [get(n, force=force) for n in names]
