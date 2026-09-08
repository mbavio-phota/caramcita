"""Inmobiliaria Invertir (inmobiliariainvertir.com): WordPress + JetEngine, CPT `inmueble`.

Dos fuentes que se combinan por id de post:

- La página `/en-alquiler/` (HTML, JetEngine listing grid, máx. 9 tarjetas, sin paginación) trae
  precio, dormitorios, baños, superficie, dirección y foto (background-image). Los alquileres
  temporarios están en otra página, así que esto es sólo alquiler anual.
- El REST `/wp-json/wp/v2/inmueble?tipo-operacion=<id alquiler>&_embed` trae título, descripción,
  foto destacada y las taxonomías `ubicaciones` (localidad), `tipo-inmueble` y `tipo-operacion`.
  No expone meta (precio/dormitorios), por eso no alcanza solo.

Si el REST falla se devuelve lo del HTML; si el HTML falla, lo del REST.
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

_BG_RE = re.compile(r"background-image\s*:\s*url\(\s*['\"]?([^'\")]+)")
_BEDS_RE = re.compile(r"(?i)^\s*(\d+)\s*dormitorio")
_BATHS_RE = re.compile(r"(?i)^\s*(\d+)\s*ba[ñn]o")
_SURF_RE = re.compile(r"(?i)superficie\s*:?\s*(.+)")
_OPS = ("alquiler", "venta", "alquiler temporario")


class Adapter(Source):
    def __init__(self, slug: str, name: str, **params):
        super().__init__(slug, name, **params)
        self.base: str = params.get("base", "https://inmobiliariainvertir.com").rstrip("/")
        self.list_path: str = params.get("list_path", "/en-alquiler/")
        self.operation_slugs: list[str] = list(params.get("operation_slugs", ["alquiler"]))

    # ---- fetch -----------------------------------------------------------
    def fetch(self, http: Http) -> list[Listing]:
        html_cards: dict[str, dict] = {}
        try:
            html_cards = self.parse_html(http.get_text(self.base + self.list_path))
        except Exception as e:  # noqa: BLE001
            log.warning("[%s] listado HTML falló: %s", self.slug, e)

        rest_posts: list[dict] = []
        try:
            rest_posts = self._fetch_rest(http)
        except Exception as e:  # noqa: BLE001
            log.warning("[%s] REST falló: %s", self.slug, e)

        return self.merge(html_cards, rest_posts)

    def _fetch_rest(self, http: Http) -> list[dict]:
        terms = http.get_json(f"{self.base}/wp-json/wp/v2/tipo-operacion?per_page=100")
        ids = [str(t["id"]) for t in terms if t.get("slug") in self.operation_slugs]
        if not ids:
            log.warning("[%s] no encontré términos tipo-operacion %s", self.slug, self.operation_slugs)
            return []
        posts: list[dict] = []
        for page in range(1, 6):
            url = (f"{self.base}/wp-json/wp/v2/inmueble?tipo-operacion={','.join(ids)}"
                   f"&per_page=100&page={page}&_embed=1")
            batch = http.get_json(url)
            if not isinstance(batch, list) or not batch:
                break
            posts.extend(batch)
            if len(batch) < 100:
                break
        return posts

    # ---- parse HTML ------------------------------------------------------
    def parse_html(self, html: str) -> dict[str, dict]:
        soup = BeautifulSoup(html, "lxml")
        out: dict[str, dict] = {}
        for item in soup.select(".jet-listing-grid__item[data-post-id]"):
            try:
                pid, d = self._parse_card(item)
            except Exception as e:  # noqa: BLE001
                log.warning("[%s] tarjeta no parseable: %s", self.slug, e)
                continue
            out[pid] = d
        return out

    def _parse_card(self, item) -> tuple[str, dict]:
        pid = str(item["data-post-id"])
        wrap = item.select_one("[data-url]")
        url = wrap["data-url"] if wrap else ""
        d: dict = {"url": url, "extra": {}}

        heads = [text_of(h) for h in item.select(".elementor-heading-title")]
        others: list[str] = []
        for h in heads:
            if not h:
                continue
            if h.lower() in _OPS and "operation" not in d:
                d["operation"] = h
            elif "title" not in d and h.lower() not in _OPS:
                d["title"] = h
            else:
                others.append(h)
        for h in others:
            if m := _BEDS_RE.match(h):
                d["bedrooms"] = int(m.group(1))
            elif m := _BATHS_RE.match(h):
                d["extra"]["banios"] = int(m.group(1))
            elif m := _SURF_RE.match(h):
                d["extra"]["superficie"] = m.group(1).strip()
            elif "address" not in d:
                d["address"] = h

        price_txt = " ".join(text_of(f) for f in item.select(".jet-listing-dynamic-field__content"))
        d["price"], d["currency"] = parse_price(price_txt)

        m = _BG_RE.search(str(item))
        if m:
            d["images"] = [urljoin(self.base + "/", m.group(1).strip())]
        return pid, d

    # ---- merge -----------------------------------------------------------
    def merge(self, html_cards: dict[str, dict], rest_posts: list[dict]) -> list[Listing]:
        out: list[Listing] = []
        done: set[str] = set()
        for p in rest_posts:
            try:
                l = self._from_rest(p, html_cards.get(str(p.get("id"))))
            except Exception as e:  # noqa: BLE001
                log.warning("[%s] post REST no parseable: %s", self.slug, e)
                continue
            done.add(l.source_id)
            out.append(l)
        for pid, d in html_cards.items():
            if pid in done or not d.get("url"):
                continue
            out.append(self.listing(
                source_id=pid,
                url=d["url"],
                title=d.get("title") or f"Inmueble {pid}",
                price=d.get("price"),
                currency=d.get("currency"),
                address=d.get("address", ""),
                bedrooms=d.get("bedrooms"),
                operation=d.get("operation", ""),
                images=d.get("images", []),
                extra=d.get("extra", {}),
            ))
        return out

    def _from_rest(self, p: dict, card: dict | None) -> Listing:
        card = card or {}
        pid = str(p["id"])
        title = unescape(BeautifulSoup(p.get("title", {}).get("rendered", ""), "lxml").get_text(" ", strip=True))
        description = text_of(BeautifulSoup(p.get("content", {}).get("rendered", ""), "lxml"))
        emb = p.get("_embedded") or {}
        terms: dict[str, list[str]] = {}
        for grp in emb.get("wp:term") or []:
            for t in grp:
                terms.setdefault(t.get("taxonomy", ""), []).append(unescape(t.get("name", "")))
        images: list[str] = []
        for m in emb.get("wp:featuredmedia") or []:
            if m.get("source_url"):
                images.append(m["source_url"])
        for u in card.get("images", []):
            if u not in images:
                images.append(u)
        extra = dict(card.get("extra", {}))
        extra["slug"] = p.get("slug", "")
        if len(terms.get("ubicaciones", [])) > 1:
            extra["ubicaciones"] = terms["ubicaciones"]
        return self.listing(
            source_id=pid,
            url=p.get("link") or card.get("url", ""),
            title=title or card.get("title") or f"Inmueble {pid}",
            description=description,
            price=card.get("price"),
            currency=card.get("currency"),
            locality=(terms.get("ubicaciones") or [""])[0],
            address=card.get("address", ""),
            bedrooms=card.get("bedrooms"),
            property_type=(terms.get("tipo-inmueble") or [""])[0],
            operation=(terms.get("tipo-operacion") or [card.get("operation", "")])[0],
            images=images,
            extra=extra,
        )
