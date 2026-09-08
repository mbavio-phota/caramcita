"""Estado persistente entre corridas y cálculo de novedades."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .models import Listing, Verdict


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def _dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


@dataclass
class PricePoint:
    at: datetime
    price: float | None
    currency: str | None


@dataclass
class Entry:
    listing: Listing
    verdict: Verdict
    first_seen: datetime
    last_seen: datetime
    gone_since: datetime | None = None
    price_changed_at: datetime | None = None
    price_history: list[PricePoint] = field(default_factory=list)

    @property
    def key(self) -> str:
        return self.listing.key

    def to_dict(self) -> dict[str, Any]:
        return {
            "listing": self.listing.to_dict(),
            "verdict": self.verdict.__dict__,
            "first_seen": _iso(self.first_seen),
            "last_seen": _iso(self.last_seen),
            "gone_since": _iso(self.gone_since),
            "price_changed_at": _iso(self.price_changed_at),
            "price_history": [{"at": _iso(p.at), "price": p.price, "currency": p.currency} for p in self.price_history],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Entry":
        return cls(
            listing=Listing.from_dict(d["listing"]),
            verdict=Verdict(**d["verdict"]),
            first_seen=_dt(d["first_seen"]),
            last_seen=_dt(d["last_seen"]),
            gone_since=_dt(d.get("gone_since")),
            price_changed_at=_dt(d.get("price_changed_at")),
            price_history=[PricePoint(_dt(p["at"]), p["price"], p["currency"]) for p in d.get("price_history", [])],
        )


@dataclass
class SourceHealth:
    last_run: datetime | None = None
    last_ok: datetime | None = None
    last_count: int = 0
    zero_streak: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "last_run": _iso(self.last_run),
            "last_ok": _iso(self.last_ok),
            "last_count": self.last_count,
            "zero_streak": self.zero_streak,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SourceHealth":
        return cls(_dt(d.get("last_run")), _dt(d.get("last_ok")), d.get("last_count", 0), d.get("zero_streak", 0), d.get("error"))


@dataclass
class SourceResult:
    source: str
    listings: list[Listing]
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class Changes:
    baseline: bool
    new: list[Entry] = field(default_factory=list)
    price_changed: list[tuple[Entry, float | None, float | None]] = field(default_factory=list)
    gone: list[Entry] = field(default_factory=list)
    back: list[Entry] = field(default_factory=list)


@dataclass
class State:
    listings: dict[str, Entry]
    sources: dict[str, SourceHealth]
    runs: list[dict[str, Any]]
    baseline_done: bool = False
    last_summary_date: str | None = None  # YYYY-MM-DD (hora local) del último resumen enviado
    telegram_chat_id: str | None = None  # se descubre solo la primera vez que el bot recibe un mensaje

    @classmethod
    def empty(cls) -> "State":
        return cls({}, {}, [])

    @classmethod
    def load(cls, path: Path) -> "State":
        if not Path(path).exists():
            return cls.empty()
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return cls(
            listings={k: Entry.from_dict(v) for k, v in d.get("listings", {}).items()},
            sources={k: SourceHealth.from_dict(v) for k, v in d.get("sources", {}).items()},
            runs=d.get("runs", []),
            baseline_done=d.get("baseline_done", False),
            last_summary_date=d.get("last_summary_date"),
            telegram_chat_id=d.get("telegram_chat_id"),
        )

    def save(self, path: Path) -> None:
        d = {
            "version": 1,
            "baseline_done": self.baseline_done,
            "last_summary_date": self.last_summary_date,
            "telegram_chat_id": self.telegram_chat_id,
            "listings": {k: v.to_dict() for k, v in sorted(self.listings.items())},
            "sources": {k: v.to_dict() for k, v in sorted(self.sources.items())},
            "runs": self.runs[-60:],
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1, sort_keys=False)
            f.write("\n")


def apply_run(
    state: State,
    results: dict[str, SourceResult],
    verdicts: dict[str, Verdict],
    now: datetime,
    retention_days: int = 7,
) -> Changes:
    """Fusiona los resultados de una corrida en el estado y devuelve las novedades."""
    baseline = not state.baseline_done
    ch = Changes(baseline=baseline)

    seen_ok_sources = {s for s, r in results.items() if r.ok}

    # 1. avisos presentes en esta corrida
    for src, res in results.items():
        health = state.sources.setdefault(src, SourceHealth())
        health.last_run = now
        if res.ok:
            health.last_ok = now
            health.last_count = len(res.listings)
            health.error = None
            health.zero_streak = health.zero_streak + 1 if not res.listings else 0
        else:
            health.error = res.error
        if not res.ok:
            continue
        for l in res.listings:
            v = verdicts.get(l.key)
            if v is None or not v.shown:
                # si antes se mostraba y ahora se descarta, sale sin más
                state.listings.pop(l.key, None)
                continue
            e = state.listings.get(l.key)
            if e is None:
                e = Entry(listing=l, verdict=v, first_seen=now, last_seen=now,
                          price_history=[PricePoint(now, l.price, l.currency)])
                state.listings[l.key] = e
                if not baseline:
                    ch.new.append(e)
                continue
            old_price, old_cur = e.listing.price, e.listing.currency
            if e.gone_since is not None:
                e.gone_since = None
                ch.back.append(e)
            e.listing, e.verdict, e.last_seen = l, v, now
            if l.price != old_price or l.currency != old_cur:
                e.price_history.append(PricePoint(now, l.price, l.currency))
                e.price_changed_at = now
                if not baseline and old_price is not None and l.price is not None:
                    ch.price_changed.append((e, old_price, l.price))

    # 2. avisos que ya no aparecen en fuentes que corrieron bien
    cutoff = now - timedelta(days=retention_days)
    for key, e in list(state.listings.items()):
        if e.listing.source not in seen_ok_sources or e.last_seen == now:
            continue
        if e.gone_since is None:
            e.gone_since = now
            ch.gone.append(e)
        elif e.gone_since < cutoff:
            del state.listings[key]

    state.baseline_done = True
    state.runs.append({
        "at": now.isoformat(),
        "baseline": baseline,
        "new": len(ch.new),
        "gone": len(ch.gone),
        "price_changed": len(ch.price_changed),
        "sources": {s: {"count": len(r.listings), "error": r.error} for s, r in results.items()},
    })
    return ch
