from pathlib import Path

from caramcita.sources.tokko_html import NO_MORE, Adapter

FIX = Path(__file__).parent / "fixtures" / "tokko_ruartemoyano_alquiler.html"


class StubHttp:
    def __init__(self):
        self.urls = []

    def get_text(self, url):
        self.urls.append(url)
        return FIX.read_text(encoding="utf-8") if "&p=" not in url else NO_MORE

    def get_json(self, url):
        raise AssertionError("no se usa")

    def get(self, url):
        raise AssertionError("no se usa")


def test_tokko_parses_cards_and_stops_on_no_more():
    http = StubHttp()
    src = Adapter(slug="ruartemoyano", name="Ruarte Moyano", base="https://www.ruartemoyano.com.ar", ptypes="")
    listings = src.fetch(http)

    assert http.urls == [
        "https://www.ruartemoyano.com.ar/Buscar?operation=2&ptypes=",
        "https://www.ruartemoyano.com.ar/Buscar?operation=2&ptypes=&p=2",
    ]
    assert len(listings) == 2
    d = listings[0]
    assert d.source == "ruartemoyano" and d.agency == "Ruarte Moyano"
    assert d.source_id == "8649588"
    assert d.url == "https://www.ruartemoyano.com.ar/p/8649588-Departamento-en-Alquiler-en-Camara-Alquiler-|-1-dormitorio-|-Betania-XI"
    assert d.title == "Departamento en Alquiler en Camara, Alta Gracia"
    assert d.description == "Alquiler | 1 dormitorio | Betania XI"
    assert (d.price, d.currency) == (580000.0, "ARS")
    assert d.bedrooms is None  # Tokko muestra ambientes, no dormitorios
    assert d.locality == "Alta Gracia"
    assert d.address == "Camara"
    assert d.property_type == "Departamento"
    assert d.operation == "Alquiler"
    assert d.images[0].startswith("https://static.tokkobroker.com/pictures/8649588_")
    assert d.extra["codref"] == "IAP8649588"
    assert d.extra["ambientes"] == 3

    g = listings[1]
    assert g.property_type == "Galpón"
    assert g.locality == "Alta Gracia" and g.address == "Caferatta"
    assert g.extra["surface"].endswith("m²")


def test_tokko_default_params_filter_casas_en_alquiler():
    assert Adapter.page_url("https://x.com", 2, "3", 1) == "https://x.com/Buscar?operation=2&ptypes=3"
    assert Adapter.page_url("https://x.com", 2, "3", 3) == "https://x.com/Buscar?operation=2&ptypes=3&p=3"
