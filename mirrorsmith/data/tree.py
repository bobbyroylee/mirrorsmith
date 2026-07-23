"""Passive skill tree — normalized model.

Turns repoe-fork's ``Default.json`` into a typed graph the rest of mirrorsmith can
reason over: nodes with a clear kind, their *structured* stats (raw stat-id ->
value, ready for a calculator), and the adjacency needed for pathing / point-cost.

Upstream shape (repoe-fork extraction):
    title    : str
    roots    : [hash, ...]                 # class-start / entry nodes
    passives : { "<hash>": {hash, id, name, icon, is_keystone, is_notable,
                            is_jewel_socket, is_ascendancy_starting_node,
                            is_multiple_choice, is_multiple_choice_option,
                            is_icon_only, ascendancy, stats:{id:value},
                            reminder_text, flavour_text, skill_points} }
    groups   : [ {x, y, passives:[{hash, connections:[hash,...], ...}]} ]

Note the connectivity lives in ``groups[].passives[].connections`` (neighbour
hashes), not on the passive record — we fold it back onto each node and make it
symmetric so ``neighbors`` works from either end.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any

from . import fetch


class NodeKind(enum.Enum):
    KEYSTONE = "keystone"
    NOTABLE = "notable"
    MASTERY = "mastery"
    JEWEL_SOCKET = "jewel_socket"
    ASCENDANCY = "ascendancy"  # any node belonging to an ascendancy sub-tree
    CLASS_START = "class_start"
    SMALL = "small"  # ordinary minor passive
    PROXY = "proxy"  # layout-only / icon-only, no real allocation value


@dataclass(frozen=True, slots=True)
class PassiveNode:
    id: int  # hash
    ident: str  # stable string id, e.g. "iron_reflexes1137"
    name: str
    kind: NodeKind
    stats: dict[str, float]  # raw stat-id -> value (render via stat_translations)
    neighbors: tuple[int, ...]  # connected node hashes (symmetric)
    ascendancy: str | None = None
    is_class_start: bool = False
    icon: str | None = None
    reminder_text: tuple[str, ...] = ()
    flavour_text: str = ""

    @property
    def is_keystone(self) -> bool:
        return self.kind is NodeKind.KEYSTONE

    @property
    def is_notable(self) -> bool:
        return self.kind is NodeKind.NOTABLE

    @property
    def is_mastery(self) -> bool:
        return self.kind is NodeKind.MASTERY


@dataclass(frozen=True, slots=True)
class CharacterClass:
    name: str
    base_str: int
    base_dex: int
    base_int: int
    ascendancies: tuple[str, ...]


def _flatten_stats(raw: Any) -> dict[str, float]:
    """repoe stats are usually a dict {id: value}; be defensive about lists too."""
    if isinstance(raw, dict):
        out: dict[str, float] = {}
        for k, v in raw.items():
            try:
                out[str(k)] = float(v)
            except (TypeError, ValueError):
                out[str(k)] = 0.0
        return out
    return {}


def _classify(raw: dict[str, Any], roots: set[int]) -> NodeKind:
    if raw.get("hash") in roots or raw.get("is_ascendancy_starting_node"):
        # Class-start and ascendancy-start nodes are entry points, not allocatable
        # passives with stats of interest.
        if raw.get("ascendancy"):
            return NodeKind.ASCENDANCY
        return NodeKind.CLASS_START
    if raw.get("is_keystone"):
        return NodeKind.KEYSTONE
    if raw.get("is_jewel_socket"):
        return NodeKind.JEWEL_SOCKET
    # Masteries: repoe marks them icon-only + name ending in "Mastery" (they carry
    # their choosable effects elsewhere). Detect before generic notable/small.
    icon = raw.get("icon") or ""
    if raw.get("name", "").endswith("Mastery") or "/Masteries/" in icon:
        return NodeKind.MASTERY
    if raw.get("ascendancy"):
        return NodeKind.ASCENDANCY
    if raw.get("is_notable"):
        return NodeKind.NOTABLE
    if raw.get("is_icon_only"):
        return NodeKind.PROXY
    return NodeKind.SMALL


class PassiveTree:
    """Loaded, normalized passive tree with lookups and adjacency."""

    def __init__(self, raw: dict[str, Any], characters: Any | None = None):
        self.raw = raw
        self.title: str = str(raw.get("title", "Default"))
        self.nodes: dict[int, PassiveNode] = {}
        self._by_name: dict[str, list[int]] = {}
        self.classes: list[CharacterClass] = []
        self._parse(characters)

    # -- construction --------------------------------------------------------
    @classmethod
    def load(cls, *, force: bool = False) -> "PassiveTree":
        """Fetch (if needed) the pinned current-league tree + class data, build model."""
        raw = fetch.load_json("tree", force=force)
        try:
            characters = fetch.load_json("characters", force=force)
        except Exception:  # noqa: BLE001 — classes are a nice-to-have, tree is core
            characters = None
        return cls(raw, characters)

    def _build_adjacency(self) -> dict[int, set[int]]:
        adj: dict[int, set[int]] = {}
        for group in self.raw.get("groups", []) or []:
            for gp in group.get("passives", []) or []:
                h = gp.get("hash")
                if h is None:
                    continue
                conns = [int(c) for c in gp.get("connections", []) or []]
                adj.setdefault(int(h), set()).update(conns)
                for c in conns:  # make symmetric
                    adj.setdefault(c, set()).add(int(h))
        return adj

    def _parse(self, characters: Any | None) -> None:
        roots = {int(r) for r in self.raw.get("roots", []) or []}
        adj = self._build_adjacency()

        for _key, raw in self.raw.get("passives", {}).items():
            h = raw.get("hash")
            if h is None:
                continue
            h = int(h)
            node = PassiveNode(
                id=h,
                ident=str(raw.get("id", h)),
                name=raw.get("name", ""),
                kind=_classify(raw, roots),
                stats=_flatten_stats(raw.get("stats")),
                neighbors=tuple(sorted(adj.get(h, set()))),
                ascendancy=raw.get("ascendancy"),
                is_class_start=h in roots,
                icon=raw.get("icon"),
                reminder_text=tuple(
                    r if isinstance(r, str) else " ".join(map(str, r))
                    for r in raw.get("reminder_text", []) or ()
                ),
                flavour_text=raw.get("flavour_text", "") or "",
            )
            self.nodes[h] = node
            if node.name:
                self._by_name.setdefault(node.name.lower(), []).append(h)

        self._parse_classes(characters)

    def _parse_classes(self, characters: Any | None) -> None:
        # Ascendancy names come from the tree itself; base attributes from
        # characters.json when available.
        asc_by_class: dict[str, list[str]] = {}
        for n in self.nodes.values():
            if n.ascendancy and n.is_class_start:
                asc_by_class.setdefault("", []).append(n.ascendancy)
        if not isinstance(characters, (list, dict)):
            return
        records = characters.values() if isinstance(characters, dict) else characters
        for rec in records:
            if not isinstance(rec, dict) or "name" not in rec:
                continue
            base = rec.get("base_stats", {}) or {}
            self.classes.append(
                CharacterClass(
                    name=rec.get("name", "?"),
                    base_str=int(base.get("strength", 0) or 0),
                    base_dex=int(base.get("dexterity", 0) or 0),
                    base_int=int(base.get("intelligence", 0) or 0),
                    ascendancies=(),
                )
            )

    # -- lookups -------------------------------------------------------------
    def __len__(self) -> int:
        return len(self.nodes)

    def get(self, node_id: int) -> PassiveNode | None:
        return self.nodes.get(node_id)

    def find(self, name: str) -> list[PassiveNode]:
        """All nodes whose name matches (case-insensitive). Names aren't unique —
        many notables repeat across the tree."""
        return [self.nodes[i] for i in self._by_name.get(name.lower(), [])]

    def of_kind(self, kind: NodeKind) -> list[PassiveNode]:
        return [n for n in self.nodes.values() if n.kind is kind]

    @property
    def keystones(self) -> list[PassiveNode]:
        return self.of_kind(NodeKind.KEYSTONE)

    @property
    def notables(self) -> list[PassiveNode]:
        return self.of_kind(NodeKind.NOTABLE)

    @property
    def masteries(self) -> list[PassiveNode]:
        return self.of_kind(NodeKind.MASTERY)

    @property
    def ascendancy_names(self) -> list[str]:
        return sorted({n.ascendancy for n in self.nodes.values() if n.ascendancy})

    def neighbors(self, node_id: int) -> list[PassiveNode]:
        node = self.nodes.get(node_id)
        if node is None:
            return []
        return [self.nodes[i] for i in node.neighbors if i in self.nodes]

    def edge_count(self) -> int:
        return sum(len(n.neighbors) for n in self.nodes.values()) // 2

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {k.value: 0 for k in NodeKind}
        for n in self.nodes.values():
            out[n.kind.value] += 1
        out["total"] = len(self.nodes)
        return out


def unique_keystones(tree: PassiveTree) -> list[PassiveNode]:
    """Base-tree keystones deduplicated by name (excludes ascendancy keystones)."""
    seen: set[str] = set()
    result: list[PassiveNode] = []
    for n in sorted(tree.keystones, key=lambda x: x.name):
        if n.ascendancy or n.name in seen:
            continue
        seen.add(n.name)
        result.append(n)
    return result
