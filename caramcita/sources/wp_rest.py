"""WordPress genérico: un CPT (p. ej. `property`) expuesto por la REST API de WP.

Sirve tal cual para cualquier tema que registre el CPT con `show_in_rest` y una taxonomía de
estado/operación (alquiler / venta). Los temas conocidos (Houzez, RealHomes) heredan de acá y sólo
mapean sus campos de `property_meta`.

Params (sources.yaml):
  base         origen del sitio, p. ej. https://inmobiliaria.com.ar
  post_type    nombre del CPT (default "property")
  rest_base    rest_base del CPT si difiere de post_type (Houzez/RealHomes usan "properties")
  status_tax   rest_base de la taxonomía de estado; si falta se descubre en /wp-json/wp/v2/taxonomies
  archive_url  página HTML con las tarjetas de alquileres, para completar precio/dormitorios cuando la
               REST no expone meta. Default: {base}/{taxonomía}/{slug-del-término}/

Estrategia: resolver los ids de los términos de alquiler por slug (contienen "alquiler" y no
"tempor"), pedir `?{status_tax}=<ids>&_embed=1` paginado, y leer título, link, contenido, términos
embebidos (tipo, ciudad, barrio, estado) y foto destacada. Si no hay taxonomía de estado, se traen
todos los avisos y `operation` sale del texto; el clasificador descarta las ventas.
"""
from __future__ import annotations

import html as htmlmod
import logging
import re
from typing import Any

from bs4 import BeautifulSoup

from ..http import Http
from ..models import Listing
from .base import Source, parse_price, text_of

log = logging.getLogger(__name__)

PER_PAGE = 50
MAX_PAGES = 10

_TAX_TYPE = re.compile(r"(?i)type|tipo")
_TAX_CITY = re.compile(r"(?i)city|ciudad|locali")
_TAX_AREA = re.compile(r"(?i)area|barrio|zona")
_TAX_STATUS = re.compile(r"(?i)status|estatus|estado|operac")
_RENTAL = re.compile(r"(?i)alquiler|rent")
_TEMPORARY = re.compile(r"(?i)tempor|vacacion|turis")
_SALE = re.compile(r"(?i)venta|sale")


# ---- utilidades compartidas por los adaptadores WP ---------------------------------------

def strip_html(s: str | None) -> str:
    if not s:
        return ""
    return " ".join(BeautifulSoup(htmlmod.unescape(s), "lxml").get_text(" ", strip=True).split())


def clean_title(s: str | None) -> str:
    return " ".join(htmlmod.unescape(BeautifulSoup(s or "", "lxml").get_text(" ")).split())


def meta_value(meta: dict[str, Any] | None, key: str) -> str:
    """`property_meta` trae listas (Houzez) o escalares (RealHomes); devuelve el primer valor como str."""
    if not meta:
        return ""
    v = meta.get(key)
    if isinstance(v, list):
        v = v[0] if v else ""
    if v is None or isinstance(v, (dict, list)):
        return ""
    return str(v).strip()


def to_int(s: str | None) -> int | None:
    m = re.search(r"\d+", s or "")
    return int(m.group()) if m else None


def to_float(s: str | None) -> float | None:
    try:
        return float(str(s).replace(",", ".")) if s not in (None, "") else None
    except ValueError:
        return None


def currency_of(txt: str) -> str | None:
    t = (txt or "").lower()
    if any(k in t for k in ("u$s", "usd", "us$", "u$d", "dolar", "dólar")):
        return "USD"
    if any(k in t for k in ("$", "ars", "peso")):
        return "ARS"
    return None


def price_from(raw: str, currency_hint: str = "") -> tuple[float | None, str | None]:
    """Precio como lo guardan los temas: '500000.00', '600', '$480.000', 'consultar'."""
    raw = (raw or "").strip()
    if not raw:
        return None, None
    if re.fullmatch(r"\d+(?:\.\d+)?", raw):  # numérico puro: el punto es decimal, no de miles
        value = float(raw)
        if value <= 0:
            return None, None
        return value, currency_of(currency_hint) or ("USD" if value < 5000 else "ARS")
    return parse_price(f"{currency_hint} {raw}")


