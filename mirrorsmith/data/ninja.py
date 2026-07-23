"""poe.ninja client — Layer 2 live meta & economy.

Reverse-engineered from the live site (2026-07), because poe.ninja moved its API
under a game-namespaced path and changed formats:

  * Base is now ``https://poe.ninja/poe1/api`` (``poe2`` for PoE2).
  * ``/data/index-state`` (JSON) lists the current economy leagues and the build
    ``snapshotVersions`` — query it instead of hard-coding a league, because PoE1
    sits between leagues at times (only Standard/Hardcore live).
  * Economy is JSON at ``/economy/exchange/current/overview``.
  * Builds are now **protobuf** (``application/x-protobuf``), dictionary-compressed
    via ``/builds/dictionary/{hash}`` side tables — undocumented, no schema
    published. We expose the correct URLs and return raw bytes; decoding is
    deferred (see ``builds_search_raw``).

Responses may be gzip-encoded; we decode transparently. Standard library only.
"""

from __future__ import annotations

import gzip
import json
import urllib.error
import urllib.parse
import urllib.request
import zlib
from typing import Any

POE1_API = "https://poe.ninja/poe1/api"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) mirrorsmith/0.0.1 Chrome/126.0 Safari/537.36"


class NinjaError(RuntimeError):
    pass


def _get(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _UA,
            "Accept": "application/json, application/x-protobuf, */*",
            "Accept-Encoding": "gzip, deflate",
            "Referer": "https://poe.ninja/",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            enc = (resp.headers.get("Content-Encoding") or "").lower()
    except urllib.error.HTTPError as exc:
        raise NinjaError(f"HTTP {exc.code} for {url}") from exc
    if enc == "gzip":
        return gzip.decompress(raw)
    if enc == "deflate":
        return zlib.decompress(raw)
    return raw


def _get_json(url: str) -> Any:
    return json.loads(_get(url).decode("utf-8"))


# --- discovery -----------------------------------------------------------------
def index_state() -> dict[str, Any]:
    """Current PoE1 economy leagues + build snapshot versions (JSON).

    Keys of interest: ``economyLeagues`` (live now), ``buildLeagues``, and
    ``snapshotVersions`` — each snapshot has ``url``, ``snapshotName``, ``type``,
    ``version`` (the id used in build URLs), and ``passiveTree``/``atlasTree``.
    """
    return _get_json(f"{POE1_API}/data/index-state")


def current_economy_leagues() -> list[str]:
    """Names of leagues with live economy data right now (e.g. ['Standard', ...])."""
    return [lg.get("name", "") for lg in index_state().get("economyLeagues", []) if lg]


def default_league() -> str:
    """The most representative live economy league. Prefers the current temp
    league; falls back to Standard. Never hard-coded — derived from index-state."""
    leagues = current_economy_leagues()
    for name in leagues:
        if name not in ("Standard", "Hardcore", "SSF Standard", "Hardcore SSF Standard"):
            return name  # an active challenge league, if one is live
    return leagues[0] if leagues else "Standard"


# --- economy -------------------------------------------------------------------
def currency_overview(type_: str = "Currency", league: str | None = None) -> dict[str, Any]:
    """Currency/Fragment prices for a league. ``type_`` in {"Currency","Fragment"}.

    Returns the raw payload; ``lines`` holds priced entries (currencyTypeName,
    chaosEquivalent, ...), ``items`` holds the item metadata table.
    """
    league = league or default_league()
    q = urllib.parse.urlencode({"league": league, "type": type_})
    return _get_json(f"{POE1_API}/economy/exchange/current/overview?{q}")


# --- builds (protobuf; parse deferred) -----------------------------------------
def build_snapshot(league_url: str = "standard") -> dict[str, Any] | None:
    """Look up the current build snapshot descriptor for a league from index-state.

    Returns the snapshotVersions entry (with ``version`` id + ``passiveTree``), or
    None if that league has no build snapshot.
    """
    for snap in index_state().get("snapshotVersions", []):
        if snap.get("url") == league_url and snap.get("type") == "exp":
            return snap
    return None


def builds_search_raw(league_url: str = "standard") -> bytes:
    """Raw protobuf bytes of the top-player build corpus for a league.

    poe.ninja serves this as ``application/x-protobuf`` with no published schema,
    using ``/builds/dictionary/{hash}`` side tables for skill/item/tree names.
    Decoding is intentionally deferred — see the module docstring. Returns the
    undecoded bytes so a future parser (or a protobuf schema we reverse-engineer)
    can consume them.
    """
    snap = build_snapshot(league_url)
    if snap is None:
        raise NinjaError(f"no build snapshot for league {league_url!r}")
    version = snap["version"]
    return _get(f"{POE1_API}/builds/{version}/search?overview={snap['snapshotName']}&type=exp")


def builds_dictionary_raw(dict_hash: str) -> bytes:
    """Raw bytes of a builds dictionary side-table (also protobuf)."""
    return _get(f"{POE1_API}/builds/dictionary/{dict_hash}")
