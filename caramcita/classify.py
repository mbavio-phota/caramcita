"""Clasificación de avisos: localidad, dormitorios, tipo de propiedad, temporario."""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from .models import Listing, Verdict


def normalize(s: str | None) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("º", " ").replace("°", " ")
    return re.sub(r"\s+", " ", s).strip()


def _phrase_re(phrase: str) -> re.Pattern[str]:
    return re.compile(r"(?<![a-z0-9])" + re.escape(normalize(phrase)) + r"(?![a-z0-9])")


class Classifier:
    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg
        self.min_bedrooms: int = int(cfg.get("min_bedrooms", 3))
        # (nombre canónico, regex) ordenado por alias más largo primero
        aliases: list[tuple[str, str]] = []
        barrios: list[tuple[str, str]] = []
        for name, spec in cfg["localities"].items():
            for a in spec.get("aliases", [name]):
                aliases.append((name, a))
            for b in spec.get("barrios", []) or []:
                barrios.append((name, b))
        aliases.sort(key=lambda t: -len(t[1]))
        barrios.sort(key=lambda t: -len(t[1]))
        self.aliases = [(n, _phrase_re(a)) for n, a in aliases]
        self.barrios = [(n, _phrase_re(b)) for n, b in barrios]
        self.excluded = [_phrase_re(x) for x in cfg.get("excluded_localities", [])]

    # ---- localidad -------------------------------------------------------
    def _first_alias(self, text: str) -> tuple[str, int] | None:
        best: tuple[str, int] | None = None
        for name, rx in self.aliases:
            m = rx.search(text)
            if m and (best is None or m.start() < best[1]):
                best = (name, m.start())
        return best

    def _first_excluded(self, text: str) -> int | None:
        best: int | None = None
        for rx in self.excluded:
            m = rx.search(text)
            if m and (best is None or m.start() < best):
                best = m.start()
        return best

    def match_locality(self, locality: str, texts: list[str]) -> tuple[str | None, str]:
        loc = normalize(locality)
        if loc:
            if self._first_excluded(loc) is not None and self._first_alias(loc) is None:
                return None, "excluded"
            hit = self._first_alias(loc)
            if hit:
                return hit[0], "exact"
        text = " | ".join(normalize(t) for t in texts if t)
        alias_hit = self._first_alias(text)
        excl_pos = self._first_excluded(text)
        if alias_hit and (excl_pos is None or alias_hit[1] <= excl_pos):
            return alias_hit[0], "text"
        if excl_pos is not None:
            return None, "excluded"
        for name, rx in self.barrios:
            if rx.search(text) or rx.search(loc):
                return name, "barrio"
        return None, "unknown"

    # ---- evaluación completa --------------------------------------------
    def evaluate(self, l: Listing) -> Verdict:
        text = " ".join(x for x in [l.title, l.description] if x)
        if is_temporary(l.operation, text):
            return Verdict("rejected", "temporario o venta")
        ptype = classify_property_type(l.property_type, text)
        if ptype == "excluded":
            return Verdict("rejected", f"tipo excluido: {l.property_type or 'según texto'}")
        locality, how = self.match_locality(l.locality, [l.address, l.title, l.description])
        if how == "excluded":
            return Verdict("rejected", "localidad fuera de zona")
        bedrooms = parse_bedrooms(l.bedrooms, text)
        if bedrooms is not None and bedrooms < self.min_bedrooms:
            return Verdict("rejected", f"{bedrooms} dormitorios", locality, bedrooms)
        if locality is None:
            return Verdict("maybe_location", "ubicación sin confirmar", None, bedrooms)
        if bedrooms is None:
            return Verdict("maybe_bedrooms", "dormitorios sin dato", locality, None)
        return Verdict("match", how, locality, bedrooms)


def match_locality(clf: Classifier, locality: str, texts: list[str]) -> tuple[str | None, str]:
    return clf.match_locality(locality, texts)


# ---- dormitorios ---------------------------------------------------------
_NUM_WORDS = {
    "un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8,
}
_BED_RE = re.compile(
    r"(?<![a-z0-9])(\d{1,2}|un|una|uno|dos|tres|cuatro|cinco|seis|siete|ocho)\s*"
    r"(?:amplios?\s+|grandes?\s+)?"
    r"(dormitorios?|dorms?\b\.?|habitaciones?|habs?\b\.?|cuartos?|recamaras?)"
)


def parse_bedrooms(structured: int | None, text: str) -> int | None:
    if structured is not None:
        try:
            n = int(structured)
        except (TypeError, ValueError):
            n = 0
        if n > 0:
            return n
    m = _BED_RE.search(normalize(text))
    if not m:
        return None
    tok = m.group(1)
    n = int(tok) if tok.isdigit() else _NUM_WORDS[tok]
    return n if 0 < n < 20 else None


# ---- tipo de propiedad ---------------------------------------------------
_HOUSE_KW = [r"casa", r"casas", r"duplex", r"ph", r"chalet", r"cabana", r"cabanas", r"quinta", r"vivienda", r"casona", r"triplex"]
_EXCL_KW = [
    r"departamentos?", r"deptos?", r"dptos?", r"monoambiente", r"local(es)?( comercial(es)?)?", r"oficinas?", r"terrenos?",
    r"lotes?", r"galpon(es)?", r"cocheras?", r"campos?", r"fondo de comercio", r"hotel(es)?", r"edificios?", r"deposito",
    r"consultorios?", r"hospedaje", r"hostel", r"chacra",
]
_HOUSE_RE = re.compile(r"(?<![a-z0-9])(" + "|".join(_HOUSE_KW) + r")(?![a-z0-9])")
_EXCL_RE = re.compile(r"(?<![a-z0-9])(" + "|".join(_EXCL_KW) + r")(?![a-z0-9])")


def classify_property_type(ptype: str, text: str) -> str:
    p = normalize(ptype)
    if p:
        if _HOUSE_RE.search(p):
            return "casa"
        if _EXCL_RE.search(p):
            return "excluded"
    t = normalize(text)
    if _HOUSE_RE.search(t):
        return "casa"
    if _EXCL_RE.search(t):
        return "excluded"
    return "unknown"


# ---- temporario / venta --------------------------------------------------
_TEMP_RE = re.compile(
    r"temporari[oa]s?|temporal(es)?|temporada|por dia|por noche|diario|turistic[oa]s?|vacacion|fin(es)? de semana|estadia"
)
_ANNUAL_RE = re.compile(r"anual|permanente|no temporar|24 meses|largo plazo|contrato de 2|contrato de 3|contrato de 24|contrato de 36")


def is_temporary(operation: str, text: str) -> bool:
    op = normalize(operation)
    if op:
        if _TEMP_RE.search(op):
            return True
        if "venta" in op and "alquiler" not in op:
            return True
    t = normalize(text)
    if _ANNUAL_RE.search(t):
        return False
    return bool(_TEMP_RE.search(t))
