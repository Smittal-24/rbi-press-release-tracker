"""Data contracts for the change-detection engine.

Pure data: no I/O, no network. The extraction layer produces `Release` objects,
the engine turns two of them into a `Diff`. See docs/engine_contract.md.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Release:
    """One extracted release of one item type (the input contract, brief section 5).

    fields      scalar data points for the release (blank/unknown -> None, never estimated)
    rows        per-tenor / per-security / per-sector / per-member records; every row has a
                unique string "key" (e.g. "10Y", "91D", "Agriculture", "Member name")
    prior_year  Balance of Payments only: same-quarter-last-year figures the release republishes
    """

    item_id: str
    release_date: str  # ISO date, YYYY-MM-DD
    reference: str = ""
    source_url: str = ""
    fields: dict[str, Any] = field(default_factory=dict)
    rows: list[dict[str, Any]] = field(default_factory=list)
    prior_year: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Release":
        return cls(
            item_id=d["item_id"],
            release_date=d["release_date"],
            reference=d.get("reference", ""),
            source_url=d.get("source_url", ""),
            fields=dict(d.get("fields") or {}),
            rows=[dict(r) for r in (d.get("rows") or [])],
            prior_year=dict(d.get("prior_year") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Change:
    """One detected change: what changed -> by how much -> versus what prior value.

    Maps one-to-one onto a row of the Change Log sheet (brief section 10).
    unit: "bps" (yields/rates), "pp" (growth rates, projections), "Rs crore", "Rs",
          "x" (bid-cover), "" (other levels / text)
    comparison: "previous" (prior release), "year_ago" (BoP), "announcement" (result vs its announcement)
    """

    metric: str
    note: str
    previous: Any = None
    new: Any = None
    key: str | None = None
    delta: float | None = None
    unit: str = ""
    pct_change: float | None = None
    comparison: str = "previous"
    priority: bool = False


@dataclass
class Diff:
    """Structured diff of a release versus the previous release of the same item type."""

    item_id: str
    release_date: str
    previous_date: str | None
    changes: list[Change] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)  # labels of compared-but-flat items
    info: list[str] = field(default_factory=list)  # context: no prior, new/dropped rows, etc.
    new_articles: list[str] = field(default_factory=list)  # RBI Bulletin only

    @property
    def has_previous(self) -> bool:
        return self.previous_date is not None

    @property
    def priority_changes(self) -> list[Change]:
        return [c for c in self.changes if c.priority]

    def summary_lines(self, max_unchanged: int = 8) -> list[str]:
        """Concise plain-language lines: priority first, then other moves, then brief context."""
        lines = [f"PRIORITY: {c.note}" for c in self.changes if c.priority]
        lines += [c.note for c in self.changes if not c.priority]
        lines += self.info
        if self.new_articles:
            lines.append(f"New in this issue ({len(self.new_articles)}): " + "; ".join(self.new_articles))
        if self.unchanged:
            shown = self.unchanged[:max_unchanged]
            more = len(self.unchanged) - len(shown)
            tail = f" (+{more} more)" if more > 0 else ""
            lines.append("Unchanged: " + ", ".join(shown) + tail)
        return lines

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
