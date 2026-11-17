"""The Excel workbook (brief section 10): appended to, never overwritten.

  Release Log             one row per release (permanent structured record, with key figures)
  Change Log              one row per detected change, with the plain-language note sent to Chat
  Chat Notification Log   one row per message actually posted to Google Chat

Stored in the repo (data/RBI_Tracker.xlsx) so the daily job can commit it and the dashboard can offer it
for download. Rows are only ever added: existing rows are never edited or removed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import Workbook as _Workbook
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from ..engine.models import Diff, Release

SHEETS = {
    "Release Log": ["Logged at (UTC)", "Release date", "Item type", "Item ID", "Press release ref", "prid",
                    "Source", "Key figures", "Source URL"],
    "Change Log": ["Logged at (UTC)", "Release date", "Item type", "Item ID", "prid", "Tenor / key", "Metric",
                   "Previous value", "New value", "Change", "Unit", "% change", "Priority", "Compared with",
                   "Note (as sent to Chat)"],
    "Chat Notification Log": ["Posted at (UTC)", "Message type", "Item type", "Item ID", "Release date", "prid",
                              "Trigger", "Characters"],
}
WIDTHS = {"Key figures": 70, "Note (as sent to Chat)": 90, "Source URL": 50, "Item type": 34}

# fields worth showing as "key figures", in order, per kind of release
_RESULT = [("notified_amount", "notified"), ("bids_received_amount", "bids"), ("accepted_amount", "accepted"),
           ("total_allotment_amount", "total allotment"), ("cutoff_yield", "cut-off yield %"),
           ("cutoff_rate", "cut-off rate %"), ("wtd_avg_yield", "wtd avg yield %"), ("wtd_avg_rate", "wtd avg rate %"),
           ("bid_cover", "bid-cover x"), ("devolvement_amount", "devolvement")]
_ANNOUNCE = [("notified_amount", "notified"), ("maturity_date", "maturity")]
_CREDIT = [("yoy_growth_pct", "y-o-y growth %"), ("prior_year_yoy_growth_pct", "year-ago growth %")]
_FIELDS = {
    "bop": ["period", "current_account_balance", "trade_balance", "capital_account_balance", "overall_balance",
            "ytd_period", "ytd_current_account_balance"],
    "wss": ["forex_reserves_total_usd_mn", "forex_as_on", "aggregate_deposits_yoy_pct", "bank_credit_yoy_pct",
            "m3_yoy_pct"],
    "mpc_minutes": ["decision", "repo_rate", "repo_change_bps", "stance", "inflation_projection",
                    "growth_projection", "unanimous"],
}


def _v(x: Any) -> str:
    if isinstance(x, float):
        return f"{x:,.4f}".rstrip("0").rstrip(".")
    return str(x)


def key_figures(release: Release) -> str:
    """One readable line (or a few, one per tenor/security) of the release's headline numbers."""
    item = release.item_id
    if item in _FIELDS:
        parts = [f"{k}={_v(release.fields[k])}" for k in _FIELDS[item] if release.fields.get(k) is not None]
        if item == "mpc_minutes" and release.rows:
            parts.append(f"{len(release.rows)} members")
        return "; ".join(parts)
    spec = _CREDIT if item == "sectoral_credit" else _ANNOUNCE if item.endswith("announcement") else _RESULT
    lines = []
    for r in release.rows:
        bits = [f"{lab} {_v(r[k])}" for k, lab in spec if r.get(k) is not None]
        lines.append(f"{r['key']}: " + ", ".join(bits))
    return "\n".join(lines)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class Workbook:
    def __init__(self, path: Path, dry_run: bool = False):
        self.path, self.dry_run = Path(path), dry_run
        if self.path.exists():
            self.wb = load_workbook(self.path)
        else:
            self.wb = _Workbook()
            self.wb.remove(self.wb.active)
        for name, headers in SHEETS.items():
            if name not in self.wb.sheetnames:
                ws = self.wb.create_sheet(name)
                ws.append(headers)
                for i, h in enumerate(headers, 1):
                    c = ws.cell(row=1, column=i)
                    c.font = Font(bold=True, color="FFFFFF")
                    c.fill = PatternFill("solid", fgColor="1F4E78")
                    c.alignment = Alignment(vertical="center", wrap_text=True)
                    ws.column_dimensions[get_column_letter(i)].width = WIDTHS.get(h, 18)
                ws.freeze_panes = "A2"
        self._logged_prids = {str(r[5]) for r in self.wb["Release Log"].iter_rows(min_row=2, values_only=True)}

    def has_release(self, prid: str) -> bool:
        return str(prid) in self._logged_prids

    def _add(self, sheet: str, row: list) -> None:
        ws = self.wb[sheet]
        ws.append(row)
        for c in ws[ws.max_row]:
            c.alignment = Alignment(vertical="top", wrap_text=True)

    def log_release(self, release: Release, label: str, prid: str, source: str) -> bool:
        """Add the release to the Release Log once (a retry never adds a second row)."""
        if self.has_release(prid):
            return False
        self._add("Release Log", [_now(), release.release_date, label, release.item_id, release.reference, prid,
                                  source, key_figures(release), release.source_url])
        self._logged_prids.add(str(prid))
        return True

    def log_changes(self, diff: Diff, release: Release, label: str, prid: str) -> int:
        for c in diff.changes:
            self._add("Change Log", [
                _now(), release.release_date, label, release.item_id, prid, c.key or "", c.metric,
                "" if c.previous is None else c.previous, "" if c.new is None else c.new,
                "" if c.delta is None else c.delta, c.unit,
                "" if c.pct_change is None else round(c.pct_change, 2),
                "Yes" if c.priority else "No", c.comparison, c.note])
        return len(diff.changes)

    def log_notification(self, message_type: str, trigger: str, text: str, label: str = "", item_id: str = "",
                         release_date: str = "", prid: str = "") -> None:
        self._add("Chat Notification Log", [_now(), message_type, label, item_id, release_date, prid, trigger, len(text)])

    def save(self) -> None:
        if self.dry_run:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.wb.save(self.path)