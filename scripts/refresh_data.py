#!/usr/bin/env python3
"""Fetch & cache the pinned current-league game data.

By default pulls the eager (small/central) set — fast. Pass ``--all`` to also
pull the big item/mod/gem files, or names to pull specific files.

    python scripts/refresh_data.py                 # eager set
    python scripts/refresh_data.py --all           # everything (incl. 40MB gems)
    python scripts/refresh_data.py tree uniques    # just these
    python scripts/refresh_data.py --force         # re-download even if cached
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mirrorsmith.data import fetch, sources  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("names", nargs="*", help="specific data files (default: eager set)")
    ap.add_argument("--all", action="store_true", help="fetch every file in the manifest")
    ap.add_argument("--force", action="store_true", help="re-download even if cached")
    args = ap.parse_args()

    if args.all:
        names = list(sources.DATA_FILES)
    elif args.names:
        names = args.names
    else:
        names = list(sources.EAGER_FILES)

    print(f"mirrorsmith data refresh — pin {sources.REPOE_VERSION} @ {sources.REPOE_PIN[:10]}")
    print(f"cache: {fetch.cache_dir()}\n")

    for name in names:
        try:
            path = fetch.get(name, force=args.force)
            size = path.stat().st_size
            print(f"  ok   {name:<24} {size/1024:>10.1f} KiB  {path.name}")
        except Exception as exc:  # noqa: BLE001 — report and continue
            print(f"  FAIL {name:<24} {exc}")
    print("\ndone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
