"""The daily job: find new releases, extract, diff against the previous release, post one message each.

Statuses kept on each tracked record in the press release store:
  baseline        recorded on the first run (older than the bootstrap window); never posted
  posted          extracted and posted to Google Chat
  extract_failed  could not be fetched/read; retried on later runs (up to MAX_ATTEMPTS)
  post_failed     extracted but Google Chat delivery failed; retried on later runs
A record with no status is brand new.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Callable

from .engine import compare
from .extract.extract import extract
from .fetch.discover import discover_new
from .fetch.listing import FetchError, ParseError
from .notify import gchat
from .paths import load_yaml
from .store.archive import ReleaseArchive
from .store.records import PressReleaseStore

IST = timezone(timedelta(hours=5, minutes=30))     # India has no daylight saving: a fixed offset is exact
MAX_ATTEMPTS = 3
RETRY = ("extract_failed", "post_failed")


@dataclass
class JobResult:
    posted: int = 0
    baseline: int = 0
    failed: int = 0
    listing_ok: bool = True
    messages: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.listing_ok and self.failed == 0


def run_job(*, store: PressReleaseStore, archive: ReleaseArchive, listing_fn: Callable, detail_fn: Callable,
            poster, today: date, bootstrap_days: int = 7, pause: float = 0.0, save: bool = True) -> JobResult:
    res = JobResult()
    labels = {i["id"]: i["label"] for i in load_yaml("items.yaml")["items"]}

    def send(text: str) -> bool:
        try:
            poster.post(text)
        except gchat.PostError as e:
            res.messages.append(f"POST FAILED: {e}")
            return False
        res.messages.append(text)
        return True

    try:
        entries = listing_fn()
    except (FetchError, ParseError) as e:
        res.listing_ok = False
        send(gchat.format_listing_warning(str(e)))
        return res

    first_run = not store.records and not store.ignored
    cutoff = (today - timedelta(days=bootstrap_days)).isoformat()
    for d in discover_new(entries, store, now=datetime.now(timezone.utc)):
        if first_run and d.entry.release_date < cutoff:
            store.records[d.entry.prid]["baseline"] = True

    todo = [r for r in store.records.values()
            if r.get("status") is None or (r["status"] in RETRY and r.get("attempts", 0) < MAX_ATTEMPTS)]
    todo.sort(key=lambda r: (r["release_date"], int(r["prid"])))

    for rec in todo:
        prid, item_id = rec["prid"], rec["item_id"]
        label = labels.get(item_id, item_id)
        if not archive.has(item_id, prid):
            try:
                if pause:
                    time.sleep(pause)
                html = detail_fn(prid)
                maturities = archive.cg_maturities() if item_id == "cg_result" else None
                release = extract(item_id, html, release_date=rec["release_date"],
                                  source_url=rec["detail_url"], maturities=maturities)
            except Exception as e:                       # one bad release must never stop the others
                rec["attempts"] = rec.get("attempts", 0) + 1
                rec["status"], rec["last_error"] = "extract_failed", f"{type(e).__name__}: {e}"
                res.failed += 1
                if not rec.get("baseline"):
                    send(gchat.format_extraction_warning(label, rec["title"], rec["detail_url"],
                                                         rec["last_error"], rec["attempts"], MAX_ATTEMPTS))
                continue
            archive.save(prid, release)
        else:
            release = next(r for p, r in archive.load_all(item_id) if p == prid)
        if rec.get("baseline"):
            rec["status"] = "baseline"
            res.baseline += 1
            continue
        previous = archive.previous(item_id, release.release_date, prid)
        diff = compare(release, previous, archive.matching_announcement(item_id, release.release_date, prid))
        if send(gchat.format_release(label, release, diff, rec["detail_url"], previous)):
            rec["status"] = "posted"
            res.posted += 1
        else:
            rec["attempts"] = rec.get("attempts", 0) + 1
            rec["status"] = "post_failed"
            res.failed += 1

    if res.posted == 0 and res.failed == 0:
        send(gchat.format_quiet(today.isoformat()))
    if save:
        store.save()
    return res