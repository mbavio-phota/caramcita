"""MercadoLibre Inmuebles: páginas de listado server-rendered.

Un GET común con user-agent de navegador devuelve el HTML completo. Cada página trae:

- un bloque ``application/ld+json`` con un ``@graph`` de ``RealEstateListing`` (título, precio,
  moneda, URL del aviso, imagen, ``numberOfRooms`` que ML usa para dormitorios, vendedor, m²) y un
  ``SearchResultsPage`` cuyo ``name`` empieza con el total ("35 Casas en Alquiler en ...");
- las tarjetas ``poly-card`` con la ubicación textual ("Calle 123, Barrio, Ciudad, Córdoba"),
  atributos ("4 ambs.", "3 baños", "170 m² cubiertos") y la foto principal.

``addressLocality`` del ld+json es la "ciudad" de ML (para la búsqueda santa-maria es el departamento
"Santa María"; la localidad real viene como barrio dentro del texto de ubicación). Se guarda
``locality`` = ciudad ML y ``address`` = calle + barrio; el clasificador resuelve el resto.

Paginación: sufijo ``_Desde_49`` (48 por página). Se corta cuando una página no trae nada nuevo o al
llegar al total del ``SearchResultsPage``; tope de 5 páginas por URL. No se entra al detalle.
"""
from __future__ import annotations

import json
import logging
import math
import re
from typing import Any

from bs4 import BeautifulSoup

from ..http import Http
from ..models import Listing
from .base import Source, parse_price, text_of

log = logging.getLogger(__name__)

PER_PAGE = 48
MAX_PAGES = 5

_ID_RE = re.compile(r"(MLA-?\d+)")
_BEDS_RE = re.compile(r"(?i)(\d+)\s*(?:dorm|hab)")
_BATHS_RE = re.compile(r"(?i)(\d+)\s*baño")
_ROOMS_RE = re.compile(r"(?i)(\d+)\s*amb")
_AREA_RE = re.compile(r"(?i)(\d+(?:[.,]\d+)?)\s*m²")
_TOTAL_RE = re.compile(r"^\s*([\d.]+)\s")


def listing_id(url: str | None) -> str | None:
    m = _ID_RE.search(url or "")
    return m.group(1).replace("MLA-", "MLA") if m else None


def page_url(base: str, page: int) -> str:
    if page <= 1:
        return base
    return base.rstrip("/") + f"/_Desde_{PER_PAGE * (page - 1) + 1}"


def _clean_url(u: str | None) -> str:
    return (u or "").split("#")[0].split("?")[0]


def _ld_graph(soup: BeautifulSoup) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for sc in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(sc.string or sc.get_text() or "")
        except ValueError:
            continue
        for d in data if isinstance(data, list) else [data]:
            if isinstance(d, dict):
                nodes.extend(g for g in d.get("@graph", [d]) if isinstance(g, dict))
    return nodes


def _cards(soup: BeautifulSoup) -> dict[str, dict[str, Any]]:
    """Datos de tarjeta indexados por id MLA: ubicación, atributos, foto, encabezado."""
    out: dict[str, dict[str, Any]] = {}
    for card in soup.select(".poly-card"):
        a = card.select_one("a.poly-component__title") or card.select_one("h3 a") or card.select_one("a[href*='MLA']")
        pid = listing_id(a.get("href") if a else None)
        if not pid:
            continue
        img = card.select_one("img.poly-component__picture") or card.select_one("img")
        attrs = [text_of(li) for li in card.select(".poly-attributes_list__item")]
        out[pid] = {
            "url": _clean_url(a.get("href") if a else None),
            "title": text_of(a),
            "headline": text_of(card.select_one(".poly-component__headline")),
            "location": text_of(card.select_one(".poly-component__location")),
            "attrs": attrs,
            "image": (img.get("src") or img.get("data-src")) if img else None,
            "price_text": text_of(card.select_one(".poly-component__price")),
        }
    return out


def _split_location(loc: str) -> tuple[str, str]:
    """'Los Tilos 118, Villa La Bolsa, Santa María, Córdoba' → ('Santa María', 'Los Tilos 118, Villa La Bolsa')."""
    parts = [p.strip() for p in loc.split(",") if p.strip()]
    if len(parts) >= 3:
        return parts[-2], ", ".join(parts[:-2])
    if len(parts) == 2:
        return parts[0], ""
    return "", loc


