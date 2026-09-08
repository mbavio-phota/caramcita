from pathlib import Path

from caramcita.sources.mercadolibre import Adapter, listing_id, page_url, parse_html

FIX = Path(__file__).parent / "fixtures" / "mercadolibre_santa_maria.html"
SM = "https://inmuebles.mercadolibre.com.ar/casas/alquiler/cordoba/santa-maria/"
AG = "https://inmuebles.mercadolibre.com.ar/casas/alquiler/cordoba/alta-gracia/"


class StubHttp:
    def __init__(self, html):
        self.html = html
        self.urls: list[str] = []

    def get_text(self, url, **kw):
        self.urls.append(url)
        return self.html

    def get_json(self, url, **kw):  # pragma: no cover - no se usa
        raise AssertionError("mercadolibre usa get_text")

    def get(self, url, **kw):  # pragma: no cover - no se usa
        raise AssertionError("mercadolibre usa get_text")


def test_helpers():
    assert page_url(SM, 1) == SM
    assert page_url(SM, 2) == SM.rstrip("/") + "/_Desde_49"
    assert page_url(SM, 3) == SM.rstrip("/") + "/_Desde_97"
    assert listing_id("https://casa.mercadolibre.com.ar/MLA-2020426573-venta-duplex-_JM#polycard") == "MLA2020426573"
    assert listing_id("https://example.com/none") is None


def test_parse_fixture():
    src = Adapter(slug="mercadolibre", name="MercadoLibre Inmuebles", urls=[SM])
    ls, total = parse_html(FIX.read_text(encoding="utf-8"), src)
    assert total == 35
    assert [l.source_id for l in ls] == ["MLA2020426573", "MLA3700113114", "MLA3809097312"]

    a = ls[0]
    assert a.source == "mercadolibre"
    assert a.url == (
        "https://casa.mercadolibre.com.ar/MLA-2020426573-venta-duplex-a-estrenar-en-siete-soles-250-m-3-dorm-suite-cochera-doble-_JM"
    )
    assert a.title.startswith("Venta Duplex A Estrenar En Siete Soles")
    assert a.price == 1900000.0 and a.currency == "ARS"
    assert a.bedrooms == 3
    assert a.locality == "Santa María"
    assert a.address == "Siete Soles Al 0, Malagueño"
    assert a.property_type == "Casa" and a.operation == "Alquiler"
    assert a.images[0] == "https://http2.mlstatic.com/D_NQ_NP_2X_954480-MLA116509472665_082026-E.webp"
    assert a.agency == "MacBook Chip M3"
    assert a.extra["bathrooms"] == "3" and a.extra["rooms"] == "4" and a.extra["covered_m2"] == "170"

    b = ls[1]
    assert b.source_id == "MLA3700113114"
    assert b.price == 800.0 and b.currency == "USD"
    assert b.bedrooms == 4 and b.address == "Astor Piazzolla, Anisacate"
    assert b.agency == "TERRANORTE.SERV.INMOBILIARIOS"

    c = ls[2]
    assert c.title == "Alquiler - Casa Villa La Bolsa"
    assert c.price == 1600000.0 and c.currency == "ARS"
    assert c.bedrooms == 4 and c.address == "Los Tilos 118, Villa La Bolsa" and c.locality == "Santa María"
    assert c.images[0].endswith("982196-MLA116372073295_082026-E.webp")


def test_fetch_dedupes_across_urls_and_stops_by_total():
    http = StubHttp(FIX.read_text(encoding="utf-8"))
    src = Adapter(slug="mercadolibre", name="MercadoLibre Inmuebles", urls=[SM, AG])
    ls = src.fetch(http)
    # total=35 < 48 → una página por URL; los mismos 3 avisos bajo ambas URLs se cuentan una vez
    assert http.urls == [SM, AG]
    assert len(ls) == 3
    assert len({l.source_id for l in ls}) == 3
