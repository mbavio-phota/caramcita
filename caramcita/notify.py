"""Avisos por Telegram."""
from __future__ import annotations

import html
import logging
import os

import httpx

from .state import Entry

log = logging.getLogger(__name__)
API = "https://api.telegram.org/bot{token}/{method}"


class Telegram:
    def __init__(self, token: str | None = None, chat_id: str | None = None):
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
        self.client = httpx.Client(timeout=30)

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def _call(self, method: str, **data) -> dict:
        r = self.client.post(API.format(token=self.token, method=method), data=data)
        if r.status_code != 200:
            log.error("Telegram %s → %s %s", method, r.status_code, r.text[:300])
        r.raise_for_status()
        return r.json()

    def send(self, text: str, photo: str | None = None) -> None:
        if not self.enabled:
            log.info("Telegram deshabilitado; mensaje omitido:\n%s", text)
            return
        try:
            if photo:
                self._call("sendPhoto", chat_id=self.chat_id, photo=photo, caption=text[:1024], parse_mode="HTML")
                return
        except httpx.HTTPError:
            log.warning("sendPhoto falló, reintento como texto")
        self._call("sendMessage", chat_id=self.chat_id, text=text[:4096], parse_mode="HTML", disable_web_page_preview=False)

    def get_chat_id(self) -> str | None:
        """Devuelve el chat_id del último mensaje recibido por el bot."""
        r = self.client.get(API.format(token=self.token, method="getUpdates"))
        r.raise_for_status()
        updates = r.json().get("result", [])
        for u in reversed(updates):
            msg = u.get("message") or u.get("channel_post") or {}
            chat = msg.get("chat")
            if chat:
                return str(chat["id"])
        return None


def _fmt_price(price: float | None, cur: str | None) -> str:
    if price is None:
        return "Consultar"
    p = f"{price:,.0f}".replace(",", ".")
    return f"USD {p}" if cur == "USD" else f"$ {p}"


def esc(s: str | None) -> str:
    return html.escape(s or "", quote=False)


def listing_message(e: Entry, site_url: str, extra_sources: list[Entry] | None = None) -> str:
    l, v = e.listing, e.verdict
    tag = {"match": "🏠 Nueva casa", "maybe_location": "📍 Ubicación sin confirmar", "maybe_bedrooms": "🛏 Dormitorios sin dato"}[v.status]
    lines = [f"<b>{tag}</b>", f"<b>{esc(l.title)}</b>"]
    detail = []
    if v.locality:
        detail.append(v.locality)
    elif l.locality:
        detail.append(f"{esc(l.locality)} (?)")
    if v.bedrooms:
        detail.append(f"{v.bedrooms} dorm")
    detail.append(_fmt_price(l.price, l.currency))
    lines.append(" · ".join(detail))
    if l.agency:
        lines.append(f"<i>{esc(l.agency)}</i>")
    lines.append(f'<a href="{esc(l.url)}">Ver aviso</a>')
    for o in extra_sources or []:
        lines.append(f'<a href="{esc(o.listing.url)}">También en {esc(o.listing.agency or o.listing.source)}</a>')
    lines.append(f'<a href="{esc(site_url)}">Diario</a>')
    return "\n".join(lines)


def price_message(e: Entry, old: float, new: float, site_url: str) -> str:
    l = e.listing
    arrow = "⬇️" if new < old else "⬆️"
    return (
        f"<b>{arrow} Cambio de precio</b>\n<b>{esc(l.title)}</b>\n"
        f"{_fmt_price(old, l.currency)} → {_fmt_price(new, l.currency)}\n"
        f'<a href="{esc(l.url)}">Ver aviso</a> · <a href="{esc(site_url)}">Diario</a>'
    )
