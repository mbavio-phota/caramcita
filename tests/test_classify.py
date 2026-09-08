import pytest

from caramcita.classify import (
    Classifier,
    match_locality,
    parse_bedrooms,
    classify_property_type,
    is_temporary,
    normalize,
)
from caramcita.config import load_config
from caramcita.models import Listing


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def clf(cfg):
    return Classifier(cfg)


def test_normalize_strips_accents_and_case():
    assert normalize("Despeñaderos Córdoba") == "despenaderos cordoba"


class TestLocality:
    def test_structured_locality_exact(self, clf):
        assert match_locality(clf, locality="Alta Gracia", texts=[]) == ("Alta Gracia", "exact")

    def test_alias_in_text(self, clf):
        assert match_locality(clf, locality="", texts=["Casa en Valle Anisacate"]) == ("Valle de Anisacate", "text")

    def test_la_bolsa_alias(self, clf):
        assert match_locality(clf, locality="", texts=["Hermosa casa en La Bolsa, 3 dorm"]) == ("Villa La Bolsa", "text")

    def test_barrio_maps_to_alta_gracia(self, clf):
        assert match_locality(clf, locality="", texts=["Casa en Villa Camino Real"]) == ("Alta Gracia", "barrio")

    def test_excluded_locality_wins(self, clf):
        assert match_locality(clf, locality="Potrero de Garay", texts=["a 20 min de Alta Gracia"]) == (None, "excluded")

    def test_unknown(self, clf):
        assert match_locality(clf, locality="", texts=["Casa quinta con pileta"]) == (None, "unknown")

    def test_valle_de_anisacate_not_swallowed_by_anisacate(self, clf):
        assert match_locality(clf, locality="Valle de Anisacate", texts=[])[0] == "Valle de Anisacate"

    def test_cordoba_alone_is_not_alta_gracia(self, clf):
        # "Córdoba" solo no es barrio Córdoba de Alta Gracia
        assert match_locality(clf, locality="Córdoba", texts=["Casa en Córdoba"]) == (None, "unknown")

    def test_barrio_beats_neighbour_locality_from_source(self, clf):
        # MercadoLibre archiva Tierra Alta bajo Malagueño
        assert match_locality(clf, locality="Santa María", texts=["Tierra Alta al 2100, Malagueño"]) == ("Alta Gracia", "barrio")

    def test_excluded_without_barrio_still_excluded(self, clf):
        assert match_locality(clf, locality="Malagueño", texts=["Casa en Malagueño centro"]) == (None, "excluded")

    def test_barrio_cordoba_with_alta_gracia_context(self, clf):
        assert match_locality(clf, locality="", texts=["Casa en Barrio Córdoba, Alta Gracia"]) == ("Alta Gracia", "text")


class TestBedrooms:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Casa 3 dormitorios", 3),
            ("casa de tres dormitorios y dos baños", 3),
            ("3 dorm. 2 baños", 3),
            ("4 hab", 4),
            ("Casa 2 dormitorios + escritorio", 2),
            ("Casa con 3 ambientes", None),  # ambientes no son dormitorios
            ("hermosa casa con pileta", None),
            ("3 DORMITORIOS", 3),
            ("dos dormitorios en planta alta y uno en planta baja", 2),
            ("casa de 5 dormitorios", 5),
            ("1 dormitorio", 1),
        ],
    )
    def test_from_text(self, text, expected):
        assert parse_bedrooms(None, text) == expected

    def test_structured_wins(self):
        assert parse_bedrooms(4, "2 dormitorios") == 4

    def test_structured_zero_ignored(self):
        assert parse_bedrooms(0, "3 dormitorios") == 3


class TestPropertyType:
    @pytest.mark.parametrize(
        "ptype,text,expected",
        [
            ("Casa", "", "casa"),
            ("Departamento", "", "excluded"),
            ("", "Duplex en Alta Gracia", "casa"),
            ("", "PH de 3 dormitorios", "casa"),
            ("", "Chalet en El Golf", "casa"),
            ("Local comercial", "", "excluded"),
            ("Terreno", "", "excluded"),
            ("Lote", "", "excluded"),
            ("", "Casa en venta", "casa"),
            ("", "Monoambiente luminoso", "excluded"),
            ("", "Galpón", "excluded"),
            ("", "Quinta con casa principal", "casa"),
            ("", "Cabaña en Anisacate", "casa"),
            ("", "Sin datos", "unknown"),
        ],
    )
    def test_types(self, ptype, text, expected):
        assert classify_property_type(ptype, text) == expected


