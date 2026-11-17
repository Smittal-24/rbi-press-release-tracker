"""Excel workbook: appended to, never overwritten; logs releases, changes and Chat messages."""
from datetime import date
from pathlib import Path

from openpyxl import load_workbook

from rbi_tracker import cli, paths
from rbi_tracker.fetch.listing import PressReleaseEntry
from rbi_tracker.job import run_job
from rbi_tracker.store.archive import ReleaseArchive
from rbi_tracker.store.records import PressReleaseStore
from rbi_tracker.store.workbook import Workbook, key_figures
from rbi_tracker.extract.extract import extract

FIX = Path(__file__).parent / "fixtures" / "rbi"


def entry(prid, d, title):
    return PressReleaseEntry(prid, d, title, f"https://example.test/{prid}")


E_OLD = entry("63937", "2026-11-06", "Government Stock - Full Auction Results")
E_NEW = entry("63970", "2026-11-13", "Government Stock - Full Auction Results")
E_BOP = entry("63974", "2026-11-13", "Developments in India's Balance of Payments during the Second Quarter")


class Poster:
    def __init__(self):
        self.sent = []

    def post(self, text):
        self.sent.append(text)


def detail(prid):
    return (FIX / f"{prid}.html").read_text(encoding="utf-8")


def rows(path, sheet):
    ws = load_workbook(path)[sheet]
    return list(ws.iter_rows(min_row=2, values_only=True))


def run(tmp_path, entries, wb, store=None, trigger="scheduled", detail_fn=detail):
    store = store or PressReleaseStore(tmp_path / "idx.json")
    run_job(store=store, archive=ReleaseArchive(tmp_path / "rel"), listing_fn=lambda: entries, detail_fn=detail_fn,
            poster=Poster(), today=date(2026, 11, 16), save=True, workbook=wb, trigger=trigger)
    return store


def test_job_logs_release_changes_and_notifications(tmp_path):
    path = tmp_path / "wb.xlsx"
    run(tmp_path, [E_NEW, E_OLD, E_BOP], Workbook(path))
    rel = rows(path, "Release Log")
    assert {r[5] for r in rel} == {"63937", "63970", "63974"}          # prid column
    by = {r[5]: r for r in rel}
    assert by["63937"][6] == "baseline" and by["63970"][6] == "scheduled"
    assert "10Y" in by["63970"][7] and "7.3203" in by["63970"][7]       # key figures
    chg = rows(path, "Change Log")
    assert chg and all(r[4] in ("63970", "63974") for r in chg)         # none for the silent baseline
    assert any(r[14] and "year" in r[14] for r in chg if r[4] == "63974")  # note text as sent
    note = rows(path, "Chat Notification Log")
    assert {r[1] for r in note} == {"release"} and len(note) == 2 and all(r[6] == "scheduled" for r in note)


def test_rows_are_appended_never_overwritten(tmp_path):
    path = tmp_path / "wb.xlsx"
    store = run(tmp_path, [E_OLD], Workbook(path))
    first = rows(path, "Release Log")
    run(tmp_path, [E_NEW, E_OLD], Workbook(path), store)
    second = rows(path, "Release Log")
    assert len(second) == len(first) + 1 and second[0] == first[0]
    quiet = rows(path, "Chat Notification Log")
    assert any(r[1] == "release" for r in quiet)


def test_quiet_day_message_is_logged_with_its_type(tmp_path):
    path = tmp_path / "wb.xlsx"
    store = run(tmp_path, [E_OLD], Workbook(path))
    run(tmp_path, [E_OLD], Workbook(path), store, trigger="manual")
    last = rows(path, "Chat Notification Log")[-1]
    assert last[1] == "no-new-releases" and last[6] == "manual"


def test_release_logged_once_even_on_retry(tmp_path):
    path = tmp_path / "wb.xlsx"
    wb = Workbook(path)
    rel = extract("tbill_result", detail("63956"), release_date="2026-11-11")
    assert wb.log_release(rel, "T-Bill Auction - Result", "63956", "scheduled") is True
    assert wb.log_release(rel, "T-Bill Auction - Result", "63956", "scheduled") is False
    wb.save()
    assert len(rows(path, "Release Log")) == 1


def test_dry_run_never_writes_the_file(tmp_path):
    path = tmp_path / "wb.xlsx"
    run(tmp_path, [E_NEW, E_OLD], Workbook(path, dry_run=True))
    assert not path.exists()


def test_workbook_failure_does_not_stop_posting(tmp_path):
    class Broken(Workbook):
        def log_release(self, *a, **k):
            raise RuntimeError("disk full")
    poster = Poster()
    store = PressReleaseStore(tmp_path / "idx.json")
    res = run_job(store=store, archive=ReleaseArchive(tmp_path / "rel"), listing_fn=lambda: [E_NEW, E_OLD],
                  detail_fn=detail, poster=poster, today=date(2026, 11, 16), save=True,
                  workbook=Broken(tmp_path / "wb.xlsx"), trigger="scheduled")
    assert res.posted == 1 and len(poster.sent) == 1 and any("WORKBOOK LOGGING FAILED" in m for m in res.messages)


def test_key_figures_for_publications():
    assert "current_account_balance=-7.4" in key_figures(extract("bop", detail("63974")))
    assert "decision=hike" in key_figures(extract("mpc_minutes", detail("63839")))


def test_sync_workbook_backfills_processed_releases_without_duplicates(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(paths, "INDEX_FILE", tmp_path / "index" / "press_releases.json")
    store = PressReleaseStore(paths.INDEX_FILE)
    arch = ReleaseArchive(tmp_path / "releases")
    for e, item in ((E_OLD, "cg_result"), (E_BOP, "bop")):
        store.add_tracked(e, item)
        arch.save(e.prid, extract(item, detail(e.prid), release_date=e.release_date))
    store.records["63937"]["status"] = "baseline"
    store.records["63974"]["status"] = "posted"
    store.save()
    assert cli.main(["sync-workbook"]) == 0
    assert "Added 2 release(s)" in capsys.readouterr().out
    path = tmp_path / "RBI_Tracker.xlsx"
    assert {r[6] for r in rows(path, "Release Log")} == {"backfill"}
    assert {r[4] for r in rows(path, "Change Log")} == {"63974"}
    assert cli.main(["sync-workbook"]) == 0
    assert "Added 0 release(s)" in capsys.readouterr().out
    assert len(rows(path, "Release Log")) == 2