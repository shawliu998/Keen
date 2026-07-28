# Keen Figma component checkpoint

Date: 2026-07-19
Figma file: `ugwiIPdF43v2woYsLM3b9R`
Run ID: `keen-hyperknow-v1-20260719`

## Button

- Page: `30:2` (`05.01 · Button`)
- Component set: `33:2`
- Variants: 18 = 3 styles × 6 states
- Styles: Primary, Secondary, Ghost
- States: Default, Hover, Focus, Active, Disabled, Loading
- Editable text property: `Label#33:0`, wired to 15 non-loading variants
- Loading copy: fixed `Working…` on three variants
- Geometry: every variant is 96×36 px
- Token checks: sampled variants retain semantic fill/stroke bindings plus
  bound 36 px height, 8 px radius, 12 px horizontal padding, and 8 px gap
- Structure checks: no duplicate variant names and no unnamed descendants
- Responsive label constraint: all 18 label layers stretch and center inside
  wider instances while the 96×36 default variants remain unchanged in size

`button.png` is a direct Figma render of the complete Button page after visual
inspection and repair of light-mode paint fallbacks. It verifies the Figma
artifact only.

`button-responsive-labels.png` is the same-size render after enabling stretched
instance labels. ImageMagick reported 7,185 changed pixels (0.697%) against
`button.png`; `button-responsive-labels-diff.png` retains the diff image. The
new render was visually inspected and keeps all 18 variants legible. This is a
local regression comparison, not an accepted Keen product baseline.

## IconButton

- Page: `38:2` (`05.02 · IconButton`)
- Component set: `45:30`
- States: Default, Hover, Focus, Active, Disabled, Loading
- Instance-swap property: `Icon#46:0` on the five non-loading variants
- Geometry: 32×32 px, 16 px nested icon, 8 px radius
- Internal icon sources: local wrappers around Simple Design System Plus and
  Refresh library instances; the library is identified by Figma as CC BY 4.0
- Runtime boundary: React requires an accessible `label`, has no Loading API,
  and continues to render the existing Lucide icon children

`icon-button.png` is the inspected direct Figma render. The Simple Design
System instances are design-file references only; no upstream source code or
distributed production asset was copied into Keen.

## Badge

- Page: `51:5` (`05.03 · Badge`)
- Component set: `52:12`
- Tones: Neutral, Accent, Success, Warning, Danger
- Editable text property: `Label#52:5`
- Geometry: 22 px height, 8 px horizontal padding, pill radius
- Token addition: `light/warning-soft`, `dark/warning-soft`, and semantic
  `color/warning-soft`
- Runtime boundary: mirrors the React `Badge` tone union and content; it is
  informational, so no hover, focus, active, disabled or loading state exists

`badge.png` is the second direct render. The first render exposed wrapped spec
labels and a documentation-frame overflow; both were repaired before this file
was retained.

## Service Banner

- Page: `56:2` (`05.04 · Service Banner`)
- Component set: `59:32`
- States: Starting, Unavailable, Configuration error, Request error
- Editable properties: `Title#59:8` and `Message#59:9`
- Nested dependency: the three recovery states reuse the Secondary/Default
  Button component and preserve the current runtime action copy
- Starting has no retry action while startup is active
- Healthy is intentionally absent: current runtime uses compact
  `LearningCoreStatus` instead of a success banner
- Runtime boundary: this set specifies the existing `FeedServiceState` and
  related compositions; there is not yet a shared React `ServiceBanner` export

`service-banner.png` is the repaired direct render. Its first retained QA pass
showed three-line recovery labels; the Button label constraint was corrected
and the page was rendered again with single-line actions.

## Boundary

The React Button still exposes native button props and CSS class treatments;
it does not expose a verified Loading property. Runtime refresh CSS currently
uses 34 px button height and 14 px horizontal padding, so Figma/runtime geometry
is not yet synchronized. These captures do not validate runtime accessibility,
responsive behavior, motion, packaging, or product pixel parity. No accepted
Keen baseline exists for these component pages.
