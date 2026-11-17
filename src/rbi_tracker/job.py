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
from .store.workbook import Workbook

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


def sync_workbook(store: PressReleaseStore, archive: ReleaseArchive, workbook: Workbook) -> tuple[int, int]:
    """Add releases already processed (before the workbook existed) to the Release Log and, for posted ones,
    the Change Log. Never duplicates and never edits existing rows. Returns (releases added, change rows added)."""
    labels = {i["id"]: i["label"] for i in load_yaml("items.yaml")["items"]}
    added = changes = 0
    for rec in sorted(store.records.values(), key=lambda r: (r["release_date"], int(r["prid"]))):
        found = [r for p, r in archive.load_all(rec["item_id"]) if p == rec["prid"]]
        if not found or workbook.has_release(rec["prid"]):
            continue
        release, label = found[0], labels.get(rec["item_id"], rec["item_id"])
        workbook.log_release(release, label, rec["prid"], "backfill")
        added += 1
        if rec.get("status") == "posted":
            diff = compare(release, archive.previous(rec["item_id"], release.release_date, rec["prid"]),
                           archive.matching_announcement(rec["item_id"], release.release_date, rec["prid"]))
            changes += workbook.log_changes(diff, release, label, rec["prid"])
    return added, changes


def run_job(*, store: PressReleaseStore, archive: ReleaseArchive, listing_fn: Callable, detail_fn: Callable,
            poster, today: date, bootstrap_days: int = 7, pause: float = 0.0, save: bool = True,
            workbook: Workbook | None = None, trigger: str = "manual") -> JobResult:
    res = JobResult()
    labels = {i["id"]: i["label"] for i in load_yaml("items.yaml")["items"]}

    def wb(fn, *a, **k):
        """Workbook logging must never stop the job: a problem there is reported, not raised."""
        if workbook is None:
            return
        try:
            fn(*a, **k)
        except Exception as e:
            res.messages.append(f"WORKBOOK LOGGING FAILED: {type(e).__name__}: {e}")

    def send(text: str, kind: str = "release", label: str = "", item_id: str = "", release_date: str = "",
             prid: str = "") -> bool:
        try:
            poster.post(text)
        except gchat.PostError as e:
            res.messages.append(f"POST FAILED: {e}")
            return False
        res.messages.append(text)
        if workbook is not None:
            wb(workbook.log_notification, kind, trigger, text, label, item_id, release_date, prid)
        return True

    try:
        entries = listing_fn()
    except (FetchError, ParseError) as e:
        res.listing_ok = False
        send(gchat.format_listing_warning(str(e)), kind="warning")
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
                                                         rec["last_error"], rec["attempts"], MAX_ATTEMPTS),
                         kind="warning", label=label, item_id=item_id, release_date=rec["release_date"], prid=prid)
                continue
            archive.save(prid, release)
        else:
            release = next(r for p, r in archive.load_all(item_id) if p == prid)
        if workbook is not None:
            wb(workbook.log_release, release, label, prid, "baseline" if rec.get("baseline") else trigger)
        if rec.get("baseline"):
            rec["status"] = "baseline"
            res.baseline += 1
            continue
        previous = archive.previous(item_id, release.release_date, prid)
        diff = compare(release, previous, archive.matching_announcement(item_id, release.release_date, prid))
        if send(gchat.format_release(label, release, diff, rec["detail_url"], previous), kind="release",
                label=label, item_id=item_id, release_date=release.release_date, prid=prid):
            if workbook is not None:
                wb(workbook.log_changes, diff, release, label, prid)
            rec["status"] = "posted"
            res.posted += 1
        else:
            rec["attempts"] = rec.get("attempts", 0) + 1
            rec["status"] = "post_failed"
            res.failed += 1

    if res.posted == 0 and res.failed == 0:
        send(gchat.format_quiet(today.isoformat()), kind="no-new-releases")
    if save:
        store.save()
        if workbook is not None:
            wb(workbook.save)
    return res