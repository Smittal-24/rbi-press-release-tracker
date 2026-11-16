"""Classify a press release title into a tracked item type, driven by config/classifier.yaml."""
from __future__ import annotations

import re
from functools import lru_cache

from ..paths import load_yaml


def normalize_title(title: str) -> str:
    t = (title.replace("\u2019", "'").replace("\u2018", "'")
         .replace("\u201c", '"').replace("\u201d", '"')
         .replace("\u2013", "-").replace("\u2014", "-"))
    return " ".join(t.split()).lower()


class Classifier:
    def __init__(self, config: dict):
        self.exclude = [re.compile(p, re.I) for p in config.get("exclude", [])]
        self.rules = [(r["item_id"], [re.compile(p, re.I) for p in r["patterns"]])
                      for r in config["rules"]]

    def classify(self, title: str) -> str | None:
        """Return the item_id for a tracked title, else None. First matching rule wins."""
        t = normalize_title(title)
        if any(p.search(t) for p in self.exclude):
            return None
        for item_id, patterns in self.rules:
            if any(p.search(t) for p in patterns):
                return item_id
        return None


@lru_cache(maxsize=1)
def default_classifier() -> Classifier:
    return Classifier(load_yaml("classifier.yaml"))
