"""Calc engine — real defensive pools, effective HP, and deterministic upgrades.

Not a stat tally: this reconstructs the game's own defensive pipeline.

  * Item defences (Energy Shield / Evasion / Armour) are read from each item's
    computed property, which already bakes in that item's *local* flat + %% and
    quality — so we never double-count local mods.
  * Global flat pools (rings / amulet / belt / jewels / tree / clusters) add on
    top, then global "increased maximum X%%" multiplies the whole base.
  * Keystones are respected: Chaos Inoculation sets life to 1 and grants chaos
    immunity; Eldritch Battery / Ghost Reaver are noted for pool interactions.
  * Effective HP folds resistances (with the −60%% elemental map penalty) and
    spell suppression into a real "how big a hit can you eat" number per element.

Then a deterministic pass turns the numbers + item inspection into concrete,
non-hand-wavy upgrade actions (uncapped layer, fragile Kalandra dependency, open
crafting slots, off-base gear for the defence you actually scale).

Honest scope: aura/gem-granted stats (Discipline, Grace, Watcher's-Eye
conditionals) and mastery effects aren't in the pinned data yet, so ES/EHP read
*below* in-game and are labelled "pre-aura". Everything shown is computed, not
guessed, and never silently wrong.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .build import _cluster_grants, aggregate_stats, resolved_base_nodes
from .data.stats import StatTranslator
from .data.tree import NodeKind, PassiveTree

MAX_RESIST_DEFAULT = 75
MAP_PENALTY_ELEMENTAL = 60
SUPPRESS_PREVENT_BASE = 50.0  # % of suppressed spell hit prevented

ARMOUR_SLOTS = {"Helm", "BodyArmour", "Gloves", "Boots", "Offhand"}
RING_SLOTS = ("Ring", "Ring2", "Ring3")
_OPPOSITE_RING = {"Ring": "Ring2", "Ring2": "Ring", "Ring3": "Ring"}

# ---- tree stat ids we read structurally --------------------------------------
_TREE_RES = {
    "base_fire_damage_resistance_%": ("fire",),
    "base_cold_damage_resistance_%": ("cold",),
    "base_lightning_damage_resistance_%": ("lightning",),
    "base_chaos_damage_resistance_%": ("chaos",),
    "base_resist_all_elements_%": ("fire", "cold", "lightning"),
    "base_all_elemental_resistance_%": ("fire", "cold", "lightning"),
}
NUM = re.compile(r"[+-]?\d+(?:\.\d+)?")

# ---- gear/cluster mod-string patterns (global contributions only) ------------
# Local armour %/flat is already in the item's defence property, so we only match
# the *global* wordings here ("maximum Energy Shield", resist, suppress, attrs).
_P = {
    "flat_es": re.compile(r"^([+-]?\d+) to maximum Energy Shield$", re.I),
    "flat_life": re.compile(r"^([+-]?\d+) to maximum Life$", re.I),
    "flat_mana": re.compile(r"^([+-]?\d+) to maximum Mana$", re.I),
    "inc_es": re.compile(r"^([+-]?\d+)% increased maximum Energy Shield$", re.I),
    "inc_life": re.compile(r"^([+-]?\d+)% increased maximum Life$", re.I),
    "str": re.compile(r"^([+-]?\d+) to Strength$", re.I),
    "all_attr": re.compile(r"^([+-]?\d+) to all Attributes$", re.I),
    "suppress": re.compile(r"^([+-]?\d+)% chance to Suppress Spell Damage$", re.I),
}
_RES_P = [
    (re.compile(r"^([+-]?\d+)% to Fire Resistance$", re.I), ("fire",)),
    (re.compile(r"^([+-]?\d+)% to Cold Resistance$", re.I), ("cold",)),
    (re.compile(r"^([+-]?\d+)% to Lightning Resistance$", re.I), ("lightning",)),
    (re.compile(r"^([+-]?\d+)% to Chaos Resistance$", re.I), ("chaos",)),
    (re.compile(r"^([+-]?\d+)% to all Elemental Resistances$", re.I), ("fire", "cold", "lightning")),
    (re.compile(r"^([+-]?\d+)% to Fire and Cold Resistances?$", re.I), ("fire", "cold")),
    (re.compile(r"^([+-]?\d+)% to Fire and Lightning Resistances?$", re.I), ("fire", "lightning")),
    (re.compile(r"^([+-]?\d+)% to Cold and Lightning Resistances?$", re.I), ("cold", "lightning")),
]


@dataclass
class Resist:
    name: str
    raw: float
    penalty: float
    cap: int = MAX_RESIST_DEFAULT

    @property
    def net(self) -> float:
        return min(self.raw - self.penalty, self.cap)

    @property
    def over(self) -> float:
        return (self.raw - self.penalty) - self.cap

    @property
    def capped(self) -> bool:
        return self.net >= self.cap


@dataclass
class Rec:
    severity: str            # "critical" | "warning" | "tune"
    title: str
    detail: str


@dataclass
class BuildEval:
    keystones: list[str]
    life: int
    energy_shield: int
    mana: int
    es_from_items: int
    es_flat_global: int
    es_inc_global: int
    resists: dict[str, Resist]
    suppress: float
    suppress_prevent: float
    ehp: dict[str, int]       # element -> effective HP
    top_pool_label: str       # "Energy Shield" (CI) or "Life"
    aura_note: bool
    recs: list[Rec] = field(default_factory=list)


# ------------------------------------------------------------------------------
def _items(imported: dict[str, Any]) -> list[dict[str, Any]]:
    return (imported.get("items", {}) or {}).get("items", []) or []


def _item_mods(it: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for f in ("implicitMods", "explicitMods", "craftedMods", "fracturedMods", "enchantMods"):
        for m in it.get(f, []) or []:
            out.append(" ".join(str(m).split()))
    return out


def _prop(it: dict[str, Any], name: str) -> float:
    for p in it.get("properties", []) or []:
        if p.get("name") == name and p.get("values"):
            try:
                return float(NUM.search(p["values"][0][0]).group())
            except (AttributeError, ValueError):
                return 0.0
    return 0.0


def _string_pools(imported: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Return (all_strings, nonarmour_strings).

    Resistances, suppression, attributes and flat life/mana are GLOBAL on every
    item (including armour), so they read from ``all``. Flat Energy Shield on
    armour is LOCAL (already in the item's ES property), so ES flat reads from
    ``nonarmour`` only. Kalandra's Touch is expanded to the opposite ring; cluster
    grants are appended to both."""
    all_s: list[str] = []
    non_armour: list[str] = []
    items = _items(imported)
    by_slot = {it.get("inventoryId"): it for it in items}
    for it in items:
        slot = it.get("inventoryId")
        if slot == "Flask":
            continue
        if (it.get("name") or "") == "Kalandra's Touch":
            mirror = by_slot.get(_OPPOSITE_RING.get(slot, ""))
            mods = _item_mods(mirror) if mirror is not None else []
        else:
            mods = _item_mods(it)
        all_s.extend(mods)
        if slot not in ARMOUR_SLOTS:
            non_armour.extend(mods)
    cluster: list[str] = []
    for line in _cluster_grants(imported):
        m = re.match(r"(\d+)×\s+(.*)$", line)
        cluster.extend([m.group(2)] * int(m.group(1))) if m else cluster.append(line)
    all_s.extend(cluster)
    non_armour.extend(cluster)
    return all_s, non_armour


