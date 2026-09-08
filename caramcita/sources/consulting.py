"""Consulting Inmobiliaria (consultinginmobiliaria.com): PHP a medida.

Buscador GET en `inmuebles.php` (o `index.php`): `localidad=N`, `propiedad=N`, `paginador_pagina=P`
(desde 0). Cada aviso es un `div.caja` con las fotos, un `<script>` que llama a
`listados.agregar_etiquetas(n, 'Operación en Localidad<br />Dirección', 'dorms', 'baños', videos, mapa)`,
`div.precio` y el link `detalle.php?id=N`.

Ojo: el parámetro `operacion` no filtra (operacion=2 devuelve las mismas ventas que sin filtro y
operacion=1 no devuelve nada), así que no se manda y la operación se lee del título.
"""
from __future__ import annotations

import logging
import re
from html import unescape
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..http import Http
from ..models import Listing
from .base import Source, parse_price, text_of

log = logging.getLogger(__name__)

_ETIQUETAS_RE = re.compile(
    r"listados\.agregar_etiquetas\(\s*\d+\s*,\s*'((?:[^'\\]|\\.)*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'", re.S
)
_MAPA_RE = re.compile(r"mostrar_mapa\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)")
_TITLE_RE = re.compile(r"^\s*(venta|alquiler[^<]*?)\s+en\s+(.+?)\s*$", re.I)
_ID_RE = re.compile(r"detalle\.php\?id=(\d+)")

DEFAULT_LOCALITIES = {1: "Alta Gracia", 2: "Anisacate", 11: "Villa La Bolsa"}
PROPERTY_TYPES = {1: "Departamento", 2: "Casa", 3: "Local Comercial", 4: "Lote", 5: "Cabaña", 6: "Cocheras", 7: "Inversión"}


def _int_or_none(s: str) -> int | None:
    m = re.search(r"\d+", s or "")
    n = int(m.group(0)) if m else 0
    return n if n > 0 else None


class Adapter(Source):
    def __init__(self, slug: str, name: str, **params):
        super().__init__(slug, name, **params)
        self.base: str = params.get("base", "https://consultinginmobiliaria.com/")
        if not self.base.endswith("/"):
            self.base += "/"
        locs = params.get("localities") or DEFAULT_LOCALITIES
        self.localities: dict[int, str] = {int(k): str(v) for k, v in locs.items()}
        self.propiedad: int | None = params.get("propiedad", 2)
        self.max_pages: int = int(params.get("max_pages", 10))

    def _url(self, loc_id: int, page: int) -> str:
        q = f"localidad={loc_id}&paginador_pagina={page}"
        if self.propiedad:
            q = f"propiedad={self.propiedad}&" + q
        return f"{self.base}inmuebles.php?{q}"

    def fetch(self, http: Http) -> list[Listing]:
        out: list[Listing] = []
        seen: set[str] = set()
        for loc_id, loc_name in self.localities.items():
            for page in range(self.max_pages):
                html = http.get_text(self._url(loc_id, page))
                cards = self.parse_page(html, loc_name)
                new = [c for c in cards if c.source_id not in seen]
                if not new:
                    break
                for c in new:
                    seen.add(c.source_id)
                    out.append(c)
                if len(cards) < 6:  # la página trae 6 por vez
                    break
        return out

    def parse_page(self, html: str, locality: str) -> list[Listing]:
        soup = BeautifulSoup(html, "lxml")
        out: list[Listing] = []
        for caja in soup.select("div#listado div.caja"):
            try:
                l = self._parse_caja(caja, locality)
            except Exception as e:  # noqa: BLE001
                log.warning("[%s] aviso no parseable: %s", self.slug, e)
                continue
            if l:
                out.append(l)
        return out

    def _parse_caja(self, caja, locality: str) -> Listing | None:
        link = caja.find("a", href=_ID_RE)
        if not link:
            log.warning("[%s] caja sin link a detalle", self.slug)
            return None
        source_id = _ID_RE.search(link["href"]).group(1)
        url = urljoin(self.base, link["href"])

        script = " ".join(s.get_text() for s in caja.find_all("script"))
        m = _ETIQUETAS_RE.search(script)
        title_raw, beds_raw, baths_raw = (m.group(1), m.group(2), m.group(3)) if m else ("", "", "")
        title_raw = unescape(title_raw.replace("\\'", "'"))
        parts = [p.strip() for p in re.split(r"<br\s*/?>", title_raw) if p.strip()]
        head = parts[0] if parts else ""
        address = " ".join(parts[1:]) if len(parts) > 1 else ""
        operation, loc_from_title = "", ""
        tm = _TITLE_RE.match(head)
        if tm:
            operation = tm.group(1).strip().capitalize()
            loc_from_title = tm.group(2).strip()
        title = f"{head} - {address}" if address else head or f"Inmueble {source_id}"

        price, currency = parse_price(text_of(caja.select_one("div.precio")))
        images = [urljoin(self.base, img["src"]) for img in caja.select("img[src]")]
        lat = lng = None
        mm = _MAPA_RE.search(script)
        if mm:
            lat, lng = float(mm.group(1)), float(mm.group(2))

        extra = {"localidad_titulo": loc_from_title}
        baths = _int_or_none(baths_raw)
        if baths:
            extra["banios"] = baths
        n_img = caja.select_one("div.images-available-num")
        if n_img:
            extra["imagenes"] = text_of(n_img)

        return self.listing(
            source_id=source_id,
            url=url,
            title=title,
            price=price,
            currency=currency,
            locality=locality,
            address=address,
            bedrooms=_int_or_none(beds_raw),
            property_type=PROPERTY_TYPES.get(self.propiedad or 0, ""),
            operation=operation,
            images=images,
            lat=lat,
            lng=lng,
            extra=extra,
        )
