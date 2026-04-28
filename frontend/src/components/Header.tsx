import { ChevronDown, Ellipsis, Moon, Share2, SunMedium, UsersRound } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useTheme } from "../context/ThemeContext";
import { useProfiles } from "../context/ProfilesContext";
import type { ChatThread } from "../types";
import { getModeConfig } from "../constants";
import ProjectPickerDropdown from "./ProjectPickerDropdown";

export default function Header({
  thread,
  onProfileChange,
  backendMode,
  localRootDir,
  onBackendModeChange,
  onImportLocalProject,
  projectHistory,
  onSelectExistingProject,
  onRemoveProject,
  showConversationActions,
}: {
  thread: ChatThread | null;
  onProfileChange: (profileId: string) => void;
  backendMode: "sandbox" | "local";
  localRootDir: string;
  onBackendModeChange: (mode: "sandbox" | "local") => void;
  onImportLocalProject: (files: File[]) => void;
  projectHistory: string[];
  onSelectExistingProject: (path: string) => void;
  onRemoveProject: (path: string) => void;
  showConversationActions: boolean;
}) {
  const { t } = useTranslation();
  const { theme, toggleTheme } = useTheme();
  const { profiles, activeProfileId } = useProfiles();
  const mode = thread?.mode ?? "build";
  const modeConfig = getModeConfig(mode);

  return (
    /**
     * Key responsive rules:
     * - Container: min-w-0 + overflow-hidden — allows the whole header to shrink
     * - Left title: min-w-0 + flex-1 — takes up available space, truncates
     * - Right controls: min-w-0 + flex-shrink — can shrink; no fixed min-w
     * - Profile select: no min-w; uses w-full inside a capped flex container
     * - Backend toggle text: hidden below a threshold via @container queries
     */
    <div className="flex shrink-0 min-w-0 items-center gap-2 border-b border-[var(--border-subtle)] bg-[var(--app-bg)] px-3 py-2.5 sm:px-4 sm:py-3 overflow-hidden">
      {/* ── Left: thread title + mode badge ── */}
      <div className="flex min-w-0 flex-1 items-center gap-2">
        <h1 className="truncate text-[clamp(0.75rem,1.6vw,1rem)] font-medium text-[var(--text-primary)]">
          {thread?.title || t("chat.newConversation", "New conversation")}
        </h1>
        <span className="shrink-0 whitespace-nowrap rounded-full border border-[var(--border-subtle)] bg-[var(--surface-badge)] px-1.5 py-0.5 text-[9px] text-[var(--text-soft)]">
          {modeConfig.label}
        </span>
      </div>

      {/* ── Right: controls — all allowed to shrink ── */}
      <div className="flex min-w-0 shrink items-center gap-1">

        {/* Conversation action buttons — icon-only, fixed 32×32 so always fit */}
        {showConversationActions ? (
          <>
            <button
              type="button"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-soft)] text-[var(--text-soft)] transition-all hover:border-[var(--border-strong)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] cursor-pointer"
              title={t("chat.shareConversation", "Share conversation")}
              aria-label={t("chat.shareConversation", "Share conversation")}
            >
              <Share2 size={15} strokeWidth={1.8} />
            </button>
            <button
              type="button"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-soft)] text-[var(--text-soft)] transition-all hover:border-[var(--border-strong)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] cursor-pointer"
              title={t("chat.conversationMembers", "Conversation members")}
              aria-label={t("chat.conversationMembers", "Conversation members")}
            >
              <UsersRound size={15} strokeWidth={1.8} />
            </button>
            <button
              type="button"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-soft)] text-[var(--text-soft)] transition-all hover:border-[var(--border-strong)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] cursor-pointer"
              title={t("chat.moreOptions", "More options")}
              aria-label={t("chat.moreOptions", "More options")}
            >
              <Ellipsis size={15} strokeWidth={1.8} />
            </button>
          </>
        ) : null}

        {/* Theme toggle — icon-only, always fixed */}
        <button
          type="button"
          onClick={toggleTheme}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-soft)] text-[var(--text-soft)] transition-all hover:border-[var(--border-strong)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] cursor-pointer"
          title={theme === "dark" ? t("chat.switchLightMode", "Switch to light mode") : t("chat.switchDarkMode", "Switch to dark mode")}
          aria-label={theme === "dark" ? t("chat.switchLightMode", "Switch to light mode") : t("chat.switchDarkMode", "Switch to dark mode")}
        >
          {theme === "dark" ? (
            <SunMedium size={15} strokeWidth={1.8} />
          ) : (
            <Moon size={15} strokeWidth={1.8} />
          )}
        </button>

        {/* Profile selector — no min-w, shrinks with container */}
        {profiles.length > 0 ? (
          <div className="relative min-w-0 shrink" style={{ flexBasis: "120px", flexShrink: 1, maxWidth: "160px" }}>
            <select
              value={activeProfileId}
              onChange={(e) => onProfileChange(e.target.value)}
              className="w-full min-w-0 appearance-none rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-soft)] py-1 pl-2 pr-5 text-[10px] text-[var(--text-secondary)] outline-none transition-all hover:border-[var(--border-strong)] hover:text-[var(--text-primary)] cursor-pointer sm:py-1.5 sm:text-xs"
              style={{ colorScheme: "inherit" }}
            >
              {profiles.map((p) => (
                <option key={p.id} value={p.id} className="bg-[var(--panel-elevated)] text-[var(--text-primary)]">
                  {p.name || p.model}
                </option>
              ))}
            </select>
            <ChevronDown size={10} strokeWidth={1.8} className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-[var(--text-faint)]" />
          </div>
        ) : (
          <span className="shrink-0 text-xs text-[var(--text-faint)]">{t("chat.noProfiles", "No profiles")}</span>
        )}

        {/* Backend mode toggle — text hidden at narrow widths via overflow */}
        <div
          className="flex shrink-0 items-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-soft)] p-0.5"
          title={t("chat.executionBackend", "Execution backend")}
        >
          <button
            type="button"
            onClick={() => onBackendModeChange("sandbox")}
            className={`rounded-md px-2 py-1 text-[10px] transition-all cursor-pointer sm:text-xs ${
              backendMode === "sandbox"
                ? "bg-[var(--surface-hover)] font-medium text-[var(--text-primary)]"
                : "text-[var(--text-faint)] hover:text-[var(--text-secondary)]"
            }`}
          >
            {t("chat.sandbox", "Sandbox")}
          </button>
          <button
            type="button"
            onClick={() => onBackendModeChange("local")}
            className={`rounded-md px-2 py-1 text-[10px] transition-all cursor-pointer sm:text-xs ${
              backendMode === "local"
                ? "bg-[var(--surface-hover)] font-medium text-[var(--text-primary)]"
                : "text-[var(--text-faint)] hover:text-[var(--text-secondary)]"
            }`}
          >
            {t("chat.local", "Local")}
          </button>
        </div>

        {/* Project picker dropdown — shrinks: shows only icon when narrow, full path when wide */}
        {backendMode === "local" ? (
          <ProjectPickerDropdown
            currentDir={localRootDir}
            history={projectHistory}
            onSelectExisting={onSelectExistingProject}
            onBrowse={onImportLocalProject}
            onRemoveProject={onRemoveProject}
          />
        ) : null}
      </div>
    </div>
  );
}
