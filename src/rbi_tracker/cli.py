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


def cmd_run(args: argparse.Namespace) -> int:
    """The daily job. --dry-run prints the messages and writes nothing."""
    from datetime import datetime

    from .fetch.detail import fetch_detail_html
    from .job import IST, run_job
    from .notify.gchat import GChatPoster, PostError, PrintPoster
    from .paths import DATA_DIR, INDEX_FILE
    from .store.archive import ReleaseArchive
    from .store.records import PressReleaseStore

    try:
        poster = PrintPoster() if args.dry_run else GChatPoster()
    except PostError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    store = PressReleaseStore.load(INDEX_FILE)
    archive = ReleaseArchive(DATA_DIR / "releases", dry_run=args.dry_run)
    res = run_job(store=store, archive=archive, listing_fn=fetch_listing, detail_fn=fetch_detail_html,
                  poster=poster, today=datetime.now(IST).date(), bootstrap_days=args.bootstrap_days,
                  pause=1.0, save=not args.dry_run)
    print(f"\nposted {res.posted}, baseline {res.baseline}, failed {res.failed}, "
          f"listing {'ok' if res.listing_ok else 'FAILED'}{' (dry run: nothing saved)' if args.dry_run else ''}")
    return 0 if res.ok else 1


def cmd_test_webhook(args: argparse.Namespace) -> int:
    from .notify.gchat import GChatPoster, PostError
    try:
        GChatPoster().post("RBI tracker: webhook test message. If you can read this, Google Chat is connected.")
    except PostError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print("Test message sent.")
    return 0


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
    rn = sub.add_parser("run", help="the daily job: detect new releases, extract, diff, post to Google Chat")
    rn.add_argument("--dry-run", action="store_true", help="print messages instead of posting; save nothing")
    rn.add_argument("--bootstrap-days", type=int, default=7,
                    help="first run only: post releases from the last N days, record older ones silently")
    rn.set_defaults(func=cmd_run)
    tw = sub.add_parser("test-webhook", help="send one test message to Google Chat")
    tw.set_defaults(func=cmd_test_webhook)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
