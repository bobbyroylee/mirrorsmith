"""Stat-translation renderer — raw stat-ids -> human-readable English.

repoe-fork stores passive/item stats as structured ``{stat_id: value}`` (great for
math). To *show* them we apply the game's own stat-description rules from
``stat_translations.json`` — the same data pathofexile.com and Path of Building use.

Each translation entry maps a set of stat ids to one or more English rules. A rule
carries, per id: a ``condition`` (value range that selects the rule), a ``format``
spec ("#", "+#", "ignore"), and ``index_handlers`` (numeric transforms like
"divide_by_100", "negate", "milliseconds_to_seconds"). We pick the rule whose
conditions match the raw values, transform each value, and fill the template.

Multi-id lines (e.g. "Adds X to Y Fire Damage") are matched greedily, longest
id-set first, so combined stats render as one line instead of two.
"""

from __future__ import annotations

from typing import Any, Callable

from . import fetch

# --- numeric index handlers ----------------------------------------------------
# The common ones; unknown handlers pass the value through unchanged so rendering
# degrades gracefully rather than crashing on a rare handler.
_HANDLERS: dict[str, Callable[[float], float]] = {
    "negate": lambda v: -v,
    "times_minus_one": lambda v: -v,
    "double": lambda v: v * 2,
    "negate_and_double": lambda v: -v * 2,
    "times_twenty": lambda v: v * 20,
    "times_one_point_five": lambda v: v * 1.5,
    "divide_by_two_0dp": lambda v: v / 2,
    "divide_by_three": lambda v: v / 3,
    "divide_by_four": lambda v: v / 4,
    "divide_by_five": lambda v: v / 5,
    "divide_by_six": lambda v: v / 6,
    "divide_by_ten_0dp": lambda v: v / 10,
    "divide_by_ten_1dp": lambda v: v / 10,
    "divide_by_twelve": lambda v: v / 12,
    "divide_by_fifteen_0dp": lambda v: v / 15,
    "divide_by_twenty_then_double_0dp": lambda v: v / 20 * 2,
    "divide_by_one_hundred": lambda v: v / 100,
    "divide_by_100": lambda v: v / 100,
    "divide_by_100_2dp": lambda v: v / 100,
    "divide_by_100_2dp_if_required": lambda v: v / 100,
    "divide_by_one_hundred_and_negate": lambda v: -v / 100,
    "divide_by_one_thousand": lambda v: v / 1000,
    "milliseconds_to_seconds": lambda v: v / 1000,
    "milliseconds_to_seconds_0dp": lambda v: v / 1000,
    "milliseconds_to_seconds_1dp": lambda v: v / 1000,
    "milliseconds_to_seconds_2dp": lambda v: v / 1000,
    "deciseconds_to_seconds": lambda v: v / 10,
    "per_minute_to_per_second": lambda v: v / 60,
    "per_minute_to_per_second_0dp": lambda v: v / 60,
    "per_minute_to_per_second_1dp": lambda v: v / 60,
    "per_minute_to_per_second_2dp": lambda v: v / 60,
}


def _fmt_num(v: float) -> str:
    """Whole numbers as ints; otherwise trim trailing zeros (max 2 dp)."""
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _apply_handlers(value: float, handlers: list[str] | None) -> float:
    for h in handlers or ():
        fn = _HANDLERS.get(h)
        if fn is not None:
            value = fn(value)
    return value


def _cond_matches(value: float, cond: dict[str, Any] | None) -> bool:
    if not cond:
        return True
    lo, hi, neg = cond.get("min"), cond.get("max"), cond.get("negated")
    inside = (lo is None or value >= lo) and (hi is None or value <= hi)
    return (not inside) if neg else inside


class StatTranslator:
    def __init__(self, entries: list[dict[str, Any]]):
        self._entries = entries
        # id -> entries that reference it, for candidate lookup during rendering.
        self._index: dict[str, list[dict[str, Any]]] = {}
        for e in entries:
            for sid in e.get("ids", []) or ():
                self._index.setdefault(sid, []).append(e)

    @classmethod
    def load(cls, *, force: bool = False) -> "StatTranslator":
        return cls(fetch.load_json("stat_translations", force=force))

    def _alias(self, stat_id: str) -> str:
        """Map a tree stat id to its translatable equivalent when they differ.
        Passive nodes use ``base_strength`` etc., but the description file keys
        those on ``additional_strength``."""
        if stat_id in self._index:
            return stat_id
        if stat_id.startswith("base_"):
            alt = "additional_" + stat_id[len("base_"):]
            if alt in self._index:
                return alt
        return stat_id

    # -- public API ----------------------------------------------------------
    def render(self, stats: dict[str, float]) -> list[str]:
        """Render a stat dict to English lines. Untranslated ids fall back to a
        readable ``id = value`` so nothing is silently dropped."""
        remaining: dict[str, float] = {}
        for sid, val in stats.items():
            key = self._alias(sid)
            remaining[key] = remaining.get(key, 0.0) + val
        lines: list[str] = []

        candidates = {
            id(e): e
            for sid in remaining
            for e in self._index.get(sid, ())
        }
        # Longest id-set first so combined lines win over single-stat ones.
        for e in sorted(candidates.values(), key=lambda e: -len(e.get("ids", []))):
            ids = e.get("ids", [])
            if ids and all(i in remaining for i in ids):
                line = self._translate(e, [remaining[i] for i in ids])
                if line is not None:
                    lines.append(line)
                    for i in ids:
                        remaining.pop(i, None)

        for sid in sorted(remaining):
            lines.append(f"{sid} = {_fmt_num(remaining[sid])}")
        return lines

    def render_one(self, stat_id: str, value: float) -> str:
        out = self.render({stat_id: value})
        return out[0] if out else f"{stat_id} = {_fmt_num(value)}"

    # -- internals -----------------------------------------------------------
    def _translate(self, entry: dict[str, Any], values: list[float]) -> str | None:
        rules = entry.get("English", []) or []
        if not rules:
            return None
        chosen = None
        for rule in rules:
            conds = rule.get("condition", []) or [None] * len(values)
            if all(_cond_matches(values[i], conds[i] if i < len(conds) else None)
                   for i in range(len(values))):
                chosen = rule
                break
        if chosen is None:
            chosen = rules[0]

        fmts = chosen.get("format", []) or ["#"] * len(values)
        handlers = chosen.get("index_handlers", []) or [[]] * len(values)
        string = chosen.get("string", "")

        out = string
        for i, raw in enumerate(values):
            spec = fmts[i] if i < len(fmts) else "#"
            if spec == "ignore":
                disp = ""
            else:
                v = _apply_handlers(raw, handlers[i] if i < len(handlers) else [])
                num = _fmt_num(v)
                if spec.startswith("+") and v >= 0:
                    num = "+" + num
                disp = num
            out = out.replace("{" + str(i) + "}", disp)
        # Some game templates embed hard line breaks; normalize to single spaces.
        return " ".join(out.split())
