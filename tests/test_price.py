import pytest
from caramcita.sources.base import parse_price


@pytest.mark.parametrize("txt,exp", [
    ("$ 850.000", (850000.0, "ARS")),
    ("$850.000,00", (850000.0, "ARS")),
    ("USD 1.200", (1200.0, "USD")),
    ("U$S 900", (900.0, "USD")),
    ("1200 USD", (1200.0, "USD")),
    ("Consultar", (None, None)),
    ("", (None, None)),
    ("ARS 1.100.000", (1100000.0, "ARS")),
    ("950000", (950000.0, "ARS")),
    ("Precio: $ 1,200,000 por mes", (1200000.0, "ARS")),
])
def test_parse_price(txt, exp):
    assert parse_price(txt) == exp
