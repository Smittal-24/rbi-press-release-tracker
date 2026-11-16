"""Repo paths and config loading (config is data, never hard-coded in code)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
INDEX_FILE = DATA_DIR / "index" / "press_releases.json"


def load_yaml(name: str) -> Any:
    return yaml.safe_load((CONFIG_DIR / name).read_text(encoding="utf-8"))


def load_settings() -> dict[str, Any]:
    return load_yaml("settings.yaml")
