from pathlib import Path

from caramcita.sources.guillermocortes import Adapter

FIX = Path(__file__).parent / "fixtures"


class StubHttp:
    def __init__(self):
        self.urls: list[str] = []

    def get_text(self, url: str) -> str:
        self.urls.append(url)
        if url.endswith("/alquileres"):
            return (FIX / "guillermocortes_list.html").read_text()
        return (FIX / "guillermocortes_empty.html").read_text()

    def get_json(self, url: str):  # pragma: no cover - no se usa
        raise AssertionError("no debería pedir JSON")

    def get(self, url: str):  # pragma: no cover - no se usa
        raise AssertionError("no debería usar get()")


def test_parse_fixture():
    http = StubHttp()
    ls = Adapter(slug="guillermocortes", name="Guillermo Cortes").fetch(http)

    assert [l.source_id for l in ls] == ["1833", "1806"]
    # página 1 con tarjetas, página 2 vacía → corta
    assert http.urls == [
        "https://guillermocortes.com.ar/alquileres",
        "https://guillermocortes.com.ar/alquileres/pagina2",
    ]

    l = ls[0]
    assert l.source == "guillermocortes"
    assert l.agency == "Guillermo Cortes"
    assert l.url == "https://guillermocortes.com.ar/inmueble-1833"
    assert l.title == "Departamento - INTENDENTE LLORENS Nº 542 (Bº"
    assert l.address == "INTENDENTE LLORENS Nº 542 (Bº"
    assert (l.price, l.currency) == (750000.0, "ARS")
    assert l.bedrooms == 2
    assert l.locality == "Alta Gracia"
    assert l.property_type == "Departamento"
    assert l.operation == "Alquiler"
    assert l.images[0] == "https://guillermocortes.com.ar/images/inmuebles/382681964683-1.jpeg"
    assert "Localidad: Alta Gracia" in l.description
    assert l.extra == {"complejo": "Departamento"}

    l2 = ls[1]
    assert l2.title == "Departamento - OLMOS 144 - ED. CASINO (Nº NORTE)"
    assert l2.bedrooms == 3
    assert (l2.price, l2.currency) == (750000.0, "ARS")
    assert l2.images[0] == "https://guillermocortes.com.ar/images/inmuebles/222652469129-1.jpeg"
