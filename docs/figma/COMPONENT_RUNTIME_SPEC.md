# Keen shared component runtime specification

This document records the implemented React/CSS component contract. Runtime state and data remain authoritative over Figma specimens and reference-product screenshots.

## Shared foundations

| Element | Implemented value | Rule |
| --- | --- | --- |
| Product font | macOS system stack / SF Pro where available | One UI family; no display font for controls |
| Medium control | 34 px minimum height | Default desktop Button and compact workflow actions |
| Small control | 30 px minimum height | Dense secondary actions only |
| Control radius | 8 px | Button, IconButton and form controls |
| Badge | 22 px minimum height, 11 px text | Informational status only; never a substitute for an action |
| Fast motion | 140 ms | Hover, focus-adjacent and pressed state transitions |
| Standard motion | 220 ms | Measurable progress/state movement |
| Focus | shared `--focus-ring` | Keyboard focus is never removed without a visible replacement |

Semantic colors come from `packages/design-tokens/src/tokens.css`. Accent is reserved for primary/current state; success, warning and danger use their matching `*-soft` surfaces. Light and dark themes share the same semantic roles.

## Button

`Button` supports `secondary`, `primary`, `danger` and `ghost` variants; `small` and `medium` sizes; and a real `loading` state. Loading sets `aria-busy`, disables repeat activation and adds a CSS spinner without replacing the visible action label. Existing `className="primary"` and `className="danger"` calls remain compatible while feature code migrates incrementally.

Required visual states:

- default: stable border and surface;
- hover: surface or semantic soft-color change;
- focus: shared focus ring;
- active: one-pixel pressed translation;
- disabled: non-interactive cursor and 48% opacity;
- loading: disabled, `aria-busy=true`, motion reduced by the global reduced-motion rule;
- error/success: expressed by surrounding validated state, not by silently recoloring an unchanged action.

## IconButton

IconButton is 32×32 px, uses Lucide children, always requires an accessible `label`, and defaults to `type="button"` so toolbar actions cannot accidentally submit a surrounding form. Hover, focus, active and disabled behavior matches Button.

## Badge

Badge supports neutral, accent, success, warning and danger tones. It is non-interactive and may receive ordinary span/ARIA attributes. Badge copy must describe a supplied state such as `Browser Demo`, `Not implemented`, or a validated runtime status; it must not imply provider, OAuth, indexing or task success without matching runtime evidence.

## Form controls

Inputs, textareas and selects use a 36 px minimum height, 8 px radius, tokenized border/surface colors and the shared focus ring. Hover strengthens the border; disabled controls use the secondary surface and remain readable. Placeholders use `--text-secondary` at full opacity to retain legibility.

## Progress

Progress clamps values to 0–100, exposes a labelled `progressbar`, and animates the fill with `transform: scaleX()` rather than layout width. Reduced-motion mode makes the update effectively immediate.

## Evidence boundary

The matching Figma component sets remain design intent, not accepted product baselines. Runtime screenshots must use a fixed route, state, viewport and seed before a mismatch percentage can be treated as visual-regression evidence.
