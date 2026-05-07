import type { ProviderType, ReasoningEffort } from "../types";

export type ReasoningSupportState = "supported" | "manual" | "unsupported";
export type ReasoningControlType = "reasoning_effort" | "thinking_budget" | "none";

export type ThinkingBudgetPreset = {
  id: Extract<ReasoningEffort, "low" | "medium" | "high">;
  tokens: number;
};

export type ProviderReasoningCapabilities = {
  state: ReasoningSupportState;
  supportsReasoningEffort: boolean;
  supportsThinkingBudget: boolean;
  control: ReasoningControlType;
  effortOptions: ReasoningEffort[];
  thinkingBudgetPresets: ThinkingBudgetPreset[];
};

export function getProviderReasoningCapabilities(provider: ProviderType): ProviderReasoningCapabilities {
  return getModelReasoningCapabilities(provider, "");
}

const REASONING_MODEL_TOKENS = ["o1", "o3", "o4", "reason", "gpt-5", "gpt5"];
const OPENROUTER_REASONING_MODEL_TOKENS = [
  ...REASONING_MODEL_TOKENS,
  "claude-3.7",
  "claude-4",
  "claude-opus-4",
  "claude-sonnet-4",
  "gemini-2.5",
  "gemini-3",
  "grok",
  "qwen3",
  "qwen-3",
  "thinking",
];
const OPENAI_GPT5_OPTIONS: ReasoningEffort[] = ["none", "low", "medium", "high"];
const OPENAI_REASONING_OPTIONS: ReasoningEffort[] = ["low", "medium", "high"];
const OPENROUTER_REASONING_OPTIONS: ReasoningEffort[] = ["none", "minimal", "low", "medium", "high", "xhigh"];
const DEEPSEEK_V4_OPTIONS: ReasoningEffort[] = ["none", "high", "max"];
export const REASONING_EFFORT_OPTIONS: ReasoningEffort[] = ["low", "medium", "high"];
export const THINKING_BUDGET_PRESETS: ThinkingBudgetPreset[] = [
  { id: "low", tokens: 1024 },
  { id: "medium", tokens: 4096 },
  { id: "high", tokens: 8192 },
];

function unsupportedCapabilities(state: ReasoningSupportState = "unsupported"): ProviderReasoningCapabilities {
  return {
    state,
    supportsReasoningEffort: false,
    supportsThinkingBudget: false,
    control: "none",
    effortOptions: [],
    thinkingBudgetPresets: [],
  };
}

export function getModelReasoningCapabilities(
  provider: ProviderType,
  model: string,
): ProviderReasoningCapabilities {
  const normalizedModel = model.trim().toLowerCase();
  const supportsReasoningModel = REASONING_MODEL_TOKENS.some((token) => normalizedModel.includes(token));
  const supportsOpenRouterReasoningModel = OPENROUTER_REASONING_MODEL_TOKENS.some((token) => (
    normalizedModel.includes(token)
  ));
  const isGpt5Family = normalizedModel.includes("gpt-5") || normalizedModel.includes("gpt5");
  const isDeepSeekV4 = normalizedModel.includes("deepseek-v4");

  switch (provider) {
    case "deepseek":
      if (!isDeepSeekV4 && !normalizedModel.includes("reasoner")) {
        return unsupportedCapabilities("manual");
      }
      return {
        state: "supported",
        supportsReasoningEffort: true,
        supportsThinkingBudget: false,
        control: "reasoning_effort",
        effortOptions: isDeepSeekV4 ? DEEPSEEK_V4_OPTIONS : OPENAI_REASONING_OPTIONS,
        thinkingBudgetPresets: [],
      };
    case "openrouter":
      if (!supportsOpenRouterReasoningModel && !isDeepSeekV4) {
        return unsupportedCapabilities("manual");
      }
      return {
        state: "manual",
        supportsReasoningEffort: true,
        supportsThinkingBudget: false,
        control: "reasoning_effort",
        effortOptions: OPENROUTER_REASONING_OPTIONS,
        thinkingBudgetPresets: [],
      };
    case "openai":
    case "together":
    case "groq":
    case "xai":
    case "fireworks":
    case "perplexity":
    case "azure_openai":
    case "9router":
    case "openai_compatible":
      if (!supportsReasoningModel) {
        return unsupportedCapabilities("manual");
      }
      return {
        state: "manual",
        supportsReasoningEffort: true,
        supportsThinkingBudget: false,
        control: "reasoning_effort",
        effortOptions: isGpt5Family ? OPENAI_GPT5_OPTIONS : OPENAI_REASONING_OPTIONS,
        thinkingBudgetPresets: [],
      };
    case "anthropic":
      if (!normalizedModel.includes("claude")) {
        return unsupportedCapabilities("supported");
      }
      return {
        state: "supported",
        supportsReasoningEffort: false,
        supportsThinkingBudget: true,
        control: "thinking_budget",
        effortOptions: [],
        thinkingBudgetPresets: THINKING_BUDGET_PRESETS,
      };
    case "google_genai":
    case "bedrock":
      return unsupportedCapabilities("manual");
    default:
      return unsupportedCapabilities();
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
