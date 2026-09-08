# Caramcita

Buscador automático de **casas en alquiler anual con 3+ dormitorios** en Alta Gracia, Falda del Carmen,
Anisacate, Valle de Anisacate y Villa La Bolsa. Corre solo cada 6 horas en GitHub Actions, publica un
diario en HTML y avisa por Telegram cuando aparece algo nuevo.

- **Diario:** https://mbavio-phota.github.io/caramcita/ (también `feed.xml` y `data.json`)
- **Telegram:** un mensaje por casa nueva, resumen diario a las 08:00 y alerta si una fuente se rompe.

## Qué mira

Portales: Clasificados La Voz, MercadoLibre Inmuebles, Zonaprop (con navegador).
Inmobiliarias locales: Consulting, Guillermo Cortes, Invertir, Goya Tucci, Terra, Raíces, Facundo
Sánchez, Villa Los Aromos, Faretta, Fiornovelli, Lequio, Ruarte Moyano, Juárez Beltrán, Zarate & Medina
Díaz. La lista completa está en `sources.yaml`; las que no se pueden scrapear aparecen al pie del diario
para revisar a mano.

## Puesta en marcha (dos pasos manuales)

1. Crear el bot de Telegram: hablarle a [@BotFather](https://t.me/BotFather), `/newbot`, copiar el token.
2. Guardarlo como secreto del repo (pide el valor por consola, no queda en el historial):

   ```bash
   gh secret set TELEGRAM_BOT_TOKEN --repo mbavio-phota/caramcita
   ```

3. Mandarle cualquier mensaje al bot (por ejemplo "hola"). En la próxima corrida el sistema descubre
   el chat solo, lo guarda en `state.json` y responde "Caramcita conectado".

Nada más. La primera corrida es una línea base: registra todo lo publicado sin avisar; desde la segunda,
lo que aparece es "nuevo".

## Ajustar requisitos

Todo está en `config.yaml`: `min_bedrooms`, la lista de localidades con sus alias y barrios,
localidades vecinas excluidas, retención de avisos que desaparecen, hora del resumen. Para agregar una
inmobiliaria que use una plataforma conocida (WordPress Houzez/RealHomes, Tokko, Wasi) alcanza con una
entrada en `sources.yaml`; para una web a medida hay que escribir un adaptador (ver `ADAPTERS.md`).

## Correr a mano

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev,browser]" && .venv/bin/playwright install chromium
.venv/bin/caramcita probe lavoz            # prueba una fuente y muestra cómo se clasifica cada aviso
.venv/bin/caramcita run --dry-run --no-notify --no-images   # corrida completa sin guardar ni avisar
.venv/bin/caramcita render                 # regenera docs/ desde state.json
.venv/bin/pytest -q
```

En GitHub, la pestaña Actions permite lanzar una corrida a mano ("Run workflow"), opcionalmente sólo
para algunas fuentes.

## Zonaprop

Zonaprop está detrás de un challenge de Cloudflare y se scrapea con Playwright. Se intenta desde GitHub
Actions; si Cloudflare lo bloquea, el plan B es un job `launchd` en la Mac que sube un snapshot al repo
(ver `launchd/README.md`).

## Cómo funciona

`caramcita run` → cada adaptador en `caramcita/sources/` devuelve avisos crudos → `classify.py` decide
localidad, dormitorios, tipo y si es temporario → `state.py` compara con la corrida anterior (nuevos,
cambios de precio, desaparecidos) → `dedupe.py` une el mismo inmueble publicado en varias fuentes →
`report.py` genera `docs/` → `notify.py` avisa por Telegram. El estado vive en `state.json`, commiteado
por el propio workflow.
