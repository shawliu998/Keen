import { describe, expect, it } from "vitest";
import {
  providerRequiresRemoteApiKey,
  savedApiKeyAppliesToDraft,
  type ProviderConfiguration,
} from "../src/features/settings/providerConfiguration";

const savedRemoteProvider: ProviderConfiguration = {
  configured: true,
  provider: "openai-compatible",
  endpoint: "https://api.example.com/v1",
  model: "fixture-model",
  apiKeyConfigured: true,
};

describe("provider configuration key scope", () => {
  it("reuses a saved key only for the same canonical HTTPS origin", () => {
    expect(
      savedApiKeyAppliesToDraft(
        savedRemoteProvider,
        "openai-compatible",
        "https://api.example.com:443/another-path",
      ),
    ).toBe(true);
    expect(
      savedApiKeyAppliesToDraft(
        savedRemoteProvider,
        "openai-compatible",
        "https://other.example.com/v1",
      ),
    ).toBe(false);
  });

  it("does not require or reuse remote keys for loopback providers", () => {
    expect(
      providerRequiresRemoteApiKey(
        "openai-compatible",
        "http://[::1]:11434/v1",
      ),
    ).toBe(false);
    expect(
      savedApiKeyAppliesToDraft(
        savedRemoteProvider,
        "ollama",
        "http://127.0.0.1:11434",
      ),
    ).toBe(false);
  });
});
