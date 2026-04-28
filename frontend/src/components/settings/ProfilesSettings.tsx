import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, ChevronDown, Eye, EyeOff, Plus, Trash2 } from "lucide-react";
import type { ProviderProfile, ProviderType } from "../../types";
import { PROVIDER_OPTIONS } from "../../constants";
import { newEmptyProfile, validateProfile } from "../../utils/profiles";
import { useProfiles } from "../../context/ProfilesContext";
import {
  getProviderReasoningCapabilities,
  parseModelKwargsJson,
  REASONING_EFFORT_OPTIONS,
  stringifyModelKwargs,
} from "../../utils/reasoning";

// Default names and base URLs per provider — reduces friction for users
const PROVIDER_DEFAULTS: Record<ProviderType, { name: string; baseUrl?: string }> = {
  openrouter: { name: "OpenRouter", baseUrl: "https://openrouter.ai/api/v1" },
  anthropic: { name: "Anthropic" },
  openai: { name: "OpenAI" },
  deepseek: { name: "DeepSeek", baseUrl: "https://api.deepseek.com/v1" },
  together: { name: "Together", baseUrl: "https://api.together.xyz/v1" },
  groq: { name: "Groq", baseUrl: "https://api.groq.com/openai/v1" },
  xai: { name: "xAI", baseUrl: "https://api.x.ai/v1" },
  fireworks: { name: "Fireworks", baseUrl: "https://api.fireworks.ai/inference/v1" },
  perplexity: { name: "Perplexity", baseUrl: "https://api.perplexity.ai" },
  google_genai: { name: "Google GenAI" },
  bedrock: { name: "Amazon Bedrock" },
  azure_openai: { name: "Azure OpenAI" },
  openai_compatible: { name: "Custom OpenAI" },
};

// ─── Profile Row ─────────────────────────────────────────────────────────────

function ProfileRow({
  profile,
  isActive,
  confirmDelete,
  onEdit,
  onDelete,
  onSetActive,
}: {
  profile: ProviderProfile;
  isActive: boolean;
  confirmDelete: boolean;
  onEdit: () => void;
  onDelete: () => void;
  onSetActive: () => void;
}) {
  const { t } = useTranslation();
  const providerLabel =
    PROVIDER_OPTIONS.find((p) => p.value === profile.provider)?.label ?? profile.provider;

  return (
    <div
      className={`flex items-center gap-3 rounded-xl border px-4 py-3 transition ${isActive
          ? "border-[var(--accent)] bg-[var(--accent-subtle)]"
          : "border-[var(--border-subtle)] bg-[var(--surface-soft)]"
        }`}
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-medium text-[var(--text-primary)]">
            {profile.name || t("settings.unnamed", "(unnamed)")}
          </span>
          {isActive && (
            <span className="shrink-0 rounded-full bg-[var(--accent)] px-2 py-0.5 text-[10px] font-medium text-white">
              {t("settings.active", "Active")}
            </span>
          )}
        </div>
        <div className="mt-0.5 flex items-center gap-2 text-[11px] text-[var(--text-soft)]">
          <span className="rounded border border-[var(--border-subtle)] px-1.5 py-0.5">
            {providerLabel}
          </span>
          <span className="truncate font-mono">{profile.model}</span>
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-1">
        {!isActive && (
          <button
            type="button"
            onClick={onSetActive}
            className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-soft)] px-2.5 py-1 text-xs text-[var(--text-soft)] transition hover:border-[var(--accent)] hover:text-[var(--accent)]"
          >
            {t("settings.use", "Use")}
          </button>
        )}
        <button
          type="button"
          onClick={onEdit}
          className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-soft)] px-2.5 py-1 text-xs text-[var(--text-soft)] transition hover:border-[var(--border-strong)] hover:text-[var(--text-primary)]"
        >
          {t("settings.edit", "Edit")}
        </button>
        {confirmDelete ? (
          <button
            type="button"
            onClick={onDelete}
            className="rounded-lg border border-[var(--danger)] bg-[var(--danger-subtle)] px-2.5 py-1 text-xs font-medium text-[var(--danger)] transition hover:bg-[var(--danger)] hover:text-white"
          >
            {t("settings.confirm", "Confirm?")}
          </button>
        ) : (
          <button
            type="button"
            onClick={onDelete}
            className="flex h-7 w-7 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-soft)] text-[var(--text-faint)] transition hover:border-[var(--danger)] hover:text-[var(--danger)]"
            title={t("settings.deleteProfile", "Delete profile")}
          >
            <Trash2 size={13} strokeWidth={1.8} />
          </button>
        )}
      </div>
    </div>
  );
}

