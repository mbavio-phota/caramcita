"""Hash perceptual (dHash) de la primera foto, para detectar el mismo inmueble en distintas fuentes."""
from __future__ import annotations

import io
import logging

from PIL import Image

from .http import Http

log = logging.getLogger(__name__)


def dhash_bytes(data: bytes, size: int = 8) -> str:
    img = Image.open(io.BytesIO(data)).convert("L").resize((size + 1, size), Image.Resampling.LANCZOS)
    px = list(img.getdata())
    bits = 0
    for row in range(size):
        for col in range(size):
            left = px[row * (size + 1) + col]
            right = px[row * (size + 1) + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return f"{bits:0{size * size // 4}x}"


def image_hash(http: Http, url: str) -> str | None:
    try:
        r = http.get(url)
        return dhash_bytes(r.content)
    except Exception as e:  # noqa: BLE001 - una foto rota no debe frenar la corrida
        log.info("no se pudo hashear %s: %s", url, e)
        return None
