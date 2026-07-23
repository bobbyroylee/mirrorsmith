#!/usr/bin/env python3
"""Proof-of-pipeline: fetch + parse the live passive tree and print stats.

If this prints sane numbers, real keystone names, and structured stats for the
pinned league, the whole Layer-1 data foundation is working end to end.

    python scripts/tree_stats.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mirrorsmith.data import sources  # noqa: E402
from mirrorsmith.data.tree import PassiveTree, unique_keystones  # noqa: E402


def main() -> int:
    print(f"Loading passive tree - pin {sources.REPOE_VERSION} @ {sources.REPOE_PIN[:10]}\n")
    tree = PassiveTree.load()

    counts = tree.counts()
    print(f"tree title  : {tree.title}")
    print(f"total nodes : {counts['total']}")
    print(f"total edges : {tree.edge_count()}")
    print("node counts :")
    for kind in ("keystone", "notable", "mastery", "jewel_socket", "ascendancy",
                 "class_start", "small", "proxy"):
        print(f"    {kind:<13} {counts.get(kind, 0):>5}")

    print(f"\nascendancies ({len(tree.ascendancy_names)}):")
    print("    " + ", ".join(tree.ascendancy_names))

    if tree.classes:
        print(f"\nclasses ({len(tree.classes)}):")
        for c in tree.classes:
            print(f"    {c.name:<12} str{c.base_str:>3} dex{c.base_dex:>3} int{c.base_int:>3}")

    ks = unique_keystones(tree)
    print(f"\nbase-tree keystones ({len(ks)}):")
    for n in ks:
        stat = next(iter(n.stats), "")
        print(f"    {n.name}")

    # Spot-check well-known keystones survive round-trip with structured stats.
    print("\nstructured-stat probes:")
    for probe in ("Chaos Inoculation", "Resolute Technique", "Elemental Overload",
                  "Blood Magic", "Iron Reflexes"):
        hits = tree.find(probe)
        if hits:
            n = hits[0]
            print(f"    {probe:<22} stats={n.stats}  degree={len(n.neighbors)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
