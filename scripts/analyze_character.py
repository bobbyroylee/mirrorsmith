#!/usr/bin/env python3
"""Analyze a character: aggregate the allocated tree into "what your build grants".

Import a character (needs POESESSID, like import_character.py) OR load a previously
saved raw import with --from. Prints categorized stat totals from the passive tree.

    python scripts/analyze_character.py "account#1234" "CharName"
    python scripts/analyze_character.py --from saved_import.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mirrorsmith.build import analyze  # noqa: E402
from mirrorsmith.character import summarize  # noqa: E402
from mirrorsmith.data import account  # noqa: E402
from mirrorsmith.data.stats import StatTranslator  # noqa: E402
from mirrorsmith.data.tree import PassiveTree  # noqa: E402


def _load_poesessid(explicit_file: str | None) -> str | None:
    if explicit_file:
        return Path(explicit_file).read_text(encoding="utf-8").strip()
    if os.environ.get("POESESSID"):
        return os.environ["POESESSID"].strip()
    default = Path.home() / ".mirrorsmith" / "poesessid"
    return default.read_text(encoding="utf-8").strip() if default.exists() else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("account", nargs="?", default="")
    ap.add_argument("character", nargs="?", default="")
    ap.add_argument("--realm", default="pc", choices=["pc", "xbox", "sony"])
    ap.add_argument("--poesessid-file", dest="poesessid_file", default=None)
    ap.add_argument("--from", dest="from_file", default=None,
                    help="load a saved raw import JSON instead of fetching")
    args = ap.parse_args()

    if args.from_file:
        imported = json.loads(Path(args.from_file).read_text(encoding="utf-8"))
    else:
        if not args.character:
            print("give account + character, or --from a saved import.")
            return 2
        sess = _load_poesessid(args.poesessid_file)
        if not sess:
            print("no POESESSID found (see import_character.py).")
            return 2
        try:
            imported = account.fetch_character(args.account, args.character, args.realm, sess)
        except account.AccountError as exc:
            print(f"import failed: {exc}")
            return 1

    tree = PassiveTree.load()
    translator = StatTranslator.load()
    b = summarize(imported, tree, translator)
    a = analyze(imported, tree, translator)

    print(f"{'=' * 62}")
    print(f"{b.character}  —  {b.char_class or '?'}  lvl {b.level or '?'}  [{b.league or '?'}]")
    print(f"passive tree grants ({a.points_counted} stat-bearing nodes, "
          f"{len(a.totals)} distinct stats):")
    print(f"{'=' * 62}")

    from mirrorsmith.build import _CATEGORIES

    for cat, _ in _CATEGORIES + [("Other", ())]:
        lines = a.rendered.get(cat, [])
        if not lines:
            continue
        print(f"\n{cat}")
        for line in lines:
            print(f"    {line}")

    if a.cluster_lines:
        print(f"\nCluster jewels grant")
        for line in a.cluster_lines:
            print(f"    {line}")

    print("\ndone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
