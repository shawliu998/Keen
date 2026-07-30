import { describe, expect, it } from "vitest";
import {
  matchProviderPreset,
  providerMaturityLabel,
  providerPreset,
  providerPresets,
} from "../src/features/settings/providerCatalog";

describe("provider catalog", () => {
  it("offers the bounded release presets plus one custom API base", () => {
    expect(providerPresets.map((preset) => preset.id)).toEqual([
      "ollama",
      "openai",
      "deepseek",
      "anthropic",
      "gemini",
      "openrouter",
      "groq",
      "mistral",
      "xai",
      "qwen",
      "kimi",
      "custom",
    ]);
    expect(providerPresets.filter((preset) => preset.id !== "custom").every(
      (preset) => Boolean(preset.endpoint && preset.suggestedModel && preset.description),
    )).toBe(true);
  });

  it("distinguishes compatibility mappings from built-in transports", () => {
    expect(providerMaturityLabel(providerPreset("openai").maturity))
      .toBe("Built-in transport");
    expect(providerMaturityLabel(providerPreset("deepseek").maturity))
      .toBe("Compatible preset");
    expect(providerMaturityLabel(providerPreset("gemini").maturity))
      .toBe("Compatibility preview");
    expect(providerMaturityLabel(providerPreset("custom").maturity))
      .toBe("Advanced");
  });

  it("restores a saved preset from its transport and canonical API base", () => {
    expect(matchProviderPreset("openai-compatible", "https://api.deepseek.com/"))
      .toBe("deepseek");
    expect(matchProviderPreset(
      "openai-compatible",
      "https://generativelanguage.googleapis.com/v1beta/openai/",
    )).toBe("gemini");
    expect(matchProviderPreset(
      "openai-compatible",
      "https://gateway.example.com/v2",
    )).toBe("custom");
    expect(matchProviderPreset("ollama", "http://127.0.0.1:11434/"))
      .toBe("ollama");
  });
});
