from datetime import datetime, timezone

from caramcita.dedupe import cluster, similar_title, hamming
from caramcita.models import Listing, Verdict
from caramcita.state import Entry

T = datetime(2026, 9, 8, tzinfo=timezone.utc)


def E(src, sid, title, price=100000.0, cur="ARS", loc="Alta Gracia", beds=3, img_hash=None, first=T):
    l = Listing(source=src, source_id=sid, url=f"https://{src}/{sid}", title=title, price=price, currency=cur,
                extra={"img_hash": img_hash} if img_hash else {})
    return Entry(listing=l, verdict=Verdict("match", "ok", loc, beds), first_seen=first, last_seen=T)


def test_similar_title():
    assert similar_title("Casa 3 dormitorios en El Golf con pileta", "CASA 3 DORMITORIOS EN EL GOLF CON PILETA!!")
    assert not similar_title("Casa 3 dormitorios en El Golf", "Casa en Anisacate con arroyo")


def test_hamming():
    assert hamming("ff00", "ff01") == 1


def test_merges_same_title_and_price():
    a = E("lavoz", "1", "Casa 3 dorm en El Golf", 100000)
    b = E("ml", "9", "Casa 3 dorm en el golf", 102000)
    cards = cluster([a, b])
    assert len(cards) == 1 and {e.key for e in cards[0].entries} == {"lavoz:1", "ml:9"}


def test_merges_same_image_hash_different_title():
    a = E("lavoz", "1", "Hermosa casa en barrio residencial", 100000, img_hash="ff00ff00ff00ff00")
    b = E("ml", "9", "Alquiler anual casa El Golf", 100000, img_hash="ff00ff00ff00ff01")
    assert len(cluster([a, b])) == 1


def test_no_merge_price_far():
    a = E("lavoz", "1", "Casa 3 dorm en El Golf", 100000)
    b = E("ml", "9", "Casa 3 dorm en El Golf", 110000)
    assert len(cluster([a, b])) == 2


def test_no_merge_different_locality():
    a = E("lavoz", "1", "Casa 3 dorm con pileta", 100000, loc="Alta Gracia")
    b = E("ml", "9", "Casa 3 dorm con pileta", 100000, loc="Anisacate")
    assert len(cluster([a, b])) == 2


def test_no_merge_same_source():
    a = E("lavoz", "1", "Casa 3 dorm con pileta", 100000)
    b = E("lavoz", "2", "Casa 3 dorm con pileta", 100000)
    assert len(cluster([a, b])) == 2


def test_no_merge_different_currency():
    a = E("lavoz", "1", "Casa 3 dorm con pileta", 1000, cur="USD")
    b = E("ml", "9", "Casa 3 dorm con pileta", 1000, cur="ARS")
    assert len(cluster([a, b])) == 2


def test_primary_is_earliest():
    from datetime import timedelta
    a = E("lavoz", "1", "Casa 3 dorm en El Golf", 100000, first=T + timedelta(days=1))
    b = E("ml", "9", "Casa 3 dorm en El Golf", 100000, first=T)
    c = cluster([a, b])[0]
    assert c.primary.key == "ml:9"


def test_price_none_both_merge_on_title():
    a = E("lavoz", "1", "Casa 3 dorm en El Golf", None)
    b = E("ml", "9", "Casa 3 dorm en El Golf", None)
    assert len(cluster([a, b])) == 1
