"""Punto de entrada: caramcita run | render | chat-id | probe <slug>."""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .classify import Classifier
from .config import ROOT, load_config, load_sources
from .dedupe import cluster
from .http import Http
from .images import image_hash
from .models import Verdict
from .notify import Telegram, esc, listing_message, price_message
from .report import render
from .sources import build_source
from .state import SourceResult, State, apply_run

log = logging.getLogger("caramcita")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


SNAPSHOT_MAX_AGE_H = 26


def load_snapshot(snap_dir: Path, slug: str, now: datetime) -> SourceResult | None:
    """Snapshot generado por `caramcita snapshot` (p. ej. desde la Mac para fuentes con navegador)."""
    p = snap_dir / f"{slug}.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    at = datetime.fromisoformat(d["fetched_at"])
    if now - at > timedelta(hours=SNAPSHOT_MAX_AGE_H):
        log.warning("[%s] snapshot viejo (%s); se ignora", slug, at)
        return None
    from .models import Listing
    listings = [Listing.from_dict(x) for x in d["listings"]]
    log.info("[%s] %d avisos desde snapshot de %s", slug, len(listings), at)
    return SourceResult(slug, listings)


def fetch_one(spec, http) -> SourceResult:
    src = build_source(spec)
    try:
        listings = src.fetch(http)
        log.info("[%s] %d avisos", src.slug, len(listings))
        return SourceResult(src.slug, listings)
    except Exception as e:  # noqa: BLE001 - una fuente rota no frena las demás
        log.exception("[%s] falló", src.slug)
        return SourceResult(src.slug, [], f"{type(e).__name__}: {e}"[:200])


def host() -> str:
    """'mac' cuando corre en la Mac (launchd o a mano), 'ci' en GitHub Actions."""
    return os.environ.get("CARAMCITA_HOST") or ("ci" if os.environ.get("GITHUB_ACTIONS") else "mac")


def fetch_all(specs, http, only=None, with_browser=False, snap_dir: Path | None = None, now: datetime | None = None) -> dict[str, SourceResult]:
    results: dict[str, SourceResult] = {}
    now = now or _now()
    for spec in specs:
        if only and spec["slug"] not in only:
            continue
        src = build_source(spec)
        mac_only = spec.get("run_from") == "mac" and host() != "mac"
        if not src.needs_browser and not mac_only:
            results[src.slug] = fetch_one(spec, http)
            continue
        can_try = (not src.needs_browser or with_browser) and not mac_only
        res = fetch_one(spec, http) if can_try else None
        if res is not None and res.ok:
            results[src.slug] = res
            continue
        snap = load_snapshot(snap_dir, src.slug, now) if snap_dir else None
        if snap is not None:
            results[src.slug] = snap
        elif res is not None:
            results[src.slug] = res  # falló y no hay snapshot: queda el error
        else:
            log.info("[%s] %s y no hay snapshot fresco; omitida", src.slug,
                     "se corre desde la Mac" if mac_only else "necesita navegador")
    return results


def cmd_run(args) -> int:
    cfg = load_config()
    specs = load_sources()
    clf = Classifier(cfg)
    state_path = Path(args.state)
    state = State.load(state_path)
    now = _now()
    http = Http(delay=cfg.get("request_delay_seconds", 3))
    with_browser = args.browser or os.environ.get("CARAMCITA_BROWSER") == "1"
    results = fetch_all(specs, http, only=args.only, with_browser=with_browser, snap_dir=Path(args.snapshots), now=now)

    verdicts: dict[str, Verdict] = {}
    for r in results.values():
        for l in r.listings:
            verdicts[l.key] = clf.evaluate(l)
            log.debug("%s → %s (%s)", l.key, verdicts[l.key].status, verdicts[l.key].reason)

    changes = apply_run(state, results, verdicts, now, retention_days=cfg.get("retention_days", 7))

    # hash de la primera foto para detectar duplicados entre fuentes (sólo entradas sin hash)
    if not args.no_images:
        for e in state.listings.values():
            if e.listing.images and "img_hash" not in e.listing.extra:
                h = image_hash(http, e.listing.images[0])
                e.listing.extra["img_hash"] = h or ""

    # el diario
    ctx = render(state, cfg, specs, Path(args.out), now)
    if not args.dry_run:
        state.save(state_path)  # antes de avisar: si Telegram falla, no se repiten avisos en la próxima

    # avisos
    tg = Telegram(chat_id=os.environ.get("TELEGRAM_CHAT_ID") or state.telegram_chat_id)
    if tg.token and not tg.chat_id:
        try:
            cid = tg.get_chat_id()
        except Exception as e:  # noqa: BLE001
            log.warning("no se pudo obtener chat_id: %s", e)
            cid = None
        if cid:
            tg.chat_id = state.telegram_chat_id = cid
            log.info("chat_id de Telegram descubierto y guardado en el estado")
            tg.send("✅ Caramcita conectado. Vas a recibir acá las casas nuevas.")
        else:
            log.warning("Telegram: falta chat_id. Mandale un mensaje al bot y en la próxima corrida se conecta solo.")
    site_url = cfg["site"]["base_url"]
    if changes.baseline:
        log.info("Primera corrida: %d avisos como base, sin notificar", len(state.listings))
    elif not args.no_notify:
        _notify(state, cfg, tg, ctx, changes, now, site_url)

    if not args.dry_run:
        state.save(state_path)
    else:
        log.info("dry-run: estado no guardado")
    http.close()
    return 0


