---
name: Caramcita
description: A Nordic daily's fact-box page for houses to rent around Alta Gracia
colors:
  paper: "#ffffff"
  ink: "#111111"
  ink-2: "#5c5c5c"
  hair: "#d6d6d6"
  rule: "#111111"
  signal: "#1f45d6"
  signal-ink: "#ffffff"
  plate: "#efefef"
  paper-dark: "#121212"
  ink-dark: "#f1f1f1"
  ink-2-dark: "#a3a3a3"
  hair-dark: "#2e2e2e"
  rule-dark: "#f1f1f1"
  signal-dark: "#8ea2ff"
  signal-ink-dark: "#121212"
  plate-dark: "#1f1f1f"
typography:
  headline:
    fontFamily: "Schibsted Grotesk, Helvetica Neue, Helvetica, Arial, sans-serif"
    fontSize: "clamp(22px, 2.4vw, 30px)"
    fontWeight: 700
    lineHeight: 1.12
    letterSpacing: "-0.018em"
  title:
    fontSize: "22px"
    fontWeight: 800
    letterSpacing: "-0.02em"
  section:
    fontSize: "15px"
    fontWeight: 700
    letterSpacing: "0.02em"
  body:
    fontFamily: "Schibsted Grotesk, Helvetica Neue, Helvetica, Arial, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.5
  facts:
    fontSize: "16px"
    lineHeight: 1.35
  small:
    fontSize: "14px"
  label:
    fontSize: "13px"
rounded:
  none: "0"
spacing:
  xs: "6px"
  sm: "10px"
  md: "14px"
  lg: "18px"
  xl: "26px"
  gutter: "32px"
  section: "48px"
  footer: "64px"
  tail: "96px"
components:
  masthead-name:
    textColor: "{colors.ink}"
    typography: "{typography.title}"
  section-head:
    textColor: "{colors.ink}"
    typography: "{typography.section}"
  entry-headline:
    textColor: "{colors.ink}"
    typography: "{typography.headline}"
  mark:
    textColor: "{colors.signal}"
    typography: "{typography.headline}"
  meta-link:
    textColor: "{colors.ink-2}"
    typography: "{typography.label}"
  meta-link-hover:
    textColor: "{colors.signal}"
  plate:
    backgroundColor: "{colors.plate}"
    rounded: "{rounded.none}"
    width: "220px"
  checkbox:
    backgroundColor: "{colors.paper}"
    rounded: "{rounded.none}"
    size: "14px"
  checkbox-checked:
    backgroundColor: "{colors.ink}"
---

# Design System: Caramcita

## Overview

**Creative North Star: "The Faktaruta Front Page"**

A Nordic daily's front page reduced to its fact boxes: every house is a headline plus a ruled strip of facts. The page is hairline rules and one grotesk; it refuses the photo-card grid with coloured badges. Two grounds only, white or near-black; one signal colour, cobalt, for what is new and for hover; everything else is ink at two strengths. State is typographic (weight, rule, strike, colour on a word), never a pill, icon or shadow.

**Key Characteristics:**
- Hairline rules do all the structure; no boxes.
- One face, Schibsted Grotesk; rank by weight before size.
- Cobalt is a word, not a surface.
- Grey (`ink-2`) means lower rank, never disabled.

## Colors

Black on white with one cobalt signal; dark mirrors it, signal lifted to periwinkle.

### Primary
- **Cobalt Signal** (`signal`): the "Nueva"/"Volvió" mark, new count, "Guardada", hover, focus ring, selection. Never a fill.

### Neutral
- **Paper** (`paper`): the only ground. No cream, no tint.
- **Ink** (`ink`): headlines, body, price, section heads, checkbox fill.
- **Ink 2** (`ink-2`): edition, intro, notes, day labels, address, description, meta, footer, dim ledger cells, gone headlines.
- **Rule** (`rule`): 1px full-strength line under the masthead, above sections, under the ledger header, above the footer.
- **Hair** (`hair`): 1px between entries, rack columns, ledger rows, manual items, facts.
- **Plate** (`plate`): ground behind a missing photo.