def embedded_terms(post: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for group in (post.get("_embedded") or {}).get("wp:term") or []:
        if isinstance(group, list):
            out.extend(t for t in group if isinstance(t, dict) and t.get("name"))
    return out


def featured_image(post: dict[str, Any]) -> str | None:
    media = (post.get("_embedded") or {}).get("wp:featuredmedia") or []
    for m in media:
        if not isinstance(m, dict):
            continue
        url = m.get("source_url")
        if not url:
            sizes = ((m.get("media_details") or {}).get("sizes") or {})
            url = (sizes.get("full") or sizes.get("large") or {}).get("source_url")
        if url:
            return url
    return None


def is_rental_term(term: dict[str, Any]) -> bool:
    txt = f"{term.get('slug', '')} {term.get('name', '')}"
    return bool(_RENTAL.search(txt)) and not _TEMPORARY.search(txt)


class Adapter(Source):
    """CPT genérico. Subclases: `rest_base_default` y `apply_meta`."""

    rest_base_default: str | None = None

    def __init__(self, slug: str, name: str, base: str, post_type: str = "property", **params: Any):
        super().__init__(slug, name, base=base, post_type=post_type, **params)
        self.base = base.rstrip("/")
        self.post_type = post_type
        self.rest_base = params.get("rest_base") or self.rest_base_default or post_type
        self.status_tax = params.get("status_tax")  # rest_base de la taxonomía, si se conoce
        self.archive_url = params.get("archive_url")
        self.api = f"{self.base}/wp-json/wp/v2"

    # ---- fetch --------------------------------------------------------------------------
    def fetch(self, http: Http) -> list[Listing]:
        tax = self._status_taxonomy(http)
        rental_terms = self._rental_terms(http, tax) if tax else []
        if tax and not rental_terms:
            log.warning("[%s] taxonomía %s sin término de alquiler; traigo todo", self.slug, tax["rest_base"])
        query = f"per_page={PER_PAGE}&_embed=1"
        if rental_terms:
            query += f"&{tax['rest_base']}={','.join(str(t['id']) for t in rental_terms)}"
        posts = self._paginate(http, f"{self.api}/{self.rest_base}?{query}")

        listings: list[Listing] = []
        for post in posts:
            try:
                l = self.build(post)
            except Exception as e:  # noqa: BLE001
                log.warning("[%s] aviso %s no parseable: %s", self.slug, post.get("id"), e)
                continue
            if l is not None:
                listings.append(l)
        self.enrich(http, listings, tax, rental_terms)
        return listings

    def _paginate(self, http: Http, url: str) -> list[dict[str, Any]]:
        posts: list[dict[str, Any]] = []
        for page in range(1, MAX_PAGES + 1):
            try:
                data = http.get_json(f"{url}&page={page}")
            except Exception as e:  # noqa: BLE001 - WP devuelve 400 pasada la última página
                if page == 1:
                    raise
                log.debug("[%s] fin de paginación en %s: %s", self.slug, page, e)
                break
            if not isinstance(data, list) or not data:
                break
            posts.extend(data)
            if len(data) < PER_PAGE:
                break
        return posts

    # ---- taxonomía de estado ------------------------------------------------------------
    def _status_taxonomy(self, http: Http) -> dict[str, str] | None:
        """{name, rest_base} de la taxonomía de estado, o None si el sitio no la expone."""
        if self.status_tax:
            return {"name": self.status_tax, "rest_base": self.status_tax}
        try:
            taxes = http.get_json(f"{self.api}/taxonomies")
        except Exception as e:  # noqa: BLE001
            log.warning("[%s] sin /taxonomies (%s); traigo todo", self.slug, e)
            return None
        if not isinstance(taxes, dict):
            return None
        for key, t in taxes.items():
            if not isinstance(t, dict):
                continue
            types = t.get("types") or []
            if self.post_type not in types and self.rest_base not in types:
                continue
            rest_base = t.get("rest_base") or key
            if _TAX_STATUS.search(key) or _TAX_STATUS.search(rest_base):
                return {"name": key, "rest_base": rest_base}
        return None

    def _rental_terms(self, http: Http, tax: dict[str, str]) -> list[dict[str, Any]]:
        try:
            terms = http.get_json(f"{self.api}/{tax['rest_base']}?per_page=100")
        except Exception as e:  # noqa: BLE001
            log.warning("[%s] no pude leer términos de %s: %s", self.slug, tax["rest_base"], e)
            return []
        if not isinstance(terms, list):
            return []
        return [t for t in terms if isinstance(t, dict) and t.get("id") and is_rental_term(t)]

    # ---- construcción del aviso ---------------------------------------------------------
    def build(self, post: dict[str, Any]) -> Listing | None:
        pid = post.get("id")
        url = post.get("link") or ""
        if not pid or not url:
            return None
        title = clean_title((post.get("title") or {}).get("rendered"))
        content = strip_html((post.get("content") or {}).get("rendered"))
        excerpt = strip_html((post.get("excerpt") or {}).get("rendered"))
        kw: dict[str, Any] = dict(
            source_id=str(pid),
            url=url,
            title=title,
            description=content or excerpt,
            extra={},
        )
        types, cities, areas, statuses = [], [], [], []
        for t in embedded_terms(post):
            tax = t.get("taxonomy", "")
            if _TAX_STATUS.search(tax):
                statuses.append(t["name"])
            elif _TAX_TYPE.search(tax):
                types.append(t["name"])
            elif _TAX_CITY.search(tax):
                cities.append(t["name"])
            elif _TAX_AREA.search(tax):
                areas.append(t["name"])
        kw["property_type"] = " / ".join(types)
        kw["locality"] = cities[0] if cities else ""
        kw["operation"] = " / ".join(statuses) or self._operation_from_text(title)
        if areas:
            kw["address"] = areas[0]
            kw["extra"]["area"] = areas[0]
        img = featured_image(post)
        kw["images"] = [img] if img else []
        self.apply_meta(post, kw)
        return self.listing(**kw)

    @staticmethod
    def _operation_from_text(title: str) -> str:
        if _RENTAL.search(title):
            return "Alquiler temporario" if _TEMPORARY.search(title) else "Alquiler"
        if _SALE.search(title):
            return "Venta"
        return ""

    def apply_meta(self, post: dict[str, Any], kw: dict[str, Any]) -> None:
        """Genérico: mira `meta`/`acf` si el sitio los expone y busca claves conocidas."""
        meta = post.get("meta") or post.get("acf") or {}
        if not isinstance(meta, dict) or not meta:
            return
        for k, v in meta.items():
            kl = k.lower()
            if isinstance(v, (dict, list)) or v in (None, ""):
                continue
            if "price" in kl or "precio" in kl:
                if kw.get("price") is None:
                    kw["price"], kw["currency"] = price_from(str(v))
            elif "bedroom" in kl or "dormitorio" in kl:
                kw.setdefault("bedrooms", to_int(str(v)))
            elif "address" in kl or "direccion" in kl or "dirección" in kl:
                if not kw.get("address"):
                    kw["address"] = str(v)

    # ---- enriquecer con la página HTML de tarjetas -------------------------------------
    def enrich(self, http: Http, listings: list[Listing], tax: dict[str, str] | None,
               rental_terms: list[dict[str, Any]]) -> None:
        if not listings or all(l.price is not None for l in listings):
            return
        urls = self._archive_urls(tax, rental_terms)
        if not urls:
            return
        by_url = {l.url.rstrip("/"): l for l in listings}
        for url in urls:
            for page in range(1, MAX_PAGES + 1):
                page_url = url if page == 1 else f"{url}page/{page}/"
                try:
                    html = http.get_text(page_url)
                except Exception as e:  # noqa: BLE001
                    log.debug("[%s] sin página %s: %s", self.slug, page_url, e)
                    break
                cards = self.parse_archive_cards(html, set(by_url))
                if not cards:
                    break
                for link, data in cards.items():
                    self._merge_card(by_url[link], data)

    def _archive_urls(self, tax: dict[str, str] | None, rental_terms: list[dict[str, Any]]) -> list[str]:
        if self.archive_url:
            return [self.archive_url if self.archive_url.endswith("/") else self.archive_url + "/"]
        if tax and rental_terms:
            return [f"{self.base}/{tax['name']}/{t['slug']}/" for t in rental_terms if t.get("slug")]
        return []

    @staticmethod
    def _merge_card(l: Listing, data: dict[str, Any]) -> None:
        if l.price is None and data.get("price"):
            l.price, l.currency = parse_price(data["price"])
        if l.bedrooms is None and data.get("bedrooms") is not None:
            l.bedrooms = data["bedrooms"]
        # la tarjeta trae la dirección completa; pisa el barrio que se puso como relleno
        if data.get("address") and (not l.address or l.address == l.extra.get("area")):
            l.address = data["address"]
        if not l.property_type and data.get("property_type"):
            l.property_type = data["property_type"]
        if not l.operation and data.get("operation"):
            l.operation = data["operation"]
        for k in ("area", "bathrooms"):
            if data.get(k) and k not in l.extra:
                l.extra[k] = data[k]

    @staticmethod
    def parse_archive_cards(html: str, wanted: set[str]) -> dict[str, dict[str, Any]]:
        """Tarjetas de un archivo WP cualquiera: {url: {price, bedrooms, address, ...}}.

        Busca los links a los avisos y sube hasta el contenedor de la tarjeta (clase con item/card/
        property/listing) para leer precio, dormitorios y dirección con selectores tolerantes.
        """
        soup = BeautifulSoup(html, "lxml")
        out: dict[str, dict[str, Any]] = {}
        for a in soup.select("a[href]"):
            link = a["href"].rstrip("/")
            if link not in wanted or link in out:
                continue
            card = a
            for _ in range(8):
                if card.parent is None or card.parent.name in ("body", "html"):
                    break
                card = card.parent
                cls = " ".join(card.get("class") or [])
                if re.search(r"(?i)\b(sl-item|item|card|property|listing)", cls) and card.select_one("[class*=price]"):
                    break
            price_el = card.select_one("[class*=price]")
            addr_el = card.select_one("[class*=address]")
            data: dict[str, Any] = {
                "price": text_of(price_el) if price_el else "",
                "address": text_of(addr_el) if addr_el else "",
            }
            txt = text_of(card)
            m = re.search(r"(?i)(?:habitaci\w*|dormitorio\w*|dorm\.?)\s*:?\s*(\d+)", txt)
            if m:
                data["bedrooms"] = int(m.group(1))
            m = re.search(r"(?i)ba[ñn]os?\s*:?\s*(\d+)", txt)
            if m:
                data["bathrooms"] = int(m.group(1))
            type_el = card.select_one("a.type, .type, [class*=property-type], .h-type")
            if type_el:
                data["property_type"] = text_of(type_el)
            status_el = card.select_one("a.status, .status, .label-status")
            if status_el:
                data["operation"] = text_of(status_el)
            m = re.search(r"(\d[\d.,]*)\s*-?\s*m2", txt)
            if m:
                data["area"] = m.group(1)
            out[link] = data
        return out
