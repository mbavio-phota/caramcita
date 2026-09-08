from pathlib import Path

from caramcita.sources.lequio import Adapter

FIX = Path(__file__).parent / "fixtures"


class StubHttp:
    def __init__(self):
        self.urls: list[str] = []

    def get_text(self, url: str) -> str:
        self.urls.append(url)
        if url.endswith("&page=1"):
            return (FIX / "lequio_list.html").read_text()
        return (FIX / "lequio_empty.html").read_text()

    def get_json(self, url: str):  # pragma: no cover - no se usa
        raise AssertionError("no debería pedir JSON")

    def get(self, url: str):  # pragma: no cover - no se usa
        raise AssertionError("no debería usar get()")


def test_parse_fixture_skips_rented():
    http = StubHttp()
    ls = Adapter(slug="lequio", name="Lequio Propiedades").fetch(http)

    # la tarjeta 141280 está marcada "Alquilado" → se omite por defecto
    assert [l.source_id for l in ls] == ["168572"]
    assert http.urls == [
        "https://lequiopropiedades.com.ar/listing?user_id=69&purpose=rent&page=1",
        "https://lequiopropiedades.com.ar/listing?user_id=69&purpose=rent&page=2",
    ]

    l = ls[0]
    assert l.source == "lequio"
    assert l.agency == "Lequio Propiedades"
    assert l.url == "https://lequiopropiedades.com.ar/ad/alquiler-propiedad-anisacate-cordoba"
    assert l.title == "ALQUILER PROPIEDAD ANISACATE, CORDOBA"
    assert (l.price, l.currency) == (600000.0, "ARS")
    assert l.bedrooms == 3
    assert l.locality == "Anisacate"
    assert l.address == "Anisacate, Córdoba, Argentina"
    assert l.property_type == "Casa"
    assert l.operation == "En Alquiler"
    assert l.images[0] == (
        "https://lequiopropiedades.com.ar/uploads/lequiopropiedades/images/thumbs/"
        "1749250227qwlmn-whatsapp-image-2025-06-06-at-165355.jpeg"
    )
    assert l.extra == {
        "slug": "alquiler-propiedad-anisacate-cordoba",
        "codigo": "168572",
        "estado": "Alquilo",
        "m2": "1",
        "banios": 1,
    }


def test_keep_rented_when_asked():
    ls = Adapter(slug="lequio", name="Lequio", skip_rented=False).fetch(StubHttp())
    assert [l.source_id for l in ls] == ["168572", "141280"]
    rented = ls[1]
    assert rented.extra["estado"] == "Alquilado"
    assert rented.title == "Alquiler propiedad en Alta Gracia, Cordoba"
    assert (rented.price, rented.currency, rented.bedrooms) == (350000.0, "ARS", 2)
    assert rented.locality == "Alta Gracia"
