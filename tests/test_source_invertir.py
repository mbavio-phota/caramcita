import json
from pathlib import Path

from caramcita.sources.invertir import Adapter

FIX = Path(__file__).parent / "fixtures"


class StubHttp:
    def __init__(self, rest_ok: bool = True):
        self.rest_ok = rest_ok
        self.urls: list[str] = []

    def get_text(self, url: str) -> str:
        self.urls.append(url)
        assert url == "https://inmobiliariainvertir.com/en-alquiler/"
        return (FIX / "invertir_list.html").read_text()

    def get_json(self, url: str):
        self.urls.append(url)
        if not self.rest_ok:
            raise RuntimeError("REST caído")
        if "/tipo-operacion" in url:
            return json.loads((FIX / "invertir_tipo_operacion.json").read_text())
        assert "/wp/v2/inmueble?tipo-operacion=11&" in url and "_embed=1" in url
        return json.loads((FIX / "invertir_rest.json").read_text())

    def get(self, url: str):  # pragma: no cover - no se usa
        raise AssertionError("no debería usar get()")


def test_parse_fixture_html_plus_rest():
    http = StubHttp()
    ls = Adapter(slug="invertir", name="Inmobiliaria Invertir").fetch(http)
    by_id = {l.source_id: l for l in ls}

    # 2 posts del REST (3795 con tarjeta HTML, 3582 sin) + 3787 sólo en el HTML
    assert set(by_id) == {"3795", "3582", "3787"}
    assert len(http.urls) == 3

    l = by_id["3795"]
    assert l.source == "invertir"
    assert l.agency == "Inmobiliaria Invertir"
    assert l.url == "https://inmobiliariainvertir.com/inmueble/casa-nueva-en-villa-del-prado-a-5-cuadras-de-la-autovia-ruta-5-3/"
    assert l.title.startswith("Alquiler Villa del Prado Barrio La Donosa Casa Nueva de 1 dormitorio")
    assert (l.price, l.currency) == (500000.0, "ARS")
    assert l.bedrooms == 1
    assert l.locality == "Alta Gracia"
    assert l.extra["ubicaciones"] == ["Alta Gracia", "Villa del Prado"]
    assert l.address == "Ubicada sobre calle 12 en Barrio La Donosa, a solo 5 cuadras del ingreso."
    assert l.property_type == "Casa"
    assert l.operation == "Alquiler"
    assert l.images[0] == "https://inmobiliariainvertir.com/wp-content/uploads/jet-engine-forms/7/2026/07/Captura-de-pantalla-2026-07-16-122802.png"
    assert l.extra["banios"] == 1 and l.extra["superficie"] == "55 m²"
    assert "Villa del Prado" in l.description

    # sólo REST: sin precio ni dormitorios, pero con localidad/tipo/foto destacada
    l2 = by_id["3582"]
    assert l2.title == "Alquiler Anisacate Barrio Parque La Lila Casa de 2 dormitorios"
    assert l2.locality == "Anisacate"
    assert l2.property_type == "Casa"
    assert (l2.price, l2.currency, l2.bedrooms) == (None, None, None)
    assert l2.images[0].startswith("https://inmobiliariainvertir.com/wp-content/uploads/")

    # sólo HTML
    l3 = by_id["3787"]
    assert (l3.price, l3.currency, l3.bedrooms) == (680000.0, "ARS", 2)
    assert l3.locality == "" and l3.property_type == ""


def test_rest_failure_falls_back_to_html():
    ls = Adapter(slug="invertir", name="Invertir").fetch(StubHttp(rest_ok=False))
    assert [l.source_id for l in ls] == ["3795", "3787"]
    assert ls[0].bedrooms == 1 and ls[0].price == 500000.0
    assert ls[0].images[0].endswith("Captura-de-pantalla-2026-07-16-122802.png")
