"""Command line helpers.

    python -m rbi_tracker.cli list                 # fetch the live page, show how each release classifies
    python -m rbi_tracker.cli list --all           # also show releases that are not tracked
    python -m rbi_tracker.cli list --file page.html  # use a saved copy of the page instead of the network

`list` never writes anything: it is a read-only check.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .fetch.classify import default_classifier
from .fetch.listing import FetchError, ParseError, fetch_listing, parse_listing


def cmd_list(args: argparse.Namespace) -> int:
    try:
        if args.file:
            entries = parse_listing(Path(args.file).read_text(encoding="utf-8", errors="replace"))
        else:
            entries = fetch_listing()
    except (FetchError, ParseError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    clf = default_classifier()
    tracked = 0
    for e in entries:
        item = clf.classify(e.title)
        tracked += item is not None
        if item or args.all:
            print(f"{e.release_date}  {item or '-':<18} {e.prid:>6}  {e.title[:90]}")
    print(f"\n{len(entries)} releases on the page, {tracked} tracked, {len(entries) - tracked} not tracked.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="rbi_tracker")
    sub = p.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list", help="show how the current press release page classifies")
    ls.add_argument("--all", action="store_true", help="include releases that are not tracked")
    ls.add_argument("--file", help="parse a saved HTML copy of the page instead of fetching")
    ls.set_defaults(func=cmd_list)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
