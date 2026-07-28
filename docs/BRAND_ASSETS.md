# Keen brand assets

This file is the canonical asset map for the current Keen identity.

## Current masters

| Use | Canonical source | Status |
| --- | --- | --- |
| Product mark on light surfaces | `apps/desktop/public/brand/keen-mark.svg` | Current; flat three-path mark selected on 2026-07-23 |
| Product mark on dark surfaces | `apps/desktop/public/brand/keen-mark-reverse.svg` | Current reverse variant |
| Keen wordmark on light surfaces | `apps/desktop/public/brand/keen-wordmark.svg` | Current; unchanged by the 2026-07-23 icon selection |
| Keen wordmark on dark surfaces | `apps/desktop/public/brand/keen-wordmark-reverse.svg` | Current reverse variant |
| Packaged application icon | `apps/desktop/src-tauri/icons/icon.svg` | Current; derived from the canonical product mark |

Canonical colours are dark `#161E25`, teal `#11ADA2`, light icon field `#F7F8FA`, and white `#FFFFFF` for reverse artwork.

## Usage rules

- Use `keen-mark.svg` for the Sidebar, browser favicon, product identity, and any new light-surface placement.
- Use `keen-wordmark.svg` only when the name “Keen” must be shown. The wordmark is separate from the product mark and was not redesigned during the icon selection.
- Treat `apps/desktop/src-tauri/icons/icon.svg` as the only source for generated application icons. Regenerate platform outputs with:

  ```sh
  npm run tauri -- icon src-tauri/icons/icon.svg
  ```

  Run the command from `apps/desktop`.
- Do not edit generated PNG, ICNS, or ICO files by hand.
- Do not use historical screenshots, Figma cover artwork, `dist/` output, packaged `.app` resources, or generated platform images as masters.
- The retired low-resolution raster mark and the provisional line-art `K` application icon are not current Keen branding.

The current SVGs are implementation artwork derived from user-supplied references. They are not represented as original vector masters or pixel-identical reconstructions.