def _headline(h: str) -> tuple[str, str]:
    """'Casa en alquiler' → ('Casa', 'Alquiler')."""
    m = re.match(r"(?i)\s*(.+?)\s+en\s+(.+?)\s*$", h or "")
    if not m:
        return "", ""
    return m.group(1).strip(), m.group(2).strip().capitalize()


def parse_html(html: str, source: Source) -> tuple[list[Listing], int | None]:
    """Devuelve (avisos de la página, total según SearchResultsPage o None)."""
    soup = BeautifulSoup(html, "lxml")
    cards = _cards(soup)
    total: int | None = None
    out: list[Listing] = []
    seen: set[str] = set()
    for node in _ld_graph(soup):
        t = node.get("@type")
        if t == "SearchResultsPage":
            m = _TOTAL_RE.match(node.get("name") or "")
            if m:
                try:
                    total = int(m.group(1).replace(".", ""))
                except ValueError:
                    pass
            continue
        if t != "RealEstateListing":
            continue
        try:
            offers = node.get("offers") or {}
            url = _clean_url(node.get("mainEntityOfPage") or offers.get("url"))
            pid = listing_id(url)
            if not pid or pid in seen:
                continue
            seen.add(pid)
            card = cards.get(pid, {})
            price = offers.get("price")
            cur = offers.get("priceCurrency")
            if price in (None, ""):
                price, cur = parse_price(card.get("price_text"))
            else:
                price = float(price)
            locality, address = _split_location(card.get("location") or "")
            if not locality:
                locality = ((node.get("address") or {}).get("addressLocality") or "").strip()
            attrs = card.get("attrs") or []
            attrs_txt = " | ".join(attrs)
            beds = node.get("numberOfRooms")
            beds = int(beds) if isinstance(beds, (int, float)) and beds > 0 else None
            if beds is None:
                m = _BEDS_RE.search(attrs_txt)
                beds = int(m.group(1)) if m else None
            ptype, operation = _headline(card.get("headline") or "")
            images = [u for u in [card.get("image"), node.get("image")] if u]
            seller = (node.get("seller") or {}).get("name") or ""
            extra: dict[str, Any] = {"attrs": attrs_txt}
            for key, rx in (("bathrooms", _BATHS_RE), ("rooms", _ROOMS_RE), ("covered_m2", _AREA_RE)):
                m = rx.search(attrs_txt)
                if m:
                    extra[key] = m.group(1)
            fs = node.get("floorSize") or {}
            if fs.get("value"):
                extra["floor_size"] = fs.get("value")
            if node.get("datePosted"):
                extra["date_posted"] = node["datePosted"]
            if (node.get("address") or {}).get("addressLocality"):
                extra["ml_locality"] = node["address"]["addressLocality"]
            out.append(source.listing(
                source_id=pid,
                url=url,
                title=" ".join((node.get("name") or card.get("title") or "").split()),
                description="",
                price=price,
                currency=cur,
                locality=locality,
                address=address,
                bedrooms=beds,
                property_type=ptype,
                operation=operation,
                images=images[:1],
                agency=seller or source.name,
                extra=extra,
            ))
        except Exception as e:  # noqa: BLE001
            log.warning("mercadolibre: aviso no parseable (%s): %s", node.get("name", "?")[:40], e)
    return out, total


class Adapter(Source):
    def __init__(self, slug: str, name: str, urls: list[str], **params: Any):
        super().__init__(slug, name, **params)
        self.urls = list(urls)

    def fetch(self, http: Http) -> list[Listing]:
        out: list[Listing] = []
        seen: set[str] = set()
        for base in self.urls:
            page = 1
            while page <= MAX_PAGES:
                html = http.get_text(page_url(base, page))
                listings, total = parse_html(html, self)
                new = [l for l in listings if l.source_id not in seen]
                for l in new:
                    seen.add(l.source_id)
                    out.append(l)
                log.info("[%s] %s p%d: %d avisos (%d nuevos)", self.slug, base, page, len(listings), len(new))
                if not listings or (page > 1 and not new):
                    break
                if total is not None and page >= math.ceil(total / PER_PAGE):
                    break
                page += 1
        return out
