"""Pinned source manifest — the single place that says *which* game data we use.

Reproducibility rule: we pin Layer-1 static data to an exact upstream commit, not
a moving branch. A build made today must be re-derivable after a future league
reshapes the tree. Bumping to a new league = change ``REPOE_PIN`` (+ version) here
and re-run ``scripts/refresh_data.py``. Nothing else in the codebase hardcodes a
source URL.
"""

from __future__ import annotations

# --- Layer 1: static game data (repoe-fork, pinned to an exact commit) ---------
#
# repoe-fork extracts PoE's own game files to clean JSON and republishes within
# hours of each patch. https://github.com/repoe-fork/repoe-fork.github.io
REPOE_OWNER = "repoe-fork"
REPOE_REPO = "repoe-fork.github.io"

# Pinned commit (committed 2026-07-22). Data version 3.28.0.16 — Mirage league.
REPOE_PIN = "6f9877fef995686e9a52123acda7eb3e90c8356a"
REPOE_VERSION = "3.28.0.16"

# raw.githubusercontent.com serves a file at an exact commit — immutable, cacheable.
_RAW = "https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"


def repoe_url(path: str) -> str:
    """URL for a file in the pinned repoe-fork commit. ``path`` is repo-relative."""
    return _RAW.format(owner=REPOE_OWNER, repo=REPOE_REPO, ref=REPOE_PIN, path=path)


# Logical name -> repo-relative path. Grouped by how big / how often we need them.
# Small, always-needed files are pulled eagerly by refresh_data; the huge item
# files (gems 40MB, mods 33MB) are fetched on demand.
DATA_FILES: dict[str, str] = {
    # Passive tree (Layer 1 core) --------------------------------------------
    "tree": "data/passive_skill_trees/Default.json",           # ~2.3 MB
    "tree_alt_ascendancies": "data/passive_skill_trees/DefaultAltAscendancies.json",
    "atlas_tree": "data/passive_skill_trees/AtlasCurrentLeague.json",
    "characters": "data/characters.json",  # class base attributes + starting ascendancy
    # Items / crafting --------------------------------------------------------
    "base_items": "data/base_items.json",                      # ~7.5 MB
    "uniques": "data/uniques.json",                            # ~0.6 MB
    "item_classes": "data/item_classes.json",
    "cluster_jewels": "data/cluster_jewels.json",
    "cluster_jewel_notables": "data/cluster_jewel_notables.json",
    "essences": "data/essences.json",
    "fossils": "data/fossils.json",
    "crafting_bench_options": "data/crafting_bench_options.json",
    # Skills ------------------------------------------------------------------
    "gems": "data/gems.json",                                  # ~40 MB
    "gems_minimal": "data/gems_minimal.json",
    "gem_tags": "data/gem_tags.json",
    "active_skill_types": "data/active_skill_types.json",
    # Mods & stats ------------------------------------------------------------
    "mods": "data/mods.json",                                  # ~33 MB
    "mod_types": "data/mod_types.json",
    "mods_by_base": "data/mods_by_base.json",
    "stats": "data/stats.json",
    "stat_translations": "data/stat_translations.json",        # ~12 MB
}

# Files small/central enough to pull on every refresh. Big item/mod files are
# left for on-demand fetch (fetch.get) to keep a refresh fast.
EAGER_FILES: tuple[str, ...] = (
    "tree",
    "atlas_tree",
    "characters",
    "uniques",
    "item_classes",
    "cluster_jewels",
    "cluster_jewel_notables",
    "gems_minimal",
    "gem_tags",
    "mod_types",
)


# --- Layer 2: live meta & economy (poe.ninja) ----------------------------------
#
# poe.ninja's API is now game-namespaced (poe1/poe2) and no longer uses the old
# /api/data/currencyoverview path. Endpoints + formats live in ninja.py, which
# discovers the current league dynamically from /data/index-state (PoE1 is often
# between leagues, so a hard-coded league name would 404). Economy is JSON; the
# build corpus is now undocumented protobuf (parse deferred).
NINJA_POE1_API = "https://poe.ninja/poe1/api"


# --- Layer 3: official GGG API (deferred) --------------------------------------
# OAuth 2.0 client registration required before use; intentionally not wired yet.
GGG_API_BASE = "https://api.pathofexile.com"
GGG_OAUTH_AUTHORIZE = "https://www.pathofexile.com/oauth/authorize"
GGG_OAUTH_TOKEN = "https://www.pathofexile.com/oauth/token"
