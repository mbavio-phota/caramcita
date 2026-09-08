from datetime import datetime, timedelta, timezone

from caramcita.config import load_config
from caramcita.models import Listing, Verdict
from caramcita.report import render
from caramcita.state import State, SourceResult, apply_run

T0 = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)


def L(sid, title, price=800000.0, src="lavoz", **kw):
    return Listing(source=src, source_id=sid, url=f"https://x/{sid}", title=title, price=price, currency="ARS",
                   images=[f"https://img/{sid}.jpg"], agency="Inmo Test", **kw)


def test_render_smoke(tmp_path):
    cfg = load_config()
    st = State.empty()
    ok = Verdict("match", "exact", "Alta Gracia", 3)
    a, b = L("1", "Casa en El Golf"), L("2", "Casa en Anisacate")
    apply_run(st, {"lavoz": SourceResult("lavoz", [a, b])}, {a.key: ok, b.key: ok}, T0)
    c = L("3", "Casa nueva en Falda del Carmen", src="ml")
    d = L("4", "Casa sin dorm", src="ml")
    apply_run(st, {"lavoz": SourceResult("lavoz", [a]), "ml": SourceResult("ml", [c, d], None), "x": SourceResult("x", [], "boom")},
              {a.key: ok, c.key: ok, d.key: Verdict("maybe_bedrooms", "?", "Anisacate", None)}, T0 + timedelta(hours=6))
    ctx = render(st, cfg, [{"slug": "lavoz", "name": "La Voz", "url": "https://lavoz"}], tmp_path, T0 + timedelta(hours=7))
    html = (tmp_path / "index.html").read_text()
    assert "Casa nueva en Falda del Carmen" in html
    assert ctx["news_count"] == 2  # la nueva casa y la de dormitorios sin dato
    assert [c["title"] for c in ctx["gone"]] == ["Casa en Anisacate"]
    assert len(ctx["maybe_beds"]) == 1
    assert "boom" in html
    feed = (tmp_path / "feed.xml").read_text()
    assert "<item>" in feed and "Casa nueva" in feed
    assert (tmp_path / "data.json").exists()


def test_back_badge_health_and_rfc822(tmp_path):
    cfg = load_config()
    st = State.empty()
    ok = Verdict("match", "exact", "Alta Gracia", 3)
    a, b = L("1", "Casa uno"), L("2", "Casa dos")
    apply_run(st, {"lavoz": SourceResult("lavoz", [a, b])}, {a.key: ok, b.key: ok}, T0)
    apply_run(st, {"lavoz": SourceResult("lavoz", [a])}, {a.key: ok}, T0 + timedelta(hours=6))
    apply_run(st, {"lavoz": SourceResult("lavoz", [a, b])}, {a.key: ok, b.key: ok}, T0 + timedelta(hours=12))
    specs = [{"slug": "lavoz", "name": "La Voz"}, {"slug": "lequio", "name": "Lequio", "run_from": "mac"}]
    ctx = render(st, cfg, specs, tmp_path, T0 + timedelta(hours=13))
    two = next(c for c in ctx["all_cards"] if c["title"] == "Casa dos")
    assert two["is_back"] and not two["is_gone"]
    html = (tmp_path / "index.html").read_text()
    assert "Volvió" in html
    lequio = next(h for h in ctx["health"] if h["slug"] == "lequio")
    assert lequio["status"].startswith("sin datos todavía") and not lequio["broken"]
    feed = (tmp_path / "feed.xml").read_text()
    assert "+0000" in feed and "T12:00:00" not in feed
