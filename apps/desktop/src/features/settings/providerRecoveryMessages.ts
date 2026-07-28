import { LearningCoreResponseError } from "@keen/api-client";

export type ProviderSaveFailure = {
  outcome: "not_activated" | "saved_restart_failed" | "unknown";
  text: string;
};

const restartFailure = "Provider settings were saved, but Keen could not begin restarting the local learning service. The service may still be using its previous runtime configuration; retry from Settings after it recovers.";
const safeSaveFailures = new Set([
  "Choose Ollama or an OpenAI-compatible provider.",
  "Enter a valid provider endpoint without embedded credentials or query parameters.",
  "Enter a valid provider endpoint.",
  "Enter a valid provider endpoint without embedded credentials or fragments.",
  "Ollama must use an explicit loopback HTTP endpoint; remote OpenAI-compatible endpoints must use HTTPS.",
  "Enter a provider model name up to 256 characters.",
  "An API key is required for this remote OpenAI-compatible endpoint.",
  "Enter a valid API key.",
  "Keen could not access the macOS Keychain for this provider key.",
  "Keen could not access the macOS Keychain. Check Keychain access and try again.",
  "Keen could not save the API key in the macOS Keychain.",
  "Keen could not locate its private app data.",
  "Keen could not prepare the provider configuration location.",
  "Keen could not prepare private local storage for the provider configuration.",
  "Keen could not encode the provider configuration.",
  "Keen could not save the provider configuration.",
  "Keen could not protect the provider configuration.",
  "Keen could not finish saving the provider configuration.",
]);
const safeKeyNote = " The provider settings were not switched, but the API key may have been saved in macOS Keychain for this endpoint.";
const safeNoSwitchNote = " The provider settings were not switched.";

function containsControlCharacter(value: string): boolean {
  return Array.from(value).some((character) => {
    const codePoint = character.codePointAt(0) ?? 0;
    return codePoint < 32 || codePoint === 127;
  });
}

function errorText(error: unknown): string | null {
  const value = typeof error === "string"
    ? error
    : error instanceof Error ? error.message : null;
  if (!value || value.length > 1_000 || containsControlCharacter(value)) return null;
  return value.trim();
}

function approvedSaveFailure(value: string): string | null {
  if (safeSaveFailures.has(value)) return value;
  for (const suffix of [safeKeyNote, safeNoSwitchNote]) {
    if (!value.endsWith(suffix)) continue;
    const base = value.slice(0, -suffix.length);
    if (safeSaveFailures.has(base)) return value;
  }
  return null;
}

export function providerSaveFailure(error: unknown): ProviderSaveFailure {
  const value = errorText(error);
  if (value === restartFailure) {
    return {
      outcome: "saved_restart_failed",
      text: `${restartFailure} Your learning step remains saved.`,
    };
  }
  const approved = value ? approvedSaveFailure(value) : null;
  if (approved) {
    return {
      outcome: "not_activated",
      text: `${approved} New provider settings were not switched into use, and Keen did not begin a learning-core restart. Your learning step is unchanged; correct the issue and save again.`,
    };
  }
  return {
    outcome: "unknown",
    text: "Keen could not confirm that the provider settings were saved. No restart or connection is assumed. Your learning step is unchanged; review the fields and try again.",
  };
}

function learnerSafeDetail(value: string | null): string | null {
  if (!value || value.length > 1_000 || containsControlCharacter(value)) return null;
  const normalized = value.replace(/\s+/gu, " ").trim();
  if (
    !normalized
    || /\bBearer\s+\S+/iu.test(normalized)
    || /\bsk-[A-Za-z0-9_-]{4,}/u.test(normalized)
    || /(?:api[_-]?key|token|secret)=[^\s&]+/iu.test(normalized)
    || /https?:\/\/[^/\s]*@/iu.test(normalized)
  ) {
    return null;
  }
  return normalized;
}

export function providerTestFailure(error: unknown): string {
  const fallback = "Keen could not verify this provider connection. Your learning step is unchanged; check the endpoint, model, and credentials, then retry.";
  if (!(error instanceof LearningCoreResponseError) || !error.detail) return fallback;
  const message = learnerSafeDetail(error.detail.message);
  if (!message) return fallback;
  const recovery = learnerSafeDetail(error.detail.recovery);
  if (!recovery || recovery === message) return message;
  return `${message} ${recovery}`;
}
