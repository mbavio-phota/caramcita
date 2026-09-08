"""Lequio Propiedades (lequiopropiedades.com.ar): plataforma "Pixel Inmobiliario".

Listado en `/listing?user_id=69&purpose=rent&page=N` (9 por página, hasta una página vacía). Cada
tarjeta es un `div.thumbnail_one` con `a[href=/ad/<slug>]`, `img`, `.Featured` (estado: Alquilo /
Alquilado / Amoblado), `.sale` (En Alquiler), `.area_price`, `h5 a[title]` (título completo),
`h7` ("Código: N"), `p` con "Localidad , dirección" y dos `.ft_area.p_20` (tipo + m²; dormitorios +
baños).
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

_CODE_RE = re.compile(r"(?i)c[oó]digo\s*:?\s*(\d+)")
_SLUG_RE = re.compile(r"/ad/([^/?#]+)")
_BEDS_RE = re.compile(r"(?i)(\d+)\s*dormitorio")
_BATHS_RE = re.compile(r"(?i)(\d+)\s*ba[ñn]o")
_M2_RE = re.compile(r"(?i)(\d+(?:[.,]\d+)?)\s*m²")


class Adapter(Source):
    def __init__(self, slug: str, name: str, **params):
        super().__init__(slug, name, **params)
        self.base: str = params.get("base", "https://lequiopropiedades.com.ar").rstrip("/")
        self.user_id: int = int(params.get("user_id", 69))
        self.purpose: str = params.get("purpose", "rent")
        self.max_pages: int = int(params.get("max_pages", 10))
        #: los avisos marcados "Alquilado" por la fuente ya no están disponibles
        self.skip_rented: bool = bool(params.get("skip_rented", True))

    def _url(self, page: int) -> str:
        return f"{self.base}/listing?user_id={self.user_id}&purpose={self.purpose}&page={page}"

    def fetch(self, http: Http) -> list[Listing]:
        out: list[Listing] = []
        seen: set[str] = set()
        for page in range(1, self.max_pages + 1):
            cards = self.parse_page(http.get_text(self._url(page)))
            if not cards:
                break
            new = [c for c in cards if c.source_id not in seen]
            if not new:
                break
            for c in new:
                seen.add(c.source_id)
                if self.skip_rented and c.extra.get("estado", "").lower() == "alquilado":
                    log.debug("[%s] %s ya alquilado, se omite", self.slug, c.source_id)
                    continue
                out.append(c)
        return out

    def parse_page(self, html: str) -> list[Listing]:
        soup = BeautifulSoup(html, "lxml")
        out: list[Listing] = []
        for card in soup.select("div.thumbnail_one"):
            try:
                l = self._parse_card(card)
            except Exception as e:  # noqa: BLE001
                log.warning("[%s] tarjeta no parseable: %s", self.slug, e)
                continue
            if l:
                out.append(l)
        return out

    def _parse_card(self, card) -> Listing | None:
        link = card.find("a", href=_SLUG_RE)
        if not link:
            log.warning("[%s] tarjeta sin link /ad/", self.slug)
            return None
        url = urljoin(self.base + "/", link["href"])
        slug = _SLUG_RE.search(url).group(1)

        code = ""
        cm = _CODE_RE.search(text_of(card.select_one(".thum_title h7")) or text_of(card))
        if cm:
            code = cm.group(1)
        source_id = code or slug

        title_a = card.select_one(".thum_title h5 a") or link
        title = (title_a.get("title") or "").strip() or text_of(title_a)
        img = card.find("img")
        if not title and img:
            title = (img.get("alt") or "").strip()

        locality = address = ""
        loc_p = card.select_one(".thum_title p")
        if loc_p:
            loc_txt = text_of(loc_p)
            locality, _, address = (x.strip() for x in loc_txt.partition(","))

        price, currency = parse_price(text_of(card.select_one(".area_price")))
        operation = text_of(card.select_one(".sale"))
        status = text_of(card.select_one(".Featured"))

        ptype = ""
        bedrooms = None
        extra: dict = {"slug": slug}
        if code:
            extra["codigo"] = code
        if status:
            extra["estado"] = status
        for area in card.select(".ft_area.p_20"):
            right = area.select_one(".post_date")
            right_txt = text_of(right) if right else ""
            if right:
                right.extract()
            left_txt = text_of(area)
            for txt in (left_txt, right_txt):
                if m := _BEDS_RE.search(txt):
                    bedrooms = int(m.group(1)) or None
                elif m := _BATHS_RE.search(txt):
                    extra["banios"] = int(m.group(1))
                elif m := _M2_RE.search(txt):
                    extra["m2"] = m.group(1)
                elif txt and not ptype:
                    ptype = txt

        images = []
        if img and img.get("src"):
            images.append(urljoin(self.base + "/", img["src"]))

        return self.listing(
            source_id=source_id,
            url=url,
            title=title or f"Aviso {source_id}",
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
