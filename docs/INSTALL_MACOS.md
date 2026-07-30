# Install Keen on macOS

## Current build boundary

The current release candidate is an Apple Silicon (`arm64`) local Alpha. It is
ad-hoc signed for local verification, but it is not Developer ID signed or
notarized. It is therefore suitable for the project owner and trusted testers,
not frictionless public distribution.

## Install the local Alpha

1. Open `Keen_0.1.0_aarch64.dmg`.
2. Drag `Keen.app` to Applications.
3. Open Keen.
4. If macOS blocks this ad-hoc build, Control-click Keen and choose **Open**.
   If macOS still blocks it, use **System Settings → Privacy & Security →
   Open Anyway** only when the DMG came directly from this repository's
   packaging output and its checksum matches the release record.

Do not disable Gatekeeper globally.

## Connect a model

1. Open **Settings → Model**.
2. Choose Ollama, OpenAI, or one of the compatible API presets.
3. Enter the exact model ID used by your account.
4. For a remote provider, enter its API key.
5. Choose **Save and verify**.

Keen reports three separate outcomes:

- the non-secret provider configuration and Keychain entry were saved;
- the local learning service restarted with that configuration;
- the restarted service could access the selected model.

Remote API keys are stored in macOS Keychain. They are not written to the
provider configuration JSON, SQLite, command-line arguments, logs, or this
repository.

The catalog includes Ollama, OpenAI, DeepSeek, Anthropic Claude, Google
Gemini, OpenRouter, Groq, Mistral, xAI, Qwen, and Kimi. Compatible presets
prefill a known API base; they are not a claim that every provider, account,
region, or model has been live-certified. Choose **Custom API base** for
another OpenAI-compatible service and enter its API base rather than a final
`/chat/completions` URL.

## First learning journey

1. Open **Knowledge Base** and create a course.
2. Import a PDF, Markdown, or text source and wait until indexing completes.
3. Choose **New learning**.
4. Select the course material, enter a focused learning goal, and start Study.
5. Complete the visible lesson and Recall step.
6. Return later through **Learning Feed** or **History**.

Keen stores the learning session locally and restores the current path after
the app and learning service restart.

## If verification fails

- Confirm that the model ID exactly matches the provider account.
- Re-enter the API key if the saved key belongs to another account or API
  origin.
- Check the selected preset or Custom API base.
- Retry after the provider or network recovers.
- If Settings reports that the learning service did not restart, use
  **Retry save and verify**. Keen does not treat saved settings as a verified
  model connection.

## Public distribution still requires

- Developer ID Application signing with hardened runtime;
- Apple notarization and stapling;
- clean-Mac installation and launch acceptance;
- a release decision for Intel/universal support and updates.
