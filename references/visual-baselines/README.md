# Keen-owned visual regression baselines

These files are Keen-owned regression inputs. They detect unintended changes
to the recorded Keen implementation; they are not Figma exports, a claim of
Figma pixel parity, or a comparison to any third-party product.

## Accepted 2026-07-21 baselines

| Baseline | Route and deterministic fixture | CSS viewport / capture scale | Motion | SHA-256 | Approved Figma design reference | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `keen-home-browser-demo-1180x740-reduced-motion.png` | `/?demo=true&visualTest=true`; Browser Demo July 2026 | 1180×740 CSS px; Playwright `deviceScaleFactor: 1`; PNG raster 1180×740 | `prefers-reduced-motion: reduce`; animations and transitions disabled by the harness | `d17f2d2f2459a70cff658c40f162cecc2107a46d6f07173f6b43853558cf95ec` | Home compact `155:187`, freshly exported to `../keen/2026-07-21-figma-baseline/home-approved-155-187-1180x740.png` | accepted Keen regression baseline |
| `keen-learning-feed-browser-demo-1180x740-reduced-motion.png` | `/feed?demo=true&visualTest=true`; Browser Demo July 2026 calendar fixed to July 19 | 1180×740 CSS px; Playwright `deviceScaleFactor: 1`; PNG raster 1180×740 | `prefers-reduced-motion: reduce`; animations and transitions disabled by the harness | `22bbd78a21d4cc7d585ac5c61636ed56ee633be08b21289761029e35df204c3b` | Learning Feed compact `164:179`, freshly exported to `../keen/2026-07-21-figma-baseline/learning-feed-approved-164-179-1180x740.png` | accepted Keen regression baseline |

The harness enforces this contract for both accepted entries. Its init script
records application `fetch`/XHR calls and the report records `browserRuntime`
only when neither Tauri marker is present; either a request or a Tauri marker
makes the baseline fail. Therefore Browser Demo makes no Tauri command,
learning-core, or provider request. The only separately observed network
traffic besides local Vite modules was an environment-injected Figma capture
helper, which is not application `fetch`/XHR traffic and is not part of the
screenshot state. Any raster dimension mismatch now also makes the harness
exit non-zero.

The current implementation was separately measured against its Approved Figma
design references with the same 1180×740 PNG dimensions. Those comparisons
remain explicitly provisional: Home `2.0290884104443423%`, Learning Feed
`1.5566880439761797%`. The recorded visual differences are product-adaptation
differences (notably the live shell/status treatment and calendar-day styling),
not a pass threshold. The Keen regression checks above use a strict `0%`
threshold and do not weaken those comparisons.

Knowledge Base, Conversation, Deep Learn, and every non-listed state remain
unapproved: their report entries stay `missing_reference` or `provisional`.
