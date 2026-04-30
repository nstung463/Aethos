import { useTranslation } from "react-i18next";
import type { SettingsSection } from "../types";

const SETTINGS_ITEMS: { id: SettingsSection; labelKey: string; defaultLabel: string }[] = [
  { id: "general", labelKey: "settings.general", defaultLabel: "General" },
  { id: "appearance", labelKey: "settings.appearance", defaultLabel: "Appearance" },
  { id: "profiles", labelKey: "settings.profiles", defaultLabel: "Profiles" },
  { id: "model-settings", labelKey: "settings.modelSettings", defaultLabel: "Model Settings" },
  { id: "security", labelKey: "settings.security", defaultLabel: "Security" },
  { id: "extensions", labelKey: "settings.extensions", defaultLabel: "Extensions" },
];

export default function SettingsSubSidebar({
  section,
  onSectionChange,
}: {
  section: SettingsSection;
  onSectionChange: (section: SettingsSection) => void;
}) {
  const { t } = useTranslation();

  return (
    <aside className="w-[200px] shrink-0 flex flex-col border-r border-[var(--border-subtle)] bg-[var(--panel-bg)] px-3 py-4 overflow-y-auto">
      {/* Profile Card */}
      <div className="flex items-center gap-2 rounded-[12px] border border-[var(--border-subtle)] bg-[var(--surface-soft)] px-2.5 py-2 mb-4">
        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-[#f59e0b] text-xs font-semibold text-white">
          ET
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-xs font-medium text-[var(--text-primary)]">{t("settings.ethosUser", "Ethos User")}</div>
          <div className="truncate text-[10px] text-[var(--text-soft)]">{t("settings.personal", "Personal")}</div>
        </div>
      </div>

      {/* Divider */}
      <div className="my-3 h-px bg-[var(--border-subtle)]" />

      {/* Navigation Items */}
      <nav className="space-y-1">
        {SETTINGS_ITEMS.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => onSectionChange(item.id)}
            className={`w-full text-left rounded-[10px] px-3 py-2 text-sm transition ${
              section === item.id
                ? "bg-[var(--surface-active)] text-[var(--surface-active-text)] font-medium"
                : "text-[var(--text-soft)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
            }`}
          >
            {t(item.labelKey, item.defaultLabel)}
          </button>
        ))}
      </nav>
    </aside>
  );
}
