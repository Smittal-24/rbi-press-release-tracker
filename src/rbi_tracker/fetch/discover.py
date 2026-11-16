"""Find genuinely new tracked releases in a fetched listing."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..store.records import PressReleaseStore
from .classify import Classifier, default_classifier
from .listing import PressReleaseEntry


@dataclass
class Discovered:
    entry: PressReleaseEntry
    item_id: str


def discover_new(entries: list[PressReleaseEntry], store: PressReleaseStore,
                 classifier: Classifier | None = None, now: datetime | None = None) -> list[Discovered]:
    """Classify entries not yet in the store and record them (the caller saves the store).

    Every new tracked release is its own item (never bundled; an announcement and its later result
    are never merged). Returned oldest first so history is processed in order. Entries that are not
    tracked are remembered as ignored so they are not evaluated again.
    """
    classifier = classifier or default_classifier()
    found: list[Discovered] = []
    for e in entries:
        if store.is_known(e.prid):
            continue
        item_id = classifier.classify(e.title)
        if item_id is None:
            store.add_ignored(e.prid)
            continue
        store.add_tracked(e, item_id, now)
        found.append(Discovered(e, item_id))
    return sorted(found, key=lambda d: (d.entry.release_date, int(d.entry.prid)))
