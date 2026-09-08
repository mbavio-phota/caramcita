"""Clasificados La Voz (clasificados.lavoz.com.ar).

El sitio HTML está detrás de Cloudflare, pero la API JSON de búsqueda contesta pedidos comunes:
``/api/search?page=N&filters=tid:6330 tid:6331 ss_operacion:Alquileres tid_location_should:<tid> ...``

- ``tid:6330`` = Inmuebles, ``tid:6331`` = Casas, ``ss_operacion:Alquileres`` = alquileres (excluye
  "Alquileres Temporarios", que es otro valor del mismo campo).
- ``tid_location_should:<tid>`` repetido funciona como OR en un solo pedido (verificado: la suma de
  los totales por localidad coincide con el total del pedido combinado).
- 24 avisos por página; ``results.meta.last_page`` da la cantidad de páginas.
"""
from __future__ import annotations

import html
import logging
import re
from typing import Any
from urllib.parse import quote

from ..http import Http
from ..models import Listing
from .base import Source, parse_price

log = logging.getLogger(__name__)

API = "https://clasificados.lavoz.com.ar/api/search"
MAX_PAGES = 10

_BEDS_RE = re.compile(r"(\d+)")
_TAG_RE = re.compile(r"<[^>]+>")


def _clean_text(s: str | None) -> str:
    if not s:
        return ""
    s = s.replace("[[inline-break]]", "\n")
    s = html.unescape(_TAG_RE.sub(" ", s))
    return "\n".join(" ".join(line.split()) for line in s.splitlines()).strip()


def _int_prefix(s: str | None) -> int | None:
    """'3 Dormitorios' → 3; '4 Dormitorios o más' → 4; 'Monoambiente' → None."""
    if not s:
        return None
    m = _BEDS_RE.search(str(s))
    return int(m.group(1)) if m else None


def _float(v: Any) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def build_filters(location_tids: list[int]) -> str:
    parts = ["tid:6330", "tid:6331", "ss_operacion:Alquileres"]
    parts += [f"tid_location_should:{int(t)}" for t in location_tids]
    return " ".join(parts)


def page_url(filters: str, page: int) -> str:
    return f"{API}?page={page}&filters={quote(filters, safe=':')}"


def parse_item(item: dict[str, Any], source: Source) -> Listing:
    addr = item.get("address") or {}
    re_ = item.get("real_estate") or {}
    user = item.get("user") or {}
    price_info = item.get("price") or {}
    price, cur = parse_price(f"{price_info.get('currency') or ''} {price_info.get('amount') or ''}")
    images: list[str] = []
    for img in ((item.get("multimedia") or {}).get("images") or {}).get("carousel") or []:
        u = (img.get("original") or {}).get("url")
        if u:
            images.append(u)
    operation = (item.get("third_level") or {}).get("name") or ""
    ptype = (item.get("subcategory") or {}).get("label") or ""
    extra = {
        "bathrooms": re_.get("number_bathrooms"),
        "total_area": re_.get("total_area"),
        "neighborhood_type": re_.get("neighborhood_type"),
        "publish_date": item.get("publish_date"),
        "province": addr.get("province"),
        "seller_role": user.get("role_name"),
        "highlight": (item.get("products") or {}).get("highlight"),
    }
    return source.listing(
        source_id=str(item["id"]),
        url=item["url"],
        title=_clean_text(item.get("title")),
        description=_clean_text(item.get("body") or item.get("body_excerpt")),
        price=price,
        currency=cur,
        locality=(addr.get("city") or "").strip(),
        address=(addr.get("neighborhood") or "").strip(),
        bedrooms=_int_prefix(re_.get("number_bedrooms")),
        property_type=ptype,
        operation=operation,
        images=images,
        agency=user.get("trade_name") or user.get("name") or source.name,
        lat=_float(addr.get("latitude")),
        lng=_float(addr.get("longitude")),
        extra={k: v for k, v in extra.items() if v not in (None, "")},
    )


def parse_page(payload: dict[str, Any], source: Source) -> tuple[list[Listing], int]:
    """Devuelve (avisos, last_page) a partir de la respuesta JSON de una página."""
    results = ((payload.get("data") or {}).get("results")) or {}
    meta = results.get("meta") or {}
    last_page = int(meta.get("last_page") or 1)
    out: list[Listing] = []
    for item in results.get("data") or []:
        try:
            out.append(parse_item(item, source))
        except Exception as e:  # noqa: BLE001
            log.warning("lavoz: aviso no parseable (id=%s): %s", item.get("id") if isinstance(item, dict) else "?", e)
    return out, last_page


class Adapter(Source):
    def __init__(self, slug: str, name: str, location_tids: list[int], **params: Any):
        super().__init__(slug, name, **params)
        self.location_tids = list(location_tids)

    def fetch(self, http: Http) -> list[Listing]:
        filters = build_filters(self.location_tids)
        out: list[Listing] = []
        seen: set[str] = set()
        page = 1
        while page <= MAX_PAGES:
            payload = http.get_json(page_url(filters, page))
            listings, last_page = parse_page(payload, self)
            for l in listings:
                if l.source_id not in seen:
                    seen.add(l.source_id)
                    out.append(l)
            if page >= last_page or not listings:
                break
            page += 1
        return out
