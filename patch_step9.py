"""Step 9 patch: two scheduled runs a day (3:30 PM and 5:15 PM IST). The 'no new releases' line is posted
only by the 5:15 PM run, and only if nothing was posted earlier that day. Safe to run twice."""
import pathlib


def sub(path, old, new):
    p = pathlib.Path(path)
    t = p.read_text(encoding="utf-8")
    if new in t:
        print("already applied:", path, "|", new.strip().splitlines()[0][:60])
        return
    assert old in t, f"expected text not found in {path}: {old[:60]!r}"
    p.write_text(t.replace(old, new, 1), encoding="utf-8", newline="\n")
    print("patched:", path)


J = "src/rbi_tracker/job.py"
sub(J, 'MAX_ATTEMPTS = 3\n', 'MAX_ATTEMPTS = 3\nEVENING_SCHEDULE = "45 11 * * *"     # the 5:15 PM IST run (11:45 UTC): the only one that posts the quiet line\n')
sub(J, '''            workbook: Workbook | None = None, trigger: str = "manual") -> JobResult:''',
       '''            workbook: Workbook | None = None, trigger: str = "manual", quiet_line: bool = True) -> JobResult:''')
sub(J, '''            rec["status"] = "posted"
            res.posted += 1''',
       '''            rec["status"] = "posted"
            rec["posted_at"] = datetime.now(IST).isoformat(timespec="seconds")
            rec["posted_on"] = today.isoformat()
            res.posted += 1''')
sub(J, '''    if res.posted == 0 and res.failed == 0:
        send(gchat.format_quiet(today.isoformat()), kind="no-new-releases")''',
       '''    posted_today = any(r.get("posted_on") == today.isoformat() for r in store.records.values())
    if quiet_line and res.posted == 0 and res.failed == 0 and not posted_today:
        send(gchat.format_quiet(today.isoformat()), kind="no-new-releases")''')

C = "src/rbi_tracker/cli.py"
sub(C, "    from .job import IST, run_job, sync_workbook\n", "    from .job import EVENING_SCHEDULE, IST, run_job, sync_workbook\n")
sub(C, '''    added, _ = sync_workbook(store, archive, workbook)''',
       '''    schedule = os.environ.get("EVENT_SCHEDULE", "")          # set by the workflow for scheduled runs
    quiet_line = not schedule or schedule == EVENING_SCHEDULE  # the earlier scheduled run stays silent
    added, _ = sync_workbook(store, archive, workbook)''')
sub(C, "workbook=workbook, trigger=trigger)", "workbook=workbook, trigger=trigger, quiet_line=quiet_line)")

W = ".github/workflows/daily.yml"
sub(W, '''    - cron: "45 11 * * *"        # 11:45 UTC = 17:15 IST''',
       '''    - cron: "0 10 * * *"         # 10:00 UTC = 15:30 IST (afternoon check)
    - cron: "45 11 * * *"        # 11:45 UTC = 17:15 IST (end-of-day check)''')
sub(W, '''          GCHAT_WEBHOOK_URL: ${{ secrets.GCHAT_WEBHOOK_URL }}
''', '''          GCHAT_WEBHOOK_URL: ${{ secrets.GCHAT_WEBHOOK_URL }}
          EVENT_SCHEDULE: ${{ github.event.schedule }}
''')

sub("tests/test_step5_job.py",
    """    _, _, r = go(tmp_path, [E_NEW, E_OLD], p2, s, a)
    assert r.posted == 0 and p2.sent == [gchat.format_quiet("2026-11-16")]""",
    """    _, _, r = go(tmp_path, [E_NEW, E_OLD], p2, s, a, today=date(2026, 11, 17))   # next day: nothing posted that day
    assert r.posted == 0 and p2.sent == [gchat.format_quiet("2026-11-17")]""")