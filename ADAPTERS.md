# Cómo escribir un adaptador de fuente

Cada fuente es un módulo en `caramcita/sources/<adapter>.py` que expone una clase `Adapter(Source)`.
Se instancia desde `sources.yaml` como `Adapter(slug=..., name=..., **params)` y debe implementar:

```python
from ..http import Http
from ..models import Listing
from .base import Source, parse_price, text_of

class Adapter(Source):
    def fetch(self, http: Http) -> list[Listing]:
        ...
```

Reglas:

- Usar **sólo** `http.get(url)` / `http.get_text(url)` / `http.get_json(url)` (ya tienen user-agent de
  navegador, pausa entre pedidos y reintentos). No crear clientes propios.
- Devolver un `Listing` por aviso con `self.listing(source_id=..., url=..., title=..., ...)`
  (`self.listing` completa `source` y `agency`). Campos:
  - `source_id`: id estable dentro de la fuente (id numérico, slug de la URL, etc.). Nunca el índice.
  - `url`: absoluta.
  - `title`, `description`: texto plano (sin HTML). Descripción completa si está en el listado; no hace
    falta entrar al detalle salvo que el listado no traiga dormitorios ni localidad.
  - `price`, `currency`: usar `parse_price(texto)` → `(float|None, "ARS"|"USD"|None)`.
  - `locality`: la localidad tal como la da la fuente (campo estructurado si existe; si no, vacío).
    NO adivinar desde el texto: el clasificador ya lo hace.
  - `address`: dirección/barrio si existe.
  - `bedrooms`: entero si la fuente lo da como dato estructurado; si no, `None` (el clasificador lo
    saca del texto).
  - `property_type`: tal como lo da la fuente ("Casa", "Departamento", ...). Vacío si no hay.
  - `operation`: tal como lo da la fuente ("Alquiler", "Alquiler temporario", "Venta"). Vacío si no hay.
  - `images`: URLs absolutas; primera = foto principal.
  - `lat`, `lng` si están.
  - `extra`: dict con lo que sobre (m², baños, cochera, código de referencia...).
- Filtrar del lado del adaptador **sólo** lo que la fuente ya filtra por URL (p. ej. pedir sólo
  alquileres). Todo lo demás (localidad, dormitorios, tipo) lo decide `caramcita.classify`. Devolver
  departamentos o 2 dormitorios está bien: se descartan después. Pero si la fuente permite filtrar por
  operación=alquiler, hacerlo para no traer ventas.
- Paginar hasta el final (con un tope razonable, p. ej. 10 páginas).
- Ante un aviso que no se puede parsear, saltearlo con `log.warning`, nunca tirar la corrida.
- Sin sleeps propios ni threads.

Fixtures y tests:

- Guardar una respuesta real recortada (1–3 avisos, sin scripts pesados) en
  `tests/fixtures/<adapter>_<algo>.html|json` y escribir `tests/test_source_<adapter>.py` que parsee el
  fixture (monkeypatch/stub de `Http` con un objeto que tenga `get_text`/`get_json`) y verifique
  `source_id`, `url`, `title`, `price`, `currency`, `bedrooms`, `locality`, `images[0]`.
- Probar en vivo con `.venv/bin/caramcita probe <slug>`; tiene que listar avisos con su clasificación.

Plataformas compartidas: si el sitio es WordPress con tema Houzez/RealHomes o un CPT `property`,
Tokko Broker, Wasi, etc., escribir un adaptador genérico parametrizado por `base` (y lo que haga falta)
para que la próxima inmobiliaria sea una línea en `sources.yaml`.
