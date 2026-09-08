"""Adaptadores de fuentes. Cada adaptador devuelve una lista de Listing."""
from __future__ import annotations

import importlib
from typing import Any

from .base import Source


def build_source(spec: dict[str, Any]) -> Source:
    """spec viene de sources.yaml: {slug, name, adapter, params}."""
    mod = importlib.import_module(f"caramcita.sources.{spec['adapter']}")
    cls = getattr(mod, "Adapter")
    return cls(slug=spec["slug"], name=spec["name"], **(spec.get("params") or {}))