// ─── Profile Form ─────────────────────────────────────────────────────────────

function ProfileForm({
  profile,
  onSave,
  onCancel,
}: {
  profile: ProviderProfile;
  onSave: (p: ProviderProfile) => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const [form, setForm] = useState<ProviderProfile>(() => {
    // Pre-fill name and baseUrl for new (empty) profiles
    const defaults = PROVIDER_DEFAULTS[profile.provider];
    return {
      ...profile,
      name: profile.name || defaults.name,
      baseUrl: profile.baseUrl ?? defaults.baseUrl,
    };
  });
  const [showKey, setShowKey] = useState(false);
  const [modelKwargsText, setModelKwargsText] = useState(() => stringifyModelKwargs(form.modelKwargs));
  const reasoningCapabilities = getProviderReasoningCapabilities(form.provider);
  let error: string | null = null;

  try {
    parseModelKwargsJson(modelKwargsText);
  } catch {
    error = t("settings.invalidJsonObject", "Enter a valid JSON object.");
  }
  error = error ?? validateProfile(form);

  function set<K extends keyof ProviderProfile>(key: K, value: ProviderProfile[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function handleProviderChange(provider: ProviderType) {
    const defaults = PROVIDER_DEFAULTS[provider];
    setForm((prev) => ({
      ...prev,
      provider,
      // Auto-fill name only if user hasn't typed one yet or it was a previous default
      name: !prev.name.trim() || Object.values(PROVIDER_DEFAULTS).some(d => d.name === prev.name)
        ? defaults.name
        : prev.name,
      // Auto-fill baseUrl only if field is empty or was a previous default
      baseUrl: !prev.baseUrl?.trim() || Object.values(PROVIDER_DEFAULTS).some(d => d.baseUrl === prev.baseUrl)
        ? defaults.baseUrl
        : prev.baseUrl,
      reasoningEffort: provider === "anthropic" ? undefined : prev.reasoningEffort,
      thinkingBudgetTokens: provider === "anthropic" ? prev.thinkingBudgetTokens : undefined,
    }));
  }

  const needsBaseUrl =
    form.provider === "openai_compatible"
    || form.provider === "openrouter"
    || form.provider === "deepseek"
    || form.provider === "together"
    || form.provider === "groq"
    || form.provider === "xai"
    || form.provider === "fireworks"
    || form.provider === "perplexity";
  const isAzure = form.provider === "azure_openai";

  return (
    <form
      className="mt-4 space-y-4 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-soft)] p-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (!error) onSave(form);
      }}
    >
      {/* Name */}
      <div className="space-y-1.5">
        <label className="block text-xs font-medium text-[var(--text-secondary)]">
          {t("settings.profileName", "Profile name")}
        </label>
        <input
          value={form.name}
          onChange={(e) => set("name", e.target.value)}
          placeholder={t("settings.profileNamePlaceholder", "e.g. Work GPT-5")}
          className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--panel-bg)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none transition hover:border-[var(--border-strong)] focus:border-[var(--accent)]"
        />
      </div>

      {/* Provider */}
      <div className="space-y-1.5">
        <label className="block text-xs font-medium text-[var(--text-secondary)]">{t("settings.provider", "Provider")}</label>
        <div className="relative">
          <select
            value={form.provider}
            onChange={(e) => handleProviderChange(e.target.value as ProviderType)}
            className="w-full appearance-none rounded-lg border border-[var(--border-subtle)] bg-[var(--panel-bg)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none transition hover:border-[var(--border-strong)] focus:border-[var(--accent)]"
            style={{ colorScheme: "inherit" }}
          >
            {PROVIDER_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <ChevronDown
            size={13}
            strokeWidth={1.8}
            className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[var(--text-faint)]"
          />
        </div>
      </div>

      {/* Model */}
      <div className="space-y-1.5">
        <label className="block text-xs font-medium text-[var(--text-secondary)]">{t("settings.modelId", "Model ID")}</label>
        <input
          value={form.model}
          onChange={(e) => set("model", e.target.value)}
          placeholder={
            form.provider === "openrouter"
              ? "openai/gpt-5-mini"
              : form.provider === "anthropic"
                ? "claude-opus-4-5"
                : form.provider === "azure_openai"
                  ? "gpt-4o"
                  : t("settings.modelIdPlaceholder", "model-id")
          }
          className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--panel-bg)] px-3 py-2 text-sm font-mono text-[var(--text-primary)] outline-none transition hover:border-[var(--border-strong)] focus:border-[var(--accent)]"
        />
      </div>

      {/* API Key */}
      <div className="space-y-1.5">
        <label className="block text-xs font-medium text-[var(--text-secondary)]">{t("settings.apiKey", "API Key")}</label>
        <div className="flex gap-2">
          <input
            type={showKey ? "text" : "password"}
            value={form.apiKey}
            onChange={(e) => set("apiKey", e.target.value)}
            placeholder={t("settings.apiKeyPlaceholder", "sk-...")}
            className="flex-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--panel-bg)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none transition hover:border-[var(--border-strong)] focus:border-[var(--accent)]"
          />
          <button
            type="button"
            onClick={() => setShowKey((s) => !s)}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--panel-bg)] text-[var(--text-soft)] transition hover:border-[var(--border-strong)] hover:text-[var(--text-primary)]"
            title={showKey ? t("settings.hideKey", "Hide key") : t("settings.showKey", "Show key")}
          >
            {showKey ? <EyeOff size={15} strokeWidth={1.8} /> : <Eye size={15} strokeWidth={1.8} />}
          </button>
        </div>
      </div>

      {/* Base URL (openai_compatible required, openrouter optional) */}
      {(needsBaseUrl || isAzure) && (
        <div className="space-y-1.5">
          <label className="block text-xs font-medium text-[var(--text-secondary)]">
            {isAzure ? t("settings.azureEndpointOptional", "Azure Endpoint URL (optional)") : t("settings.baseUrl", "Base URL")}
            {form.provider === "openai_compatible" && (
              <span className="ml-1 text-[var(--danger)]">*</span>
            )}
          </label>
          <input
            value={form.baseUrl ?? ""}
            onChange={(e) => set("baseUrl", e.target.value || undefined)}
            placeholder={
              isAzure
                ? t("settings.azureEndpointPlaceholder", "https://your-resource.openai.azure.com/")
                : t("settings.baseUrlPlaceholder", "https://your-proxy/v1")
            }
            className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--panel-bg)] px-3 py-2 text-sm font-mono text-[var(--text-primary)] outline-none transition hover:border-[var(--border-strong)] focus:border-[var(--accent)]"
          />
        </div>
      )}

      {/* Azure-specific fields */}
      {isAzure && (
        <>
          <div className="space-y-1.5">
            <label className="block text-xs font-medium text-[var(--text-secondary)]">
              {t("settings.deploymentName", "Deployment name")} <span className="text-[var(--danger)]">*</span>
            </label>
            <input
              value={form.deployment ?? ""}
              onChange={(e) => set("deployment", e.target.value || undefined)}
              placeholder={t("settings.deploymentPlaceholder", "gpt-4o-prod")}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--panel-bg)] px-3 py-2 text-sm font-mono text-[var(--text-primary)] outline-none transition hover:border-[var(--border-strong)] focus:border-[var(--accent)]"
            />
          </div>
          <div className="space-y-1.5">
            <label className="block text-xs font-medium text-[var(--text-secondary)]">
              {t("settings.apiVersionOptional", "API version (optional)")}
            </label>
            <input
              value={form.apiVersion ?? ""}
              onChange={(e) => set("apiVersion", e.target.value || undefined)}
              placeholder={t("settings.apiVersionPlaceholder", "2024-12-01-preview")}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--panel-bg)] px-3 py-2 text-sm font-mono text-[var(--text-primary)] outline-none transition hover:border-[var(--border-strong)] focus:border-[var(--accent)]"
            />
          </div>
        </>
      )}

      <div className="space-y-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--panel-bg)] p-4">
        <div>
          <div className="text-xs font-medium text-[var(--text-secondary)]">
            {t("settings.reasoningOptions", "Reasoning options")}
          </div>
          <p className="mt-1 text-xs text-[var(--text-soft)]">
            {reasoningCapabilities.state === "supported"
              ? t("settings.reasoningSupportedDesc", "This provider exposes dedicated reasoning controls.")
              : reasoningCapabilities.state === "manual"
                ? t("settings.reasoningManualDesc", "Ethos will apply common reasoning settings when possible and ignore unsupported ones safely.")
                : t("settings.reasoningUnsupportedDesc", "This provider does not advertise a standard reasoning API. Use advanced kwargs only if your endpoint supports them.")}
          </p>
        </div>

        <label className="flex items-center justify-between gap-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-soft)] px-3 py-2">
          <div>
            <div className="text-sm text-[var(--text-primary)]">
              {t("settings.enableReasoning", "Enable reasoning")}
            </div>
            <div className="text-xs text-[var(--text-soft)]">
              {t("settings.enableReasoningDesc", "If the selected model supports reasoning or thinking, Ethos will request it.")}
            </div>
          </div>
          <input
            type="checkbox"
            checked={form.reasoningEnabled ?? true}
            onChange={(e) => set("reasoningEnabled", e.target.checked)}
            className="h-4 w-4 rounded border-[var(--border-strong)] bg-[var(--panel-bg)] text-[var(--accent)]"
          />
        </label>

        {reasoningCapabilities.supportsReasoningEffort && (
          <div className="space-y-1.5">
            <label className="block text-xs font-medium text-[var(--text-secondary)]">
              {t("settings.reasoningEffortLabel", "Reasoning effort")}
            </label>
            <div className="relative">
              <select
                value={form.reasoningEffort ?? "medium"}
                onChange={(e) => set("reasoningEffort", e.target.value as ProviderProfile["reasoningEffort"])}
                className="w-full appearance-none rounded-lg border border-[var(--border-subtle)] bg-[var(--panel-bg)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none transition hover:border-[var(--border-strong)] focus:border-[var(--accent)]"
                style={{ colorScheme: "inherit" }}
              >
                {REASONING_EFFORT_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {t(`settings.reasoningEffortOption.${option}`, option)}
                  </option>
                ))}
              </select>
              <ChevronDown
                size={13}
                strokeWidth={1.8}
                className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[var(--text-faint)]"
              />
            </div>
          </div>
        )}

        {reasoningCapabilities.supportsThinkingBudget && (
          <div className="space-y-1.5">
            <label className="block text-xs font-medium text-[var(--text-secondary)]">
              {t("settings.thinkingBudgetTokens", "Thinking budget tokens")}
            </label>
            <input
              type="number"
              min={1}
              step={1}
              value={form.thinkingBudgetTokens ?? ""}
              onChange={(e) => {
                const value = e.target.value.trim();
                set("thinkingBudgetTokens", value ? Number(value) : undefined);
              }}
              placeholder={t("settings.thinkingBudgetPlaceholder", "e.g. 2048")}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--panel-bg)] px-3 py-2 text-sm font-mono text-[var(--text-primary)] outline-none transition hover:border-[var(--border-strong)] focus:border-[var(--accent)]"
            />
          </div>
        )}

        <div className="space-y-1.5">
          <label className="block text-xs font-medium text-[var(--text-secondary)]">
            {t("settings.advancedModelKwargs", "Advanced model kwargs")}
          </label>
          <textarea
            value={modelKwargsText}
            onChange={(e) => {
              const nextValue = e.target.value;
              setModelKwargsText(nextValue);
              try {
                set("modelKwargs", parseModelKwargsJson(nextValue));
              } catch {
                if (!nextValue.trim()) {
                  set("modelKwargs", undefined);
                }
              }
            }}
            placeholder={t("settings.advancedModelKwargsPlaceholder", "{\"custom_option\": true}")}
            rows={5}
            spellCheck={false}
            className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--panel-bg)] px-3 py-2 font-mono text-sm text-[var(--text-primary)] outline-none transition hover:border-[var(--border-strong)] focus:border-[var(--accent)]"
          />
          <p className="text-xs text-[var(--text-soft)]">
            {t("settings.advancedModelKwargsDesc", "Optional JSON object merged into the provider request after Ethos applies the common reasoning settings.")}
          </p>
        </div>
      </div>

      {/* Error */}
      {error && <p className="text-xs text-[var(--danger)]">{error}</p>}

      {/* Actions */}
      <div className="flex gap-2 pt-1">
        <button
          type="submit"
          disabled={!!error}
          className="rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {t("settings.save", "Save")}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-soft)] px-4 py-2 text-sm text-[var(--text-soft)] transition hover:border-[var(--border-strong)] hover:text-[var(--text-primary)]"
        >
          {t("settings.cancel", "Cancel")}
        </button>
      </div>
    </form>
  );
}

