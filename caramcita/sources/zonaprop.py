"""Zonaprop: detrás de un challenge de Cloudflare, necesita navegador (Playwright).

Si el challenge no se supera (típico desde IPs de datacenter), fetch() levanta
BlockedError y el pipeline usa el último snapshot generado desde la Mac.
"""
from __future__ import annotations

import logging
import re
import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..http import UA, Http
from ..models import Listing
from .base import Source, parse_price, text_of

log = logging.getLogger(__name__)
BASE = "https://www.zonaprop.com.ar"


class BlockedError(RuntimeError):
    pass


_ID_RE = re.compile(r"-(\d+)\.html")
_BED_RE = re.compile(r"(\d+)\s*dorm")


def parse_html(html: str, source: "Adapter") -> list[Listing]:
    soup = BeautifulSoup(html, "lxml")
    out: list[Listing] = []
    for card in soup.select('[data-qa="posting PROPERTY"]'):
        try:
            path = card.get("data-to-posting") or ""
            path = path.split("?")[0]
            pid = card.get("data-id") or (_ID_RE.search(path).group(1) if _ID_RE.search(path) else None)
            if not pid or not path:
                continue
            url = urljoin(BASE, path)
            slug = path.rsplit("/", 1)[-1].replace(".html", "")
            slug = re.sub(r"^[a-z]+-", "", slug, count=1)  # prefijo tipo "alclcain-"
            slug = re.sub(r"-\d+$", "", slug)
            title = slug.replace("-", " ").strip().capitalize() or "Aviso Zonaprop"
            price, cur = parse_price(text_of(card.select_one('[data-qa="POSTING_CARD_PRICE"]')))
            loc_el = card.select_one('[data-qa="POSTING_CARD_LOCATION"]')
            loc = text_of(loc_el)
            addr_el = loc_el.find_previous_sibling() if loc_el else None
            addr = text_of(addr_el) if addr_el else ""
            feats = text_of(card.select_one('[data-qa="POSTING_CARD_FEATURES"]'))
            m = _BED_RE.search(feats)
            beds = int(m.group(1)) if m else None
            desc = text_of(card.select_one('[data-qa="POSTING_CARD_DESCRIPTION"]'))
            img = card.select_one('[data-qa="POSTING_CARD_GALLERY"] img')
            images = [img["src"]] if img and img.get("src") else []
            pub = card.select_one('[data-qa="POSTING_CARD_PUBLISHER"] img')
            agency = (pub.get("alt") if pub else "") or "Zonaprop"
            # "Reserva Tajamar, Alta Gracia" → localidad = último tramo
            locality = loc.split(",")[-1].strip() if loc else ""
            if locality.lower() == "córdoba" and "," in loc:
                locality = loc.split(",")[-2].strip()
            ptype = "Departamento" if "departamento" in slug else ("Casa" if "casa" in slug else "")
            out.append(source.listing(
                source_id=str(pid), url=url, title=title, description=desc, price=price, currency=cur,
                locality=locality, address=", ".join(x for x in [addr, loc] if x), bedrooms=beds,
                property_type=ptype, operation="Alquiler", images=images, agency=agency,
                extra={"features": feats},
            ))
        except Exception as e:  # noqa: BLE001
            log.warning("zonaprop: aviso no parseable: %s", e)
    return out


class Adapter(Source):
    needs_browser = True

    def __init__(self, slug: str, name: str, urls: list[str], **params):
        super().__init__(slug, name, **params)
        self.urls = urls

    def fetch(self, http: Http) -> list[Listing]:
        from playwright.sync_api import sync_playwright  # import tardío: sólo si hace falta

        seen: dict[str, Listing] = {}
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for url in self.urls:
                # Un contexto nuevo (cookies limpias) por URL: la segunda navegación en el mismo
                # contexto dispara el challenge de Cloudflare y en headless no se resuelve solo.
                html = self._load_fresh(browser, url)
                if html is None:
                    time.sleep(15)  # segundo intento tras una pausa
                    html = self._load_fresh(browser, url)
                if html is None:
                    browser.close()
                    raise BlockedError(f"Cloudflare challenge en {url}")
                found = parse_html(html, self)
                for l in found:
                    seen.setdefault(l.key, l)
                log.info("zonaprop %s → %d avisos (%d acumulados)", url, len(found), len(seen))
            browser.close()
        return list(seen.values())

    def _load_fresh(self, browser, url: str) -> str | None:
        ctx = browser.new_context(locale="es-AR", user_agent=UA, viewport={"width": 1280, "height": 900})
        try:
            return self._load(ctx.new_page(), url)
        finally:
            ctx.close()

    @staticmethod
    def _is_challenge(page) -> bool:
        t = page.title().lower()
        return "un momento" in t or "just a moment" in t or "attention required" in t

    def _load(self, page, url: str) -> str | None:
        """Carga la URL y espera a que el challenge pasivo de Cloudflare se resuelva. None si no pasa."""
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        for _ in range(15):  # hasta ~30 s
            if not self._is_challenge(page):
                break
            page.wait_for_timeout(2_000)
        if self._is_challenge(page):
            return None
        try:
            page.wait_for_selector('[data-qa="posting PROPERTY"], h1', timeout=20_000)
        except Exception:  # noqa: BLE001
            pass
        page.wait_for_timeout(1_500)
        return page.content()
