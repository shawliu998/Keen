# Keen 0.1.0 Alpha RC

Status: **verified local Alpha candidate** on 2026-07-22. This is an ad-hoc macOS build for local testing, not a signed or notarized public release.

## Product baseline

The candidate keeps the current Keen product boundary: local source import and indexing, source-scoped Ask with durable conversations and citations, focused Study Sessions, deterministic Recall and Practice, bounded adaptive remediation, FSRS Review, Learning Feed, History, and restart recovery. It adds no new navigation, integration, model capability, or visual direction.

Product implementation is anchored by commit `2bc2df3`. Packaging closeout is recorded by `aec9915` and `8c251b6`.

## Local artifacts

| Artifact | Path | SHA-256 |
| --- | --- | --- |
| ad-hoc app executable | `apps/desktop/src-tauri/target/release/bundle/macos/Keen.app/Contents/MacOS/keen-desktop` | `0ca318c0eb84b892863935ba2cf2ecca7aa574862f7bbce11dd03bedb94cd147` |
| bundled learning core | `apps/desktop/src-tauri/target/release/bundle/macos/Keen.app/Contents/MacOS/keen-learning-core` | `aac42c75b95b20a580e065065225123985247d7cfc3c0eeb45f36da7ab0488a7` |
| unsigned DMG | `apps/desktop/src-tauri/target/release/bundle/dmg/Keen_0.1.0_aarch64.dmg` | `c6b479f2d9cd8ca2fb9a73349da687c57a87e9618f39dac40a443fc19217696b` |

The standard packaging workflow freezes migrations `001`–`030`, verifies the mounted DMG, and leaves both the DMG and standalone app available. Deep/strict ad-hoc signature checks, the bundled-sidecar smoke, and the Review restart/replay/FSRS smoke passed for both mounted and standalone app copies.

## Acceptance result

- A fresh production-identity launch exposed one pre-existing, day-old development sidecar that still owned the production database lock without a Tauri parent. Only that confirmed orphan was terminated normally; no database, lock file, or user document was removed. The RC recovered through its visible Retry action.
- The repository-local app then reached `Learning core ready`, quit through Command-Q, released its lock and both app/sidecar processes, restarted to ready, and exited cleanly again.
- The DMG was mounted read-only, its `Keen.app` was copied to a temporary installation directory, deep signature verification passed, and the copied app reached ready and exited without a residual process or lock holder.
- The current focused backend matrix covering import, durable Conversation, focused Study, Recall, adaptive remediation, Practice, Summary, Review and recovery passed across eight test files. The corresponding six desktop workflow files passed **124/124** tests.
- The lightweight Home continuity projection passed 5 focused desktop files / **140/140** tests. A freshly rebuilt packaged UI-audit app restored an existing persisted Alpha Bayesian task/session, its exact learner goal and `Finish summary` action across a full restart, then opened the exact course-scoped Deep Learn route. This check created no replacement data.
- A read-only copy of the isolated Dev database retained one indexed source, two real `openai-compatible` completed assistant messages, two citations, one answered Recall, one answered Practice, one Review attempt, and one completed Study Task. The real DeepSeek call was not repeated because only packaging scripts changed after the already-recorded provider acceptance.

No scoped P0 or P1 remains open from this closeout.

## Known limits

- There is no Apple Developer ID, hardened-runtime release identity, notarization, or public distribution claim. Another Mac may present Gatekeeper friction for this local build.
- The configured DeepSeek gateway is an external loopback adapter. Its selected credential file is mode `0600` plaintext rather than Keychain-backed.
- Retrieval remains lexical-only when no embedding provider is configured.
- Calendar, Drive, Canvas and other external writes remain unavailable.
- Packaged Dark mode, reduced-motion-on, long-content capture, complete keyboard/accessibility coverage, accepted references, and pixel parity remain unverified.
- Visual research, Figma exports, screenshots and tooling output remain outside the product commits and were not cleaned or promoted during this closeout.

## Alpha feedback focus

Use this candidate to evaluate whether the core sequence feels coherent: add material, ask or start focused study, complete Recall/Practice, review the scheduled item, and resume from Feed or History after restart. New platform features are intentionally deferred until this flow receives real usage feedback.
