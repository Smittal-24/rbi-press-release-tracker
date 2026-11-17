"""The daily job end to end, with fake network and fake Google Chat, on real saved pages."""
from datetime import date
from pathlib import Path

import pytest

from rbi_tracker.fetch.listing import FetchError, PressReleaseEntry
from rbi_tracker.job import run_job
from rbi_tracker.notify import gchat
from rbi_tracker.store.archive import ReleaseArchive
from rbi_tracker.store.records import PressReleaseStore

FIX = Path(__file__).parent / "fixtures" / "rbi"


def entry(prid, d, title):
    return PressReleaseEntry(prid, d, title, f"https://example.test/{prid}")


E_OLD = entry("63937", "2026-11-06", "Government Stock - Full Auction Results")
E_NEW = entry("63970", "2026-11-13", "Government Stock - Full Auction Results")
E_ANN = entry("63983", "2026-11-16", "Auction of Government of India Dated Securities")
E_SKIP = entry("60000", "2026-11-12", "Something RBI publishes that we do not track")


class FakePoster:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    def post(self, text):
        if self.fail:
            raise gchat.PostError("down")
        self.sent.append(text)


def detail(prid):
    return (FIX / f"{prid}.html").read_text(encoding="utf-8")


def make(tmp_path):
    return PressReleaseStore(tmp_path / "idx.json"), ReleaseArchive(tmp_path / "rel")


def go(tmp_path, entries, poster, store=None, archive=None, detail_fn=detail, today=date(2026, 11, 16)):
    s, a = make(tmp_path) if store is None else (store, archive)
    return s, a, run_job(store=s, archive=a, listing_fn=lambda: entries, detail_fn=detail_fn,
                         poster=poster, today=today, save=False)


def test_first_run_posts_only_last_7_days_and_diffs_against_baseline(tmp_path):
    p = FakePoster()
    s, a, r = go(tmp_path, [E_ANN, E_NEW, E_SKIP, E_OLD], p)
    assert (r.posted, r.baseline, r.failed) == (2, 1, 0)           # 63937 baseline; 63970 + 63983 posted
    assert s.records["63937"]["status"] == "baseline" and s.records["63970"]["status"] == "posted"
    assert len(p.sent) == 2 and "CG Auction - Result" in p.sent[0] and "13 Nov 2026" in p.sent[0]
    assert "Compared with the previous release (6 Nov 2026)" in p.sent[0]       # baseline is the comparison
    assert "First recorded" in p.sent[1]                                         # first CG announcement
    assert "60000" in s.ignored


def test_second_run_with_nothing_new_posts_quiet_line(tmp_path):
    s, a, _ = go(tmp_path, [E_NEW, E_OLD], FakePoster())
    p2 = FakePoster()
    _, _, r = go(tmp_path, [E_NEW, E_OLD], p2, s, a, today=date(2026, 11, 17))   # next day: nothing posted that day
    assert r.posted == 0 and p2.sent == [gchat.format_quiet("2026-11-17")]


def test_new_release_on_later_run_posts_once(tmp_path):
    s, a, _ = go(tmp_path, [E_NEW, E_OLD], FakePoster())
    p2 = FakePoster()
    _, _, r = go(tmp_path, [E_ANN, E_NEW, E_OLD], p2, s, a)
    assert r.posted == 1 and len(p2.sent) == 1 and "CG Auction - Announcement" in p2.sent[0]


def test_extraction_failure_warns_then_retries_next_run(tmp_path):
    def broken(prid):
        return "<html><body>nothing useful</body></html>"
    p = FakePoster()
    s, a, r = go(tmp_path, [E_NEW, E_OLD], p, detail_fn=lambda prid: detail(prid) if prid == "63937" else broken(prid))
    assert r.failed == 1 and s.records["63970"]["status"] == "extract_failed"
    assert any("WARNING" in m and "Will retry" in m for m in p.sent)
    p2 = FakePoster()
    _, _, r2 = go(tmp_path, [E_NEW, E_OLD], p2, s, a)               # RBI page now readable
    assert r2.posted == 1 and s.records["63970"]["status"] == "posted"


def test_gives_up_after_three_attempts(tmp_path):
    def broken(prid):
        raise FetchError("HTTP 500")
    s, a = make(tmp_path)
    for _ in range(5):
        go(tmp_path, [E_NEW], FakePoster(), s, a, detail_fn=broken)
    assert s.records["63970"]["attempts"] == 3


def test_post_failure_keeps_release_and_retries_without_refetching(tmp_path):
    s, a, r = go(tmp_path, [E_NEW, E_OLD], FakePoster(fail=True))
    assert r.failed >= 1 and s.records["63970"]["status"] == "post_failed"
    def no_network(prid):
        raise AssertionError("must not refetch")
    p = FakePoster()
    _, _, r2 = go(tmp_path, [E_NEW, E_OLD], p, s, a, detail_fn=no_network)
    assert s.records["63970"]["status"] == "posted" and len(p.sent) >= 1


def test_listing_failure_posts_warning_and_fails(tmp_path):
    s, a = make(tmp_path)
    p = FakePoster()
    def bad():
        raise FetchError("HTTP 403 fetching page")
    r = run_job(store=s, archive=a, listing_fn=bad, detail_fn=detail, poster=p, today=date(2026, 11, 16), save=False)
    assert not r.ok and "403" in p.sent[0]


def test_message_never_exceeds_google_chat_limit():
    long = [f"line {i} " + "x" * 200 for i in range(100)]
    assert len(gchat._clip(long)) <= 4096


def test_webhook_url_required():
    with pytest.raises(gchat.PostError):
        gchat.GChatPoster(url="")


def test_archive_dry_run_writes_nothing(tmp_path):
    a = ReleaseArchive(tmp_path / "rel", dry_run=True)
    s = PressReleaseStore(tmp_path / "idx.json")
    run_job(store=s, archive=a, listing_fn=lambda: [E_NEW], detail_fn=detail, poster=FakePoster(),
            today=date(2026, 11, 16), save=False)
    assert not (tmp_path / "rel").exists()