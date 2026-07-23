"""poe.ninja client — Layer 2 live meta & economy.

Two surfaces:
  * Economy (public, documented-ish): currency + item prices per league.
  * Build corpus (internal/undocumented): what the top-ranked players run. Powerful
    as an example set and a validation target, but the endpoint shape can change
    without notice, so callers should treat it as best-effort.

Standard library only. No API key required.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from . import sources

_USER_AGENT = "mirrorsmith/0.0.1 (+https://github.com/bobbyroylee/mirrorsmith)"

# Currency-type overviews (get_currency_overview) vs item-type overviews
# (get_item_overview). These are the stable overview categories.
CURRENCY_TYPES = ("Currency", "Fragment")
ITEM_TYPES = (
    "DivinationCard", "UniqueWeapon", "UniqueArmour", "UniqueAccessory",
    "UniqueFlask", "UniqueJewel", "SkillGem", "Cluster", "Fossil", "Essence",
    "Scarab", "BaseType",
)


def _get_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _url(path: str, **params: str) -> str:
    q = urllib.parse.urlencode(params)
    return f"{sources.NINJA_BASE}/{path}?{q}"


def currency_overview(type_: str = "Currency", league: str | None = None) -> dict[str, Any]:
    """Currency/fragment prices for a league. ``type_`` in CURRENCY_TYPES."""
    league = league or sources.DEFAULT_LEAGUE
    return _get_json(_url("currencyoverview", league=league, type=type_))


def item_overview(type_: str, league: str | None = None) -> dict[str, Any]:
    """Item prices for a league. ``type_`` in ITEM_TYPES."""
    league = league or sources.DEFAULT_LEAGUE
    return _get_json(_url("itemoverview", league=league, type=type_))


def builds_overview(league: str | None = None) -> dict[str, Any]:
    """Top-ranked players' build snapshots for a league (undocumented endpoint).

    Returns the raw poe.ninja build payload (accounts, characters, and the
    per-character tree/skill/item indices). Best-effort: shape may change.
    """
    league = league or sources.DEFAULT_LEAGUE
    # poe.ninja serves the builds snapshot from the character/getState surface.
    overview = urllib.parse.quote(f"{league}")
    return _get_json(
        f"https://poe.ninja/api/data/{overview}/getbuildoverview"
        f"?overview={overview}&type=exp&language=en"
    )
