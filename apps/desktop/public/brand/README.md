# Keen browser brand assets

The repository-wide canonical asset map is `docs/BRAND_ASSETS.md`. The files in this directory are the current browser/UI masters, not alternatives to that map.

These transparent SVGs were derived from the two raster references supplied by the user on 2026-07-19. The wordmark remains vector-traced; the selected flat mark was redrawn as three clean paths on 2026-07-23:

- `keen-mark.svg`: two-colour Keen mark for light surfaces.
- `keen-mark-reverse.svg`: white-and-teal mark for dark surfaces.
- `keen-wordmark.svg`: dark Keen wordmark for light surfaces.
- `keen-wordmark-reverse.svg`: white Keen wordmark for dark surfaces.

Canonical colours are dark `#161E25`, teal `#11ADA2`, and white `#FFFFFF` for reverse variants. The original 204×228 mark and 386×178 wordmark references were background-separated and reduced to stable brand colours with VTracer 0.6.5; the current mark was subsequently redrawn as three clean paths. The current SVG files have tight transparent view boxes and contain paths only; they do not embed the source screenshots.

These are implementation assets, not an original vector master. Their silhouettes were checked at small UI sizes and on light/dark surfaces, but they must not be described as pixel-identical to an unavailable master.

On 2026-07-23 the user selected this flat mark as Keen's product icon direction. The mark was redrawn as a clean three-path SVG before the matching silhouette was applied to the generated Tauri platform icon set from `apps/desktop/src-tauri/icons/icon.svg`; this records the chosen identity but does not turn the implementation asset into an original master or establish a packaged visual-verification result.

The former `keen-icon.png` low-resolution raster is retired and intentionally absent. Do not recreate or use it as a source.
