"""Imported character -> readable build summary, joined against our tree.

This is where Layer 1 (the tree) meets a real player's build. The import payload
has three distinct kinds of allocated node:

  * ``hashes``          — base passive tree nodes. These resolve directly against
                          ``PassiveTree`` node ids; a 100% resolve rate is our
                          correctness check that the pinned tree matches the game.
  * ``hashes_ex``       — cluster-jewel expansion nodes. NOT in the base tree —
                          each socketed cluster jewel ships its own subgraph in
                          ``jewel_data`` defining these nodes' names and stats.
  * ``skill_overrides`` — tattoos: they replace a base node's stats in place.

We resolve each against the right source so the summary reflects the real build.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .data.stats import StatTranslator
from .data.tree import NodeKind, PassiveNode, PassiveTree


@dataclass
class BuildSummary:
    account: str
    character: str
    level: int | None
    char_class: str | None
    ascendancy: str | None
    league: str | None

    # base tree (the validation metric)
    base_allocated: int
    base_resolved: int
    unknown_base_hashes: list[int]
    # cluster jewels (resolved from the payload's own jewel_data)
    cluster_allocated: int
    cluster_resolved: int

    keystones: list[PassiveNode]
    notables: list[PassiveNode]
    cluster_notables: list[str]
    masteries: list[str]
    tattoos: list[str]

    equipment: list[str]
    main_gems: list[str]

    @property
    def base_resolve_rate(self) -> float:
        return self.base_resolved / self.base_allocated if self.base_allocated else 0.0


def _character_meta(items_payload: dict[str, Any]) -> dict[str, Any]:
    return items_payload.get("character", {}) if isinstance(items_payload, dict) else {}


def _mastery_map(passives: dict[str, Any]) -> dict[int, int]:
    """node hash -> chosen effect hash, tolerating list or dict encodings."""
    raw = passives.get("mastery_effects")
    out: dict[int, int] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            try:
                out[int(k)] = int(v)
            except (TypeError, ValueError):
                continue
    elif isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, dict) and "hash" in entry and "effect" in entry:
                try:
                    out[int(entry["hash"])] = int(entry["effect"])
                except (TypeError, ValueError):
                    continue
    return out


def _cluster_node_map(passives: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """Merge every socketed cluster jewel's subgraph into one {node id -> def}."""
    out: dict[int, dict[str, Any]] = {}
    for _socket, jd in (passives.get("jewel_data") or {}).items():
        sub = (jd or {}).get("subgraph") or {}
        for nid, node in (sub.get("nodes") or {}).items():
            try:
                out[int(nid)] = node
            except (TypeError, ValueError):
                continue
    return out


def _extract_gems(items: list[dict[str, Any]]) -> list[str]:
    """Active (non-support) skill gems across equipped items."""
    gems: list[str] = []
    for it in items:
        for sock in it.get("socketedItems", []) or []:
            name = sock.get("typeLine", "")
            if name and "Support" not in name:
                gems.append(name)
    seen: set[str] = set()
    return [g for g in gems if not (g in seen or seen.add(g))]


def summarize(imported: dict[str, Any], tree: PassiveTree,
              translator: StatTranslator | None = None) -> BuildSummary:
    passives = imported.get("passives", {}) or {}
    items_payload = imported.get("items", {}) or {}
    meta = _character_meta(items_payload)

    # --- base tree nodes -----------------------------------------------------
    base = [int(h) for h in passives.get("hashes", []) or []]
    resolved_nodes: list[PassiveNode] = []
    unknown: list[int] = []
    for h in base:
        node = tree.get(h)
        (resolved_nodes if node else unknown).append(node if node else h)  # type: ignore[arg-type]
    resolved_nodes = [n for n in resolved_nodes if isinstance(n, PassiveNode)]
    unknown = [h for h in unknown if isinstance(h, int)]

    keystones = [n for n in resolved_nodes if n.kind is NodeKind.KEYSTONE]
    notables = [n for n in resolved_nodes if n.kind is NodeKind.NOTABLE and not n.ascendancy]

    # --- cluster jewel nodes (resolve from jewel_data, not the base tree) -----
    cluster_ids = [int(h) for h in passives.get("hashes_ex", []) or []]
    cluster_map = _cluster_node_map(passives)
    cluster_resolved = sum(1 for h in cluster_ids if h in cluster_map)
    cluster_notables = sorted({
        cluster_map[h].get("name", "")
        for h in cluster_ids
        if h in cluster_map and cluster_map[h].get("isNotable")
    } - {""})

    # --- masteries -----------------------------------------------------------
    masteries: list[str] = []
    for node_hash, effect_hash in _mastery_map(passives).items():
        node = tree.get(node_hash)
        label = node.name if node else f"Mastery {node_hash}"
        masteries.append(f"{label} (effect {effect_hash})")

    # --- tattoos (skill_overrides) ------------------------------------------
    tattoos = sorted({
        ov.get("name", "")
        for ov in (passives.get("skill_overrides") or {}).values()
        if isinstance(ov, dict) and ov.get("isTattoo")
    } - {""})

    asc = passives.get("alternate_ascendancy") or passives.get("ascendancy")
    if isinstance(asc, dict):
        asc = asc.get("name")

    # --- items ---------------------------------------------------------------
    equipment: list[str] = []
    item_list = items_payload.get("items", []) or []
    for it in item_list:
        slot = it.get("inventoryId", "")
        name = (it.get("name") or "").strip()
        base_name = it.get("typeLine", "")
        label = f"{name} {base_name}".strip() if name else base_name
        if slot and label and slot != "PassiveJewels":
            equipment.append(f"{slot}: {label}")

    return BuildSummary(
        account=imported.get("account", "?"),
        character=meta.get("name", imported.get("character", "?")),
        level=meta.get("level"),
        char_class=meta.get("class"),
        ascendancy=asc,
        league=meta.get("league"),
        base_allocated=len(base),
        base_resolved=len(resolved_nodes),
        unknown_base_hashes=unknown,
        cluster_allocated=len(cluster_ids),
        cluster_resolved=cluster_resolved,
        keystones=sorted(keystones, key=lambda n: n.name),
        notables=sorted(notables, key=lambda n: n.name),
        cluster_notables=cluster_notables,
        masteries=sorted(masteries),
        tattoos=tattoos,
        equipment=equipment,
        main_gems=_extract_gems(item_list),
    )
