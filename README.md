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
**Source: [poe.ninja](https://poe.ninja)** — currency/item prices (public API) and the
build corpus of the top-ranked players each league. This answers *"is this strong right
now"* and *"what does it cost to gear."* The build corpus also doubles as our example set
for learning and for validating the build engine.

### Layer 3 — Player-specific ("import my character") — *deferred*
The [official GGG Developer API](https://www.pathofexile.com/developer/docs) (OAuth 2.0)
can import a real account's characters, tree, and gear. Deferred until the core works —
poe.ninja + Path of Building import codes give us far more example builds with no auth.

### Calculation reference
[Path of Building Community](https://github.com/PathOfBuildingCommunity/PathOfBuilding)
(pinned mentally to v2.65.0) is the gold-standard open-source damage/defense engine. As we
build our own calculations we align to its logic for correctness.

---

## Quickstart

```bash
# Pull the current-league data (tree first; large item files on demand)
python scripts/refresh_data.py

# Prove it: parse the live passive tree and print stats
python scripts/tree_stats.py
```

## Layout

```
mirrorsmith/
  data/
    sources.py   # pinned source manifest (SHA, version, file list, poe.ninja base)
    fetch.py     # cached downloader — pulls pinned JSON, caches locally by version
    tree.py      # passive tree normalizer — Default.json -> typed node model
    ninja.py     # poe.ninja economy + build-corpus client
scripts/
  refresh_data.py  # fetch & cache current-league data
  tree_stats.py    # validation: fetch + parse the tree, print stats
```

## Data ownership & attribution

All *game data* (passive tree, gems, mods, items, stats) is the property of
**Grinding Gear Games**, surfaced here via the community extraction projects credited above.
This repository's own **code** is MIT-licensed (see [LICENSE](LICENSE)). `mirrorsmith` is a
fan-made tool and is not affiliated with or endorsed by Grinding Gear Games.
