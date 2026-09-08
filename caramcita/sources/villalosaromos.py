"""Inmobiliaria Villa Los Aromos: WordPress con plugin Estatik, sin CPT en la REST.

Se parsea el archivo HTML https://inmobiliariavillalosaromos.com.ar/property/ (paginado con
?paged=N). Cada tarjeta `.es-listing[data-post-id]` trae título, link, extracto recortado, fotos y
la categoría ("Alquiler Permanente", "Alquiler temporal", "Casas en venta", "Terrenos").

Se devuelven sólo los avisos cuyo título o categoría dice alquiler (se excluyen ventas). Las
tarjetas no traen precio, dormitorios ni localidad, así que para los alquileres permanentes se entra
al detalle (descripción completa + fotos) y el precio se busca en el texto ("Precio mensual:
$800.000"). Los temporarios (muchos, y el clasificador los descarta) se devuelven sólo con la tarjeta.

Params opcionales: `base` (default el sitio), `detail_temporary` (bool, entrar también al detalle de
los temporarios).
"""
from __future__ import annotations

import html as htmlmod
import json
import logging
import re
from typing import Any

from bs4 import BeautifulSoup

from ..http import Http
from ..models import Listing
from .base import Source, parse_price, text_of

log = logging.getLogger(__name__)

MAX_PAGES = 10
_RENTAL = re.compile(r"(?i)alquiler")
_TEMPORARY = re.compile(r"(?i)tempor")
_SALE = re.compile(r"(?i)\bventa\b")
_PRICE_IN_TEXT = re.compile(r"(?i)precio[^\d$u]{0,25}((?:u\$s|usd|us\$|\$)\s*[\d.,]+(?:\s*(?:usd|dólares|dolares))?)")
_PRICE_ANY = re.compile(r"(?i)((?:u\$s|usd|us\$|\$)\s*\d[\d.,]*)")
_SIZE_SUFFIX = re.compile(r"-\d+x\d+(?=\.\w+$)")


def _full_image(url: str) -> str:
    return _SIZE_SUFFIX.sub("", url)


def operation_of(title: str, terms: list[str]) -> str:
    """'Alquiler' / 'Alquiler temporario' / 'Venta' / '' según título y categorías."""
    txt = f"{title} {' '.join(terms)}"
    if _RENTAL.search(txt):
        return "Alquiler temporario" if _TEMPORARY.search(txt) else "Alquiler"
    if _SALE.search(txt):
        return "Venta"
    return ""


class Adapter(Source):
    def __init__(self, slug: str, name: str, **params: Any):
        super().__init__(slug, name, **params)
        self.base = params.get("base", "https://inmobiliariavillalosaromos.com.ar").rstrip("/")
        self.detail_temporary = bool(params.get("detail_temporary", False))

    def fetch(self, http: Http) -> list[Listing]:
        listings: list[Listing] = []
        seen: set[str] = set()
        for page in range(1, MAX_PAGES + 1):
            url = f"{self.base}/property/" + ("" if page == 1 else f"?paged={page}")
            try:
                html = http.get_text(url)
            except Exception as e:  # noqa: BLE001
                if page == 1:
                    raise
                log.debug("[%s] fin de paginación en %s: %s", self.slug, page, e)
                break
            cards = self.parse_archive(html)
            if not cards:
                break
            new = 0
            for c in cards:
                if c["source_id"] in seen:
                    continue
                seen.add(c["source_id"])
                new += 1
                if c["operation"] in ("Alquiler", "Alquiler temporario"):
                    listings.append(self._build(http, c))
            if new == 0 or not self.has_next_page(html, page + 1):
                break
        return listings

    @staticmethod
    def has_next_page(html: str, next_page: int) -> bool:
        return bool(re.search(rf"[?&]paged={next_page}\b|/property/page/{next_page}/", html))

    # ---- archivo --------------------------------------------------------------------------
    @staticmethod
    def parse_archive(html: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "lxml")
        out: list[dict[str, Any]] = []
        for card in soup.select(".es-listing[data-post-id]"):
            try:
                a = card.select_one(".es-listing__title a[href]")
                if a is None:
                    continue
                title = " ".join(htmlmod.unescape(a.get_text(" ")).split())
                terms = [text_of(t) for t in card.select(".es-listing__terms a")]
                images = []
                for img in card.select(".es-listing__image img"):
                    src = img.get("data-lazy") or img.get("src")
                    if src and _full_image(src) not in images:
                        images.append(_full_image(src))
                out.append(dict(
                    source_id=card["data-post-id"],
                    url=a["href"],
                    title=title,
                    excerpt=text_of(card.select_one(".es-excerpt")),
                    terms=terms,
                    images=images,
                    operation=operation_of(title, terms),
                ))
            except Exception as e:  # noqa: BLE001
                log.warning("villalosaromos: tarjeta %s no parseable: %s", card.get("data-post-id"), e)
        return out

    def _build(self, http: Http, c: dict[str, Any]) -> Listing:
        kw: dict[str, Any] = dict(
            source_id=c["source_id"], url=c["url"], title=c["title"], description=c["excerpt"],
            operation=c["operation"], images=list(c["images"]), extra={"categoria": ", ".join(c["terms"])},
        )
        if c["operation"] == "Alquiler" or self.detail_temporary:
            try:
                kw.update(self.parse_detail(http.get_text(c["url"])))
            except Exception as e:  # noqa: BLE001
                log.warning("[%s] detalle %s falló: %s", self.slug, c["url"], e)
        if kw.get("price") is None:
            kw["price"], kw["currency"] = self._price_in(kw["description"]) if kw["description"] else (None, None)
        return self.listing(**kw)

    # ---- detalle --------------------------------------------------------------------------
    @staticmethod
    def parse_detail(html: str) -> dict[str, Any]:
        """description (completa), images, price/currency, address si aparece."""
        soup = BeautifulSoup(html, "lxml")
        out: dict[str, Any] = {}
        desc = soup.select_one(".es-property-field--post_content .es-property-field__value")
        if desc is not None:
            out["description"] = text_of(desc)
        images = [a["href"] for a in soup.select(".es-slider__item[href]") if a.get("href")]
        if not images:
            for s in soup.select("script[type='application/ld+json']"):
                try:
                    data = json.loads(s.string or "")
                except ValueError:
                    continue
                if isinstance(data, dict) and data.get("@type") == "House":
                    images = [i for i in data.get("image") or [] if isinstance(i, str)]
                    if not out.get("description") and data.get("description"):
                        out["description"] = " ".join(htmlmod.unescape(data["description"]).split())
                    break
        if images:
            out["images"] = images
        addr = soup.select_one(".es-property-field--address .es-property-field__value, .es-entity__address")
        if addr is not None:
            out["address"] = text_of(addr)
        if out.get("description"):
            out["price"], out["currency"] = Adapter._price_in(out["description"])
        return out

    @staticmethod
    def _price_in(text: str) -> tuple[float | None, str | None]:
        m = _PRICE_IN_TEXT.search(text) or _PRICE_ANY.search(text)
        return parse_price(m.group(1)) if m else (None, None)
