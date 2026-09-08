"""Adaptadores WordPress (wp_rest genérico, wp_houzez, wp_realhomes) contra fixtures reales recortados."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from caramcita.sources import wp_houzez, wp_realhomes, wp_rest
from caramcita.sources.wp_rest import is_rental_term, price_from

FIX = Path(__file__).parent / "fixtures"


class StubHttp:
    """Despacha por fragmento de URL. routes: [(fragmento, respuesta | Exception)]."""

    def __init__(self, routes):
        self.routes = routes
        self.calls: list[str] = []

    def _lookup(self, url):
        self.calls.append(url)
        for frag, resp in self.routes:
            if frag in url:
                if isinstance(resp, Exception):
                    raise resp
                return resp
        raise AssertionError(f"URL inesperada: {url}")

    def get_json(self, url, **kw):
        return self._lookup(url)

    def get_text(self, url, **kw):
        return self._lookup(url)

    def get(self, url, **kw):  # pragma: no cover - los adaptadores no lo usan
        return self._lookup(url)


def load_json(name):
    return json.loads((FIX / name).read_text())


def load_text(name):
    return (FIX / name).read_text()


# ---- utilidades -------------------------------------------------------------------------

@pytest.mark.parametrize("term,exp", [
    ({"slug": "en-alquiler", "name": "En alquiler"}, True),
    ({"slug": "alquiler", "name": "Alquiler"}, True),
    ({"slug": "alquileres", "name": "Alquileres"}, True),
    ({"slug": "en-alquiler-temporario", "name": "En alquiler temporario"}, False),
    ({"slug": "en-venta", "name": "En venta"}, False),
])
def test_is_rental_term(term, exp):
    assert is_rental_term(term) is exp


@pytest.mark.parametrize("raw,hint,exp", [
    ("500000.00", "$ $", (500000.0, "ARS")),      # Houzez numérico (el punto es decimal)
    ("600", "U$S  POR UNIDAD", (600.0, "USD")),
    ("$480.000", "", (480000.0, "ARS")),           # Terra: precio con símbolo
    ("0.00", "$", (None, None)),
    ("consultar al cel 3547501286", "$ ", (None, None)),
    ("", "$", (None, None)),
    ("70000", "", (70000.0, "ARS")),               # RealHomes sin moneda: heurística
    ("70000", "USD", (70000.0, "USD")),
])
def test_price_from(raw, hint, exp):
    assert price_from(raw, hint) == exp


# ---- Houzez -----------------------------------------------------------------------------

HOUZEZ_TAXONOMIES = {
    "property_type": {"rest_base": "property_type", "types": ["property"]},
    "property_status": {"rest_base": "property_status", "types": ["property"]},
    "property_city": {"rest_base": "property_city", "types": ["property"]},
}
HOUZEZ_STATUS = [
    {"id": 31, "slug": "en-alquiler", "name": "En alquiler"},
    {"id": 5904, "slug": "en-alquiler-temporario", "name": "En alquiler temporario"},
    {"id": 32, "slug": "en-venta", "name": "En venta"},
]


def houzez_http(posts, html=None):
    routes = [
        ("/wp-json/wp/v2/taxonomies", HOUZEZ_TAXONOMIES),
        ("/wp-json/wp/v2/property_status?per_page=100", HOUZEZ_STATUS),
        ("/wp-json/wp/v2/properties?per_page=50&_embed=1&property_status=31&page=1", posts),
    ]
    if html is not None:
        routes += [("/estado/en-alquiler/page/2/", RuntimeError("404")), ("/estado/en-alquiler/", html)]
    return StubHttp(routes)


def test_houzez_rest():
    http = houzez_http(load_json("wp_houzez_properties.json"))
    ls = wp_houzez.Adapter(slug="goyatucci", name="Goya Tucci", base="https://www.goyatucci.com.ar").fetch(http)
    assert [l.source_id for l in ls] == ["7247", "7386"]
    casa, local = ls
    assert casa.url == "https://www.goyatucci.com.ar/propiedad/223315_casa-en-alquiler-en-barrio-norte/"
    assert casa.title == "Casa en alquiler en Barrio Norte"
    assert (casa.price, casa.currency) == (800000.0, "ARS")
    assert casa.bedrooms == 3
    assert casa.locality == "Alta Gracia"
    assert casa.address == "Brasil 481"
    assert casa.property_type == "Casas"
    assert casa.operation == "En alquiler"
    assert casa.images[0].endswith("713f0739-6b38-4484-a601-9735d5a8549d_wm.jpeg")
    assert casa.lat == pytest.approx(-31.6560998)
    assert casa.extra["area"] == "Barrio Norte"
    assert casa.extra["ref"] == "GOY-223315"
    assert "<" not in casa.description and "ALQUILA" in casa.description
    assert casa.agency == "Goya Tucci" and casa.source == "goyatucci"
    assert local.bedrooms is None
    assert (local.price, local.currency) == (450000.0, "ARS")
    assert local.property_type == "Locales comerciales"
    # filtró por el id del término de alquiler (no el temporario) y no pidió el HTML
    assert any("property_status=31&" in u for u in http.calls)
    assert not any("/estado/" in u for u in http.calls)


def test_houzez_html_fallback_when_no_meta():
    posts = load_json("wp_houzez_properties.json")
    for p in posts:
        del p["property_meta"]
    http = houzez_http(posts, html=load_text("wp_houzez_estado.html"))
    ls = wp_houzez.Adapter(slug="goyatucci", name="Goya Tucci", base="https://www.goyatucci.com.ar").fetch(http)
    casa, local = ls
    assert (casa.price, casa.currency) == (800000.0, "ARS")
    assert casa.bedrooms == 3
    assert casa.address.startswith("Brasil 481")
    assert casa.extra["bathrooms"] == 2
    assert (local.price, local.currency) == (450000.0, "ARS")
    assert local.bedrooms is None
    assert any(u.endswith("/estado/en-alquiler/") for u in http.calls)


def test_houzez_without_status_taxonomy_fetches_all():
    posts = load_json("wp_houzez_properties.json")
    http = StubHttp([
        ("/wp-json/wp/v2/taxonomies", {}),
        ("/wp-json/wp/v2/properties?per_page=50&_embed=1&page=1", posts),
    ])
    ls = wp_houzez.Adapter(slug="x", name="X", base="https://x.test").fetch(http)
    assert len(ls) == 2 and ls[0].operation == "En alquiler"


def test_houzez_skips_unparseable_post():
    posts = load_json("wp_houzez_properties.json") + [{"id": 1, "link": "https://x/1", "title": "roto", "content": 3}]
    http = houzez_http(posts)
    ls = wp_houzez.Adapter(slug="x", name="X", base="https://www.goyatucci.com.ar").fetch(http)
    assert [l.source_id for l in ls] == ["7247", "7386"]


# ---- RealHomes --------------------------------------------------------------------------

def test_realhomes_rest():
    posts = load_json("wp_realhomes_properties.json")
    http = StubHttp([
        ("/wp-json/wp/v2/taxonomies", {
            "property-status": {"rest_base": "estatus-propiedad", "types": ["property"]},
            "property-type": {"rest_base": "tipos-propiedad", "types": ["property"]},
        }),
        ("/wp-json/wp/v2/estatus-propiedad?per_page=100", [
            {"id": 42, "slug": "alquileres", "name": "Alquileres"}, {"id": 41, "slug": "ventas", "name": "Ventas"}]),
        ("/wp-json/wp/v2/properties?per_page=50&_embed=1&estatus-propiedad=42&page=1", posts),
    ])
    ls = wp_realhomes.Adapter(slug="raices", name="Raíces", base="https://raicesaltagracia.com.ar", currency="USD").fetch(http)
    assert len(ls) == 1
    l = ls[0]
    assert l.source_id == "14691"
    assert l.url == "https://raicesaltagracia.com.ar/blog/property/casa-ecologica-en-villa-los-aromos/"
    assert l.title == "CASA ECOLÓGICA EN VILLA LOS AROMOS"
    assert (l.price, l.currency) == (70000.0, "USD")
    assert l.bedrooms == 1
    assert l.locality == "Los Aromos"
    assert l.address.startswith("Villa Los Aromos, Comuna de Villa Los Aromos")
    assert l.property_type == "Casas / Departamentos"
    assert l.operation == "Ventas"
    assert l.images[0].endswith("VENTA-LOS-AROMOS-CASA-ECOLOGICA-15.jpeg")
    assert (l.lat, l.lng) == (pytest.approx(-31.71183116845), pytest.approx(-64.437346499019))
    assert l.extra["m2"] == "42" and l.extra["banos"] == "1"
    assert not any("/blog/" in u or "property-status" in u for u in http.calls)  # sin fallback HTML


# ---- wp_rest genérico (Facundo Sánchez) --------------------------------------------------

def test_wp_rest_with_html_enrichment():
    posts = load_json("wp_rest_property.json")
    http = StubHttp([
        ("/wp-json/wp/v2/taxonomies", {
            "property_type": {"rest_base": "property_type", "types": ["property"]},
            "property_status": {"rest_base": "property_status", "types": ["property"]},
        }),
        ("/wp-json/wp/v2/property_status?per_page=100", [
            {"id": 90, "slug": "alquiler", "name": "Alquiler"}, {"id": 91, "slug": "venta", "name": "Venta"}]),
        ("/wp-json/wp/v2/property?per_page=50&_embed=1&property_status=90&page=1", posts),
        ("/property_status/alquiler/page/2/", RuntimeError("404")),
        ("/property_status/alquiler/", load_text("wp_rest_archive.html")),
    ])
    ls = wp_rest.Adapter(slug="facundosanchez", name="Facundo Sánchez", base="https://facundosanchez.com.ar",
                         post_type="property").fetch(http)
    assert len(ls) == 1
    l = ls[0]
    assert l.source_id == "20223"
    assert l.url == "https://facundosanchez.com.ar/property/casa-en-venta-b-el-golf-alta-gracia/"
    assert l.title == "Casa en venta B° El Golf, Alta Gracia"
    assert (l.price, l.currency) == (280000.0, "USD")   # de la tarjeta HTML
    assert l.bedrooms == 3                               # de la tarjeta HTML
    assert l.address == "Los Jazmines N°318"
    assert l.locality == "Alta Gracia"
    assert l.property_type == "Casas"
    assert l.operation == "Venta"
    assert l.images[0] == "https://facundosanchez.com.ar/wp-content/uploads/2026/08/sdfghfd.jpeg"
    assert l.extra["area"] == "204" and l.extra["bathrooms"] == 1
    assert "tres dormitorios" in l.description


def test_wp_rest_empty_when_no_rentals():
    http = StubHttp([
        ("/wp-json/wp/v2/taxonomies", {"property_status": {"rest_base": "property_status", "types": ["property"]}}),
        ("/wp-json/wp/v2/property_status?per_page=100", [{"id": 90, "slug": "alquiler", "name": "Alquiler"}]),
        ("/wp-json/wp/v2/property?per_page=50&_embed=1&property_status=90&page=1", []),
    ])
    assert wp_rest.Adapter(slug="f", name="F", base="https://facundosanchez.com.ar", post_type="property").fetch(http) == []


def test_wp_rest_paginates_until_short_page():
    post = load_json("wp_rest_property.json")[0]
    page1 = [copy.deepcopy(post) | {"id": i, "link": f"https://x.test/property/p{i}/"} for i in range(1, 51)]
    page2 = [copy.deepcopy(post) | {"id": 99, "link": "https://x.test/property/p99/"}]
    http = StubHttp([
        ("/wp-json/wp/v2/taxonomies", {}),
        ("&page=1", page1), ("&page=2", page2),
    ])
    ls = wp_rest.Adapter(slug="x", name="X", base="https://x.test", post_type="property").fetch(http)
    assert len(ls) == 51 and ls[-1].source_id == "99"
