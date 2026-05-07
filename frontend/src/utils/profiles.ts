import {
  ACTIVE_PROFILE_STORAGE_KEY,
  API_KEYS_STORAGE_KEY,
  PROFILES_STORAGE_KEY,
} from "../constants";
import type { ProviderProfile } from "../types";

function migrateFromApiKeys(): ProviderProfile[] {
  const raw = localStorage.getItem(API_KEYS_STORAGE_KEY);
  if (!raw) return [];
  try {
    const old = JSON.parse(raw) as Record<string, string>;
    const profiles: ProviderProfile[] = [];
    if (old.openrouter?.trim()) {
      profiles.push({
        id: crypto.randomUUID(),
        name: "OpenRouter",
        provider: "openrouter",
        apiKey: old.openrouter,
        model: "openai/gpt-4o-mini",
        reasoningEnabled: true,
      });
    }
    if (old.anthropic?.trim()) {
      profiles.push({
        id: crypto.randomUUID(),
        name: "Anthropic",
        provider: "anthropic",
        apiKey: old.anthropic,
        model: "claude-opus-4-5",
        reasoningEnabled: true,
      });
    }
    if (old.openai?.trim()) {
      profiles.push({
        id: crypto.randomUUID(),
        name: "OpenAI",
        provider: "openai",
        apiKey: old.openai,
        model: "gpt-4o",
        reasoningEnabled: true,
      });
    }
    return profiles;
  } catch {
    return [];
  }
}

export function loadProfiles(): ProviderProfile[] {
  const raw = localStorage.getItem(PROFILES_STORAGE_KEY);
  if (!raw) {
    const migrated = migrateFromApiKeys();
    if (migrated.length > 0) {
      saveProfiles(migrated);
      localStorage.removeItem(API_KEYS_STORAGE_KEY);
    }
    return migrated;
  }
  try {
    return JSON.parse(raw) as ProviderProfile[];
  } catch {
    return [];
  }
}

export function saveProfiles(profiles: ProviderProfile[]): void {
  localStorage.setItem(PROFILES_STORAGE_KEY, JSON.stringify(profiles));
}

export function loadActiveProfileId(): string {
  return localStorage.getItem(ACTIVE_PROFILE_STORAGE_KEY) ?? "";
}

export function saveActiveProfileId(profileId: string): void {
  if (profileId) {
    localStorage.setItem(ACTIVE_PROFILE_STORAGE_KEY, profileId);
    return;
  }
  localStorage.removeItem(ACTIVE_PROFILE_STORAGE_KEY);
}

export function newEmptyProfile(): ProviderProfile {
  return {
    id: crypto.randomUUID(),
    name: "",
    provider: "9router",
    apiKey: "",
    model: "",
    reasoningEnabled: true,
  };
}

export function validateProfile(p: ProviderProfile): string | null {
  if (!p.name.trim()) return "Name is required";
  if (!p.model.trim()) return "Model ID is required";
  if (!p.apiKey.trim()) return "API key is required";
  if ((p.provider === "openai_compatible" || p.provider === "9router") && !p.baseUrl?.trim())
    return "Base URL is required for OpenAI-compatible provider";
  if (p.provider === "azure_openai" && !p.deployment?.trim())
    return "Deployment name is required for Azure OpenAI";
  if (p.thinkingBudgetTokens !== undefined && (!Number.isInteger(p.thinkingBudgetTokens) || p.thinkingBudgetTokens <= 0))
    return "Thinking budget tokens must be a positive integer";
  return null;
}
