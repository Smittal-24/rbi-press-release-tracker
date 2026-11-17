"""`repost` rebuilds a message from saved data only: no RBI fetch, no status change."""
from pathlib import Path

from rbi_tracker import cli, paths
from rbi_tracker.extract.extract import extract
from rbi_tracker.fetch.listing import PressReleaseEntry
from rbi_tracker.store.archive import ReleaseArchive
from rbi_tracker.store.records import PressReleaseStore

FIX = Path(__file__).parent / "fixtures" / "rbi"


def setup(tmp_path, monkeypatch, save_release=True):
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(paths, "INDEX_FILE", tmp_path / "index" / "press_releases.json")
    store = PressReleaseStore(paths.INDEX_FILE)
    store.add_tracked(PressReleaseEntry("63956", "2026-11-11", "Treasury Bills: Full Auction Results",
                                        "https://example.test/63956"), "tbill_result")
    store.records["63956"]["status"] = "posted"
    store.save()
    if save_release:
        rel = extract("tbill_result", (FIX / "63956.html").read_text(encoding="utf-8"), release_date="2026-11-11")
        ReleaseArchive(tmp_path / "releases").save("63956", rel)


def test_repost_dry_run_prints_new_format_and_changes_nothing(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
    before = paths.INDEX_FILE.read_text(encoding="utf-8")
    assert cli.main(["repost", "--dry-run", "63956"]) == 0
    out = capsys.readouterr().out
    assert "Re-posted in the updated format" in out and "Yield chg vs prev (bps)" in out and "previewed" in out
    assert paths.INDEX_FILE.read_text(encoding="utf-8") == before


def test_repost_list_shows_ids_and_status(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
    assert cli.main(["repost", "--list"]) == 0
    assert "63956" in capsys.readouterr().out


def test_repost_without_saved_data_fails_clearly(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch, save_release=False)
    assert cli.main(["repost", "--dry-run", "63956"]) == 1
    assert "no saved data" in capsys.readouterr().err


def test_repost_unknown_id_fails(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
    assert cli.main(["repost", "--dry-run", "11111"]) == 1


def test_repost_needs_webhook_when_not_dry_run(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
    monkeypatch.delenv("GCHAT_WEBHOOK_URL", raising=False)
    assert cli.main(["repost", "63956"]) == 2