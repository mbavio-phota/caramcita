from pathlib import Path

from caramcita.sources.zonaprop import Adapter, parse_html

FIX = Path(__file__).parent / "fixtures" / "zonaprop_list.html"


def test_parse_cards():
    src = Adapter(slug="zonaprop", name="Zonaprop", urls=[])
    ls = parse_html(FIX.read_text(), src)
    assert len(ls) == 2
    a = ls[0]
    assert a.source_id == "59219512"
    assert a.url.startswith("https://www.zonaprop.com.ar/propiedades/clasificado/")
    assert a.price == 650000.0 and a.currency == "ARS"
    assert a.locality == "Alta Gracia"
    assert a.bedrooms == 1
    assert a.images[0].startswith("https://imgar.zonapropcdn.com/")
    assert a.property_type == "Casa"
    b = ls[1]
    assert b.source_id == "60008685" and b.bedrooms == 2 and b.locality == "Alta Gracia"
