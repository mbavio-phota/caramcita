"""Genera el diario HTML, el feed RSS y data.json en docs/."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta
from email.utils import format_datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .dedupe import Card, cluster
from .state import Entry, SourceHealth, State

TEMPLATES = Path(__file__).parent / "templates"
NEW_DAYS = 7


def fmt_price(price: float | None, cur: str | None) -> str:
    if price is None:
        return "Consultar"
    p = f"{price:,.0f}".replace(",", ".")
    return f"USD {p}" if cur == "USD" else f"$ {p}"


def _fmt_dt(d: datetime | None, tz: ZoneInfo) -> str:
    if not d:
        return "—"
    return d.astimezone(tz).strftime("%d/%m %H:%M")


def _day(d: datetime, tz: ZoneInfo) -> str:
    return d.astimezone(tz).strftime("%Y-%m-%d")


_DAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _fmt_long(d: datetime, tz: ZoneInfo) -> str:
    l = d.astimezone(tz)
    return f"{_DAYS[l.weekday()]} {l.day} de {_MONTHS[l.month - 1]} de {l.year}, {l.strftime('%H:%M')}"


def _day_label(day: str, today: str) -> str:
    d = datetime.strptime(day, "%Y-%m-%d")
    if day == today:
        return "Hoy"
    if day == (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d"):
        return "Ayer"
    return f"{_DAYS[d.weekday()].capitalize()} {d.day} de {_MONTHS[d.month - 1]}"


def card_view(c: Card, now: datetime, tz: ZoneInfo, baseline_at: datetime | None) -> dict[str, Any]:
    p = c.primary
    l, v = p.listing, p.verdict
    is_new = baseline_at is not None and p.first_seen > baseline_at and (now - p.first_seen) <= timedelta(days=NEW_DAYS)
    gone = all(e.gone_since is not None for e in c.entries)
    is_back = (not gone) and any(e.back_at is not None and (now - e.back_at) <= timedelta(days=NEW_DAYS) for e in c.entries)
    price_changed = (
        p.price_changed_at is not None and (now - p.price_changed_at) <= timedelta(days=NEW_DAYS)
        and len(p.price_history) > 1 and p.price_history[-2].price is not None and l.price is not None
        and p.price_history[-2].currency == l.currency
    )
    prev_price = p.price_history[-2].price if price_changed else None
    return {
        "key": c.key,
        "title": l.title,
        "url": l.url,
        "image": (l.images[0] if l.images else None),
        "locality": v.locality or (l.locality or None),
        "locality_confirmed": v.locality is not None,
        "bedrooms": v.bedrooms,
        "price": fmt_price(l.price, l.currency),
        "price_raw": l.price,
        "currency": l.currency,
        "prev_price": fmt_price(prev_price, l.currency) if prev_price is not None else None,
        "price_dir": ("down" if (prev_price is not None and l.price is not None and l.price < prev_price) else "up") if price_changed else None,
        "address": l.address,
        "description": (l.description or "")[:400],
        "agency": l.agency,
        "sources": [{"name": e.listing.agency or e.listing.source, "url": e.listing.url, "source": e.listing.source} for e in sorted(c.entries, key=lambda e: e.first_seen)],
        "status": v.status,
        "is_new": is_new,
        "is_gone": gone,
        "is_back": is_back,
        "first_seen": _fmt_dt(p.first_seen, tz),
        "first_seen_day": _day(p.first_seen, tz),
        "first_seen_iso": p.first_seen.isoformat(),
        "first_seen_rfc822": format_datetime(p.first_seen),
        "last_seen": _fmt_dt(max(e.last_seen for e in c.entries), tz),
        "gone_since": _fmt_dt(p.gone_since, tz) if gone else None,
        "extra": {k: v for k, v in l.extra.items() if k not in ("img_hash",)},
    }


def build_context(state: State, cfg: dict[str, Any], sources_meta: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    tz = ZoneInfo(cfg["telegram"]["timezone"])
    baseline_at = state.baseline_at
    if baseline_at is None:  # estados anteriores a que se guardara baseline_at
        for r in state.runs:
            if r.get("baseline"):
                baseline_at = datetime.fromisoformat(r["at"])
                break
    entries = list(state.listings.values())
    cards = [card_view(c, now, tz, baseline_at) for c in cluster(entries)]
    cards.sort(key=lambda c: c["first_seen_iso"], reverse=True)

    today = _day(now, tz)
    news_by_day: dict[str, list[dict]] = defaultdict(list)
    for c in cards:
        if c["is_new"] and not c["is_gone"]:
            news_by_day[c["first_seen_day"]].append(c)
    news = [{"day": d, "label": _day_label(d, today), "cards": cs} for d, cs in sorted(news_by_day.items(), reverse=True)]

    active = [c for c in cards if not c["is_gone"] and c["status"] == "match"]
    maybe_loc = [c for c in cards if not c["is_gone"] and c["status"] == "maybe_location"]
    maybe_beds = [c for c in cards if not c["is_gone"] and c["status"] == "maybe_bedrooms"]
    gone = [c for c in cards if c["is_gone"]]

    thr = cfg.get("zero_streak_alert", 2)
    health = []
    slugs = [s["slug"] for s in sources_meta] + [s for s in sorted(state.sources) if s not in {m["slug"] for m in sources_meta}]
    meta_by_slug = {s["slug"]: s for s in sources_meta}
    for slug in slugs:
        m = meta_by_slug.get(slug, {})
        h = state.sources.get(slug, SourceHealth())
        stale = h.last_ok is None or (now - h.last_ok) > timedelta(hours=13)
        broken = h.error is not None or h.zero_streak >= thr
        if h.error:
            status = f"error: {h.error[:80]}"
        elif h.zero_streak >= thr:
            status = f"{h.zero_streak} corridas sin resultados"
        elif h.last_ok is None:
            status = "sin datos todavía" + (" (se corre desde la Mac)" if m.get("run_from") == "mac" else "")
        elif stale:
            status = "sin datos recientes" + (" (se corre desde la Mac)" if m.get("run_from") == "mac" else "")
        else:
            status = "ok"
        health.append({
            "slug": slug,
            "name": m.get("name", slug),
            "url": m.get("url", ""),
            "last_ok": _fmt_dt(h.last_ok, tz),
            "last_count": h.last_count,
            "error": h.error,
            "zero_streak": h.zero_streak,
            "broken": broken,          # para el resumen de Telegram
            "ok": not broken and not stale,
            "status": status,
        })
    return {
        "site": cfg["site"],
        "min_bedrooms": cfg["min_bedrooms"],
        "generated": _fmt_long(now, tz),
        "generated_iso": now.isoformat(),
        "generated_rfc822": format_datetime(now),
        "news": news,
        "news_count": sum(len(d["cards"]) for d in news),
        "active": active,
        "maybe_loc": maybe_loc,
        "maybe_beds": maybe_beds,
        "gone": gone,
        "health": health,
        "manual_check": cfg.get("manual_check", []),
        "localities": list(cfg["localities"].keys()),
        "all_cards": cards,
    }


def render(state: State, cfg: dict[str, Any], sources_meta: list[dict[str, Any]], out_dir: Path, now: datetime) -> dict[str, Any]:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html", "xml"]))
    ctx = build_context(state, cfg, sources_meta, now)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(env.get_template("index.html").render(**ctx), encoding="utf-8")
    (out_dir / "feed.xml").write_text(env.get_template("feed.xml").render(**ctx), encoding="utf-8")
    (out_dir / "data.json").write_text(json.dumps({"generated": ctx["generated_iso"], "cards": ctx["all_cards"]}, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / ".nojekyll").write_text("")
    return ctx
