from datetime import datetime, timedelta, timezone

from caramcita.models import Listing, Verdict
from caramcita.state import State, SourceResult, apply_run

T0 = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)


def L(sid="1", price=500000.0, src="a", **kw):
    return Listing(source=src, source_id=sid, url=f"https://x/{sid}", title=f"Casa {sid}", price=price, currency="ARS", **kw)


def V(status="match"):
    return Verdict(status, "ok", "Alta Gracia", 3)


def run(state, listings, at=T0, errors=None, rejected=()):
    results = {}
    for l in listings:
        results.setdefault(l.source, SourceResult(source=l.source, listings=[], error=None)).listings.append(l)
    for src in (errors or {}):
        results[src] = SourceResult(source=src, listings=[], error=errors[src])
    verdicts = {l.key: (Verdict("rejected", "x") if l.key in rejected else V()) for l in listings}
    return apply_run(state, results, verdicts, at, retention_days=7)


def test_first_run_is_baseline():
    st = State.empty()
    ch = run(st, [L("1"), L("2")])
    assert ch.baseline is True
    assert ch.new == [] and len(st.listings) == 2
    assert st.baseline_done


def test_new_listing_detected_after_baseline():
    st = State.empty()
    run(st, [L("1")])
    ch = run(st, [L("1"), L("2")], at=T0 + timedelta(hours=6))
    assert [e.key for e in ch.new] == ["a:2"]
    assert st.listings["a:2"].first_seen == T0 + timedelta(hours=6)


def test_price_change_recorded_not_new():
    st = State.empty()
    run(st, [L("1", price=100.0)])
    ch = run(st, [L("1", price=120.0)], at=T0 + timedelta(hours=6))
    assert ch.new == []
    assert [(e.key, old, new) for e, old, new in ch.price_changed] == [("a:1", 100.0, 120.0)]
    assert len(st.listings["a:1"].price_history) == 2
    assert st.listings["a:1"].price_changed_at == T0 + timedelta(hours=6)


def test_gone_then_dropped_after_retention():
    st = State.empty()
    run(st, [L("1"), L("2")])
    ch = run(st, [L("1")], at=T0 + timedelta(days=1))
    assert [e.key for e in ch.gone] == ["a:2"]
    assert st.listings["a:2"].gone_since == T0 + timedelta(days=1)
    run(st, [L("1")], at=T0 + timedelta(days=5))
    assert "a:2" in st.listings
    run(st, [L("1")], at=T0 + timedelta(days=9))
    assert "a:2" not in st.listings


def test_gone_listing_that_returns_is_back():
    st = State.empty()
    run(st, [L("1"), L("2")])
    run(st, [L("1")], at=T0 + timedelta(days=1))
    ch = run(st, [L("1"), L("2")], at=T0 + timedelta(days=2))
    assert [e.key for e in ch.back] == ["a:2"] and ch.new == []
    assert st.listings["a:2"].gone_since is None


def test_source_error_does_not_mark_gone():
    st = State.empty()
    run(st, [L("1", src="a"), L("1", src="b")])
    ch = run(st, [L("1", src="a")], at=T0 + timedelta(hours=6), errors={"b": "timeout"})
    assert ch.gone == []
    assert st.sources["b"].error == "timeout"
    assert st.sources["b"].last_ok == T0


def test_rejected_not_stored():
    st = State.empty()
    run(st, [L("1"), L("2")], rejected={"a:2"})
    assert set(st.listings) == {"a:1"}


def test_previously_shown_now_rejected_is_removed():
    st = State.empty()
    run(st, [L("1"), L("2")])
    ch = run(st, [L("1"), L("2")], at=T0 + timedelta(hours=6), rejected={"a:2"})
    assert "a:2" not in st.listings and ch.gone == []


def test_zero_streak_counts_consecutive_empty_ok_runs():
    st = State.empty()
    run(st, [L("1", src="a")])
    run(st, [], at=T0 + timedelta(hours=6), errors={})
    # fuente "a" ni corrió ni falló → sin cambios
    assert st.sources["a"].zero_streak == 0
    results = {"a": SourceResult("a", [], None)}
    apply_run(st, results, {}, T0 + timedelta(hours=12), retention_days=7)
    apply_run(st, results, {}, T0 + timedelta(hours=18), retention_days=7)
    assert st.sources["a"].zero_streak == 2


def test_roundtrip_json(tmp_path):
    st = State.empty()
    run(st, [L("1", price=100.0)])
    run(st, [L("1", price=110.0)], at=T0 + timedelta(hours=6))
    p = tmp_path / "state.json"
    st.save(p)
    st2 = State.load(p)
    assert st2.listings["a:1"].price_history[-1].price == 110.0
    assert st2.baseline_done and st2.listings["a:1"].first_seen == T0


def test_baseline_at_persisted(tmp_path):
    st = State.empty()
    run(st, [L("1")])
    p = tmp_path / "s.json"
    st.save(p)
    assert State.load(p).baseline_at == T0


def test_new_source_first_result_is_not_new():
    st = State.empty()
    run(st, [L("1", src="a")])
    ch = run(st, [L("1", src="a"), L("1", src="b"), L("2", src="b")], at=T0 + timedelta(hours=6))
    assert ch.new == []  # fuente b recién agregada: base
    ch = run(st, [L("1", src="a"), L("1", src="b"), L("3", src="b")], at=T0 + timedelta(hours=12))
    assert [e.key for e in ch.new] == ["b:3"]


def test_img_hash_survives_refresh():
    st = State.empty()
    run(st, [L("1")])
    st.listings["a:1"].listing.extra["img_hash"] = "abcd"
    run(st, [L("1")], at=T0 + timedelta(hours=6))
    assert st.listings["a:1"].listing.extra["img_hash"] == "abcd"


def test_error_streak_and_back_at():
    st = State.empty()
    run(st, [L("1"), L("2")])
    run(st, [L("1")], at=T0 + timedelta(hours=6), errors={"b": "x"})
    run(st, [L("1"), L("2")], at=T0 + timedelta(hours=12), errors={"b": "x"})
    assert st.sources["b"].error_streak == 2
    assert st.listings["a:2"].back_at == T0 + timedelta(hours=12)
    run(st, [L("1"), L("2"), L("1", src="b")], at=T0 + timedelta(hours=18))
    assert st.sources["b"].error_streak == 0
