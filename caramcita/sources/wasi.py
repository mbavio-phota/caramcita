"""Adaptador genérico para sitios de Wasi (wasi.co) con listado server-rendered.

El buscador vive en `/search?...` con `business_type[0]=for_rent&for_rent=1&lax_business_type=1`
y `page=N`; opcionalmente `id_property_type=<id>` (1 = Casa, 2 = Departamento, 3 = Local, ...).
Las URLs bonitas `/s/alquileres` y `/s/casa/alquileres?...` muestran lo mismo, pero al paginarlas
con `?page=2` pierden el filtro de operación, por eso se pagina siempre sobre `/search`.

Las cards (`.list-properties .item`) traen tipo, operación, título, ubicación (`.ubicacion`, que
en algunos sitios sólo dice el país), dormitorios/baños/garaje y precio. La URL del detalle es
`<base>/<tipo>-<operacion>-<ciudad>/<id>`; el id es el `source_id`.

Params:
  base:          URL raíz (obligatorio).
  property_type: id de tipo de Wasi o null para todos. Default 1 (Casa).
  business_type: "for_rent" | "for_sale" | "for_temporary_rent". Default "for_rent".
  max_pages:     Default 10.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urlencode, urljoin, urlparse

from bs4 import BeautifulSoup

from ..http import Http
from ..models import Listing
from .base import Source, parse_price, text_of

log = logging.getLogger(__name__)

_OPERATIONS = {"for_rent": "Alquiler", "for_sale": "Venta", "for_temporary_rent": "Alquiler temporario"}
_COUNTRY_ONLY = {"argentina", "colombia", "méxico", "mexico", "chile", "perú", "peru", "uruguay", ""}


class Adapter(Source):
    def fetch(self, http: Http) -> list[Listing]:
        base = self.params["base"].rstrip("/")
        ptype = self.params.get("property_type", 1)
        business = str(self.params.get("business_type", "for_rent"))
        max_pages = int(self.params.get("max_pages", 10))

        out: list[Listing] = []
        seen: set[str] = set()
        for page in range(1, max_pages + 1):
            url = self.page_url(base, business, ptype, page)
            soup = BeautifulSoup(http.get_text(url), "lxml")
            cards = soup.select(".list-properties .item")
            if not cards:
                break
            new = 0
            for card in cards:
                try:
                    lst = self.parse_card(card, base, business)
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
    def page_url(base: str, business: str, ptype, page: int) -> str:
        q: list[tuple[str, str]] = [("business_type[0]", business)]
        if ptype not in (None, "", 0):
            q.append(("id_property_type", str(ptype)))
        for k in ("for_sale", "for_rent", "for_temporary_rent", "for_transfer"):
            q.append((k, "1" if k == business else "0"))
        q += [("lax_business_type", "1"), ("order_by", "created_at"), ("order", "desc"), ("page", str(page))]
        return f"{base}/search?{urlencode(q)}"

    @staticmethod
    def _has_next(soup, page: int) -> bool:
        return any(re.search(rf"[?&]page={page + 1}(&|$)", a.get("href", "")) for a in soup.select(".pagination a"))

    def parse_card(self, card, base: str, business: str) -> Listing | None:
        a = card.select_one("h2 a[href]") or card.select_one("figure a[href]")
        if not a:
            return None
        url = urljoin(base + "/", a["href"])
        path = urlparse(url).path.rstrip("/")
        m = re.search(r"/(\d+)$", path)
        pid = m.group(1) if m else path.rsplit("/", 1)[-1]

        title = text_of(a)
        ptype = text_of(card.select_one(".tag1"))
        op = text_of(card.select_one(".tag2")) or _OPERATIONS.get(business, "")
        location = text_of(card.select_one(".ubicacion"))

        # ciudad según el slug de la URL: /<tipo>-<operacion>-<ciudad>/<id>
        slug = path.rsplit("/", 2)[-2] if path.count("/") >= 2 else ""
        slug_city = ""
        sm = re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)?-(?:alquiler|venta|arriendo)(?:-temporal|-temporario)?-(.+)$", slug)
        if sm:
            slug_city = sm.group(1).replace("-", " ").title()
        locality = location if location.lower() not in _COUNTRY_ONLY else slug_city

        bedrooms = None
        extra: dict = {}
        for col in card.select(".info_details .col-3, .info_details [class*=col]"):
            n = text_of(col.select_one(".dt1"))
            label = text_of(col.select_one(".dt2")).lower()
            if not n.isdigit() or not label:
                continue
            if label.startswith("dormitorio") or label.startswith("habitaci"):
                bedrooms = int(n)
            elif label.startswith("baño") or label.startswith("bano"):
                extra["bathrooms"] = int(n)
            elif label.startswith("garaje") or label.startswith("cochera"):
                extra["garages"] = int(n)
        if bedrooms == 0:
            bedrooms = None  # Wasi muestra 0 cuando el dato no está cargado
        price_el = card.select_one(".areaPrecio p") or card.select_one(".areaPrecio")
        price, currency = parse_price(text_of(price_el))

        images: list[str] = []
        img = card.select_one("figure img")
        if img:
            src = img.get("data-src") or img.get("src") or ""
            if src:
                images.append(urljoin(base + "/", src))
        if location:
            extra["location"] = location
        if slug_city:
            extra["url_city"] = slug_city

        return self.listing(
            source_id=pid,
            url=url,
            title=title,
            price=price,
            currency=currency,
            locality=locality,
            bedrooms=bedrooms,
            property_type=ptype.capitalize() if ptype.isupper() else ptype,
            operation=op.capitalize() if op.isupper() else op,
            images=images,
            extra=extra,
        )
