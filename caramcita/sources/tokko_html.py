"""Adaptador genérico para sitios de Tokko Broker con listado server-rendered.

Los sitios "tfw" de Tokko sirven el listado en `/Buscar?operation=<id>&ptypes=<ids>` (a lo que
redirigen `/Alquiler`, `/Venta`, `/Casas`, etc.). Las páginas siguientes se piden con `&p=N` y el
servidor devuelve un fragmento con más `<li prop-id=...>` o el texto `--NoMoreProperties--`.

Params (sources.yaml):
  base:      URL raíz del sitio (obligatorio), p. ej. https://www.ruartemoyano.com.ar
  operation: id de operación de Tokko (1 = Venta, 2 = Alquiler, 3 = Alquiler temporario). Default 2.
  ptypes:    ids de tipo de propiedad separados por coma (3 = Casa). "" trae todos. Default "3".
  max_pages: tope de páginas. Default 10.
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

NO_MORE = "--NoMoreProperties--"

# "Departamento en Alquiler   en Camara, Alta Gracia" → tipo / operación / ubicación
_TIPO_UB_RE = re.compile(
    r"^(?P<type>.+?)\s+en\s+(?P<op>Alquiler(?:\s+temporario)?|Venta)\s+en\s+(?P<loc>.+)$",
    re.IGNORECASE,
)
_OPERATIONS = {1: "Venta", 2: "Alquiler", 3: "Alquiler temporario"}


class Adapter(Source):
    def fetch(self, http: Http) -> list[Listing]:
        base = self.params["base"].rstrip("/")
        operation = int(self.params.get("operation", 2))
        ptypes = str(self.params.get("ptypes", "3") or "")
        max_pages = int(self.params.get("max_pages", 10))
        default_op = _OPERATIONS.get(operation, "")

        out: list[Listing] = []
        seen: set[str] = set()
        for page in range(1, max_pages + 1):
            url = self.page_url(base, operation, ptypes, page)
            html = http.get_text(url)
            if NO_MORE in html:
                break
            cards = BeautifulSoup(html, "lxml").select("li[prop-id]")
            if not cards:
                break
            new = 0
            for li in cards:
                try:
                    lst = self.parse_card(li, base, default_op)
                except Exception as e:  # noqa: BLE001
                    log.warning("[%s] aviso ilegible en %s: %s", self.slug, url, e)
                    continue
                if lst and lst.source_id not in seen:
                    seen.add(lst.source_id)
                    out.append(lst)
                    new += 1
            if new == 0:
                break
        return out

    @staticmethod
    def page_url(base: str, operation: int, ptypes: str, page: int) -> str:
        url = f"{base}/Buscar?operation={operation}&ptypes={ptypes}"
        return url if page == 1 else f"{url}&p={page}"

    def parse_card(self, li, base: str, default_op: str) -> Listing | None:
        pid = (li.get("prop-id") or "").strip()
        a = li.find("a", href=re.compile(r"/p/\d+"))
        if not a:
            return None
        if not pid:
            pid = re.search(r"/p/(\d+)", a["href"]).group(1)
        url = urljoin(base + "/", a["href"])

        tipo_ub = text_of(li.select_one(".prop-desc-tipo-ub"))
        dir_txt = text_of(li.select_one(".prop-desc-dir"))
        ptype, op, address, locality = "", default_op, "", ""
        m = _TIPO_UB_RE.match(tipo_ub)
        if m:
            ptype = m.group("type").strip()
            op = m.group("op").strip().capitalize()
            parts = [p.strip() for p in m.group("loc").split(",") if p.strip()]
            if parts:
                locality = parts[-1]
                address = ", ".join(parts[:-1])

        # precio: texto directo de .prop-valor-nro (los hijos son código de referencia y favoritos)
        val = li.select_one(".prop-valor-nro")
        price_txt = " ".join(s.strip() for s in val.find_all(string=True, recursive=False)) if val else ""
        price, currency = parse_price(price_txt)

        img = li.select_one("img.dest-img") or li.select_one(".prop-img img[src*='/pictures/'], .prop-img img[src*='w_pics']")
        images: list[str] = []
        if img:
            src = img.get("data-src") or img.get("src") or ""
            if src and "prop-icons" not in src:
                images.append(urljoin(base + "/", src))

        extra: dict = {}
        codref = text_of(li.select_one(".codref"))
        if codref:
            extra["codref"] = codref
        surface = text_of(li.select_one(".prop-data div"))
        if surface and surface != "0 m²":
            extra["surface"] = surface
        amb = text_of(li.select_one(".prop-data2 div"))
        if amb.isdigit() and int(amb) > 0:
            extra["ambientes"] = int(amb)

        title = tipo_ub or text_of(a)
        return self.listing(
            source_id=pid,
            url=url,
            title=title,
            description=dir_txt,
            price=price,
            currency=currency,
            locality=locality,
            address=address,
            bedrooms=None,  # Tokko muestra ambientes, no dormitorios; lo saca el clasificador del texto
            property_type=ptype,
            operation=op,
            images=images,
            extra=extra,
        )
