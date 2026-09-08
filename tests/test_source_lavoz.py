import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from caramcita.sources.lavoz import Adapter, build_filters, page_url

FIX = Path(__file__).parent / "fixtures" / "lavoz_search.json"


class StubHttp:
    def __init__(self, payload):
        self.payload = payload
        self.urls: list[str] = []

    def get_json(self, url, **kw):
        self.urls.append(url)
        return self.payload

    def get_text(self, url, **kw):  # pragma: no cover - no se usa
        raise AssertionError("lavoz usa get_json")

    def get(self, url, **kw):  # pragma: no cover - no se usa
        raise AssertionError("lavoz usa get_json")


def test_filters_and_url():
    f = build_filters([3202, 3206])
    assert f == "tid:6330 tid:6331 ss_operacion:Alquileres tid_location_should:3202 tid_location_should:3206"
    u = page_url(f, 2)
    q = parse_qs(urlparse(u).query)
    assert q["page"] == ["2"]
    assert q["filters"] == [f]
    assert u.startswith("https://clasificados.lavoz.com.ar/api/search?")


def test_parse_fixture():
    http = StubHttp(json.loads(FIX.read_text(encoding="utf-8")))
    src = Adapter(slug="lavoz", name="Clasificados La Voz", location_tids=[3202, 3206, 3299])
    ls = src.fetch(http)
    assert len(http.urls) == 1  # last_page == 1 → una sola página
    assert "tid_location_should:3299" in http.urls[0]
    assert len(ls) == 3

    a = ls[0]
    assert a.source == "lavoz" and a.source_id == "5636915"
    assert a.url == "https://clasificados.lavoz.com.ar/avisos/inmuebles/casa/5636915/se-alquila-casa-potrerillo-de-larreta-alta-gracia-064grupofuturosi"
    assert a.title.startswith("SE ALQUILA CASA POTRERILLO DE LARRETA ALTA GRACIA")
    assert a.price == 1600.0 and a.currency == "USD"
    assert a.bedrooms == 3
    assert a.locality == "Alta Gracia"
    assert a.address == "Potrerillo de Larreta"
    assert a.property_type == "Casas" and a.operation == "Alquileres"
    assert a.images[0] == (
        "https://cdncla.lavoz.com.ar/avisos/aviso_casa/5636915/"
        "inmuebles-casa-alquileres-5636915-9e8a4352-e284-48a8-9311-f78eacb770f0.webp"
    )
    assert a.agency == "Grupo Futuro"
    assert a.lat is not None and abs(a.lat + 31.648) < 0.01 and a.lng is not None and abs(a.lng + 64.478) < 0.01
    assert a.extra["bathrooms"] == "2 Baños"
    assert "[[inline-break]]" not in a.description and "<" not in a.description

    b = ls[1]
    assert b.source_id == "5644305"
    assert b.price == 690000.0 and b.currency == "ARS"
    assert b.bedrooms == 2 and b.locality == "Anisacate" and b.address == ""
    assert b.lat is None and b.lng is None
    assert b.description.startswith("Casa en alquiler ubicada en la tranquila localidad de Dique Chico.")
    assert "\n" in b.description  # [[inline-break]] → salto de línea

    c = ls[2]
    assert c.source_id == "5137750" and c.locality == "Alta Gracia" and c.bedrooms == 2
    assert c.agency == "Eduardo Rando Negocios Inmobiliarios"
