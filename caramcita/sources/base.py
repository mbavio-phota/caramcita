from __future__ import annotations

import re
from typing import Any

from ..http import Http
from ..models import Listing


class Source:
    """Base de un adaptador. Subclases implementan fetch()."""

    #: fuentes que necesitan navegador (Playwright); se corren aparte
    needs_browser = False

    def __init__(self, slug: str, name: str, **params: Any):
        self.slug = slug
        self.name = name
        self.params = params

    def fetch(self, http: Http) -> list[Listing]:  # pragma: no cover - abstracta
        raise NotImplementedError

    # ---- utilidades comunes ---------------------------------------------
    def listing(self, **kw: Any) -> Listing:
        kw.setdefault("agency", self.name)
        return Listing(source=self.slug, **kw)


_PRICE_RE = re.compile(r"(?i)(u\$s|usd|us\$|u\$d|dolares|dólares|\$|ars|pesos)?\s*([\d.,]+)\s*(usd|dolares|dólares|u\$s|ars|pesos)?")


def parse_price(text: str | None) -> tuple[float | None, str | None]:
    """'$ 850.000' → (850000.0, 'ARS'); 'USD 1.200' → (1200.0, 'USD'); 'Consultar' → (None, None)."""
    if not text:
        return None, None
    t = text.strip()
    if re.search(r"(?i)consult", t):
        return None, None
    m = _PRICE_RE.search(t)
    if not m:
        return None, None
    num = m.group(2)
    if not re.search(r"\d", num):
        return None, None
    # 850.000 / 850,000 / 850.000,50
    if "," in num and "." in num:
        num = num.replace(".", "").replace(",", ".")
    elif "," in num:
        num = num.replace(",", "") if len(num.split(",")[-1]) == 3 else num.replace(",", ".")
    else:
        num = num.replace(".", "")
    try:
        value = float(num)
    except ValueError:
        return None, None
    pre = (m.group(1) or "").lower()
    post = (m.group(3) or "").lower()
    cur_txt = pre + " " + post
    if any(k in cur_txt for k in ("u$s", "usd", "us$", "u$d", "dolar", "dólar")):
        cur = "USD"
    elif "$" in cur_txt or "ars" in cur_txt or "pesos" in cur_txt:
        cur = "ARS"
    else:
        cur = "USD" if value < 5000 else "ARS"
    return value, cur


def text_of(el: Any) -> str:
    return " ".join(el.get_text(" ", strip=True).split()) if el is not None else ""
