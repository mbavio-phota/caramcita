from pathlib import Path

from caramcita.sources.wasi import Adapter

FIX = Path(__file__).parent / "fixtures" / "wasi_zaratemedinadiaz_alquileres.html"


class StubHttp:
    def __init__(self):
        self.urls = []

    def get_text(self, url):
        self.urls.append(url)
        return FIX.read_text(encoding="utf-8")

    def get_json(self, url):
        raise AssertionError("no se usa")

    def get(self, url):
        raise AssertionError("no se usa")


def test_wasi_parses_cards_and_stops_without_next_page():
    http = StubHttp()
    src = Adapter(slug="zaratemedinadiaz", name="Zarate & Medina Díaz", base="https://zarate-medinadiaz.com.ar", property_type=None)
    listings = src.fetch(http)

    assert len(http.urls) == 1  # la paginación del fixture sólo tiene página 1
    assert http.urls[0].startswith("https://zarate-medinadiaz.com.ar/search?business_type%5B0%5D=for_rent&")
    assert "for_rent=1" in http.urls[0] and "for_sale=0" in http.urls[0] and "page=1" in http.urls[0]
    assert "id_property_type" not in http.urls[0]
    assert len(listings) == 2

    casa = listings[0]
    assert casa.source == "zaratemedinadiaz"
    assert casa.source_id == "10283226"
    assert casa.url == "https://zarate-medinadiaz.com.ar/casa-alquiler-despenaderos/10283226"
    assert casa.title
    assert casa.property_type == "Casa"
    assert casa.operation == "Alquiler"
    assert casa.currency == "ARS" and casa.price and casa.price > 100000
    assert casa.bedrooms == 2
    assert casa.locality == "Despenaderos"  # .ubicacion sólo dice "Argentina"; sale del slug de la URL
    assert casa.images[0].startswith("https://image.wasi.co/")
    assert casa.extra["url_city"] == "Despenaderos"

    local = listings[1]
    assert local.property_type == "Local"
    assert local.bedrooms is None  # "0 Dormitorios" = sin dato


def test_wasi_page_url_with_property_type():
    url = Adapter.page_url("https://x.com", "for_rent", 1, 2)
    assert url.startswith("https://x.com/search?business_type%5B0%5D=for_rent&id_property_type=1&")
    assert url.endswith("&page=2")
