import type { ModeConfig, ProviderType, UserApiKeys } from "./types";

export const STORAGE_KEY = "ethos.frontend.threads.v2";
export const LEGACY_STORAGE_KEY = "ethos.frontend.threads.v1";
/** @deprecated kept for migration reads only */
export const API_KEYS_STORAGE_KEY = "ethos.frontend.api-keys.v1";
export const PROFILES_STORAGE_KEY = "ethos.frontend.profiles.v1";

export const PROVIDER_OPTIONS: { value: ProviderType; label: string }[] = [
  { value: "openrouter", label: "OpenRouter" },
  { value: "anthropic", label: "Anthropic" },
  { value: "openai", label: "OpenAI" },
  { value: "deepseek", label: "DeepSeek" },
  { value: "together", label: "Together" },
  { value: "groq", label: "Groq" },
  { value: "xai", label: "xAI" },
  { value: "fireworks", label: "Fireworks" },
  { value: "perplexity", label: "Perplexity" },
  { value: "google_genai", label: "Google GenAI" },
  { value: "bedrock", label: "Amazon Bedrock" },
  { value: "azure_openai", label: "Azure OpenAI" },
  { value: "openai_compatible", label: "OpenAI Compatible" },
];

export const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ??
  "http://localhost:8080";

export const MODES: ModeConfig[] = [
  {
    id: "build",
    label: "Build",
    eyebrow: "Ship changes",
    instruction:
      "You are helping with implementation work. Prefer concrete edits, working code, and direct execution steps.",
    placeholder: "Ask Ethos to inspect code, make edits, or implement a change...",
    suggestions: [
      "Audit this repo and list the highest-risk bugs first.",
      "Refactor this API route to be easier to maintain.",
      "Implement chat persistence with a stable chat_id.",
    ],
  },
  {
    id: "review",
    label: "Review",
    eyebrow: "Risk first",
    instruction:
      "You are reviewing code. Prioritize bugs, regressions, missing tests, and operational risk over summaries.",
    placeholder: "Ask Ethos to review a diff, API, or architecture path...",
    suggestions: [
      "Review this endpoint for hidden state-management bugs.",
      "Find regressions if we replace OpenWebUI with this custom frontend.",
      "List testing gaps before this UI goes live.",
    ],
  },
  {
    id: "explain",
    label: "Explain",
    eyebrow: "Understand systems",
    instruction:
      "You are explaining the system clearly and pragmatically. Optimize for fast comprehension, not fluff.",
    placeholder: "Ask Ethos to explain a code path, architecture, or behavior...",
    suggestions: [
      "Explain how streaming works end to end in this stack.",
      "Walk me through how the backend handles conversation state.",
      "Compare this frontend architecture against OpenWebUI.",
    ],
  },
];

export const QUICK_ACTIONS = [
  {
    title: "Create slides",
    prompt: "Create a polished slide deck for a product strategy review.",
  },
  {
    title: "Build website",
    prompt: "Build a responsive marketing website with clear sections and calls to action.",
  },
  {
    title: "Develop desktop apps",
    prompt: "Plan and scaffold a desktop app with the right architecture and packaging approach.",
  },
  {
    title: "Design",
    prompt: "Design a clean, modern product experience for this workflow.",
  },
];

export const CHAT_SUGGESTIONS = [
  // "Create a presentation deck for a product strategy review",
  // "Draft a customer email then attach the latest project brief",
  // "Check my calendar and suggest a review slot this week",
];

export function getModeConfig(mode: string): ModeConfig {
  return MODES.find((m) => m.id === mode) ?? MODES[0];
}

/** @deprecated use profiles instead */
export const EMPTY_API_KEYS: UserApiKeys = {
  openrouter: "",
  anthropic: "",
  openai: "",
};
