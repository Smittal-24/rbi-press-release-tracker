"""Step 5 patch: add the `run` and `test-webhook` commands to cli.py. Safe to run twice."""
import pathlib

FUNCS = 'def cmd_run(args: argparse.Namespace) -> int:\n    """The daily job. --dry-run prints the messages and writes nothing."""\n    from datetime import datetime\n\n    from .fetch.detail import fetch_detail_html\n    from .job import IST, run_job\n    from .notify.gchat import GChatPoster, PostError, PrintPoster\n    from .paths import DATA_DIR, INDEX_FILE\n    from .store.archive import ReleaseArchive\n    from .store.records import PressReleaseStore\n\n    try:\n        poster = PrintPoster() if args.dry_run else GChatPoster()\n    except PostError as e:\n        print(f"ERROR: {e}", file=sys.stderr)\n        return 2\n    store = PressReleaseStore.load(INDEX_FILE)\n    archive = ReleaseArchive(DATA_DIR / "releases", dry_run=args.dry_run)\n    res = run_job(store=store, archive=archive, listing_fn=fetch_listing, detail_fn=fetch_detail_html,\n                  poster=poster, today=datetime.now(IST).date(), bootstrap_days=args.bootstrap_days,\n                  pause=1.0, save=not args.dry_run)\n    print(f"\\nposted {res.posted}, baseline {res.baseline}, failed {res.failed}, "\n          f"listing {\'ok\' if res.listing_ok else \'FAILED\'}{\' (dry run: nothing saved)\' if args.dry_run else \'\'}")\n    return 0 if res.ok else 1\n\n\ndef cmd_test_webhook(args: argparse.Namespace) -> int:\n    from .notify.gchat import GChatPoster, PostError\n    try:\n        GChatPoster().post("RBI tracker: webhook test message. If you can read this, Google Chat is connected.")\n    except PostError as e:\n        print(f"ERROR: {e}", file=sys.stderr)\n        return 1\n    print("Test message sent.")\n    return 0\n\n\n'
PARSER = '    rn = sub.add_parser("run", help="the daily job: detect new releases, extract, diff, post to Google Chat")\n    rn.add_argument("--dry-run", action="store_true", help="print messages instead of posting; save nothing")\n    rn.add_argument("--bootstrap-days", type=int, default=7,\n                    help="first run only: post releases from the last N days, record older ones silently")\n    rn.set_defaults(func=cmd_run)\n    tw = sub.add_parser("test-webhook", help="send one test message to Google Chat")\n    tw.set_defaults(func=cmd_test_webhook)\n'

p = pathlib.Path("src/rbi_tracker/cli.py")
t = p.read_text(encoding="utf-8")
if "def cmd_run" in t:
    print("already applied: cli.py")
else:
    assert "def main(argv" in t and "    args = p.parse_args(argv)" in t, "cli.py is not in the expected shape"
    t = t.replace("def main(argv", FUNCS + "def main(argv", 1)
    t = t.replace("    args = p.parse_args(argv)", PARSER + "    args = p.parse_args(argv)", 1)
    p.write_text(t, encoding="utf-8", newline="\n")
    print("patched: cli.py")