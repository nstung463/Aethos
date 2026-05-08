import {
  CreditCard,
  Cable,
  ChevronsUpDown,
  Paintbrush,
  Settings2,
  Shield,
  Sparkles,
  User,
  Users,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { API_BASE_URL } from "../constants";
import type { SettingsSection } from "../types";
import { authFetch } from "../utils/auth";

type SessionUser = {
  display_name?: string;
};

const SETTINGS_GROUPS: Array<{
  titleKey: string;
  defaultTitle: string;
  items: Array<{ id: SettingsSection; labelKey: string; defaultLabel: string; icon: LucideIcon }>;
}> = [
  {
    titleKey: "settings.personalWorkspace",
    defaultTitle: "Personal workspace",
    items: [
      { id: "account", labelKey: "settings.account", defaultLabel: "Account", icon: User },
      { id: "general", labelKey: "settings.general", defaultLabel: "General", icon: Settings2 },
      { id: "usage-billing", labelKey: "settings.usageBilling", defaultLabel: "Usage & Billing", icon: CreditCard },
      { id: "personalization", labelKey: "settings.personalization", defaultLabel: "Personalization", icon: Paintbrush },
    ],
  },
  {
    titleKey: "settings.buildersAndIntegrations",
    defaultTitle: "Builders & integrations",
    items: [
      { id: "connections", labelKey: "settings.connections", defaultLabel: "Connections", icon: Cable },
      { id: "extensions", labelKey: "settings.skillsAndMcp", defaultLabel: "Skills & MCP", icon: Sparkles },
    ],
  },
  {
    titleKey: "settings.advanced",
    defaultTitle: "Advanced",
    items: [
      { id: "security", labelKey: "settings.security", defaultLabel: "Security", icon: Shield },
      { id: "profiles", labelKey: "settings.profiles", defaultLabel: "Profiles", icon: Users },
    ],
  },
];

function initialsFromName(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "ET";
  return parts
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

export default function SettingsSubSidebar({
  section,
  onSectionChange,
}: {
  section: SettingsSection;
  onSectionChange: (section: SettingsSection) => void;
}) {
  const { t } = useTranslation();
  const [userName, setUserName] = useState("");

  useEffect(() => {
    let cancelled = false;
    authFetch(`${API_BASE_URL}/auth/me`)
      .then((response) => (response.ok ? (response.json() as Promise<SessionUser>) : null))
      .then((payload) => {
        if (!cancelled && payload?.display_name) setUserName(payload.display_name);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  const displayName = userName || t("settings.aethosUser", "Aethos User");
  const initials = useMemo(() => initialsFromName(displayName), [displayName]);

  return (
    <aside className="flex h-full min-h-0 w-[248px] shrink-0 flex-col border-r border-[var(--border-subtle)] bg-[var(--panel-bg)] py-4">
      <div className="shrink-0 px-3 py-1">
        <div className="group grid w-full cursor-pointer ps-1 pe-1 pt-4 pb-[18px]">
          <div className="col-start-1 row-start-1 min-h-[36px] min-w-0">
            <div className="flex items-center gap-2">
              <div className="flex min-w-0 flex-1 items-center gap-[10px] overflow-hidden">
                <div className="relative flex h-8 w-8 flex-shrink-0 items-center justify-center overflow-hidden rounded-full bg-[var(--surface-active)] text-xs font-semibold text-[var(--surface-active-text)]">
                  {initials}
                </div>
                <div className="flex min-w-0 flex-1 flex-col">
                  <div className="flex items-center gap-1 overflow-hidden">
                    <span className="truncate text-[12px] font-medium text-[var(--text-primary)]" title={displayName}>
                      {displayName}
                    </span>
                  </div>
                  <span className="truncate text-xs text-[var(--text-tertiary)]">{t("settings.personal", "Personal")}</span>
                </div>
              </div>
              <div className="flex-shrink-0 rounded-[6px] p-1 text-[var(--text-secondary)] transition group-hover:bg-[var(--surface-hover)]">
                <ChevronsUpDown size={16} />
              </div>
            </div>
          </div>
          <div className="px-[6px] pt-4">
            <div className="h-[1px] bg-[var(--border-subtle)]" />
          </div>
        </div>
      </div>

      <div className="mt-2 min-h-0 flex-1 overflow-y-auto px-4 pb-4">
        <div className="space-y-3">
        {SETTINGS_GROUPS.map((group) => (
          <nav key={group.titleKey} className="space-y-1">
            <div className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
              {t(group.titleKey, group.defaultTitle)}
            </div>
            {group.items.map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => onSectionChange(item.id)}
                  className={`flex w-full items-center gap-2.5 rounded-[12px] px-3 py-2 text-left text-[12px] leading-5 transition ${
                    section === item.id
                      ? "bg-[var(--surface-active)] font-medium text-[var(--surface-active-text)] shadow-sm"
                      : "text-[var(--text-soft)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
                  }`}
                >
                  <Icon size={15} strokeWidth={1.9} className="shrink-0" />
                  <span className="min-w-0 truncate">{t(item.labelKey, item.defaultLabel)}</span>
                </button>
              );
            })}
          </nav>
        ))}
        </div>
      </div>
    </aside>
  );
}
