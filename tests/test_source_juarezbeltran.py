from pathlib import Path

from caramcita.sources.juarezbeltran import Adapter

FIX = Path(__file__).parent / "fixtures" / "juarezbeltran_alquiler_p1.html"


class StubHttp:
    def __init__(self):
        self.urls = []

    def get_text(self, url):
        self.urls.append(url)
        # la página 1 tiene 2 cards; cualquier otra devuelve un listado vacío
        return FIX.read_text(encoding="utf-8") if "page=" not in url else "<div>No se encontraron resultados</div>"

    def get_json(self, url):
        raise AssertionError("no se usa")

    def get(self, url):
        raise AssertionError("no se usa")


def test_juarezbeltran_parses_cards():
    http = StubHttp()
    src = Adapter(slug="juarezbeltran", name="Juárez Beltrán")
    listings = src.fetch(http)

    assert http.urls[0] == "https://juarezbeltran.com.ar/propiedades?operation%5B%5D=2"
    assert http.urls[1] == "https://juarezbeltran.com.ar/propiedades?operation%5B%5D=2&page=2"
    assert len(listings) == 2

    casa = listings[0]
    assert casa.source == "juarezbeltran"
    assert casa.source_id == "4702759"
    assert casa.url == "https://juarezbeltran.com.ar/propiedad/alquiler-casa-premiun-de-3-dormitorios--4702759"
    assert casa.title
    assert casa.property_type == "Casa"
    assert casa.operation == "Alquiler"
    assert (casa.price, casa.currency) == (2000.0, "USD")
    assert casa.bedrooms == 3
    assert casa.locality == "Villa Allende"
    assert casa.address
    assert casa.images[0].startswith("https://d1v2p1s05qqabi.cloudfront.net/")
    assert casa.lat is not None and casa.lng is not None
    assert casa.extra["bathrooms"] == 2

    other = listings[1]
    assert other.source_id != casa.source_id
    assert other.operation == "Alquiler"
    assert other.price and other.currency in ("ARS", "USD")


def test_juarezbeltran_page_url_with_types_and_summary():
    url = Adapter.page_url("https://juarezbeltran.com.ar", [2], [1], "Alta Gracia", 2)
    assert url == "https://juarezbeltran.com.ar/propiedades?operation%5B%5D=2&type%5B%5D=1&summary=Alta+Gracia&page=2"
