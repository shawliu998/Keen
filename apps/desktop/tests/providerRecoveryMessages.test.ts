import { describe, expect, it } from "vitest";
import { LearningCoreResponseError } from "@keen/api-client";
import {
  providerSaveFailure,
  providerTestFailure,
} from "../src/features/settings/providerRecoveryMessages";

describe("provider recovery messages", () => {
  it("distinguishes a rejected configuration from a saved configuration whose restart did not begin", () => {
    const notActivated = providerSaveFailure("Enter a valid provider endpoint.");
    const restartFailed = providerSaveFailure(
      "Provider settings were saved, but Keen could not begin restarting the local learning service. The service may still be using its previous runtime configuration; retry from Settings after it recovers.",
    );

    expect(notActivated.outcome).toBe("not_activated");
    expect(notActivated.text).toContain("New provider settings were not switched into use");
    expect(restartFailed.outcome).toBe("saved_restart_failed");
    expect(restartFailed.text).toContain("Provider settings were saved");
    expect(restartFailed.text).toContain("could not begin restarting");
  });

  it("does not surface an unapproved save error containing a secret", () => {
    const failure = providerSaveFailure(new Error("save failed with sk-provider-private"));

    expect(failure.outcome).toBe("unknown");
    expect(failure.text).not.toContain("sk-provider-private");
    expect(failure.text).toContain("No restart or connection is assumed");
  });

  it("preserves bounded learner-safe connection guidance and rejects secret-bearing detail", () => {
    const safe = new LearningCoreResponseError(503, {
      message: "Keen could not confirm the provider model.",
      retryable: true,
      recovery: "Check the provider endpoint, model access, and API key, then retry.",
      documentId: null,
      code: null,
    }, "request-safe");
    const unsafe = new LearningCoreResponseError(503, {
      message: "Provider returned token=secret-value.",
      retryable: true,
      recovery: "Inspect https://user:password@example.com.",
      documentId: null,
      code: null,
    }, "request-unsafe");

    expect(providerTestFailure(safe)).toBe(
      "Keen could not confirm the provider model. Check the provider endpoint, model access, and API key, then retry.",
    );
    const unsafeMessage = providerTestFailure(unsafe);
    expect(unsafeMessage).not.toContain("secret-value");
    expect(unsafeMessage).not.toContain("password@example.com");
    expect(unsafeMessage).toContain("Keen could not verify this provider connection");
  });
});
