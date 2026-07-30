import { invoke, isTauri } from "@tauri-apps/api/core";
import { z } from "zod";
import { sidecarConnectionSchema, type SidecarConnection } from "@keen/api-client";

const providerConfigurationSchema = z.object({
  configured: z.boolean(), provider: z.enum(["ollama", "openai-compatible"]).nullable(), endpoint: z.string().url().nullable(), model: z.string().min(1).max(256).nullable(), apiKeyConfigured: z.boolean(),
}).strict();
export type ProviderConfiguration = z.infer<typeof providerConfigurationSchema>;
export type ProviderDraft = { provider: "ollama" | "openai-compatible"; endpoint: string; model: string; apiKey?: string };

export function providerRequiresRemoteApiKey(
  provider: ProviderDraft["provider"],
  endpoint: string,
): boolean {
  if (provider !== "openai-compatible") return false;
  try {
    return new URL(endpoint).protocol === "https:";
  } catch {
    return false;
  }
}

export function savedApiKeyAppliesToDraft(
  saved: ProviderConfiguration | null,
  provider: ProviderDraft["provider"],
  endpoint: string,
): boolean {
  if (
    !saved?.apiKeyConfigured
    || saved.provider !== "openai-compatible"
    || provider !== "openai-compatible"
    || !saved.endpoint
  ) {
    return false;
  }
  try {
    const savedUrl = new URL(saved.endpoint);
    const draftUrl = new URL(endpoint);
    return (
      savedUrl.protocol === "https:"
      && draftUrl.protocol === "https:"
      && savedUrl.origin === draftUrl.origin
    );
  } catch {
    return false;
  }
}

export async function getProviderConfiguration(): Promise<ProviderConfiguration> {
  return providerConfigurationSchema.parse(await invoke("get_provider_configuration"));
}
export async function saveProviderConfiguration(draft: ProviderDraft): Promise<SidecarConnection> {
  return sidecarConnectionSchema.parse(await invoke("save_provider_configuration", { configuration: { provider: draft.provider, endpoint: draft.endpoint.trim(), model: draft.model.trim() }, apiKey: draft.apiKey?.trim() || null }));
}
export function canConfigureProvider(): boolean { return isTauri(); }