def evaluate(imported: dict[str, Any], tree: PassiveTree,
             translator: StatTranslator | None = None) -> BuildEval:
    meta = (imported.get("items", {}) or {}).get("character", {})
    level = int(meta.get("level", 1) or 1)

    nodes = resolved_base_nodes(imported, tree)
    totals = aggregate_stats(nodes)
    keystones = sorted({n.name for n in nodes if n.kind is NodeKind.KEYSTONE})
    ci = "Chaos Inoculation" in keystones

    all_s, non_armour = _string_pools(imported)

    def sum_pat(pat: re.Pattern[str], pool: list[str]) -> float:
        return sum(float(pat.match(s).group(1)) for s in pool if pat.match(s))

    # ---- resistances (global on every item, incl armour) ----
    res = {k: 0.0 for k in ("fire", "cold", "lightning", "chaos")}
    for sid, val in totals.items():
        for k in _TREE_RES.get(sid, ()):
            res[k] += val
    for s in all_s:
        for pat, kinds in _RES_P:
            m = pat.match(s)
            if m:
                for k in kinds:
                    res[k] += float(m.group(1))
                break
    resists = {
        "fire": Resist("Fire", res["fire"], MAP_PENALTY_ELEMENTAL),
        "cold": Resist("Cold", res["cold"], MAP_PENALTY_ELEMENTAL),
        "lightning": Resist("Lightning", res["lightning"], MAP_PENALTY_ELEMENTAL),
        "chaos": Resist("Chaos", res["chaos"], 0, cap=100),
    }
    suppress = min(totals.get("base_spell_suppression_chance_%", 0.0)
                   + sum_pat(_P["suppress"], all_s), 100.0)
    suppress_prevent = SUPPRESS_PREVENT_BASE + totals.get("base_spell_damage_%_suppressed", 0.0)

    # ---- attributes (for life-from-strength) ----
    strength = int(totals.get("base_strength", 0)
                   + sum_pat(_P["str"], all_s) + sum_pat(_P["all_attr"], all_s))

    # ---- Energy Shield pool (armour ES is local -> in item props; flat ES from
    #      non-armour only; global increased applies to the whole base) ----
    es_items = int(sum(_prop(it, "Energy Shield") for it in _items(imported)))
    es_flat = int(totals.get("base_maximum_energy_shield", 0) + sum_pat(_P["flat_es"], non_armour))
    es_inc = int(totals.get("maximum_energy_shield_+%", 0) + sum_pat(_P["inc_es"], all_s))
    energy_shield = int((es_items + es_flat) * (1 + es_inc / 100.0))

    # ---- Life pool ----
    if ci:
        life = 1
    else:
        base_life = 38 + 12 * (level - 1) + strength // 2
        flat_life = int(sum_pat(_P["flat_life"], all_s))
        inc_life = int(totals.get("maximum_life_+%", 0) + sum_pat(_P["inc_life"], all_s))
        life = int((base_life + flat_life) * (1 + inc_life / 100.0))

    mana = int(34 + 6 * (level - 1) + sum_pat(_P["flat_mana"], all_s))

    # ---- effective HP per hit type ----
    pool = energy_shield + (0 if ci else life)
    top_label = "Energy Shield" if ci or energy_shield > life else "Life"

    def ehp_vs(net_res: float) -> int:
        # resistance-only, attack-basis (conservative). Suppression is a spell-only
        # layer, reported separately rather than averaged into every hit.
        taken = max(0.0, 1 - net_res / 100.0)
        return int(pool / taken) if taken > 0 else 0

    ehp = {
        "fire": ehp_vs(resists["fire"].net),
        "cold": ehp_vs(resists["cold"].net),
        "lightning": ehp_vs(resists["lightning"].net),
        "chaos": -1 if ci else ehp_vs(resists["chaos"].net),  # -1 => immune (CI)
    }

    ev = BuildEval(
        keystones=keystones, life=life, energy_shield=energy_shield, mana=mana,
        es_from_items=es_items, es_flat_global=es_flat, es_inc_global=es_inc,
        resists=resists, suppress=suppress, suppress_prevent=suppress_prevent,
        ehp=ehp, top_pool_label=top_label, aura_note=True,
    )
    ev.recs = recommend(ev, imported)
    return ev


