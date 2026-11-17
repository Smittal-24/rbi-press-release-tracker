"""Two scheduled runs a day: the quiet line comes only from the evening run, and only on a day with no posts."""
from datetime import date
from pathlib import Path

from rbi_tracker.fetch.listing import PressReleaseEntry
from rbi_tracker.job import EVENING_SCHEDULE, run_job
from rbi_tracker.notify import gchat
from rbi_tracker.store.archive import ReleaseArchive
from rbi_tracker.store.records import PressReleaseStore

FIX = Path(__file__).parent / "fixtures" / "rbi"
OLD = PressReleaseEntry("63937", "2026-11-06", "Government Stock - Full Auction Results", "https://example.test/63937")
NEW = PressReleaseEntry("63970", "2026-11-13", "Government Stock - Full Auction Results", "https://example.test/63970")
TODAY = date(2026, 11, 16)


class Poster:
    def __init__(self):
        self.sent = []

    def post(self, text):
        self.sent.append(text)


def detail(prid):
    return (FIX / f"{prid}.html").read_text(encoding="utf-8")


def run(tmp_path, entries, store=None, quiet_line=True, today=TODAY):
    store = store or PressReleaseStore(tmp_path / "idx.json")
    p = Poster()
    run_job(store=store, archive=ReleaseArchive(tmp_path / "rel"), listing_fn=lambda: entries, detail_fn=detail,
            poster=p, today=today, save=False, quiet_line=quiet_line)
    return store, p


def test_workflow_has_both_schedules_and_matching_evening_constant():
    wf = (Path(__file__).parent.parent / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")
    assert 'cron: "0 10 * * *"' in wf and f'cron: "{EVENING_SCHEDULE}"' in wf and "EVENT_SCHEDULE" in wf


def test_afternoon_run_stays_silent_when_nothing_new(tmp_path):
    store, _ = run(tmp_path, [OLD])
    _, p = run(tmp_path, [OLD], store, quiet_line=False)
    assert p.sent == []


def test_evening_run_posts_quiet_line_when_nothing_all_day(tmp_path):
    store, _ = run(tmp_path, [OLD])
    _, p = run(tmp_path, [OLD], store, quiet_line=True)
    assert p.sent == [gchat.format_quiet("2026-11-16")]


def test_evening_run_stays_silent_if_something_was_posted_earlier_today(tmp_path):
    store, first = run(tmp_path, [NEW, OLD])                       # "afternoon": posts the new release today
    assert len(first.sent) == 1 and store.records["63970"]["posted_on"] == "2026-11-16"
    _, evening = run(tmp_path, [NEW, OLD], store, quiet_line=True)
    assert evening.sent == []


def test_quiet_line_returns_the_next_day(tmp_path):
    store, _ = run(tmp_path, [NEW, OLD])
    _, p = run(tmp_path, [NEW, OLD], store, quiet_line=True, today=date(2026, 11, 17))
    assert p.sent == [gchat.format_quiet("2026-11-17")]


def test_new_release_is_posted_once_across_two_runs(tmp_path):
    store, afternoon = run(tmp_path, [OLD])
    store2, a = run(tmp_path, [NEW, OLD], store, quiet_line=False)
    _, b = run(tmp_path, [NEW, OLD], store2, quiet_line=True)
    assert len(a.sent) == 1 and b.sent == []