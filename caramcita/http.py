"""Cliente HTTP cortés: un user-agent normal, pausa entre pedidos, reintentos."""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

log = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


class Http:
    def __init__(self, delay: float = 3.0, timeout: float = 30.0, retries: int = 2):
        self.delay = delay
        self.retries = retries
        self._last = 0.0
        self.client = httpx.Client(
            headers={
                "User-Agent": UA,
                "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            },
            timeout=timeout,
            follow_redirects=True,
        )

    def _pace(self) -> None:
        wait = self.delay - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

    def get(self, url: str, **kw: Any) -> httpx.Response:
        err: Exception | None = None
        for attempt in range(self.retries + 1):
            self._pace()
            try:
                r = self.client.get(url, **kw)
                if 400 <= r.status_code < 500 and r.status_code != 429:
                    r.raise_for_status()  # 4xx: no tiene sentido reintentar
                if r.status_code >= 500 or r.status_code == 429:
                    raise httpx.HTTPStatusError(f"{r.status_code} en {url}", request=r.request, response=r)
                return r
            except httpx.HTTPStatusError as e:
                if e.response is not None and 400 <= e.response.status_code < 500 and e.response.status_code != 429:
                    raise
                err = e
                log.warning("GET %s falló (%s/%s): %s", url, attempt + 1, self.retries + 1, e)
                time.sleep(2 * (attempt + 1))
            except (httpx.HTTPError, httpx.TransportError) as e:
                err = e
                log.warning("GET %s falló (%s/%s): %s", url, attempt + 1, self.retries + 1, e)
                time.sleep(2 * (attempt + 1))
        assert err is not None
        raise err

    def get_text(self, url: str, **kw: Any) -> str:
        return self.get(url, **kw).text

    def get_json(self, url: str, **kw: Any) -> Any:
        return self.get(url, **kw).json()

    def close(self) -> None:
        self.client.close()
