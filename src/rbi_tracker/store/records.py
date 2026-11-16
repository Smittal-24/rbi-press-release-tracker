"""Record of every press release the tracker has seen (the "already recorded" check).

Stored as one JSON file in the repo: tracked releases with their item type, plus the ids of
releases that were looked at and ignored (so they are never re-evaluated).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..fetch.listing import PressReleaseEntry


class PressReleaseStore:
    def __init__(self, path: Path, records: dict[str, dict[str, Any]] | None = None,
                 ignored: set[str] | None = None):
        self.path = Path(path)
        self.records: dict[str, dict[str, Any]] = records or {}
        self.ignored: set[str] = ignored or set()

    @classmethod
    def load(cls, path: Path) -> "PressReleaseStore":
        path = Path(path)
        if not path.exists():
            return cls(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(path, data.get("records", {}), set(data.get("ignored", [])))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "records": dict(sorted(self.records.items(), key=lambda kv: int(kv[0]))),
            "ignored": sorted(self.ignored, key=int),
        }
        self.path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    def is_known(self, prid: str) -> bool:
        return prid in self.records or prid in self.ignored

    def add_tracked(self, entry: PressReleaseEntry, item_id: str, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        self.records[entry.prid] = {
            **entry.to_dict(),
            "item_id": item_id,
            "first_seen": now.isoformat(timespec="seconds"),
        }

    def add_ignored(self, prid: str) -> None:
        self.ignored.add(prid)

    def releases_for(self, item_id: str) -> list[dict[str, Any]]:
        """Recorded releases of one item type, oldest first."""
        rows = [r for r in self.records.values() if r["item_id"] == item_id]
        return sorted(rows, key=lambda r: (r["release_date"], int(r["prid"])))
