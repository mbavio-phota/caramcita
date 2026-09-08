# Product

Caramcita is a personal, fully automated watcher for houses for annual rent in Alta Gracia (Córdoba, Argentina) and four neighbouring localities. It scrapes portals and local agencies every six hours, keeps state between runs, and publishes a Spanish-language "diario" (a daily edition, web page) plus Telegram alerts. The user's only job is to open the page or read the message.

## Platform

web

## Stack

Python 3.12, Jinja2 templates rendered by GitHub Actions into a static site (`docs/`) served by GitHub Pages at https://mbavio-phota.github.io/caramcita/. Single HTML file with inline CSS and vanilla JS; no build step, no framework. Fonts may be loaded from Google Fonts. Decided during the build session on 2026-09-08 (user delegated stack choice).

## Users

One user: the owner, who is looking for a house to rent for their family and reads the page on both phone and laptop, equally (confirmed 2026-09-08). Reading register is Spanish (Argentina). They are technical but want zero upkeep.

## Product Purpose

Tell the reader in seconds whether a new house that meets the minimum requirements (3+ bedrooms, in the zone, annual rent, house not apartment) appeared since they last looked, and keep the full current catalogue one scroll away.

## Positioning

Not a portal and not a search engine: a personal edition compiled from 17 sources, deduplicated, with the noise already removed. Competitors are the portals themselves (Zonaprop, MercadoLibre, La Voz) and their email alerts, which the user finds noisy and incomplete.

## Operating Context

Read mode. The page is regenerated four times a day; the user opens it from a bookmark or from a Telegram link, typically once a day, and scans "what is new" first. Photos come hotlinked from the sources and may be missing. Listings are few (10–30 active at any time), so density is low and each entry deserves room.

## Capabilities and Constraints

- Static HTML only; interactivity limited to per-browser localStorage (hide, star) and native links.
- Sections that must exist: Novedades (by day, last 7 days), Todas las vigentes, Ubicación sin confirmar, Dormitorios sin dato, Ya no disponibles, Estado de las fuentes, También revisar a mano. Content of each is fixed by the pipeline; visual treatment is free (confirmed 2026-09-08: "only the content and sections must stay").
- Every listing card carries: title, price with currency, bedroom count, locality, agency, source links, first-seen time, optional address/description, badges (Nuevo, Ya no disponible, Volvió, price up/down), and the hide/star controls.
- RSS and JSON links must remain reachable.
- Must render in light and dark (system preference) and on 390px and 1440px viewports.

## Brand Commitments

- Visual direction pinned by the user (2026-09-08): minimal, typographic, Scandinavian; the reference is the Nordic daily newspaper (Aftenposten / Politiken register): grotesk headlines, hairline rules, tabular facts, black on white, one signal colour.
- All copy in Spanish (Argentina). Name: "Caramcita".
- Explicit anti-goal: must not read as generic AI-generated UI (the user's words: "less like AI slop").

## Evidence on Hand

- Real listing data in `state.json` and `docs/data.json` (titles, prices, localities, photos).
- Source list and health in `sources.yaml` / `state.json`.

## Product Principles

- News first: the first viewport answers "anything new?".
- Facts over decoration: price, bedrooms, locality are the content; the page is typography.
- Nothing silently dropped: uncertain listings are shown in their own sections.
- Zero upkeep: no controls that need maintenance; no interaction that needs a backend.

## Accessibility & Inclusion

Body text ≥ 4.5:1 contrast in both themes; keyboard-reachable controls with visible focus; images have empty alt (decorative, the title carries meaning); no motion required to read; respects prefers-color-scheme and prefers-reduced-motion.