def _safe_send(tg: Telegram, text: str, photo: str | None = None) -> None:
    try:
        tg.send(text, photo=photo)
    except Exception as e:  # noqa: BLE001 - un aviso fallido no frena la corrida ni repite los demás
        log.error("Telegram falló: %s", e)


def _notify(state: State, cfg, tg: Telegram, ctx, changes, now: datetime, site_url: str) -> None:
    cards = {e.key: c for c in cluster(list(state.listings.values())) for e in c.entries}
    new_keys = {e.key for e in changes.new}
    announced: set[str] = set()
    for e in changes.new:
        if e.verdict.status != "match":
            continue  # los "sin confirmar" van al diario y al resumen, no como mensaje propio
        card = cards.get(e.key)
        if card:
            if card.key in announced:
                continue
            if any(o.key not in new_keys for o in card.entries):
                continue  # es la misma casa que ya conocíamos por otra fuente
            announced.add(card.key)
        others = [o for o in (card.entries if card else []) if o.key != e.key]
        _safe_send(tg, listing_message(e, site_url, others), photo=(e.listing.images[0] if e.listing.images else None))
    for e, old, new in changes.price_changed:
        if e.verdict.status == "match" and e.listing.currency == e.price_history[-2].currency:
            _safe_send(tg, price_message(e, old, new, site_url))
    _health_alerts(state, cfg, tg)
    _daily_summary(state, cfg, tg, ctx, now)


def _health_alerts(state: State, cfg, tg: Telegram) -> None:
    """Un solo aviso cuando una fuente llega a N corridas seguidas con error o sin resultados."""
    thr = cfg.get("zero_streak_alert", 2)
    bad = []
    for slug, h in state.sources.items():
        if h.error_streak == thr:
            bad.append(f"• {slug}: error ({esc((h.error or '')[:60])})")
        elif h.zero_streak == thr:
            bad.append(f"• {slug}: {h.zero_streak} corridas seguidas sin resultados")
    if bad:
        _safe_send(tg, "<b>⚠️ Fuentes con problemas</b>\n" + "\n".join(bad))


def _daily_summary(state: State, cfg, tg: Telegram, ctx, now: datetime) -> None:
    tz = ZoneInfo(cfg["telegram"]["timezone"])
    local = now.astimezone(tz)
    hour = int(cfg["telegram"].get("daily_summary_hour_local", 8))
    today = local.strftime("%Y-%m-%d")
    if local.hour < hour or state.last_summary_date == today:
        return
    last24 = [c for d in ctx["news"] for c in d["cards"]
              if (now - datetime.fromisoformat(c["first_seen_iso"])).total_seconds() < 24 * 3600]
    broken = [h["name"] for h in ctx["health"] if h["broken"]]
    lines = [f"<b>☕ Resumen {local.strftime('%d/%m')}</b>",
             f"{len(last24)} novedades en 24 h · {len(ctx['active'])} casas vigentes"]
    if ctx["maybe_loc"] or ctx["maybe_beds"]:
        lines.append(f"{len(ctx['maybe_loc'])} con ubicación sin confirmar · {len(ctx['maybe_beds'])} sin dato de dormitorios")
    lines.append(("Fuentes con problemas: " + ", ".join(esc(b) for b in broken)) if broken else "Todas las fuentes OK")
    lines.append(f'<a href="{esc(cfg["site"]["base_url"])}">Abrir el diario</a>')
    _safe_send(tg, "\n".join(lines))
    state.last_summary_date = today


