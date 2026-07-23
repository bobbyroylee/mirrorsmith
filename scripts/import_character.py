#!/usr/bin/env python3
"""Import a real character from pathofexile.com and summarize the build.

GGG killed anonymous access to the character-window endpoints, so a POESESSID
session cookie is required. Provide it WITHOUT pasting it into a shell/chat:
put the value in a gitignored file and point the script at it.

    # one-time: save your cookie (never committed; see .gitignore)
    #   the file should contain ONLY the POESESSID value
    python scripts/import_character.py --list --poesessid-file secret.poesessid
    python scripts/import_character.py "AccountName" "CharacterName" --poesessid-file secret.poesessid

POESESSID resolution order: --poesessid-file, then $POESESSID, then
~/.mirrorsmith/poesessid. The value is never printed, logged, or saved.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mirrorsmith.character import summarize  # noqa: E402
from mirrorsmith.data import account  # noqa: E402
from mirrorsmith.data.stats import StatTranslator  # noqa: E402
from mirrorsmith.data.tree import PassiveTree  # noqa: E402


def _load_poesessid(explicit_file: str | None) -> str | None:
    if explicit_file:
        return Path(explicit_file).read_text(encoding="utf-8").strip()
    if os.environ.get("POESESSID"):
        return os.environ["POESESSID"].strip()
    default = Path.home() / ".mirrorsmith" / "poesessid"
    if default.exists():
        return default.read_text(encoding="utf-8").strip()
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("account", nargs="?", default="", help="PoE account name (optional with a session)")
    ap.add_argument("character", nargs="?", default="", help="exact character name")
    ap.add_argument("--realm", default="pc", choices=["pc", "xbox", "sony"])
    ap.add_argument("--poesessid-file", dest="poesessid_file", default=None,
                    help="path to a file containing ONLY your POESESSID value")
    ap.add_argument("--list", action="store_true", help="list your characters and exit")
    ap.add_argument("--save", default=None, help="also write the raw import JSON here")
    args = ap.parse_args()

    poesessid = _load_poesessid(args.poesessid_file)
    if not poesessid:
        print("no POESESSID found. Save your cookie value to a file and pass "
              "--poesessid-file, or set $POESESSID, or ~/.mirrorsmith/poesessid.")
        return 2

    if args.list:
        try:
            chars = account.get_characters(args.account, args.realm, poesessid)
        except account.AccountError as exc:
            print(f"list failed: {exc}")
            return 1
        print(f"characters ({len(chars)}):")
        for c in chars:
            print(f"    {c.get('name'):<24} lvl {c.get('level'):<3} "
                  f"{c.get('class'):<12} [{c.get('league')}]")
        return 0

    if not args.character:
        print("character name required (or use --list to see your characters).")
        return 2

    print(f"Importing {args.character} @ {args.account or '(session account)'} ({args.realm})...\n")
    try:
        imported = account.fetch_character(
            args.account, args.character, args.realm, poesessid
        )
    except account.AccountError as exc:
        print(f"import failed: {exc}")
        return 1

    if args.save:
        Path(args.save).write_text(json.dumps(imported, indent=1), encoding="utf-8")
        print(f"raw import saved to {args.save}\n")

    tree = PassiveTree.load()
    translator = StatTranslator.load()
    b = summarize(imported, tree, translator)

    print(f"{'=' * 60}")
    print(f"{b.character}  —  {b.char_class or '?'}  lvl {b.level or '?'}  [{b.league or '?'}]")
    print(f"{'=' * 60}")
    print(f"base tree nodes  : {b.base_resolved}/{b.base_allocated} resolved "
          f"({b.base_resolve_rate * 100:.1f}%)  <- tree-model validation")
    if b.unknown_base_hashes:
        print(f"  UNRESOLVED base : {b.unknown_base_hashes[:10]}"
              f"{' ...' if len(b.unknown_base_hashes) > 10 else ''}")
    print(f"cluster jewel    : {b.cluster_resolved}/{b.cluster_allocated} resolved "
          "(from jewel_data)")

    print(f"\nkeystones ({len(b.keystones)}):")
    for n in b.keystones:
        print(f"    {n.name}")

    print(f"\nnotables ({len(b.notables)}):")
    for n in b.notables:
        print(f"    {n.name}")

    if b.cluster_notables:
        print(f"\ncluster-jewel notables ({len(b.cluster_notables)}):")
        for name in b.cluster_notables:
            print(f"    {name}")

    if b.masteries:
        print(f"\nmasteries ({len(b.masteries)}):")
        for m in b.masteries:
            print(f"    {m}")

    if b.tattoos:
        print(f"\ntattoos ({len(b.tattoos)}):")
        for t in b.tattoos:
            print(f"    {t}")

    if b.main_gems:
        print(f"\nskill gems ({len(b.main_gems)}):")
        print("    " + ", ".join(b.main_gems))

    if b.equipment:
        print(f"\nequipment ({len(b.equipment)}):")
        for e in b.equipment:
            print(f"    {e}")

    print("\ndone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
