"""Agrupa el mismo inmueble publicado en varias fuentes. Conservador: ante la duda, no une."""
from __future__ import annotations

import difflib
from dataclasses import dataclass, field

from .classify import normalize
from .state import Entry

PRICE_TOL = 0.03
TITLE_MIN = 0.85
HASH_MAX = 6


def similar_title(a: str, b: str) -> bool:
    na, nb = normalize(a), normalize(b)
    na = "".join(c for c in na if c.isalnum() or c == " ")
    nb = "".join(c for c in nb if c.isalnum() or c == " ")
    if not na or not nb:
        return False
    return difflib.SequenceMatcher(None, na, nb).ratio() >= TITLE_MIN


def hamming(h1: str, h2: str) -> int:
    return bin(int(h1, 16) ^ int(h2, 16)).count("1")


def _same_price(a: Entry, b: Entry) -> bool:
    pa, pb = a.listing.price, b.listing.price
    if a.listing.currency != b.listing.currency:
        return False
    if pa is None and pb is None:
        return True
    if pa is None or pb is None:
        return False
    return abs(pa - pb) <= PRICE_TOL * max(pa, pb)


def _same_house(a: Entry, b: Entry) -> bool:
    if a.listing.source == b.listing.source:
        return False
    if a.verdict.locality != b.verdict.locality or a.verdict.bedrooms != b.verdict.bedrooms:
        return False
    if not _same_price(a, b):
        return False
    ha, hb = a.listing.extra.get("img_hash"), b.listing.extra.get("img_hash")
    if ha and hb and hamming(ha, hb) <= HASH_MAX:
        return True
    return similar_title(a.listing.title, b.listing.title)


@dataclass
class Card:
    entries: list[Entry] = field(default_factory=list)

    @property
    def primary(self) -> Entry:
        return min(self.entries, key=lambda e: e.first_seen)

    @property
    def key(self) -> str:
        return self.primary.key


def cluster(entries: list[Entry]) -> list[Card]:
    cards: list[Card] = []
    for e in entries:
        for c in cards:
            if any(_same_house(e, o) for o in c.entries) and all(o.listing.source != e.listing.source for o in c.entries):
                c.entries.append(e)
                break
        else:
            cards.append(Card([e]))
    return cards
