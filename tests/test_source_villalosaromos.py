"""Villa Los Aromos: archivo HTML de Estatik + detalle para los alquileres permanentes."""
from __future__ import annotations

from pathlib import Path

import pytest

from caramcita.sources import villalosaromos
from caramcita.sources.villalosaromos import operation_of

FIX = Path(__file__).parent / "fixtures"
BASE = "https://inmobiliariavillalosaromos.com.ar"


class StubHttp:
    def __init__(self):
        self.calls: list[str] = []

    def get_text(self, url, **kw):
        self.calls.append(url)
        if url == f"{BASE}/property/":
            return (FIX / "villalosaromos_archive.html").read_text()
        if url == f"{BASE}/property/alquiler-permanente-el-descanso-anisacate/":
            return (FIX / "villalosaromos_detail.html").read_text()
        raise RuntimeError(f"404 {url}")

    def get_json(self, url, **kw):  # pragma: no cover
        raise AssertionError("no usa REST")

    def get(self, url, **kw):  # pragma: no cover
        raise AssertionError("no usa get()")


@pytest.mark.parametrize("title,terms,exp", [
    ("ALQUILER PERMANENTE – EL DESCANSO ANISACATE", ["Alquiler Permanente"], "Alquiler"),
    ("A-114 ( VILLA LOS AROMOS ISLA )", ["Alquiler temporal"], "Alquiler temporario"),
    ("CASA EN ALQUILER TEMPORARIO", [], "Alquiler temporario"),
    ("V-27 CASA EN VENTA – ISLA USD 250.000", ["Casas en venta"], "Venta"),
    ("TERRENO P. DE GARAY", [], ""),
])
def test_operation_of(title, terms, exp):
    assert operation_of(title, terms) == exp


def test_fetch_filters_sales_and_reads_detail():
    http = StubHttp()
    ls = villalosaromos.Adapter(slug="villalosaromos", name="Villa Los Aromos").fetch(http)
    assert [l.source_id for l in ls] == ["7930", "7675"]  # la venta (8040) queda afuera
    perm, temp = ls

    assert perm.url == f"{BASE}/property/alquiler-permanente-el-descanso-anisacate/"
    assert perm.title == "ALQUILER PERMANENTE – EL DESCANSO ANISACATE"
    assert perm.operation == "Alquiler"
    assert (perm.price, perm.currency) == (800000.0, "ARS")  # "Precio mensual: $800.000" en la descripción
    assert perm.bedrooms is None and perm.locality == ""     # la fuente no lo da estructurado
    assert "4 dormitorios" in perm.description and "Mostrar toda" not in perm.description
    assert perm.images[0] == f"{BASE}/wp-content/uploads/2026/06/9c13f3f7-96f0-4ebb-bfad-74bf404fb05e.jpeg"
    assert len(perm.images) == 3
    assert perm.extra["categoria"] == "Alquiler Permanente"
    assert perm.agency == "Villa Los Aromos"

    assert temp.url == f"{BASE}/property/a-114-villa-los-aromos-isla-2/"
    assert temp.operation == "Alquiler temporario"
    assert temp.price is None
    assert temp.images and "-1024x768" not in temp.images[0]  # foto en tamaño original
    # sólo entra al detalle del permanente; el archivo se pidió una vez y no se siguió a ?paged=2 (404)
    assert http.calls.count(f"{BASE}/property/") == 1
    assert not any("a-114" in u for u in http.calls)


def test_parse_detail_price_and_images():
    d = villalosaromos.Adapter.parse_detail((FIX / "villalosaromos_detail.html").read_text())
    assert (d["price"], d["currency"]) == (800000.0, "ARS")
    assert d["description"].startswith("CASA EN ALQUILER PERMANENTE Ubicada en El Descanso- Anisacate")
    assert len(d["images"]) == 3


def test_has_next_page():
    html = (FIX / "villalosaromos_archive.html").read_text()
    assert villalosaromos.Adapter.has_next_page(html, 2)
    assert not villalosaromos.Adapter.has_next_page(html, 3)
