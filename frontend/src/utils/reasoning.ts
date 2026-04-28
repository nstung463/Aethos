import type { ProviderType, ReasoningEffort } from "../types";

export type ReasoningSupportState = "supported" | "manual" | "unsupported";

export type ProviderReasoningCapabilities = {
  state: ReasoningSupportState;
  supportsReasoningEffort: boolean;
  supportsThinkingBudget: boolean;
};

export function getProviderReasoningCapabilities(provider: ProviderType): ProviderReasoningCapabilities {
  switch (provider) {
    case "openai":
    case "openrouter":
    case "deepseek":
    case "together":
    case "groq":
    case "xai":
    case "fireworks":
    case "perplexity":
    case "azure_openai":
    case "openai_compatible":
      return {
        state: "manual",
        supportsReasoningEffort: true,
        supportsThinkingBudget: false,
      };
    case "anthropic":
      return {
        state: "supported",
        supportsReasoningEffort: false,
        supportsThinkingBudget: true,
      };
    case "google_genai":
    case "bedrock":
      return {
        state: "manual",
        supportsReasoningEffort: false,
        supportsThinkingBudget: false,
      };
    default:
      return {
        state: "unsupported",
        supportsReasoningEffort: false,
        supportsThinkingBudget: false,
      };
  }
}

export function parseModelKwargsJson(value: string): Record<string, unknown> | undefined {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  const parsed = JSON.parse(trimmed) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Model kwargs must be a JSON object");
  }
  return parsed as Record<string, unknown>;
}

export function stringifyModelKwargs(value?: Record<string, unknown>): string {
  if (!value || Object.keys(value).length === 0) return "";
  return JSON.stringify(value, null, 2);
}

export const REASONING_EFFORT_OPTIONS: ReasoningEffort[] = ["low", "medium", "high"];
