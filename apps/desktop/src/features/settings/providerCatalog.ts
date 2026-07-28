export type ProviderTransport = "ollama" | "openai-compatible";

export type ProviderPresetId =
  | "ollama"
  | "openai"
  | "deepseek"
  | "anthropic"
  | "gemini"
  | "openrouter"
  | "groq"
  | "mistral"
  | "xai"
  | "qwen"
  | "kimi"
  | "custom";

export type ProviderPresetMaturity =
  | "built-in"
  | "compatible-preset"
  | "compatibility-preview"
  | "custom";

export type ProviderPreset = {
  id: ProviderPresetId;
  name: string;
  description: string;
  transport: ProviderTransport;
  endpoint: string;
  suggestedModel: string;
  maturity: ProviderPresetMaturity;
};

export const providerPresets: readonly ProviderPreset[] = [
  {
    id: "ollama",
    name: "Ollama",
    description: "Run a model already installed on this Mac.",
    transport: "ollama",
    endpoint: "http://127.0.0.1:11434",
    suggestedModel: "qwen3",
    maturity: "built-in",
  },
  {
    id: "openai",
    name: "OpenAI",
    description: "Use an OpenAI API key with the standard Chat Completions API.",
    transport: "openai-compatible",
    endpoint: "https://api.openai.com",
    suggestedModel: "gpt-5-mini",
    maturity: "built-in",
  },
  {
    id: "deepseek",
    name: "DeepSeek",
    description: "Prefill DeepSeek's OpenAI-compatible API base.",
    transport: "openai-compatible",
    endpoint: "https://api.deepseek.com",
    suggestedModel: "deepseek-v4-flash",
    maturity: "compatible-preset",
  },
  {
    id: "anthropic",
    name: "Anthropic Claude",
    description: "Use Anthropic's OpenAI SDK compatibility layer.",
    transport: "openai-compatible",
    endpoint: "https://api.anthropic.com",
    suggestedModel: "claude-sonnet-4-6",
    maturity: "compatibility-preview",
  },
  {
    id: "gemini",
    name: "Google Gemini",
    description: "Use Google's OpenAI compatibility API base.",
    transport: "openai-compatible",
    endpoint: "https://generativelanguage.googleapis.com/v1beta/openai",
    suggestedModel: "gemini-3.6-flash",
    maturity: "compatibility-preview",
  },
  {
    id: "openrouter",
    name: "OpenRouter",
    description: "Choose from OpenRouter's OpenAI-compatible model catalog.",
    transport: "openai-compatible",
    endpoint: "https://openrouter.ai/api/v1",
    suggestedModel: "openai/gpt-5-mini",
    maturity: "compatible-preset",
  },
  {
    id: "groq",
    name: "Groq",
    description: "Use Groq's OpenAI-compatible inference API.",
    transport: "openai-compatible",
    endpoint: "https://api.groq.com/openai/v1",
    suggestedModel: "openai/gpt-oss-120b",
    maturity: "compatible-preset",
  },
  {
    id: "mistral",
    name: "Mistral AI",
    description: "Prefill Mistral's OpenAI-compatible API base.",
    transport: "openai-compatible",
    endpoint: "https://api.mistral.ai/v1",
    suggestedModel: "mistral-small-latest",
    maturity: "compatible-preset",
  },
  {
    id: "xai",
    name: "xAI",
    description: "Prefill xAI's OpenAI-compatible API base.",
    transport: "openai-compatible",
    endpoint: "https://api.x.ai/v1",
    suggestedModel: "grok-4-1-fast",
    maturity: "compatible-preset",
  },
  {
    id: "qwen",
    name: "Qwen",
    description: "Use Alibaba Cloud's DashScope compatibility API.",
    transport: "openai-compatible",
    endpoint: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    suggestedModel: "qwen-plus",
    maturity: "compatible-preset",
  },
  {
    id: "kimi",
    name: "Kimi",
    description: "Prefill Moonshot AI's OpenAI-compatible API base.",
    transport: "openai-compatible",
    endpoint: "https://api.moonshot.cn/v1",
    suggestedModel: "kimi-k2.5",
    maturity: "compatible-preset",
  },
  {
    id: "custom",
    name: "Custom API base",
    description: "Connect another OpenAI-compatible HTTPS or loopback API base.",
    transport: "openai-compatible",
    endpoint: "",
    suggestedModel: "",
    maturity: "custom",
  },
] as const;

export function providerPreset(id: ProviderPresetId): ProviderPreset {
  const preset = providerPresets.find((candidate) => candidate.id === id);
  if (!preset) throw new Error(`Unknown provider preset: ${id}`);
  return preset;
}

export function matchProviderPreset(
  transport: ProviderTransport,
  endpoint: string,
): ProviderPresetId {
  const normalizedEndpoint = normalizeApiBase(endpoint);
  return providerPresets.find((preset) => (
    preset.id !== "custom"
    && preset.transport === transport
    && normalizeApiBase(preset.endpoint) === normalizedEndpoint
  ))?.id ?? "custom";
}

export function providerMaturityLabel(maturity: ProviderPresetMaturity): string {
  if (maturity === "built-in") return "Built-in transport";
  if (maturity === "compatibility-preview") return "Compatibility preview";
  if (maturity === "compatible-preset") return "Compatible preset";
  return "Advanced";
}

function normalizeApiBase(value: string): string {
  try {
    const url = new URL(value);
    return `${url.protocol}//${url.host}${url.pathname.replace(/\/+$/, "")}`;
  } catch {
    return value.trim().replace(/\/+$/, "");
  }
}