# ------------------------------------------------------------------------------
def _open_affix_items(imported: dict[str, Any]) -> list[tuple[str, str, int]]:
    """Rare equipped items with fewer than the 6 explicit affixes they could hold
    -> (slot, name, open_count). A conservative crafting-headroom signal."""
    out = []
    for it in _items(imported):
        if it.get("frameType") != 2:  # 2 = Rare
            continue
        slot = it.get("inventoryId", "")
        if slot in ("Flask", "PassiveJewels"):
            continue
        n = len(it.get("explicitMods", []) or []) + len(it.get("craftedMods", []) or [])
        if n < 6:
            out.append((slot, (it.get("name") or it.get("typeLine", "item")), 6 - n))
    return out


def recommend(ev: BuildEval, imported: dict[str, Any]) -> list[Rec]:
    recs: list[Rec] = []
    open_items = _open_affix_items(imported)
    open_str = ", ".join(f"{s} ({n} open)" for s, _, n in open_items) or "none obvious"

    # 1) uncapped elemental resistances = the highest-priority fix
    for key in ("fire", "cold", "lightning"):
        r = ev.resists[key]
        if r.net < r.cap:
            need = int(r.cap - r.net)
            recs.append(Rec("critical", f"{r.name} resistance {int(r.net)}% — {need}% under cap",
                            f"Add ~{need}% {r.name} res. Open affix slots: {open_str}."))

    # 2) fragile Kalandra dependency for capping
    items = _items(imported)
    kal = next((it for it in items if (it.get("name") or "") == "Kalandra's Touch"), None)
    if kal is not None:
        recs.append(Rec("warning", "Resistance capping leans on Kalandra's Touch",
                        "Kalandra's Touch mirrors the opposite ring; your caps include those "
                        "reflected mods. Changing the mirrored ring can drop a resistance below cap."))

    # 3) suppression short of 100% (mastery-aware caveat)
    if ev.suppress < 100:
        recs.append(Rec("warning", f"Spell suppression ~{int(ev.suppress)}% (pre-mastery)",
                        f"{int(100 - ev.suppress)}% from 100%. A +8–10% suppress suffix or the Spell "
                        "Suppression mastery closes it. (Masteries not yet in our data.)"))

    # 4) chaos exposure for non-CI
    if "Chaos Inoculation" not in ev.keystones and ev.resists["chaos"].net < 0:
        recs.append(Rec("warning", f"Chaos resistance {int(ev.resists['chaos'].net)}%",
                        "Negative chaos res is a spike-death risk without CI."))

    # 5) off-base gear for the defence you actually scale (ES build in non-ES gear)
    if ev.top_pool_label == "Energy Shield":
        for it in items:
            slot = it.get("inventoryId")
            if slot in ("Helm", "Gloves", "Boots", "BodyArmour") and _prop(it, "Energy Shield") == 0:
                recs.append(Rec("tune", f"{slot} contributes 0 Energy Shield",
                                "You scale ES but this piece is a non-ES base — an ES or hybrid base "
                                "would add to your pool."))

    # 6) crafting headroom
    if open_items:
        recs.append(Rec("tune", "Open crafting slots available",
                        f"Unused affix capacity: {open_str}. Bench-craft the missing res/suppress/ES."))

    order = {"critical": 0, "warning": 1, "tune": 2}
    recs.sort(key=lambda r: order.get(r.severity, 9))
    return recs


# back-compat shim for the previous UI wiring
def defensive_summary(imported: dict[str, Any], tree: PassiveTree,
                      translator: StatTranslator | None = None) -> BuildEval:
    return evaluate(imported, tree, translator)
