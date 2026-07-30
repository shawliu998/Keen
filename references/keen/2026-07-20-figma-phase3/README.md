# Figma Phase 3: componentized Home

Date: 2026-07-20
Figma file: `Keen Desktop UI — HyperKnow Layout Study` (`ugwiIPdF43v2woYsLM3b9R`)
Editable file: <https://www.figma.com/design/ugwiIPdF43v2woYsLM3b9R>

## Scope

This is a Figma-only reconstruction of Keen's Home screen. It reconciles the current React state model, deterministic Browser Demo fixtures, existing design tokens/components, the user-selected light macOS direction, and the authorized HyperKnow layout evidence. It does not change the React/Tauri/FastAPI/SQLite runtime.

The data and capability contract is recorded in `docs/figma/HOME_DATA_MAPPING.md`.

## Figma nodes

| Purpose | Node |
| --- | --- |
| Home Screen page | `113:2` |
| Default Browser Demo | `113:3` |
| Offline local service | `130:52` |
| Provider not configured | `131:195` |
| Queue Row page | `120:58` |
| Queue Row component set | `121:26` |
| Queue Row: Default / Hover / Focus | `121:2`, `121:10`, `121:18` |
| Body Emphasis text style | `S:24d5afd6c525d7af69b862356f7596b55552e02f,` |

The screen reuses local Nav Row `80:56`, Badge `52:12`, Button `33:2`, and the existing Keen/Lucide-aligned icon components. Progress is intentionally absent from Home because the current Home task records do not provide actual task progress.

## Truthful states

- Default shows the three exact deterministic Browser Demo tasks and labels each row `sample`. No provider or local service is represented as contacted.
- Offline says that the learning core is not connected and that no sample tasks were substituted. The empty queue is not replaced by plausible-looking data.
- Provider missing keeps the local service `Ready` state separate from the unavailable model provider. It states that no run was created and no learning data changed.
- The empty composer uses a disabled Continue action. No model reply, citation, mastery score, review plan, calendar write, Drive/Canvas connection, or document-processing success is shown.

## Captures

- `home-default-final.png` — default Browser Demo, 1585×907
- `home-offline.png` — learning-core offline, 1585×907
- `home-provider-missing.png` — local service ready, provider not configured, 1585×907
- `queue-row-component.png` — Queue Row variant set
- `home-raw-current.png` — earlier raw current-product frame used for structural comparison

`home-componentized-v1.png` through `home-componentized-v4.png` are intermediate repair evidence, not final reference candidates.

## Validation

Final Plugin API inspection of nodes `113:3`, `130:52`, and `131:195` found:

- all frames are 1585×907;
- all visible text uses SF Pro and has positive geometry;
- no temporary lorem or shimmer artifact remains; the visible input hint is intentional product copy;
- the default frame contains 12 visible reusable instances; the two operational states contain seven after redundant status badges were removed;
- no frame contains `Completed`, provider-success, fabricated response, or fabricated citation copy;
- the offline and provider-missing disclosures are present in their corresponding frames.

The final screenshots were visually inspected after export. The status-only frames deliberately use plain disclosure copy instead of stacked badges.

The canonical PNGs were refreshed after the follow-up screenshot audit under `../2026-07-20-figma-phase3-screenshot-audit/` removed measured clipping, a stale default footer label, detached disclosure copy and unnecessary fixed panel height. The final Plugin API pass found zero visible text nodes outside clipping ancestors.

## Limitations

- These are fixed-viewport Figma designs, not accepted visual-regression baselines and not pixel-parity evidence.
- React implementation, runtime keyboard/accessibility testing, reduced-motion testing, dark mode, collapsed Sidebar, and 1180×740 / compact-window layouts remain pending.
- Figma's Plugin API returned unavailable/stale SF Pro glyph bounds when overriding nested instance text. Component masters remain reusable; screen compositions use explicit text overlays where they render reliably and remove redundant labels where they do not. This must be reconciled before a full component-library handoff.
- Code Connect could not be established because the current Figma account/tool context reported that the required Dev or Full seat on an Organization or Enterprise plan was unavailable.
- No visual mismatch percentage is reported because there is no approved, same-viewport accepted baseline.