class TestTemporary:
    @pytest.mark.parametrize(
        "op,text,expected",
        [
            ("Alquiler", "cocina con comedor diario", False),
            ("Alquiler", "", False),
            ("Alquileres Temporarios", "", True),
            ("Alquiler", "alquiler temporario por temporada", True),
            ("Alquiler", "alquiler anual, no temporario", False),
            ("", "se alquila por día", True),
            ("", "alquiler turístico", True),
            ("", "Alquiler permanente", False),
            ("Venta", "", True),  # venta no es alquiler → se excluye
        ],
    )
    def test_temp(self, op, text, expected):
        assert is_temporary(op, text) == expected


def mk(**kw):
    base = dict(source="t", source_id="1", url="u", title="Casa", description="")
    base.update(kw)
    return Listing(**base)


class TestEvaluate:
    def test_match(self, clf):
        v = clf.evaluate(mk(title="Casa 3 dormitorios en Alta Gracia", locality="Alta Gracia", property_type="Casa", operation="Alquiler", bedrooms=3))
        assert v.status == "match" and v.locality == "Alta Gracia" and v.bedrooms == 3

    def test_rejected_two_bedrooms(self, clf):
        v = clf.evaluate(mk(title="Casa 2 dormitorios", locality="Alta Gracia", property_type="Casa", operation="Alquiler", bedrooms=2))
        assert v.status == "rejected"

    def test_rejected_apartment(self, clf):
        v = clf.evaluate(mk(title="Depto 3 dormitorios", locality="Alta Gracia", property_type="Departamento", operation="Alquiler", bedrooms=3))
        assert v.status == "rejected"

    def test_rejected_temporary(self, clf):
        v = clf.evaluate(mk(title="Casa 3 dorm temporario", locality="Alta Gracia", property_type="Casa", operation="Alquiler temporario", bedrooms=3))
        assert v.status == "rejected"

    def test_rejected_excluded_locality(self, clf):
        v = clf.evaluate(mk(title="Casa 3 dorm", locality="Potrero de Garay", property_type="Casa", operation="Alquiler", bedrooms=3))
        assert v.status == "rejected"

    def test_maybe_bedrooms(self, clf):
        v = clf.evaluate(mk(title="Casa amplia en Anisacate", locality="Anisacate", property_type="Casa", operation="Alquiler"))
        assert v.status == "maybe_bedrooms" and v.locality == "Anisacate"

    def test_maybe_location(self, clf):
        v = clf.evaluate(mk(title="Casa 3 dormitorios con pileta", locality="", property_type="Casa", operation="Alquiler", bedrooms=3))
        assert v.status == "maybe_location" and v.bedrooms == 3

    def test_maybe_location_and_bedrooms_is_location(self, clf):
        v = clf.evaluate(mk(title="Casa con pileta", locality="", property_type="Casa", operation="Alquiler"))
        assert v.status == "maybe_location"

    def test_title_departamento_beats_source_type(self, clf):
        v = clf.evaluate(mk(title="Departamento en alquiler en V. Camiares", locality="Alta Gracia", property_type="Casas", operation="Alquileres", bedrooms=3))
        assert v.status == "rejected"

    def test_unknown_type_with_house_text(self, clf):
        v = clf.evaluate(mk(title="Alquilo casa 3 dorm Falda del Carmen", locality="", property_type="", operation=""))
        assert v.status == "match" and v.locality == "Falda del Carmen"

    def test_unknown_type_unknown_text_is_shown(self, clf):
        # Sin tipo ni pista → se muestra pero no se descarta
        v = clf.evaluate(mk(title="Propiedad 3 dormitorios", locality="Alta Gracia", property_type="", operation="Alquiler", bedrooms=3))
        assert v.status == "match"
