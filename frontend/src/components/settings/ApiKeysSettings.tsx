import { useEffect, useState } from "react";
import { Check, Eye, EyeOff } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { UserApiKeys } from "../../types";

export default function ApiKeysSettings({
  apiKeys,
  onSave,
}: {
  apiKeys: UserApiKeys;
  onSave: (apiKeys: UserApiKeys) => void;
}) {
  const { t } = useTranslation();
  const [draftKeys, setDraftKeys] = useState<UserApiKeys>(apiKeys);
  const [showKeys, setShowKeys] = useState({
    openrouter: false,
    anthropic: false,
    openai: false,
  });

  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setDraftKeys(apiKeys);
  }, [apiKeys]);

  const handleChange = (key: keyof typeof apiKeys, value: string) => {
    setDraftKeys((prev) => ({ ...prev, [key]: value }));
    setSaved(false);
  };

  const handleToggleShow = (key: keyof typeof showKeys) => {
    setShowKeys((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const handleSave = () => {
    onSave(draftKeys);
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  };

  const renderKeyInput = (
    label: string,
    key: keyof typeof apiKeys,
    placeholder: string
  ) => (
    <div className="space-y-2">
      <label className="block text-sm font-medium text-[var(--text-secondary)]">
        {label}
      </label>
      <div className="flex gap-2">
        <input
          type={showKeys[key] ? "text" : "password"}
          value={draftKeys[key]}
          onChange={(e) => handleChange(key, e.target.value)}
          placeholder={placeholder}
          className="flex-1 rounded-lg bg-[var(--surface-soft)] border border-[var(--border-subtle)] px-3 py-2 text-[var(--text-primary)] outline-none transition hover:border-[var(--border-strong)] focus:border-[var(--accent)]"
        />
        <button
          type="button"
          onClick={() => handleToggleShow(key)}
          className="flex h-10 w-10 items-center justify-center rounded-lg bg-[var(--surface-soft)] border border-[var(--border-subtle)] text-[var(--text-soft)] hover:text-[var(--text-primary)] hover:border-[var(--border-strong)] transition"
          title={showKeys[key] ? t("settings.hide", "Hide") : t("settings.show", "Show")}
        >
          {showKeys[key] ? (
            <EyeOff size={16} strokeWidth={1.8} />
          ) : (
            <Eye size={16} strokeWidth={1.8} />
          )}
        </button>
      </div>
    </div>
  );

  return (
    <div className="space-y-8">
      <div>
        <h1 className="mb-6 text-[26px] font-semibold text-[var(--text-primary)]">{t("settings.apiKeys", "API Keys")}</h1>
        <p className="mb-6 text-[13px] text-[var(--text-soft)]">
          {t("settings.apiKeysDesc", "Your keys stay in this browser and are only sent to your configured Aethos backend at request time.")}
        </p>

        <div className="mb-8 space-y-6">
          {renderKeyInput(
            t("settings.openRouterKey", "OpenRouter API Key"),
            "openrouter",
            "sk-or-v1-..."
          )}
          {renderKeyInput(
            t("settings.anthropicKey", "Anthropic API Key"),
            "anthropic",
            "sk-ant-..."
          )}
          {renderKeyInput(
            t("settings.openaiKey", "OpenAI API Key"),
            "openai",
            "sk-proj-..."
          )}
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleSave}
            className="rounded-lg bg-[var(--accent)] px-4 py-2 font-medium text-white transition hover:opacity-90"
          >
            {t("settings.saveKeys", "Save Keys")}
          </button>
          {saved && (
            <span className="inline-flex items-center gap-1.5 text-sm text-[var(--success)]">
              <Check size={14} strokeWidth={2} />
              {t("settings.savedSuccessfully", "Saved successfully")}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
