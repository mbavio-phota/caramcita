"""Guillermo Cortes (guillermocortes.com.ar): PHP a medida.

Listado en `/alquileres`, `/alquileres/pagina2`, ... hasta una página sin tarjetas. Cada tarjeta es
un `div.inmueble` con `p.images-num` (tipo), `img`, `p.titulo` ("Alquiler<br>Dirección"), un `<p>`
con "Complejo: X / Localidad: Y / Dormitorios: N Dormitorios", `p.precio` y el link `/inmueble-NNNN`.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..http import Http
from ..models import Listing
from .base import Source, parse_price, text_of

log = logging.getLogger(__name__)

_ID_RE = re.compile(r"/inmueble-(\d+)")
_FIELD_RE = re.compile(r"^\s*([^:]+?)\s*:\s*(.*?)\s*$")


class Adapter(Source):
    def __init__(self, slug: str, name: str, **params):
        super().__init__(slug, name, **params)
        self.base: str = params.get("base", "https://guillermocortes.com.ar").rstrip("/")
        self.path: str = params.get("path", "/alquileres")
        self.max_pages: int = int(params.get("max_pages", 10))

    def _url(self, page: int) -> str:
        return f"{self.base}{self.path}" + (f"/pagina{page}" if page > 1 else "")

    def fetch(self, http: Http) -> list[Listing]:
        out: list[Listing] = []
        seen: set[str] = set()
        for page in range(1, self.max_pages + 1):
            cards = self.parse_page(http.get_text(self._url(page)))
            new = [c for c in cards if c.source_id not in seen]
            if not new:
                break
            for c in new:
                seen.add(c.source_id)
                out.append(c)
        return out

    def parse_page(self, html: str) -> list[Listing]:
        soup = BeautifulSoup(html, "lxml")
        out: list[Listing] = []
        for card in soup.select("div.inmueble"):
            try:
                l = self._parse_card(card)
            except Exception as e:  # noqa: BLE001
                log.warning("[%s] aviso no parseable: %s", self.slug, e)
                continue
            if l:
                out.append(l)
        return out

    def _parse_card(self, card) -> Listing | None:
        link = card.find("a", href=_ID_RE)
        if not link:
            log.warning("[%s] tarjeta sin link a inmueble", self.slug)
            return None
        source_id = _ID_RE.search(link["href"]).group(1)
        url = urljoin(self.base + "/", link["href"])

        ptype = text_of(card.select_one("p.images-num"))

        titulo = card.select_one("p.titulo")
        lines = [" ".join(s.split()) for s in titulo.stripped_strings] if titulo else []
        operation = lines[0] if lines else ""
        address = " ".join(lines[1:]) if len(lines) > 1 else ""

        fields: dict[str, str] = {}
        info_lines: list[str] = []
        hover = card.select_one("div.inmueble-hover")
        for p in (hover.find_all("p", recursive=False) if hover else []):
            if p.get("class"):
                continue
            for s in p.stripped_strings:
                s = " ".join(s.split())
                info_lines.append(s)
                fm = _FIELD_RE.match(s)
                if fm:
                    fields[fm.group(1).lower()] = fm.group(2)

        locality = fields.get("localidad", "")
        bedrooms = None
        bm = re.search(r"\d+", fields.get("dormitorios", ""))
        if bm and int(bm.group(0)) > 0:
            bedrooms = int(bm.group(0))
        if not ptype:
            ptype = fields.get("complejo", "")

        price, currency = parse_price(text_of(card.select_one("p.precio")))
        images = [urljoin(self.base + "/", img["src"]) for img in card.select("img[src]")]

        title = address or f"Inmueble {source_id}"
        if ptype:
            title = f"{ptype} - {title}"
        extra = {k: v for k, v in fields.items() if k not in ("localidad", "dormitorios")}
        return self.listing(
            source_id=source_id,
            url=url,
            title=title,
            description=" | ".join(info_lines),
            price=price,
            currency=currency,
            locality=locality,
            address=address,
            bedrooms=bedrooms,
            property_type=ptype,
            operation=operation,
            images=images,
            extra=extra,
        )
