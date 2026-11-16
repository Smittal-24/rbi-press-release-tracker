"""Command line helpers.

    python -m rbi_tracker.cli list                 # fetch the live page, show how each release classifies
    python -m rbi_tracker.cli list --all           # also show releases that are not tracked
    python -m rbi_tracker.cli list --file page.html  # use a saved copy of the page instead of the network
    python -m rbi_tracker.cli capture 63970 63983  # save cleaned copies of real releases as test fixtures

`list` never writes anything. `capture` writes only tests/fixtures/rbi/<prid>.html.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .fetch.classify import default_classifier
from .fetch.detail import clean_html, fetch_detail_html, page_headline
from .fetch.listing import FetchError, ParseError, fetch_listing, parse_listing
from .paths import ROOT


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


def cmd_capture(args: argparse.Namespace) -> int:
    """Save cleaned copies of real release pages so extractors are built and tested on real data."""
    out_dir = Path(args.out) if args.out else ROOT / "tests" / "fixtures" / "rbi"
    out_dir.mkdir(parents=True, exist_ok=True)
    failures = 0
    for prid in args.prids:
        try:
            html = fetch_detail_html(prid)
        except FetchError as e:
            print(f"{prid}: FAILED - {e}", file=sys.stderr)
            failures += 1      # one failure never blocks the rest
            continue
        (out_dir / f"{prid}.html").write_text(clean_html(html), encoding="utf-8")
        print(f"{prid}: saved ({len(html) // 1024} KB page) | {page_headline(html)}")
        time.sleep(1)          # be polite to RBI's server
    print(f"\nSaved to {out_dir}. {failures} failed.")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="rbi_tracker")
    sub = p.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list", help="show how the current press release page classifies")
    ls.add_argument("--all", action="store_true", help="include releases that are not tracked")
    ls.add_argument("--file", help="parse a saved HTML copy of the page instead of fetching")
    ls.set_defaults(func=cmd_list)
    cp = sub.add_parser("capture", help="save cleaned copies of release pages as test fixtures")
    cp.add_argument("prids", nargs="+", help="press release ids (prid) to capture")
    cp.add_argument("--out", help="output folder (default tests/fixtures/rbi)")
    cp.set_defaults(func=cmd_capture)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
