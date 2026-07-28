# Keen Figma foundations checkpoint

Date: 2026-07-19
Figma file: `ugwiIPdF43v2woYsLM3b9R`
Run ID: `keen-hyperknow-v1-20260719`

## Verified foundation inventory

- Five Keen variable collections.
- 96 Keen variables: 52 color primitives, 26 Light/Dark semantic colors,
  eight spacing values, five radii, and five desktop dimensions.
- Validation returned zero missing Web code syntaxes, zero invalid scopes, and
  zero broken aliases.
- Nine text styles and six light/dark card, menu, and focus effect styles.
- Cover, Color, Type, and Layout documentation frames.
- User-provided Keen app icon and wordmark placed as source images on Cover.

## Typography decision

The first Figma screenshots exposed two separate rendering problems: generated
text nodes had zero-width geometry, and the server-side renderer did not render
the locally available `SF Pro` font. The final documentation nodes use explicit
text geometry and `Inter` as a shareable Figma rendering proxy. Keen production
code remains mapped to the macOS system/SF Pro font stack. This is a documented
design-tool constraint, not a runtime font change.

## Screenshot evidence

- `00-cover.png` — user-provided icon and wordmark on the Figma Cover.
- `01-color.png` — 26 semantic tokens shown in Light and Dark modes.
- `02-type.png` — nine text styles with UI and long-reading specimens.
- `03-layout.png` — spacing, radius, shell dimensions, viewport targets, and
  motion/reduced-motion guidance.

## Verified component work

The Button page now contains one component set (`33:2`) with 18 variants:
Primary, Secondary, and Ghost across Default, Hover, Focus, Active, Disabled,
and Loading. `Label#33:0` is wired to the 15 non-loading labels; the three
Loading variants keep the fixed `Working…` specification copy. Validation
returned 18/18 expected components, no duplicate variant names, no unnamed
descendants, consistent 96×36 geometry, and semantic bindings for the sampled
fill, stroke, spacing, radius, height, and focus treatments. The verified page
capture is `../figma-components/button.png`.

The current React `Button` still exposes native button props plus CSS classes.
The Figma Loading state is specification-only; it is not claimed as a working
runtime API. Figma uses a 36 px height and 12 px horizontal padding; the current
refresh CSS uses a 34 px override and 14 px padding. This remains a documented
sync gap, not a claimed implementation.

## Evidence boundary

These images verify the Figma artifacts only. They are not accepted
pixel-regression baselines and do not prove runtime accessibility, responsive
behavior, motion, packaging, HyperKnow parity, or implementation completion.
