from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent


def config_path() -> Path:
    return Path(os.environ.get("CARAMCITA_CONFIG", ROOT / "config.yaml"))


def sources_path() -> Path:
    return Path(os.environ.get("CARAMCITA_SOURCES", ROOT / "sources.yaml"))


def load_config(path: Path | None = None) -> dict[str, Any]:
    with open(path or config_path(), encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_sources(path: Path | None = None) -> list[dict[str, Any]]:
    with open(path or sources_path(), encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return [s for s in data.get("sources", []) if s.get("enabled", True)]
