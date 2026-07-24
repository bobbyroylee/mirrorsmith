"""Build reasoning — turn allocated passives into "what your build gives you".

The first real analysis layer. Every allocated base-tree node carries structured
stats (``{stat_id: value}``); within the passive tree, all modifiers of the same
stat id add together, so summing by stat id yields the tree's exact contribution
per stat. We render each total to English and group it into readable categories.

Cluster-jewel nodes live outside the base tree (their stats arrive as English
strings inside the import's ``jewel_data``), so they're aggregated separately by
counting identical lines rather than summed numerically.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable

from .data.stats import StatTranslator
from .data.tree import PassiveNode, PassiveTree

# (category label, substrings matched against the rendered English line).
# First match wins, so order matters: specific/defensive buckets before "damage".
_CATEGORIES: list[tuple[str, tuple[str, ...]]] = [
    ("Attributes", ("to strength", "to dexterity", "to intelligence", "to all attributes")),
    ("Life & Recovery", ("maximum life", "life regen", "life per", "recoup", "life leech",
                          "life on")),
    ("Energy Shield", ("energy shield",)),
    ("Mana", ("mana",)),
    ("Resistances", ("resistance",)),
    ("Defences", ("armour", "evasion", "block", "suppress", "dodge", "fortify",
                  "physical damage reduction", "damage taken", "avoid")),
    ("Speed", ("attack speed", "cast speed", "movement speed", "attack and cast")),
    ("Critical", ("critical",)),
    ("Ailments & Effect", ("ailment", "poison", "bleed", "ignite", "chill", "freeze",
                           "shock", "duration", "effect")),
    ("Damage", ("damage", "penetrat", "accuracy", "attack", "spell", "projectile")),
]


@dataclass
class BuildAnalysis:
    points_counted: int  # base-tree nodes contributing stats
    totals: dict[str, float]  # stat_id -> summed value
    rendered: dict[str, list[str]]  # category -> English lines (sorted)
    cluster_lines: list[str]  # aggregated cluster-jewel grants ("N× ...")

    def all_lines(self) -> list[str]:
        out: list[str] = []
        for cat, _ in _CATEGORIES:
            out += self.rendered.get(cat, [])
        out += self.rendered.get("Other", [])
        return out


def resolved_base_nodes(imported: dict[str, Any], tree: PassiveTree) -> list[PassiveNode]:
    nodes: list[PassiveNode] = []
    for h in imported.get("passives", {}).get("hashes", []) or []:
        node = tree.get(int(h))
        if node is not None:
            nodes.append(node)
    return nodes


def aggregate_stats(nodes: Iterable[PassiveNode]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for n in nodes:
        for sid, val in n.stats.items():
            totals[sid] = totals.get(sid, 0.0) + val
    return totals


def _categorize(line: str) -> str:
    low = line.lower()
    for cat, needles in _CATEGORIES:
        if any(n in low for n in needles):
            return cat
    return "Other"


def _cluster_grants(imported: dict[str, Any]) -> list[str]:
    """Count identical stat lines across allocated cluster-jewel nodes."""
    passives = imported.get("passives", {}) or {}
    allocated = {int(h) for h in passives.get("hashes_ex", []) or []}
    node_defs: dict[int, dict[str, Any]] = {}
    for _s, jd in (passives.get("jewel_data") or {}).items():
        for nid, node in ((jd or {}).get("subgraph") or {}).get("nodes", {}).items():
            node_defs[int(nid)] = node
    counter: Counter[str] = Counter()
    for h in allocated:
        node = node_defs.get(h)
        if not node:
            continue
        for stat in node.get("stats", []) or []:
            counter[" ".join(str(stat).split())] += 1  # normalize whitespace so dups merge
    lines = []
    for stat, n in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"{n}× {stat}" if n > 1 else stat)
    return lines


def analyze(imported: dict[str, Any], tree: PassiveTree,
            translator: StatTranslator) -> BuildAnalysis:
    nodes = resolved_base_nodes(imported, tree)
    totals = aggregate_stats(nodes)

    rendered: dict[str, list[str]] = {}
    for sid, total in totals.items():
        line = translator.render_one(sid, total)
        rendered.setdefault(_categorize(line), []).append(line)
    for cat in rendered:
        rendered[cat].sort()

    return BuildAnalysis(
        points_counted=len(nodes),
        totals=totals,
        rendered=rendered,
        cluster_lines=_cluster_grants(imported),
    )
