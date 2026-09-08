"""WordPress con tema RealHomes: CPT `property`, REST en /wp-json/wp/v2/properties.

Params: `base`. Opcional `currency` ("ARS"/"USD") si el sitio muestra una sola moneda global y los
precios de la REST vienen sin símbolo (RealHomes guarda sólo el número en REAL_HOMES_property_price).

La taxonomía de estado en RealHomes se llama `property-status` pero su rest_base suele estar
traducido (p. ej. `estatus-propiedad`); se descubre por /wp-json/wp/v2/taxonomies. Campos de
`property_meta`: REAL_HOMES_property_price (+prefix/postfix), REAL_HOMES_property_bedrooms,
REAL_HOMES_property_address, REAL_HOMES_property_location{latitude,longitude}, tamaño, baños, cochera.
"""
from __future__ import annotations

import logging
from typing import Any

from . import wp_rest
from .wp_rest import meta_value, price_from, to_float, to_int

log = logging.getLogger(__name__)


class Adapter(wp_rest.Adapter):
    rest_base_default = "properties"

    def __init__(self, slug: str, name: str, base: str, **params: Any):
        super().__init__(slug, name, base, post_type="property", **params)
        self.currency = params.get("currency")

    def apply_meta(self, post: dict[str, Any], kw: dict[str, Any]) -> None:
        pm = post.get("property_meta")
        if not isinstance(pm, dict) or not pm:
            return
        g = lambda k: meta_value(pm, k)  # noqa: E731
        prefix, postfix = g("REAL_HOMES_property_price_prefix"), g("REAL_HOMES_property_price_postfix")
        price, cur = price_from(g("REAL_HOMES_property_price"), f"{prefix} {postfix} {self.currency or ''}")
        kw["price"], kw["currency"] = price, cur
        kw["bedrooms"] = to_int(g("REAL_HOMES_property_bedrooms"))
        kw["address"] = g("REAL_HOMES_property_address") or kw.get("address", "")
        loc = pm.get("REAL_HOMES_property_location")
        if isinstance(loc, dict):
            kw["lat"] = to_float(loc.get("latitude"))
            kw["lng"] = to_float(loc.get("longitude"))
        extra = kw["extra"]
        size = g("REAL_HOMES_property_size")
        if size:
            extra["m2"] = f"{size} {g('REAL_HOMES_property_size_postfix')}".strip()
        for key, label in (("REAL_HOMES_property_lot_size", "m2_terreno"), ("REAL_HOMES_property_bathrooms", "banos"),
                           ("REAL_HOMES_property_garage", "cochera"), ("REAL_HOMES_property_id", "ref")):
            v = g(key)
            if v and v != "0":
                extra[label] = v
        if postfix:
            extra["price_postfix"] = postfix

    def enrich(self, http, listings, tax, rental_terms) -> None:  # noqa: ANN001
        # RealHomes expone todo en property_meta; su archivo HTML vive en /blog/property-status/...
        # y el precio ausente es ausente también ahí. Sólo se usa si se configura archive_url.
        if self.archive_url:
            super().enrich(http, listings, tax, rental_terms)
