from pathlib import Path

from caramcita.sources.consulting import Adapter

FIX = Path(__file__).parent / "fixtures"


class StubHttp:
    def __init__(self):
        self.urls: list[str] = []

    def get_text(self, url: str) -> str:
        self.urls.append(url)
        # sólo Alta Gracia página 0 tiene avisos; el resto viene vacío
        if "localidad=1&" in url and "paginador_pagina=0" in url:
            return (FIX / "consulting_list.html").read_text()
        return (FIX / "consulting_empty.html").read_text()

    def get_json(self, url: str):  # pragma: no cover - no se usa
        raise AssertionError("no debería pedir JSON")

    def get(self, url: str):  # pragma: no cover - no se usa
        raise AssertionError("no debería usar get()")


def test_parse_fixture():
    http = StubHttp()
    src = Adapter(slug="consulting", name="Consulting Inmobiliaria")
    ls = src.fetch(http)

    assert len(ls) == 2
    assert [l.source_id for l in ls] == ["99", "97"]

    l = ls[0]
    assert l.source == "consulting"
    assert l.agency == "Consulting Inmobiliaria"
    assert l.url == "https://consultinginmobiliaria.com/detalle.php?id=99"
    assert l.title == "Venta en Alta Gracia - Lote 96 Manzana 356"
    assert l.operation == "Venta"
    assert l.locality == "Alta Gracia"  # la localidad pedida en la URL
    assert l.extra["localidad_titulo"] == "Alta Gracia"
    assert l.address == "Lote 96 Manzana 356"
    assert (l.price, l.currency) == (25000.0, "USD")
    assert l.bedrooms is None  # '0' dormitorios → None
    assert l.property_type == "Casa"
    assert l.images[0] == "https://consultinginmobiliaria.com/images/inmuebles/5250993147445513.jpeg"
    assert len(l.images) == 3
    assert (l.lat, l.lng) == (-31.637662527051976, -64.42425191403326)
    assert l.extra["imagenes"] == "3 Imágenes"

    l2 = ls[1]
    assert l2.title.startswith("Venta en Alta Gracia - Prudencio Bustos 627")
    assert (l2.price, l2.currency) == (150000.0, "USD")


def test_iterates_localities_without_operacion_filter():
    http = StubHttp()
    Adapter(slug="consulting", name="Consulting").fetch(http)
    # página 0 de cada localidad; con menos de 6 avisos no pide la siguiente
    assert http.urls == [
        "https://consultinginmobiliaria.com/inmuebles.php?propiedad=2&localidad=1&paginador_pagina=0",
        "https://consultinginmobiliaria.com/inmuebles.php?propiedad=2&localidad=2&paginador_pagina=0",
        "https://consultinginmobiliaria.com/inmuebles.php?propiedad=2&localidad=11&paginador_pagina=0",
    ]
    assert all("operacion=" not in u for u in http.urls)