def cmd_snapshot(args) -> int:
    """Corre fuentes (con navegador si hace falta) y guarda sus avisos crudos en snapshots/<slug>.json."""
    cfg = load_config()
    specs = load_sources()
    slugs = list(args.slugs)
    if args.mac:
        slugs += [s["slug"] for s in specs if s.get("run_from") == "mac" and s["slug"] not in slugs]
    if not slugs:
        print("indicá slugs o --mac", file=sys.stderr)
        return 1
    http = Http(delay=cfg.get("request_delay_seconds", 3))
    rc = 0
    for slug in slugs:
        spec = next((s for s in specs if s["slug"] == slug), None)
        if not spec:
            print(f"fuente desconocida: {slug}", file=sys.stderr)
            rc = 1
            continue
        res = fetch_one(spec, http)
        if not res.ok:
            print(f"{slug}: falló: {res.error}", file=sys.stderr)
            rc = 2
            continue
        out = Path(args.snapshots) / f"{slug}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"fetched_at": _now().isoformat(), "listings": [l.to_dict() for l in res.listings]},
                                  ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{slug}: {len(res.listings)} avisos → {out}")
    return rc


def cmd_render(args) -> int:
    cfg = load_config()
    render(State.load(Path(args.state)), cfg, load_sources(), Path(args.out), _now())
    return 0


def cmd_chat_id(args) -> int:
    tg = Telegram()
    if not tg.token:
        print("Falta TELEGRAM_BOT_TOKEN", file=sys.stderr)
        return 1
    cid = tg.get_chat_id()
    if not cid:
        print("El bot todavía no recibió ningún mensaje. Mandale 'hola' y volvé a probar.", file=sys.stderr)
        return 1
    print(cid)
    return 0


def cmd_probe(args) -> int:
    """Corre una sola fuente y muestra qué devuelve y cómo se clasifica, sin tocar el estado."""
    cfg = load_config()
    clf = Classifier(cfg)
    spec = next((s for s in load_sources() if s["slug"] == args.slug), None)
    if not spec:
        print(f"fuente desconocida: {args.slug}", file=sys.stderr)
        return 1
    http = Http(delay=cfg.get("request_delay_seconds", 3))
    listings = build_source(spec).fetch(http)
    for l in listings:
        v = clf.evaluate(l)
        print(f"[{v.status:15}] {v.reason:28} | {l.title[:60]!r} | loc={l.locality!r} beds={l.bedrooms} "
              f"type={l.property_type!r} op={l.operation!r} price={l.price} {l.currency} | {l.url}")
    print(f"{len(listings)} avisos", file=sys.stderr)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="caramcita")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="scrapea, actualiza el estado, genera el diario y avisa")
    r.add_argument("--state", default=str(ROOT / "state.json"))
    r.add_argument("--out", default=str(ROOT / "docs"))
    r.add_argument("--only", nargs="*", help="slugs de fuentes a correr")
    r.add_argument("--browser", action="store_true", help="incluir fuentes que necesitan navegador")
    r.add_argument("--dry-run", action="store_true", help="no guardar el estado")
    r.add_argument("--no-notify", action="store_true")
    r.add_argument("--no-images", action="store_true", help="no descargar fotos para hash")
    r.add_argument("--snapshots", default=str(ROOT / "snapshots"))
    r.set_defaults(fn=cmd_run)

    sn = sub.add_parser("snapshot", help="guarda los avisos crudos de fuentes que se corren aparte (desde la Mac)")
    sn.add_argument("slugs", nargs="*")
    sn.add_argument("--mac", action="store_true", help="todas las fuentes con run_from: mac")
    sn.add_argument("--snapshots", default=str(ROOT / "snapshots"))
    sn.set_defaults(fn=cmd_snapshot)

    rr = sub.add_parser("render", help="regenera el diario desde el estado guardado")
    rr.add_argument("--state", default=str(ROOT / "state.json"))
    rr.add_argument("--out", default=str(ROOT / "docs"))
    rr.set_defaults(fn=cmd_render)

    c = sub.add_parser("chat-id", help="obtiene el chat_id de Telegram a partir del último mensaje al bot")
    c.set_defaults(fn=cmd_chat_id)

    pr = sub.add_parser("probe", help="prueba una fuente y muestra la clasificación")
    pr.add_argument("slug")
    pr.set_defaults(fn=cmd_probe)

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname).1s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
