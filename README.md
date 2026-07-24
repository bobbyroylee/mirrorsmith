# mirrorsmith

**The ultimate Path of Exile 1 build maker, helper, and creator.**

A Mirror of Kalandra copies a perfect item. `mirrorsmith` smiths perfect *builds* — and to
do that on a game that changes dramatically every league, it stands on one non-negotiable
foundation: **accurate, up-to-date, real game data pulled from live sources, never guessed.**

This repository is being built foundation-first. Before any build logic exists, the data
pipeline is proven to pull the *current* league's passive tree, gems, mods, item bases, and
live economy — so everything downstream reasons about the real game, not a stale snapshot.

---

## Data architecture

Three layers, each from a source that stays current on its own:

### Layer 1 — Static game data ("the rules")
The passive tree, every skill gem, every mod, every item base, and stat translations.

**Source of truth: [`repoe-fork/repoe-fork.github.io`](https://github.com/repoe-fork/repoe-fork.github.io)**
— a community pipeline that extracts Path of Exile's own game files to clean, schema'd JSON
and republishes within hours of each patch. We **pin to an exact commit** (see
[`mirrorsmith/data/sources.py`](mirrorsmith/data/sources.py)) so any build is reproducible
even after a league reshapes the tree. Bumping to a new league is a one-line pin change.

Currently pinned: **3.28.0.16** (Mirage league).

### Layer 2 — Live meta & economy ("what's good and what it costs")
**Source: [poe.ninja](https://poe.ninja)** (API base `poe.ninja/poe1/api`, discovered from
live traffic — the old `/api/data/*` paths are dead). Two surfaces:
- **Economy** — JSON, wired and working. Live currency prices, league discovered dynamically
  from `/data/index-state` (PoE1 is often *between* leagues, so the league is never
  hard-coded). See [`ninja.py`](mirrorsmith/data/ninja.py).
- **Build corpus** — the top-ranked players' builds. poe.ninja now serves this as
  **undocumented `application/x-protobuf`** (dictionary-compressed binary, no published
  schema). We resolve the snapshot and fetch the raw bytes; **decoding is deferred** pending
  a decision to reverse-engineer the protobuf schema vs. sourcing example builds another way
  (e.g. official OAuth character import, PoB codes).

### Layer 3 — Player-specific ("import my character") — *working*
Import a real character's allocated tree + gear + gems via pathofexile.com's
`character-window` endpoints (the mechanism Path of Building uses). Two GGG
realities discovered the hard way:
- The **official OAuth API is currently closed to new applications** ("We are
  currently unable to process new applications"), so a `client_id` can't be
  obtained right now.
- **Anonymous access to character data is gone** — even public profiles now
  require a `POESESSID` session cookie.

So import needs a `POESESSID` (kept in a gitignored file, never printed/committed —
see [`scripts/save_poesessid.py`](scripts/save_poesessid.py) for a paste-once GUI).
The imported base-tree hashes resolve **100%** against our pinned tree — which is
also our correctness check that the pinned data matches the live game. Cluster-jewel
nodes (`hashes_ex`) resolve from the payload's own `jewel_data`; tattoos come from
`skill_overrides`. See [`account.py`](mirrorsmith/data/account.py) and
[`character.py`](mirrorsmith/character.py).

### Calculation reference
[Path of Building Community](https://github.com/PathOfBuildingCommunity/PathOfBuilding)
(pinned mentally to v2.65.0) is the gold-standard open-source damage/defense engine. As we
build our own calculations we align to its logic for correctness.

---

## Quickstart

```bash
# Pull the current-league data (tree first; large item files on demand)
python scripts/refresh_data.py

# Prove the tree: parse the live passive tree and print stats
python scripts/tree_stats.py

# Full end-to-end demo: rendered tree + live economy + build snapshot
python scripts/demo.py

# Import a real character (needs a POESESSID; see below)
python scripts/save_poesessid.py                        # paste-once GUI, saves gitignored file
python scripts/import_character.py --list               # your characters
python scripts/import_character.py "account#1234" "CharName"

# Analyze a build: aggregate the allocated tree into "what it grants"
python scripts/analyze_character.py "account#1234" "CharName"

# Web UI: pick a character, import, and see the full build sheet in the browser
python scripts/serve.py                                 # http://127.0.0.1:8770
```

## Layout

```
mirrorsmith/
  data/
    sources.py   # pinned source manifest (SHA, version, file list, poe.ninja base)
    fetch.py     # cached downloader — pulls pinned JSON, caches locally by version
    tree.py      # passive tree normalizer — Default.json -> typed node graph
    stats.py     # stat-translation renderer — raw stat-ids -> English
    ninja.py     # poe.ninja client — economy (JSON) + build corpus (protobuf, deferred)
    account.py   # character-window import (POESESSID) — allocated tree + gear
  character.py   # imported character -> build summary, joined against the tree
  build.py       # build reasoning — aggregate allocated nodes into categorized stat totals
  calc.py        # calc engine v1 — fused defensive totals (resists/suppress) + health check
  webapp.py      # local web UI (stdlib http.server) — build sheet + health check in the browser
scripts/
  refresh_data.py     # fetch & cache current-league data
  tree_stats.py       # validation: fetch + parse the tree, print stats
  demo.py             # end-to-end: rendered tree + live currency prices + build snapshot
  save_poesessid.py   # paste-once GUI to store your POESESSID (gitignored)
  import_character.py # import a real character and summarize the build
  analyze_character.py# aggregate a character into a categorized build sheet
  serve.py            # launch the local web UI
```

## Data ownership & attribution

All *game data* (passive tree, gems, mods, items, stats) is the property of
**Grinding Gear Games**, surfaced here via the community extraction projects credited above.
This repository's own **code** is MIT-licensed (see [LICENSE](LICENSE)). `mirrorsmith` is a
fan-made tool and is not affiliated with or endorsed by Grinding Gear Games.
