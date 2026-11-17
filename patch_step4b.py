"""Step 4b patch: T-Bill total allotment, BoP year-to-date handling, OMO result title. Safe to run twice."""
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


sub("src/rbi_tracker/engine/auction.py",
    """        accepted = to_num(row.get("accepted_amount"))
        if announcement is not None and arow is None:""",
    """        accepted = to_num(row.get("accepted_amount"))
        # T-Bill notified amounts cover competitive + non-competitive allotment, so judge the total
        if family == "tbill" and to_num(row.get("total_allotment_amount")) is not None:
            accepted = to_num(row.get("total_allotment_amount"))
        if announcement is not None and arow is None:""")

sub("src/rbi_tracker/engine/utils.py",
    '''def pretty(name: str) -> str:
    return name.replace("_", " ")''',
    '''def pretty(name: str) -> str:
    if name.startswith("ytd_"):
        return pretty(name[4:]) + " (year to date)"
    return name.replace("_", " ")''')

sub("src/rbi_tracker/engine/periodic.py", "from __future__ import annotations\n",
    "from __future__ import annotations\n\nimport re\n")

sub("src/rbi_tracker/engine/periodic.py",
    "def compare_bop(",
    '''_MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september",
           "october", "november", "december"]


def _ytd_start(period):
    """'April-September 2026' -> (2026, 4): the month and year the cumulative window starts.
    Two year-to-date windows are only comparable when they start in the same month and year."""
    m = re.match(r"\\s*([A-Za-z]+)\\s*-\\s*([A-Za-z]+)\\s+(\\d{4})\\s*$", str(period or ""))
    if not m:
        return None
    try:
        s = _MONTHS.index(m.group(1).lower()) + 1
        e = _MONTHS.index(m.group(2).lower()) + 1
    except ValueError:
        return None
    end_year = int(m.group(3))
    return (end_year if e >= s else end_year - 1, s)


def compare_bop(''')

sub("src/rbi_tracker/engine/periodic.py",
    '''    for name, val in new.fields.items():
        if to_num(val) is None:
            continue
        balance_like = "balance" in name or "invisibles" in name
        if prev is not None:
            c = record(''',
    '''    ytd_comparable = prev is not None and _ytd_start(new.fields.get("ytd_period")) is not None \\
        and _ytd_start(new.fields.get("ytd_period")) == _ytd_start(prev.fields.get("ytd_period"))
    if prev is not None and not ytd_comparable:
        d.info.append("Year-to-date figures not compared with the prior release: the year-to-date window differs "
                      f"({prev.fields.get('ytd_period')} vs {new.fields.get('ytd_period')}); "
                      "they are still compared with the same period a year ago.")
    for name, val in new.fields.items():
        if to_num(val) is None:
            continue
        balance_like = "balance" in name or "invisibles" in name
        if prev is not None and (ytd_comparable or not name.startswith("ytd_")):
            c = record(''')

sub("config/classifier.yaml",
    """    patterns: ['^results?\\s+of\\s+(the\\s+)?(omo|open market operations?)\\b']""",
    """    patterns: ['^results?\\s+of\\s+(the\\s+)?(omo|open market operations?)\\b', '^detailed results?:\\s*omo\\b']""")