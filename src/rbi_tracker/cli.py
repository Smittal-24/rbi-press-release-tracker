"""Command line helpers.

    python -m rbi_tracker.cli list                 # fetch the live page, show how each release classifies
    python -m rbi_tracker.cli list --all           # also show releases that are not tracked
    python -m rbi_tracker.cli list --file page.html  # use a saved copy of the page instead of the network
    python -m rbi_tracker.cli capture 63970 63983  # save cleaned copies of real releases as test fixtures
    python -m rbi_tracker.cli run [--dry-run]      # the daily job
    python -m rbi_tracker.cli repost --list | <prid> ...   # post saved releases again in the current format
    python -m rbi_tracker.cli sync-workbook        # add already-processed releases to the Excel workbook

`list` never writes anything. `capture` writes only tests/fixtures/rbi/<prid>.html.
"""
from __future__ import annotations

import argparse
import os
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
    from .job import EVENING_SCHEDULE, IST, run_job, sync_workbook
    from .notify.gchat import GChatPoster, PostError, PrintPoster
    from .paths import DATA_DIR, INDEX_FILE
    from .store.archive import ReleaseArchive
    from .store.records import PressReleaseStore
    from .store.workbook import Workbook

    try:
        poster = PrintPoster() if args.dry_run else GChatPoster()
    except PostError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    store = PressReleaseStore.load(INDEX_FILE)
    archive = ReleaseArchive(DATA_DIR / "releases", dry_run=args.dry_run)
    workbook = Workbook(DATA_DIR / "RBI_Tracker.xlsx", dry_run=args.dry_run)
    trigger = {"schedule": "scheduled"}.get(os.environ.get("GITHUB_EVENT_NAME", ""), "manual")
    schedule = os.environ.get("EVENT_SCHEDULE", "")          # set by the workflow for scheduled runs
    quiet_line = not schedule or schedule == EVENING_SCHEDULE  # the earlier scheduled run stays silent
    added, _ = sync_workbook(store, archive, workbook)      # one-off catch-up for releases saved before the workbook
    if added:
        print(f"Workbook catch-up: added {added} earlier release(s) to the Release Log.")
    res = run_job(store=store, archive=archive, listing_fn=fetch_listing, detail_fn=fetch_detail_html,
                  poster=poster, today=datetime.now(IST).date(), bootstrap_days=args.bootstrap_days,
                  pause=1.0, save=not args.dry_run, workbook=workbook, trigger=trigger, quiet_line=quiet_line)
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


def cmd_repost(args: argparse.Namespace) -> int:
    """Post saved releases to Google Chat again, in the current message format. Uses saved data only:
    nothing is fetched from RBI and no status is changed. --list shows what is saved."""
    from .engine import compare
    from .notify.gchat import GChatPoster, PostError, PrintPoster, format_release
    from .paths import DATA_DIR, INDEX_FILE, load_yaml
    from .store.archive import ReleaseArchive
    from .store.records import PressReleaseStore
    from .store.workbook import Workbook

    store = PressReleaseStore.load(INDEX_FILE)
    archive = ReleaseArchive(DATA_DIR / "releases")
    workbook = Workbook(DATA_DIR / "RBI_Tracker.xlsx", dry_run=args.dry_run)
    if args.list:
        for r in sorted(store.records.values(), key=lambda r: (r["release_date"], int(r["prid"]))):
            print(f"{r['prid']:>6}  {r['release_date']}  {r['item_id']:<20} {r.get('status', 'new'):<15} {r['title'][:55]}")
        print(f"\n{len(store.records)} tracked releases recorded.")
        return 0
    if not args.prids:
        print("ERROR: give one or more press release ids (see: repost --list)", file=sys.stderr)
        return 2
    try:
        poster = PrintPoster() if args.dry_run else GChatPoster()
    except PostError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    labels = {i["id"]: i["label"] for i in load_yaml("items.yaml")["items"]}
    failures = 0
    for prid in args.prids:
        rec = store.records.get(prid)
        if rec is None:
            print(f"{prid}: not a tracked release in the store", file=sys.stderr)
            failures += 1
            continue
        found = [r for p, r in archive.load_all(rec["item_id"]) if p == prid]
        if not found:
            print(f"{prid}: no saved data for this release yet (the daily job has not extracted it)", file=sys.stderr)
            failures += 1
            continue
        release = found[0]
        previous = archive.previous(rec["item_id"], release.release_date, prid)
        diff = compare(release, previous, archive.matching_announcement(rec["item_id"], release.release_date, prid))
        text = "(Re-posted in the updated format)\n" + format_release(
            labels.get(rec["item_id"], rec["item_id"]), release, diff, rec["detail_url"], previous)
        try:
            poster.post(text)
        except PostError as e:
            print(f"{prid}: FAILED - {e}", file=sys.stderr)
            failures += 1
            continue
        if not args.dry_run:
            workbook.log_notification("repost", "manual", text, labels.get(rec["item_id"], rec["item_id"]),
                                      rec["item_id"], release.release_date, prid)
        print(f"{prid}: {'previewed' if args.dry_run else 'reposted'} ({rec['item_id']}, {rec['release_date']})")
    workbook.save()
    return 1 if failures else 0


def cmd_sync_workbook(args: argparse.Namespace) -> int:
    """Add releases the job already processed (before the workbook existed) to the Release Log and,
    for ones that were posted, the Change Log. Never duplicates; never touches existing rows.
    The Chat Notification Log is not backfilled: exact posting times were not recorded."""
    from .job import sync_workbook
    from .paths import DATA_DIR, INDEX_FILE
    from .store.archive import ReleaseArchive
    from .store.records import PressReleaseStore
    from .store.workbook import Workbook

    store = PressReleaseStore.load(INDEX_FILE)
    archive = ReleaseArchive(DATA_DIR / "releases")
    workbook = Workbook(DATA_DIR / "RBI_Tracker.xlsx", dry_run=args.dry_run)
    added, changes = sync_workbook(store, archive, workbook)
    workbook.save()
    print(f"Added {added} release(s) and {changes} change row(s)" + (" (dry run: nothing saved)" if args.dry_run else "."))
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
    rp = sub.add_parser("repost", help="post saved releases to Google Chat again in the current format")
    rp.add_argument("prids", nargs="*", help="press release ids to repost")
    rp.add_argument("--list", action="store_true", help="list the releases saved so far, with their ids")
    rp.add_argument("--dry-run", action="store_true", help="print the messages instead of posting")
    rp.set_defaults(func=cmd_repost)
    sw = sub.add_parser("sync-workbook", help="add already-processed releases to the Excel workbook")
    sw.add_argument("--dry-run", action="store_true", help="show what would be added; save nothing")
    sw.set_defaults(func=cmd_sync_workbook)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())