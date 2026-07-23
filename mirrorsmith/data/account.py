"""Character import via pathofexile.com's character-window endpoints.

The same mechanism Path of Building uses for "Import from site". For a character
whose account profile tab is **public**, these return the full build with zero
credentials. For a private profile, pass a ``poesessid`` session cookie.

Endpoints (GET, JSON):
  * ``/character-window/get-characters``     — account's character list
  * ``/character-window/get-passive-skills`` — allocated passive hashes, mastery
       choices, and tree jewels for one character
  * ``/character-window/get-items``          — equipped items + character summary

This is GGG's older website API. The officially-blessed path is OAuth
(``account:characters`` scope), but GGG is not accepting new OAuth applications
at time of writing, so this is the working route. Be a polite client: these are
rate-limited, so import on demand, not in a loop.
"""

from __future__ import annotations

import gzip
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from typing import Any

BASE = "https://www.pathofexile.com/character-window"

# GGG asks third-party clients to identify themselves with contact info.
_UA = "mirrorsmith/0.0.1 (PoE build tool; +https://github.com/bobbyroylee/mirrorsmith)"


class AccountError(RuntimeError):
    """Raised for GGG API errors (Forbidden = private profile or bad name)."""


def _get(path: str, params: dict[str, str], poesessid: str | None) -> Any:
    url = f"{BASE}/{path}?" + urllib.parse.urlencode(params)
    headers = {
        "User-Agent": _UA,
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate",
    }
    if poesessid:
        headers["Cookie"] = f"POESESSID={poesessid}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            enc = (resp.headers.get("Content-Encoding") or "").lower()
    except urllib.error.HTTPError as exc:
        body = b""
        try:
            body = exc.read()
            if (exc.headers.get("Content-Encoding") or "").lower() == "gzip":
                body = gzip.decompress(body)
        except Exception:  # noqa: BLE001
            pass
        msg = body.decode("utf-8", "replace")
        raise AccountError(f"HTTP {exc.code} from {path}: {msg[:200]}") from exc

    if enc == "gzip":
        raw = gzip.decompress(raw)
    elif enc == "deflate":
        raw = zlib.decompress(raw)
    data = json.loads(raw.decode("utf-8"))
    if isinstance(data, dict) and "error" in data:
        err = data["error"]
        raise AccountError(
            f"{path}: GGG error {err.get('code')} — {err.get('message')} "
            "(profile may be private: set Privacy Settings → characters tab to public, "
            "or pass a POESESSID)"
        )
    return data


def get_characters(account: str = "", realm: str = "pc",
                   poesessid: str | None = None) -> list[dict[str, Any]]:
    """List characters. GGG killed anonymous access to this endpoint, so a
    POESESSID is required. With a session and no ``account``, GGG returns the
    authenticated account's own characters."""
    params = {"realm": realm}
    if account:
        params["accountName"] = account
    return _get("get-characters", params, poesessid)


def get_passive_skills(account: str, character: str, realm: str = "pc",
                       poesessid: str | None = None) -> dict[str, Any]:
    """Allocated passive tree for one character.

    Returns GGG's payload; keys of interest: ``hashes`` (allocated node ids),
    ``hashes_ex`` (cluster-jewel nodes), ``mastery_effects``, ``items`` (jewels
    socketed in the tree), ``jewel_slots``.
    """
    return _get(
        "get-passive-skills",
        {"accountName": account, "character": character, "realm": realm},
        poesessid,
    )


def get_items(account: str, character: str, realm: str = "pc",
              poesessid: str | None = None) -> dict[str, Any]:
    """Equipped items + character summary (name, level, class, league)."""
    return _get(
        "get-items",
        {"accountName": account, "character": character, "realm": realm},
        poesessid,
    )


def fetch_character(account: str, character: str, realm: str = "pc",
                    poesessid: str | None = None) -> dict[str, Any]:
    """Convenience: pull both passives and items for a character as one dict.

    ``{"account", "character", "realm", "passives": <get-passive-skills>,
       "items": <get-items>}``. A small delay between calls keeps us polite to
    GGG's rate limiter.
    """
    passives = get_passive_skills(account, character, realm, poesessid)
    time.sleep(1.0)
    items = get_items(account, character, realm, poesessid)
    return {
        "account": account,
        "character": character,
        "realm": realm,
        "passives": passives,
        "items": items,
    }
