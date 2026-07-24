"""Calc engine v1 — defensive resolver + health check.

This is what turns mirrorsmith from an analyzer into a helper: it computes real,
fused totals and flags what's wrong. We start with the stats that are (a) truly
additive across every source — no local/global trap — and (b) where being off is
a concrete, fixable problem: **elemental/chaos resistances** and **spell
suppression**.

Resistances are collected from the tree (structured stat ids), the ascendancy
(also base-tree nodes), and gear + cluster jewels (mod strings, matched with a
small set of exact regexes). The standard endgame **−60% elemental map penalty**
is applied so the number means what it means in maps (like Path of Building's
default). Resolved values are capped at 75% by default.

Known gap, stated honestly: mastery effects aren't in repoe's tree export yet, so
suppression (which masteries often boost) can read low — it's reported with a
caveat rather than hard-flagged. Resistances rarely come from masteries, so the
resistance check is reliable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .build import _cluster_grants, aggregate_stats, resolved_base_nodes
from .data.stats import StatTranslator
from .data.tree import PassiveTree

MAX_RESIST_DEFAULT = 75
MAP_PENALTY_ELEMENTAL = 60  # standard -60% all elemental resistances in maps
MAP_PENALTY_CHAOS = 0

# Tree stat-id -> which resistances it feeds (each +value).
_TREE_RES: dict[str, tuple[str, ...]] = {
    "base_fire_damage_resistance_%": ("fire",),
    "base_cold_damage_resistance_%": ("cold",),
    "base_lightning_damage_resistance_%": ("lightning",),
    "base_chaos_damage_resistance_%": ("chaos",),
    "base_resist_all_elements_%": ("fire", "cold", "lightning"),
    "base_all_elemental_resistance_%": ("fire", "cold", "lightning"),
    "fire_and_cold_damage_resistance_%": ("fire", "cold"),
    "fire_and_lightning_damage_resistance_%": ("fire", "lightning"),
    "cold_and_lightning_damage_resistance_%": ("cold", "lightning"),
}
_TREE_SUPPRESS = "base_spell_suppression_chance_%"

# Gear/cluster mod string -> resistance contribution. Order-independent.
_GEAR_RES: list[tuple[re.Pattern[str], tuple[str, ...]]] = [
    (re.compile(r"([+-]?\d+)% to Fire Resistance$", re.I), ("fire",)),
    (re.compile(r"([+-]?\d+)% to Cold Resistance$", re.I), ("cold",)),
    (re.compile(r"([+-]?\d+)% to Lightning Resistance$", re.I), ("lightning",)),
    (re.compile(r"([+-]?\d+)% to Chaos Resistance$", re.I), ("chaos",)),
    (re.compile(r"([+-]?\d+)% to all Elemental Resistances$", re.I), ("fire", "cold", "lightning")),
    (re.compile(r"([+-]?\d+)% to Fire and Cold Resistances?$", re.I), ("fire", "cold")),
    (re.compile(r"([+-]?\d+)% to Fire and Lightning Resistances?$", re.I), ("fire", "lightning")),
    (re.compile(r"([+-]?\d+)% to Cold and Lightning Resistances?$", re.I), ("cold", "lightning")),
]
_GEAR_SUPPRESS = re.compile(r"([+-]?\d+)% chance to Suppress Spell Damage$", re.I)


@dataclass
class Resist:
    name: str
    raw: float          # summed from all sources, before map penalty
    penalty: float
    cap: int = MAX_RESIST_DEFAULT

    @property
    def net(self) -> float:
        return min(self.raw - self.penalty, self.cap)

    @property
    def over(self) -> float:  # overcap headroom (useful vs curses/pen)
        return (self.raw - self.penalty) - self.cap

    @property
    def capped(self) -> bool:
        return self.net >= self.cap


@dataclass
class Defence:
    resists: dict[str, Resist]
    suppress: float
    suppress_prevent: float  # % of suppressed damage prevented (base 50)
    flags: list[str] = field(default_factory=list)


def _item_mod_strings(it: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for f in ("implicitMods", "explicitMods", "craftedMods", "fracturedMods", "enchantMods"):
        for mod in it.get(f, []) or []:
            out.append(" ".join(str(mod).split()))
    return out


# Kalandra's Touch copies the ring in the opposite slot; the API never expands
# those reflected mods, so we mirror them ourselves. Ring <-> Ring2 are paired.
_OPPOSITE_RING = {"Ring": "Ring2", "Ring2": "Ring", "Ring3": "Ring"}


def _gear_and_cluster_strings(imported: dict[str, Any], tree: PassiveTree) -> list[str]:
    out: list[str] = []
    items = (imported.get("items", {}) or {}).get("items", []) or []
    by_slot = {it.get("inventoryId"): it for it in items}
    for it in items:
        slot = it.get("inventoryId")
        if slot in ("PassiveJewels",):
            continue
        if (it.get("name") or "") == "Kalandra's Touch":
            mirror = by_slot.get(_OPPOSITE_RING.get(slot, ""))
            if mirror is not None:
                out.extend(_item_mod_strings(mirror))  # reflected mods
            continue
        out.extend(_item_mod_strings(it))
    # cluster-jewel grants already come pre-counted as "N× text"; expand the count
    for line in _cluster_grants(imported):
        m = re.match(r"(\d+)×\s+(.*)$", line)
        if m:
            out.extend([m.group(2)] * int(m.group(1)))
        else:
            out.append(line)
    return out


def defensive_summary(imported: dict[str, Any], tree: PassiveTree,
                      translator: StatTranslator | None = None) -> Defence:
    res = {k: 0.0 for k in ("fire", "cold", "lightning", "chaos")}
    suppress = 0.0

    # tree + ascendancy (structured)
    totals = aggregate_stats(resolved_base_nodes(imported, tree))
    for sid, val in totals.items():
        for kind in _TREE_RES.get(sid, ()):  # spread all-res etc.
            res[kind] += val
    suppress += totals.get(_TREE_SUPPRESS, 0.0)

    # gear + cluster (strings)
    for mod in _gear_and_cluster_strings(imported, tree):
        for pat, kinds in _GEAR_RES:
            m = pat.search(mod)
            if m:
                for kind in kinds:
                    res[kind] += float(m.group(1))
                break
        ms = _GEAR_SUPPRESS.search(mod)
        if ms:
            suppress += float(ms.group(1))

    resists = {
        "fire": Resist("Fire", res["fire"], MAP_PENALTY_ELEMENTAL),
        "cold": Resist("Cold", res["cold"], MAP_PENALTY_ELEMENTAL),
        "lightning": Resist("Lightning", res["lightning"], MAP_PENALTY_ELEMENTAL),
        "chaos": Resist("Chaos", res["chaos"], MAP_PENALTY_CHAOS, cap=100),
    }
    suppress = min(suppress, 100.0)
    prevent = 50.0 + totals.get("base_spell_damage_%_suppressed", 0.0)

    flags: list[str] = []
    for key in ("fire", "cold", "lightning"):
        r = resists[key]
        if r.net < r.cap:
            flags.append(f"{r.name} resistance {r.net:.0f}% — {r.cap - r.net:.0f}% under the {r.cap}% cap")
    if resists["chaos"].net < 0:
        flags.append(f"Chaos resistance is negative ({resists['chaos'].net:.0f}%)")
    if suppress < 100:
        flags.append(f"Spell suppression ~{suppress:.0f}% (tree+gear; masteries not yet counted)")

    return Defence(resists=resists, suppress=suppress, suppress_prevent=prevent, flags=flags)
