# Keen Figma Phase 1 foundations

Date: 2026-07-19

Figma file: `ugwiIPdF43v2woYsLM3b9R`

This directory records the Figma-only foundations reconciliation performed after
the authorized HyperKnow screen audit. It does not record a React implementation
or a visual-parity result.

## Verified objects

- Color foundation: page `16:4`
- Type foundation: page `16:5`
- Layout foundation: page `16:6`
- Repaired one-line Type eyebrow: node `76:2` (replaced malformed node `18:4`)
- Text styles: 9 Keen styles, all using verified local `SF Pro` styles
- Effect styles: 6 Keen light/dark card, menu and focus styles
- Variables: 54 primitives, 27 semantic colors, 8 spacing, 5 radius and 5 dimensions

The semantic alias validator returned no broken Light/Dark targets or duplicate
names. Numeric variables were checked against
`packages/design-tokens/src/tokens.css`. `warning-soft` remains a Figma-only
semantic token with no web code syntax because the CSS source has no equivalent.

## Captures

- `foundations-color.png`: 1440 × 1800
- `foundations-type.png`: 1440 × 1263
- `foundations-layout.png`: 1440 × 1592

The three PNGs were exported from the corresponding Figma pages after the SF Pro
migration. Visual review checked text wrapping, clipping, overlap, padding,
border/radius consistency and inherited component typography. The first Type
render exposed a wrapped eyebrow; the retained capture is the corrected render.

## Evidence limits

- No React, Tauri, FastAPI, SQLite, authentication or local-service behavior was
  changed or validated in this phase.
- Component geometry, interaction variants, motion, responsive desktop behavior,
  keyboard behavior and reduced-motion behavior remain later work.
- The captures are documentation renders, not accepted visual-regression
  baselines. No mismatch percentage or pixel-parity claim is made.
