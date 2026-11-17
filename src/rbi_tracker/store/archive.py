"""Archive of every extracted release (the history the engine diffs against).

One JSON file per release: data/releases/<item_id>/<prid>.json. Plain files in the repo, so the
daily job can commit them and the dashboard can read them later.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..engine.models import Release


class ReleaseArchive:
    def __init__(self, root: Path, dry_run: bool = False):
        self.root = Path(root)
        self.dry_run = dry_run                       # dry run: keep new releases in memory only
        self._mem: dict[tuple[str, str], Release] = {}

    def _path(self, item_id: str, prid: str) -> Path:
        return self.root / item_id / f"{prid}.json"

    def save(self, prid: str, release: Release) -> None:
        if self.dry_run:
            self._mem[(release.item_id, prid)] = release
            return
        p = self._path(release.item_id, prid)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {"prid": prid, "release": release.to_dict()}
        p.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    def has(self, item_id: str, prid: str) -> bool:
        return (item_id, prid) in self._mem or self._path(item_id, prid).exists()

    def load_all(self, item_id: str) -> list[tuple[str, Release]]:
        """[(prid, Release)] for one item type, oldest first (by release date, then prid)."""
        found: dict[str, Release] = {}
        folder = self.root / item_id
        if folder.exists():
            for f in folder.glob("*.json"):
                data = json.loads(f.read_text(encoding="utf-8"))
                found[data["prid"]] = Release.from_dict(data["release"])
        for (iid, prid), rel in self._mem.items():
            if iid == item_id:
                found[prid] = rel
        return sorted(found.items(), key=lambda kv: (kv[1].release_date, int(kv[0])))

    def previous(self, item_id: str, release_date: str, prid: str) -> Release | None:
        """The release of the same type immediately before (release_date, prid)."""
        before = [r for p, r in self.load_all(item_id) if (r.release_date, int(p)) < (release_date, int(prid))]
        return before[-1] if before else None

    def matching_announcement(self, result_item_id: str, release_date: str, prid: str) -> Release | None:
        """For a '<family>_result': the latest '<family>_announcement' released on or before it."""
        if not result_item_id.endswith("_result"):
            return None
        ann_id = result_item_id[: -len("_result")] + "_announcement"
        before = [r for p, r in self.load_all(ann_id) if r.release_date <= release_date]
        return before[-1] if before else None

    def cg_maturities(self) -> dict[str, str]:
        """{security name: ISO maturity date} from every stored CG announcement (for tenor buckets)."""
        out: dict[str, str] = {}
        for _, rel in self.load_all("cg_announcement"):
            for row in rel.rows:
                if row.get("security") and row.get("maturity_date"):
                    out[row["security"]] = row["maturity_date"]
        return out