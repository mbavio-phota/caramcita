"""WordPress con tema Houzez: CPT `property`, REST en /wp-json/wp/v2/properties.

Params: `base` (origen del sitio). Opcionales: `html_path` (slug de la taxonomía de estado en las
URLs HTML, default "estado") para el fallback a las tarjetas cuando la REST no expone `property_meta`.

Campos: título/link/contenido y términos embebidos (property_type, property_city, property_area,
property_status) de la REST; precio, moneda, dormitorios, dirección y coordenadas de `property_meta`
(fave_property_price, fave_currency, fave_property_bedrooms, fave_property_address,
houzez_geolocation_lat/long); foto de `_embedded['wp:featuredmedia']`.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from bs4 import BeautifulSoup

from ..http import Http
from ..models import Listing
from .base import text_of
from . import wp_rest
from .wp_rest import MAX_PAGES, meta_value, price_from, to_float, to_int

log = logging.getLogger(__name__)


class Adapter(wp_rest.Adapter):
    rest_base_default = "properties"

    def __init__(self, slug: str, name: str, base: str, **params: Any):
        super().__init__(slug, name, base, post_type="property", **params)
        self.html_path = params.get("html_path", "estado")
        self._meta_seen = False

    def apply_meta(self, post: dict[str, Any], kw: dict[str, Any]) -> None:
        pm = post.get("property_meta")
        if not isinstance(pm, dict) or not pm:
            return
        self._meta_seen = True
        g = lambda k: meta_value(pm, k)  # noqa: E731
        postfix = g("fave_property_price_postfix")
        kw["price"], kw["currency"] = price_from(g("fave_property_price"), f"{g('fave_currency')} {postfix}")
        kw["bedrooms"] = to_int(g("fave_property_bedrooms"))
        kw["address"] = g("fave_property_address") or g("fave_property_map_address") or kw.get("address", "")
        kw["lat"] = to_float(g("houzez_geolocation_lat"))
        kw["lng"] = to_float(g("houzez_geolocation_long"))
        extra = kw["extra"]
        for key, label in (("fave_property_id", "ref"), ("fave_property_size", "m2"),
                           ("fave_property_land", "m2_terreno"), ("fave_property_bathrooms", "banos"),
                           ("fave_property_garage", "cochera"), ("fave_property_rooms", "ambientes")):
            v = g(key)
            if v and v not in ("0", "0.00"):
                extra[label] = v
        if postfix and postfix not in ("$", "USD", "U$S"):
            extra["price_postfix"] = postfix

    # ---- fallback: tarjetas HTML de {base}/estado/<slug>/ ----------------------------------
    def enrich(self, http: Http, listings: list[Listing], tax: dict[str, str] | None,
               rental_terms: list[dict[str, Any]]) -> None:
        if not listings or self._meta_seen:
            return
        slugs = [t["slug"] for t in rental_terms if t.get("slug")] or ["en-alquiler", "alquiler"]
        by_id = {l.source_id: l for l in listings}
        for slug in slugs:
            base_url = f"{self.base}/{self.html_path}/{slug}/"
            for page in range(1, MAX_PAGES + 1):
                url = base_url if page == 1 else f"{base_url}page/{page}/"
                try:
                    html = http.get_text(url)
                except Exception as e:  # noqa: BLE001
                    log.debug("[%s] sin %s: %s", self.slug, url, e)
                    break
                cards = self.parse_houzez_cards(html)
                if not cards:
                    break
                for pid, data in cards.items():
                    if pid in by_id:
                        self._merge_card(by_id[pid], data)

    @staticmethod
    def parse_houzez_cards(html: str) -> dict[str, dict[str, Any]]:
        """{id: {price, bedrooms, address, property_type, operation, area, bathrooms}} de .item-listing-wrap."""
        soup = BeautifulSoup(html, "lxml")
        out: dict[str, dict[str, Any]] = {}
        for card in soup.select(".item-listing-wrap[data-hz-id]"):
            m = re.search(r"\d+", card.get("data-hz-id", ""))
            if not m:
                continue
            data: dict[str, Any] = {
                "price": text_of(card.select_one(".item-price")),
                "address": text_of(card.select_one(".item-address")),
                "property_type": text_of(card.select_one(".h-type")),
                "operation": text_of(card.select_one(".label-status")),
            }
            beds = card.select_one(".h-beds .hz-figure")
            if beds:
                data["bedrooms"] = to_int(text_of(beds))
            baths = card.select_one(".h-baths .hz-figure")
            if baths:
                data["bathrooms"] = to_int(text_of(baths))
            area = card.select_one(".h-area .hz-figure")
            if area:
                data["area"] = text_of(area)
            out[m.group()] = data
        return out