### Named Rules
**The One Signal Rule.** Cobalt appears on words and rings only. A second hue is a defect.

## Typography

**Only face:** Schibsted Grotesk (Helvetica fallback), 400/700/800, Google Fonts. Kerning on; tabular figures on counts.

### Hierarchy
- **Headline** (700, clamp 22-30px, 1.12, -0.018em, balanced, 26ch): entry titles. Rack 24px; compact 22px; lone entry clamp 26-32px.
- **Title** (800, 22px, -0.02em): masthead name.
- **Section** (700, 15px, +0.02em): section heads.
- **Body** (400, 16px, 1.5, 64ch): intro, empty states.
- **Facts** (16px, 1.35; 15px in rack, compact, mobile): price 700 (18px in rack), bedrooms, locality, agency.
- **Small** (14px): edition, controls, notes, day labels, address, ledger, hidden-reveal line.
- **Label** (13px): meta line, footer.

### Named Rules
**The Weight Before Size Rule.** Inside a line, rank is weight (price 700, rest 400); size steps separate headline, facts and meta.

## Layout

Container 1120px, side padding `clamp(16px, 4vw, 40px)`, 96px tail. Masthead: three-column baseline grid (name / edition / counts) over a rule; below 720px the edition drops to a second row.

Sections open with 48px (40px mobile) and a rule; a day label sits 26px below over a hairline. Up to 899px an entry is text left, 220px plate right, 32px gutter. From 900px the rack is three columns with hairline column borders, plate above headline (4:3), meta pinned to the module foot; a rack with one entry goes full width, plate at one third right. Compact entries: 120px square plate, 18px padding; mobile plates 104px/72px. Rhythm 6/10/14/18/26/32px inside modules, 48/64px between sections.

## Elevation & Depth

Flat. No shadows, no tonal layering; one plane, two line strengths. The plate is the only surface, a flat grey; photos desaturated 8%.

**The Two Rules Rule.** Full-ink rule for section boundaries, hairline for everything inside.

## Shapes

Square everywhere: radius 0 on plates, images, checkboxes; only the focus ring carries 1px. Checkbox: 14px ink-bordered square, filled ink with a 3px paper inset when checked. Underlines 1px at 0.18em offset; headline links bare until hover.

## Components

### Masthead
Name left, "Edición del ..." (Small, `ink-2`) centre, counts right with the new count in signal 700; full rule beneath.

### Controls line
Two checkbox labels left, RSS/JSON text links right in `ink-2`, 22px gaps, Small.

### Section rule
Full rule, 10px, head left, note (Small, `ink-2`) right; stacked on mobile.

### Entry / rack
Headline; facts strip with hairline separators; optional address and two-line description in `ink-2`; meta (Label) with date, source links, and "Guardar" / "Ocultar" as underlined text buttons pushed right. Plate 4:3 or square, "sin foto" when missing.
- **Nueva / Volvió:** the word in signal 700 before the headline.
- **Gone:** headline `ink-2`, 1px line-through; meta reads "Se fue el".
- **Price change:** previous price after the current, 400, `ink-2`, struck.
- **Starred:** button reads "Guardada" in signal 700.
- **Hidden:** removed from flow; "Mostrar ocultas" reveals one Small `ink-2` line with "Mostrar".
- **Hover / Focus:** signal; 2px signal outline, 3px offset; 0.25s opacity fade when motion is allowed.

### Ledger (Fuentes)
Table at Small: header 700 over a full rule, rows over hairlines, tabular counts right, broken sources 700, the rest `ink-2`.

### Manual list and footer
Two-column list (one on mobile), hairline under each item, bare links. Footer: 64px above, full rule, Label in `ink-2`.

## Do's and Don'ts

### Do:
- **Do** express every state with weight, a rule, a strike, or the signal on a word.
- **Do** keep two line strengths and radius 0.
- **Do** keep `ink-2` text at or above 4.5:1 in both themes.

### Don't:
- **Don't** add cards, boxes or shadows.
- **Don't** add pills, badges, chips or filled buttons.
- **Don't** add icons; controls are words.
- **Don't** introduce a second colour or a cream ground.
- **Don't** add a second typeface.
