#!/usr/bin/env python3
"""End-to-end demo of the mirrorsmith data foundation.

Proves three live things at once:
  1. Layer 1 static: the current-league passive tree, parsed + human-rendered.
  2. Layer 2 economy: live currency prices from poe.ninja (dynamic league).
  3. Layer 2 builds: the build-corpus snapshot resolves (protobuf; parse deferred).

    python scripts/demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mirrorsmith.data import ninja, sources  # noqa: E402
from mirrorsmith.data.stats import StatTranslator  # noqa: E402
from mirrorsmith.data.tree import PassiveTree  # noqa: E402


def section(title: str) -> None:
    print(f"\n{'=' * 62}\n{title}\n{'=' * 62}")


def main() -> int:
    # 1) Static game data -----------------------------------------------------
    section(f"LAYER 1  passive tree  (pin {sources.REPOE_VERSION})")
    tree = PassiveTree.load()
    tr = StatTranslator.load()
    c = tree.counts()
    print(f"{c['total']} nodes / {tree.edge_count()} edges / "
          f"{c['keystone']} keystones / {c['notable']} notables / {c['mastery']} masteries")
    print("\nsample notables rendered to English:")
    shown = 0
    for n in tree.notables:
        if n.ascendancy or not n.stats:
            continue
        lines = tr.render(n.stats)
        print(f"  • {n.name}")
        for line in lines:
            print(f"      {line}")
        shown += 1
        if shown >= 4:
            break

    # 2) Live economy ---------------------------------------------------------
    section("LAYER 2  live economy  (poe.ninja)")
    try:
        state = ninja.index_state()
        econ = [lg.get("name") for lg in state.get("economyLeagues", [])]
        league = ninja.default_league()
        print(f"live economy leagues : {econ}")
        print(f"querying league      : {league}\n")
        cur = ninja.currency_overview("Currency", league=league)
        lines = cur.get("lines", [])
        names = {it.get("id"): it.get("name", it.get("id")) for it in cur.get("items", [])}
        priced = sorted(
            (x for x in lines if x.get("primaryValue")),
            key=lambda x: -x["primaryValue"],
        )
        print(f"top currencies by chaos value ({len(lines)} tracked):")
        for x in priced[:8]:
            print(f"  {names.get(x['id'], x['id']):<28} {x['primaryValue']:>10.1f}c")
    except ninja.NinjaError as exc:
        print(f"economy fetch failed: {exc}")

    # 3) Build corpus snapshot ------------------------------------------------
    section("LAYER 2  build corpus snapshot  (poe.ninja, protobuf)")
    try:
        snap = ninja.build_snapshot("standard")
        if snap:
            print(f"snapshot version : {snap.get('version')}")
            print(f"passive tree     : {snap.get('passiveTree')}")
            raw = ninja.builds_search_raw("standard")
            print(f"corpus payload   : {len(raw):,} bytes of application/x-protobuf")
            print("note             : decoding deferred (undocumented protobuf schema)")
        else:
            print("no build snapshot for 'standard'")
    except ninja.NinjaError as exc:
        print(f"builds fetch failed: {exc}")

    print("\ndone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
