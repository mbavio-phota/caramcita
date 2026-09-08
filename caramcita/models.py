from __future__ import annotations

import html
import re
from dataclasses import dataclass, field, asdict
from typing import Any


def clean_text(s: str | None) -> str:
    """Entidades HTML decodificadas y espacios colapsados; las fuentes mandan '&amp;' y saltos raros."""
    if not s:
        return ""
    return re.sub(r"[ \t\r\f\v]+", " ", html.unescape(s)).strip()


@dataclass
class Listing:
    """Un aviso tal como lo devuelve una fuente, antes de clasificar."""

    source: str
    source_id: str
    url: str
    title: str
    description: str = ""
    price: float | None = None
    currency: str | None = None  # "ARS" | "USD" | None
    locality: str = ""  # localidad tal como la da la fuente
    address: str = ""
    bedrooms: int | None = None
    property_type: str = ""  # tal como lo da la fuente ("Casa", "Departamento", ...)
    operation: str = ""  # tal como lo da la fuente ("Alquiler", "Alquiler temporario", ...)
    images: list[str] = field(default_factory=list)
    agency: str = ""
    lat: float | None = None
    lng: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.title = clean_text(self.title)
        self.description = clean_text(self.description)
        self.agency = clean_text(self.agency)
        self.address = clean_text(self.address)
        self.locality = clean_text(self.locality)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.source_id}"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["key"] = self.key
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Listing":
        d = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**d)


@dataclass
class Verdict:
    """Resultado de evaluar un aviso contra los requisitos."""

    status: str  # match | maybe_location | maybe_bedrooms | rejected
    reason: str
    locality: str | None = None
    bedrooms: int | None = None

    @property
    def shown(self) -> bool:
        return self.status != "rejected"
