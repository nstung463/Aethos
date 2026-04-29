import { Ellipsis, Moon, Share2, SunMedium, UsersRound } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useTheme } from "../context/ThemeContext";
import type { ChatThread } from "../types";
import { getModeConfig } from "../constants";
import ProjectPickerDropdown from "./ProjectPickerDropdown";

export default function Header({
  thread,
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
  backendMode: "sandbox" | "local";
  localRootDir: string;
  onBackendModeChange: (mode: "sandbox" | "local") => void;
  onImportLocalProject: () => void;
  projectHistory: string[];
  onSelectExistingProject: (path: string) => void;
  onRemoveProject: (path: string) => void;
  showConversationActions: boolean;
}) {
  const { t } = useTranslation();
  const { theme, toggleTheme } = useTheme();
  const mode = thread?.mode ?? "build";
  const modeConfig = getModeConfig(mode);

  return (
    <div className="flex shrink-0 min-w-0 items-center gap-2 overflow-hidden border-b border-[var(--border-subtle)] bg-[var(--app-bg)] px-3 py-2.5 sm:px-4 sm:py-3">
      <div className="flex min-w-0 flex-1 items-center gap-2">
        <h1 className="truncate text-[clamp(0.75rem,1.6vw,1rem)] font-medium text-[var(--text-primary)]">
          {thread?.title || t("chat.newConversation", "New conversation")}
        </h1>
        <span className="shrink-0 whitespace-nowrap rounded-full border border-[var(--border-subtle)] bg-[var(--surface-badge)] px-1.5 py-0.5 text-[9px] text-[var(--text-soft)]">
          {modeConfig.label}
        </span>
      </div>

      <div className="flex min-w-0 shrink items-center gap-1">
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