// ─── ProfilesSettings ─────────────────────────────────────────────────────────

export default function ProfilesSettings() {
  const { t } = useTranslation();
  const { profiles, activeProfileId, setActiveProfileId, saveProfiles } = useProfiles();
  const [editing, setEditing] = useState<ProviderProfile | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  function persist(nextProfiles: ProviderProfile[], nextActiveId: string) {
    saveProfiles(nextProfiles, nextActiveId);
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  }

  function handleSaveProfile(profile: ProviderProfile) {
    const next = profiles.some((p) => p.id === profile.id)
      ? profiles.map((p) => (p.id === profile.id ? profile : p))
      : [...profiles, profile];
    setEditing(null);
    persist(next, activeProfileId);
  }

  function handleDelete(id: string) {
    if (confirmDelete !== id) {
      setConfirmDelete(id);
      return;
    }
    const next = profiles.filter((p) => p.id !== id);
    const nextActive =
      id === activeProfileId ? (next[0]?.id ?? "") : activeProfileId;
    setConfirmDelete(null);
    persist(next, nextActive);
  }

  function handleSetActive(id: string) {
    setActiveProfileId(id);
  }

  function handleAddProfile() {
    setConfirmDelete(null);
    setEditing(newEmptyProfile());
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="mb-2 text-2xl font-semibold text-[var(--text-primary)]">
          {t("settings.providerProfiles", "Provider Profiles")}
        </h1>
        <p className="text-sm text-[var(--text-soft)]">
          {t("settings.providerProfilesDesc", "Each profile stores a complete LLM configuration. Your keys stay in this browser and are only sent to your configured Ethos backend at request time.")}
        </p>
      </div>

      {/* Profile list */}
      <div className="space-y-2">
        {profiles.length === 0 && (
          <p className="rounded-xl border border-dashed border-[var(--border-subtle)] px-4 py-6 text-center text-sm text-[var(--text-faint)]">
            {t("settings.noProfilesDesc", "No profiles yet. Add one to start chatting.")}
          </p>
        )}
        {profiles.map((p) => (
          <ProfileRow
            key={p.id}
            profile={p}
            isActive={p.id === activeProfileId}
            confirmDelete={confirmDelete === p.id}
            onEdit={() => {
              setConfirmDelete(null);
              setEditing({ ...p });
            }}
            onDelete={() => handleDelete(p.id)}
            onSetActive={() => handleSetActive(p.id)}
          />
        ))}
      </div>

      {/* Edit / Add form */}
      {editing ? (
        <ProfileForm
          profile={editing}
          onSave={handleSaveProfile}
          onCancel={() => setEditing(null)}
        />
      ) : (
        <button
          type="button"
          onClick={handleAddProfile}
          className="flex items-center gap-2 rounded-lg border border-dashed border-[var(--border-subtle)] px-4 py-2 text-sm text-[var(--text-soft)] transition hover:border-[var(--accent)] hover:text-[var(--accent)]"
        >
          <Plus size={14} strokeWidth={2} />
          {t("settings.addProfile", "Add profile")}
        </button>
      )}

      {saved && (
        <span className="inline-flex items-center gap-1.5 text-sm text-[var(--success)]">
          <Check size={14} strokeWidth={2} />
          {t("settings.saved", "Saved")}
        </span>
      )}
    </div>
  );
}
