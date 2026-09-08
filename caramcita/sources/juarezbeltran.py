"""Juárez Beltrán (juarezbeltran.com.ar): plataforma propia, listado server-rendered.

El listado vive en `/propiedades` con filtros por query string: `operation[]` (1 Venta, 2 Alquiler,
3 Alquiler Temporal, 4 Traspaso), `type[]` (1 Casa, 2 Departamento, 14 PH, ...), `summary=` (texto
libre: ubicación/código), `neighborhood=` y `page=N`. OJO: `?operacion=alquiler` (el link del menú)
NO filtra; hay que usar `operation[]=2`. `summary=Alta Gracia` hoy devuelve 0 resultados (la
inmobiliaria es de Córdoba capital), así que por defecto se traen todos los alquileres y filtra el
clasificador por localidad.

Cada card trae un JSON-LD (schema.org RealEstateListing) con localidad, dirección, precio y geo.

Params:
  base:       default https://juarezbeltran.com.ar
  operations: lista de ids de operación. Default [2].
  types:      lista de ids de tipo. Default [] (todos).
  summary:    texto libre para el filtro "Contiene". Default "".
  max_pages:  Default 12.
"""
from __future__ import annotations

import json
import logging
import re
from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup

from ..http import Http
from ..models import Listing
from .base import Source, parse_price, text_of

log = logging.getLogger(__name__)

_CURRENCIES = {"1": "USD", "2": "ARS"}
_BEDS_RE = re.compile(r"^(\d+)\s+Dormitorio", re.IGNORECASE)
_BATHS_RE = re.compile(r"^(\d+)\s+Baño", re.IGNORECASE)
_ID_RE = re.compile(r"-(\d+)/?$")


class Adapter(Source):
    def fetch(self, http: Http) -> list[Listing]:
        base = str(self.params.get("base", "https://juarezbeltran.com.ar")).rstrip("/")
        operations = self.params.get("operations", [2])
        types = self.params.get("types", []) or []
        summary = self.params.get("summary", "") or ""
        max_pages = int(self.params.get("max_pages", 12))

        out: list[Listing] = []
        seen: set[str] = set()
        for page in range(1, max_pages + 1):
            url = self.page_url(base, operations, types, summary, page)
            soup = BeautifulSoup(http.get_text(url), "lxml")
            cards = soup.select(".card.property-item")
            if not cards:
                break
            new = 0
            for card in cards:
                try:
                    lst = self.parse_card(card, base)
                except Exception as e:  # noqa: BLE001
                    log.warning("[%s] aviso ilegible en %s: %s", self.slug, url, e)
                    continue
                if lst and lst.source_id not in seen:
                    seen.add(lst.source_id)
                    out.append(lst)
                    new += 1
            if new == 0 or not self._has_next(soup, page):
                break
        return out

    @staticmethod
    def page_url(base: str, operations, types, summary: str, page: int) -> str:
        q: list[tuple[str, str]] = [("operation[]", str(o)) for o in operations]
        q += [("type[]", str(t)) for t in types]
        if summary:
            q.append(("summary", summary))
        if page > 1:
            q.append(("page", str(page)))
        return f"{base}/propiedades?{urlencode(q)}"

    @staticmethod
    def _has_next(soup, page: int) -> bool:
        return any(re.search(rf"[?&]page={page + 1}(&|$)", a.get("href", "")) for a in soup.select(".pagination a"))

    def parse_card(self, card, base: str) -> Listing | None:
        a = card.select_one(".details h5 a[href]") or card.select_one("a[href*='/propiedad/']")
        if not a:
            return None
        url = urljoin(base + "/", a["href"])
        pid = (card.get("data-id") or "").strip()
        if not pid:
            m = _ID_RE.search(url)
            pid = m.group(1) if m else url
        title = text_of(a)

        ld: dict = {}
        script = card.find("script", type="application/ld+json")
        if script and script.string:
            try:
                ld = json.loads(script.string)
            except ValueError:
                ld = {}
        about = ld.get("about") or {}
        addr = about.get("address") or {}
        geo = about.get("geo") or {}
        offers = ld.get("offers") or {}

        bedrooms = None
        extra: dict = {}
        for li in card.select(".details > ul > li"):
            t = text_of(li)
            if (m := _BEDS_RE.match(t)):
                bedrooms = int(m.group(1))
            elif (m := _BATHS_RE.match(t)):
                extra["bathrooms"] = int(m.group(1))
            elif t.lower().startswith("sup"):
                extra["surface"] = t
        # (about.numberOfRooms del JSON-LD son ambientes, no dormitorios: no se usa)

        price_el = card.select_one(".price[data-price]")
        price: float | None = None
        currency: str | None = None
        operation = ""
        if price_el:
            try:
                price = float(price_el["data-price"]) or None
            except (ValueError, TypeError):
                price = None
            currency = _CURRENCIES.get(str(price_el.get("data-currency", "")))
            label = text_of(price_el.select_one("small")).lower()
            if "alquiler" in label:
                operation = "Alquiler temporal" if "temporal" in label else "Alquiler"
            elif "venta" in label:
                operation = "Venta"
        if price is None:
            price, currency = parse_price(text_of(price_el.select_one("h6")) if price_el else "")
        if price is None and offers.get("price"):
            price = float(offers["price"])
            currency = offers.get("priceCurrency") or currency
        if not operation and offers.get("@type") == "OfferForLease":
            operation = "Alquiler"

        images: list[str] = []
        img = card.select_one(".image-container img")
        src = (img.get("data-src") or img.get("src")) if img else ld.get("image")
        if src:
            images.append(urljoin(base + "/", src))

        if addr.get("addressRegion"):
            extra["region"] = addr["addressRegion"]
        if ld.get("url"):
            url = ld["url"]

        return self.listing(
            source_id=pid,
            url=url,
            title=title,
            description=text_of(card.select_one(".details .description")),
            price=price,
            currency=currency,
            locality=addr.get("addressLocality", "") or "",
            address=addr.get("streetAddress") or text_of(card.select_one(".address-to-show")),
            bedrooms=bedrooms,
            property_type=(card.get("data-type") or "").strip(),
            operation=operation,
            images=images,
            lat=_float(geo.get("latitude")),
            lng=_float(geo.get("longitude")),
            extra=extra,
        )


def _float(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None
