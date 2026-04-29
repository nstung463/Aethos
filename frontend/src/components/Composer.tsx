import { ChangeEvent, FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowUp,
  Check,
  ChevronDown,
  Cloud,
  HardDrive,
  Mic,
  Monitor,
  Paperclip,
  PenTool,
  Plus,
  Puzzle,
  Square,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type {
  Attachment,
  ComposerMode,
  ModeConfig,
  ProviderProfile,
  ReasoningEffort,
} from "../types";
import {
  getModelReasoningCapabilities,
  type ThinkingBudgetPreset,
} from "../utils/reasoning";

function SlackLogo() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="h-3.5 w-3.5">
      <rect x="10.25" y="1.75" width="3.5" height="8" rx="1.75" fill="#36C5F0" />
      <rect x="14.25" y="10.25" width="8" height="3.5" rx="1.75" fill="#2EB67D" />
      <rect x="10.25" y="14.25" width="3.5" height="8" rx="1.75" fill="#ECB22E" />
      <rect x="1.75" y="10.25" width="8" height="3.5" rx="1.75" fill="#E01E5A" />
    </svg>
  );
}

function GoogleDriveLogo() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="h-3.5 w-3.5">
      <path d="M9 3h6l6 10h-6L9 3Z" fill="#0F9D58" />
      <path d="M9 3 3 13h6l6-10H9Z" fill="#4285F4" />
      <path d="M3 13 9 23h12l-6-10H3Z" fill="#F4B400" />
    </svg>
  );
}

function GoogleDocsLogo() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="h-3.5 w-3.5">
      <path d="M7 2.5h7.5L19 7v14a.5.5 0 0 1-.5.5h-11A2.5 2.5 0 0 1 5 19V5a2.5 2.5 0 0 1 2-2.45Z" fill="#4285F4" />
      <path d="M14.5 2.5V7H19l-4.5-4.5Z" fill="#AECBFA" />
      <rect x="8" y="10" width="8" height="1.5" rx=".75" fill="#E8F0FE" />
      <rect x="8" y="13" width="8" height="1.5" rx=".75" fill="#E8F0FE" />
      <rect x="8" y="16" width="6" height="1.5" rx=".75" fill="#E8F0FE" />
    </svg>
  );
}

function GmailLogo() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="h-3.5 w-3.5">
      <path d="M3.5 6.5 12 13l8.5-6.5V18a2 2 0 0 1-2 2h-1.75V10.2L12 13.7 7.25 10.2V20H5.5a2 2 0 0 1-2-2V6.5Z" fill="#EA4335" />
      <path d="M3.5 6.5A2 2 0 0 1 5.5 4.5H6l6 4.7 6-4.7h.5a2 2 0 0 1 2 2v.2L12 13 3.5 6.7v-.2Z" fill="#FBBC05" />
      <path d="M7.25 20V8.7l-3.75-2.2V18a2 2 0 0 0 2 2h1.75Z" fill="#34A853" />
      <path d="M16.75 20V8.7l3.75-2.2V18a2 2 0 0 1-2 2h-1.75Z" fill="#4285F4" />
    </svg>
  );
}

function GoogleCalendarLogo() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="h-3.5 w-3.5">
      <rect x="4" y="5" width="16" height="15" rx="3" fill="#4285F4" />
      <rect x="4" y="8" width="16" height="3.5" fill="#1A73E8" />
      <rect x="7" y="2.5" width="2" height="4" rx="1" fill="#34A853" />
      <rect x="15" y="2.5" width="2" height="4" rx="1" fill="#34A853" />
      <path d="M12 17.2c-2 0-3.4-1.2-3.4-2.95 0-1.83 1.53-3.08 3.63-3.08 1 0 1.9.24 2.54.7l-.7 1.3a3.15 3.15 0 0 0-1.72-.48c-.95 0-1.58.56-1.58 1.42 0 .84.63 1.4 1.56 1.4.78 0 1.31-.3 1.7-.94h-1.83v-1.2h3.64c.03.18.05.39.05.62 0 1.92-1.34 3.21-3.9 3.21Z" fill="#fff" />
    </svg>
  );
}

function getProfileDisplayName(profile: ProviderProfile): string {
  return profile.name.trim() || profile.model.trim() || profile.provider;
}

function getCompactModelLabel(profile: ProviderProfile | null): string {
  if (!profile) return "";
  const displayName = getProfileDisplayName(profile);
  const compactVersion = profile.model.match(/(?:gpt-|claude-|deepseek-)?(\d+(?:\.\d+)?)/i)?.[1];
  if (compactVersion && /gpt/i.test(profile.model)) {
    return compactVersion;
  }
  return displayName;
}

function getThinkingBudgetPreset(
  tokens: number | undefined,
  presets: ThinkingBudgetPreset[],
): ThinkingBudgetPreset | undefined {
  if (presets.length === 0) return undefined;
  if (!tokens) return presets.find((preset) => preset.id === "medium") ?? presets[0];
  return presets.reduce((closest, preset) => (
    Math.abs(preset.tokens - tokens) < Math.abs(closest.tokens - tokens) ? preset : closest
  ), presets[0]);
}

export default function Composer({
  draft,
  mode,
  modeConfig,
  variant,
  isStreaming,
  isUploading,
  profiles,
  activeProfile,
  activeProfileId,
  activeModel,
  attachments,
  status,
  error,
  suggestionPrompts,
  onChange,
  onSubmit,
  onStop,
  onUploadFiles,
  onRemoveAttachment,
  onModeChange,
  onProfileChange,
  onReasoningEffortChange,
  onThinkingBudgetChange,
  onSuggestion,
}: {
  draft: string;
  mode: ComposerMode;
  modeConfig: ModeConfig;
  variant: "landing" | "chat";
  isStreaming: boolean;
  isUploading: boolean;
  profiles: ProviderProfile[];
  activeProfile: ProviderProfile | null;
  activeProfileId: string;
  activeModel: string;
  attachments: Attachment[];
  status: string;
  error: string;
  suggestionPrompts: string[];
  onChange: (value: string) => void;
  onSubmit: (e?: FormEvent) => void;
  onStop: () => void;
  onUploadFiles: (files: File[]) => void;
  onRemoveAttachment: (attachmentId: string) => void;
  onModeChange: (mode: ComposerMode) => void;
  onProfileChange: (profileId: string) => void;
  onReasoningEffortChange: (reasoningEffort: ReasoningEffort) => void;
  onThinkingBudgetChange: (tokens: number) => void;
  onSuggestion: (text: string) => void;
}) {
  const { t } = useTranslation();
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const [profileMenuOpen, setProfileMenuOpen] = useState(false);
  const profileMenuRef = useRef<HTMLDivElement | null>(null);
  const [reasoningMenuOpen, setReasoningMenuOpen] = useState(false);
  const reasoningMenuRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const isLanding = variant === "landing";
  const reasoningCapabilities = useMemo(
    () => (
      activeProfile
        ? getModelReasoningCapabilities(activeProfile.provider, activeProfile.model)
        : null
    ),
    [activeProfile],
  );
  const activeReasoningControl = reasoningCapabilities?.control ?? "none";
  const supportsReasoningEffort = activeReasoningControl === "reasoning_effort";
  const supportsThinkingBudget = activeReasoningControl === "thinking_budget";
  const reasoningEffortOptions = reasoningCapabilities?.effortOptions ?? [];
  const activeReasoningEffort = reasoningEffortOptions.includes(activeProfile?.reasoningEffort ?? "medium")
    ? activeProfile?.reasoningEffort ?? "medium"
    : reasoningEffortOptions[0] ?? "medium";
  const thinkingBudgetPreset = getThinkingBudgetPreset(
    activeProfile?.thinkingBudgetTokens,
    reasoningCapabilities?.thinkingBudgetPresets ?? [],
  );
  const intelligenceLabel = supportsReasoningEffort
    ? t(`settings.reasoningEffortOption.${activeReasoningEffort}`, activeReasoningEffort)
    : supportsThinkingBudget
      ? t(`settings.reasoningEffortOption.${thinkingBudgetPreset?.id ?? "medium"}`, thinkingBudgetPreset?.id ?? "medium")
      : "";
  const intelligenceTitle = supportsThinkingBudget
    ? t("composer.thinkingBudget", "Thinking budget")
    : t("composer.intelligence", "Intelligence");
  const hasReasoningControl = supportsReasoningEffort || supportsThinkingBudget;
  const compactModelLabel = getCompactModelLabel(activeProfile);

  useEffect(() => {
    const node = textareaRef.current;
    if (!node) return;
    node.style.height = "0px";
    node.style.height = `${Math.min(node.scrollHeight, isLanding ? 260 : 200)}px`;
  }, [draft, isLanding]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
      if (profileMenuRef.current && !profileMenuRef.current.contains(e.target as Node)) {
        setProfileMenuOpen(false);
      }
      if (reasoningMenuRef.current && !reasoningMenuRef.current.contains(e.target as Node)) {
        setReasoningMenuOpen(false);
      }
    }
    if (menuOpen || profileMenuOpen || reasoningMenuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [menuOpen, profileMenuOpen, reasoningMenuOpen]);

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSubmit();
    }
  }

  function handleLocalFileClick() {
    fileInputRef.current?.click();
  }

  function handleFileInputChange(e: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    if (files.length > 0) {
      onUploadFiles(files);
    }
    e.target.value = "";
  }

  const canSend = (!!draft.trim() || attachments.length > 0) && !!activeModel && !isStreaming && !isUploading;
  const noProfile = !activeModel;
  const placeholder = isLanding ? t("composer.placeholder", "Delegate a task or ask a question...") : t("composer.placeholderChat", "Send message to Ethos");
  const composerMetaButtonClassName =
    "inline-flex items-center gap-1.5 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-soft)] px-2.5 py-1.5 text-xs text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]";
  const landingApps = [
    {
      label: "Slack",
      icon: SlackLogo,
      tint:
        "bg-[color-mix(in_oklab,#e01e5a_14%,var(--panel-raised))] text-[var(--text-secondary)] border-[color-mix(in_oklab,#e01e5a_26%,var(--border-subtle))]",
    },
    {
      label: "Drive",
      icon: GoogleDriveLogo,
      tint:
        "bg-[color-mix(in_oklab,#0f9d58_14%,var(--panel-raised))] text-[var(--text-secondary)] border-[color-mix(in_oklab,#4285f4_24%,var(--border-subtle))]",
    },
    {
      label: "Docs",
      icon: GoogleDocsLogo,
      tint:
        "bg-[color-mix(in_oklab,#4285f4_14%,var(--panel-raised))] text-[var(--text-secondary)] border-[color-mix(in_oklab,#4285f4_24%,var(--border-subtle))]",
    },
    {
      label: "Mail",
      icon: GmailLogo,
      tint:
        "bg-[color-mix(in_oklab,#ea4335_14%,var(--panel-raised))] text-[var(--text-secondary)] border-[color-mix(in_oklab,#ea4335_24%,var(--border-subtle))]",
    },
    {
      label: "Calendar",
      icon: GoogleCalendarLogo,
      tint:
        "bg-[color-mix(in_oklab,#1a73e8_14%,var(--panel-raised))] text-[var(--text-secondary)] border-[color-mix(in_oklab,#1a73e8_24%,var(--border-subtle))]",
    },
  ];
  const modelControls = profiles.length > 0 ? (
    <div className="flex min-w-0 items-center gap-2">
      <div className="relative min-w-0" ref={profileMenuRef}>
        <button
          type="button"
          onClick={() => {
            setProfileMenuOpen((open) => !open);
            setReasoningMenuOpen(false);
          }}
          className={`${composerMetaButtonClassName} max-w-[9rem] sm:max-w-[11rem]`}
          title={t("composer.changeModel", "Change model")}
        >
          <span className="truncate font-medium">{compactModelLabel || t("chat.noProfiles", "No profiles")}</span>
          <ChevronDown size={14} strokeWidth={1.9} className="shrink-0 text-[var(--text-faint)]" />
        </button>

        {profileMenuOpen ? (
          <div
            className="absolute bottom-full right-0 z-50 mb-2 w-72 rounded-2xl border border-[var(--border-strong)] bg-[var(--panel-elevated)] p-2 shadow-xl"
            style={{ boxShadow: "0 20px 45px var(--shadow-panel)" }}
          >
            <div className="px-2 pb-2 pt-1 text-xs font-medium text-[var(--text-soft)]">
              {t("composer.changeModel", "Change model")}
            </div>
            <div className="space-y-1">
              {profiles.map((profile) => {
                const isActive = profile.id === activeProfileId;
                return (
                  <button
                    key={profile.id}
                    type="button"
                    onClick={() => {
                      onProfileChange(profile.id);
                      setProfileMenuOpen(false);
                    }}
                    className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left transition-colors hover:bg-[var(--surface-hover)]"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium text-[var(--text-primary)]">
                        {getProfileDisplayName(profile)}
                      </div>
                      <div className="truncate text-xs text-[var(--text-soft)]">
                        {profile.provider} - {profile.model}
                      </div>
                    </div>
                    {isActive ? (
                      <Check size={16} strokeWidth={2.1} className="shrink-0 text-[var(--text-primary)]" />
                    ) : null}
                  </button>
                );
              })}
            </div>
          </div>
        ) : null}
      </div>

      {hasReasoningControl ? (
        <div className="relative" ref={reasoningMenuRef}>
          <button
            type="button"
            onClick={() => {
              setReasoningMenuOpen((open) => !open);
              setProfileMenuOpen(false);
            }}
            className={composerMetaButtonClassName}
            title={intelligenceTitle}
          >
            <span className="truncate">
              {intelligenceLabel}
            </span>
            <ChevronDown size={14} strokeWidth={1.9} className="shrink-0 text-[var(--text-faint)]" />
          </button>

          {reasoningMenuOpen ? (
            <div
              className="absolute bottom-full right-0 z-50 mb-2 w-56 rounded-2xl border border-[var(--border-strong)] bg-[var(--panel-elevated)] p-2 shadow-xl"
              style={{ boxShadow: "0 20px 45px var(--shadow-panel)" }}
            >
              <div className="px-2 pb-2 pt-1 text-xs font-medium text-[var(--text-soft)]">
                {intelligenceTitle}
              </div>
              <div className="space-y-1">
                {supportsReasoningEffort
                  ? reasoningCapabilities?.effortOptions.map((option) => {
                    const isActive = option === activeReasoningEffort;
                    return (
                      <button
                        key={option}
                        type="button"
                        onClick={() => {
                          onReasoningEffortChange(option);
                          setReasoningMenuOpen(false);
                        }}
                        className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left transition-colors hover:bg-[var(--surface-hover)]"
                      >
                        <div className="min-w-0 flex-1 text-sm text-[var(--text-primary)]">
                          {t(`settings.reasoningEffortOption.${option}`, option)}
                        </div>
                        {isActive ? (
                          <Check size={16} strokeWidth={2.1} className="shrink-0 text-[var(--text-primary)]" />
                        ) : null}
                      </button>
                    );
                  })
                  : reasoningCapabilities?.thinkingBudgetPresets.map((preset) => {
                    const isActive = preset.id === thinkingBudgetPreset?.id;
                    return (
                      <button
                        key={preset.id}
                        type="button"
                        onClick={() => {
                          onThinkingBudgetChange(preset.tokens);
                          setReasoningMenuOpen(false);
                        }}
                        className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left transition-colors hover:bg-[var(--surface-hover)]"
                      >
                        <div className="min-w-0 flex-1">
                          <div className="text-sm text-[var(--text-primary)]">
                            {t(`settings.reasoningEffortOption.${preset.id}`, preset.id)}
                          </div>
                          <div className="text-xs text-[var(--text-soft)]">
                            {preset.tokens.toLocaleString()} {t("composer.tokens", "tokens")}
                          </div>
                        </div>
                        {isActive ? (
                          <Check size={16} strokeWidth={2.1} className="shrink-0 text-[var(--text-primary)]" />
                        ) : null}
                      </button>
                    );
                  })}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  ) : (
    <div
      className={`${composerMetaButtonClassName} cursor-default text-[var(--danger)]`}
      title={t("composer.addProfileHint", "Add a profile in Settings")}
    >
      {t("chat.noProfiles", "No profiles")}
    </div>
  );

  return (
    <div className={variant === "chat" ? "bg-[var(--app-bg)]" : "w-full"}>
      {variant !== "chat" && (
        <div className="flex gap-1 flex-wrap items-center px-1 pb-3">
          <div className="flex-1" />

          <span
            className={`rounded-full px-2 py-1 text-xs ${
              error
                ? "text-[var(--danger)]"
                : isStreaming
                ? "text-[var(--success)]"
                : "text-[var(--text-faint)]"
            }`}
            style={
              error
                ? { background: "var(--danger-bg)" }
                : isStreaming
                  ? { background: "var(--success-bg)" }
                  : isLanding
                    ? { background: "var(--surface-soft)" }
                    : undefined
            }
          >
            {error || status}
          </span>
        </div>
      )}

      <form onSubmit={onSubmit} className={variant === "chat" ? "px-3 pb-2 sm:px-4 sm:pb-3 max-w-4xl mx-auto" : "px-0 py-0"}>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={handleFileInputChange}
        />

        {attachments.length > 0 ? (
          <div className="mb-2 flex flex-wrap gap-2">
            {attachments.map((attachment) => (
              <div
                key={attachment.id}
                className="flex items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-soft)] px-3 py-1 text-xs text-[var(--text-secondary)]"
              >
                <Paperclip size={12} strokeWidth={1.8} />
                <span className="max-w-40 truncate">{attachment.filename}</span>
                <button
                  type="button"
                  onClick={() => onRemoveAttachment(attachment.id)}
                  className="rounded-full p-0.5 text-[var(--text-faint)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
                  title={t("composer.removeAttachment", "Remove attachment")}
                >
                  <X size={12} strokeWidth={2} />
                </button>
              </div>
            ))}
          </div>
        ) : null}

        <div
          className={
            isLanding
              ? "rounded-[2rem] border border-[var(--border-subtle)] bg-[linear-gradient(180deg,color-mix(in_oklab,var(--panel-raised)_98%,transparent),color-mix(in_oklab,var(--panel-elevated)_94%,transparent))] p-2 shadow-[0_26px_90px_var(--shadow-panel)] ring-1 ring-[color-mix(in_oklab,var(--text-primary)_6%,transparent)] backdrop-blur-sm"
              : ""
          }
        >
          <div
            className={`flex gap-3 border border-[var(--border-subtle)] bg-[var(--panel-raised)] transition-colors focus-within:border-[var(--border-strong)] ${
              variant === "chat"
                ? "flex-col rounded-[22px] px-4 py-3 shadow-[0px_12px_32px_0px_rgba(0,0,0,0.02)] dark:shadow-none"
                : "flex-row items-end rounded-[26px] border-transparent px-4 py-4 shadow-[0_4px_18px_var(--shadow-panel)] sm:gap-3 sm:px-5 sm:py-5"
            }`}
          >
            {variant === "chat" ? (
              <>
                <div className="overflow-auto ps-4 pe-2 bg-transparent pt-[1px] border-0 focus-visible:ring-0 focus-visible:ring-offset-0 w-full placeholder:text-[var(--text-secondary)]">
                  <textarea
                    ref={textareaRef}
                    value={draft}
                    onChange={(e) => onChange(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder={placeholder}
                    rows={1}
                    className="flex-1 resize-none bg-transparent text-[var(--text-primary)] outline-none placeholder:text-[var(--text-secondary)] min-h-6 max-h-48 leading-6 w-full"
                    style={{ fontSize: "var(--message-text-size)" }}
                  />
                </div>

                <div className="px-3">
                  <div className="mb-[8px]"></div>
                  <div className="flex gap-2 items-center">
                    <div className="flex items-center flex-shrink-0 gap-2">
                      <div className="relative" ref={menuRef}>
                        <button
                          type="button"
                          onClick={() => setMenuOpen((o) => !o)}
                          className="rounded-full border border-[var(--border-subtle)] inline-flex items-center justify-center w-8 h-8 p-0 cursor-pointer hover:bg-[var(--surface-hover)] transition-colors"
                          style={{ color: "var(--text-secondary)" }}
                          title={t("composer.addAttachment", "Add attachment or action")}
                        >
                          <Plus size={16} strokeWidth={1.75} />
                        </button>

                        {menuOpen ? (
                          <div className="absolute bottom-full left-0 z-50 mb-2 w-56 rounded-xl border border-[var(--border-strong)] bg-[var(--panel-elevated)] py-1.5 shadow-xl" style={{ boxShadow: `0 20px 45px var(--shadow-panel)` }}>
                            {[
                              {
                                id: "drive",
                                label: t("composer.googleDrive", "Google Drive"),
                                icon: <Cloud size={16} strokeWidth={1.8} />,
                              },
                              {
                                id: "onedrive",
                                label: t("composer.oneDrive", "OneDrive"),
                                icon: <HardDrive size={16} strokeWidth={1.8} />,
                              },
                              {
                                id: "figma",
                                label: t("composer.figma", "Figma"),
                                icon: <PenTool size={16} strokeWidth={1.8} />,
                              },
                              {
                                id: "skills",
                                label: t("composer.useSkills", "Use Skills"),
                                icon: <Puzzle size={16} strokeWidth={1.8} />,
                              },
                              {
                                id: "local",
                                label: t("composer.addFromLocal", "Add from local files"),
                                icon: <Paperclip size={16} strokeWidth={1.8} />,
                              },
                            ].map((item) => (
                              <button
                                key={item.id}
                                type="button"
                                onClick={() => {
                                  if (item.id === "local") {
                                    handleLocalFileClick();
                                  }
                                  setMenuOpen(false);
                                }}
                                className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] cursor-pointer"
                              >
                                {item.icon}
                                <span>{item.label}</span>
                              </button>
                            ))}
                          </div>
                        ) : null}
                      </div>

                      <button
                        type="button"
                        className="flex items-center gap-1 p-2 cursor-pointer rounded-full border border-[var(--border-subtle)] hover:bg-[var(--surface-hover)] transition-colors"
                        style={{ color: "var(--text-secondary)" }}
                        title={t("composer.integrations", "Integrations")}
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="lucide lucide-cable">
                          <path d="M17 19a1 1 0 0 1-1-1v-2a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2a1 1 0 0 1-1 1z"></path>
                          <path d="M17 21v-2"></path>
                          <path d="M19 14V6.5a1 1 0 0 0-7 0v11a1 1 0 0 1-7 0V10"></path>
                          <path d="M21 21v-2"></path>
                          <path d="M3 5V3"></path>
                          <path d="M4 10a2 2 0 0 1-2-2V6a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2a2 2 0 0 1-2 2z"></path>
                          <path d="M7 5V3"></path>
                        </svg>
                      </button>

                      <button
                        type="button"
                        className="inline-flex items-center justify-center px-2 py-1.5 rounded-full border border-[var(--border-subtle)] hover:bg-[var(--surface-hover)] transition-colors cursor-pointer relative"
                        style={{ color: "var(--text-secondary)" }}
                        title={t("composer.screenShare", "Screen share")}
                      >
                        <div className="relative flex items-center justify-normal">
                          <span className="flex items-center">
                            <Monitor size={16} strokeWidth={2} />
                          </span>
                          <div role="button" className="size-6 items-center justify-center hidden rounded-full hover:bg-[var(--surface-hover)] absolute -start-2">
                            <X size={14} strokeWidth={2} />
                          </div>
                        </div>
                      </button>
                    </div>

                    <div className="ml-auto flex min-w-0 flex-shrink items-center gap-2">
                      <div className="flex items-center gap-2">
                        {modelControls}
                        <div className="flex items-center">
                          <button
                            type="button"
                            className="flex items-center justify-center cursor-pointer hover:bg-[var(--surface-hover)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] size-8 flex-shrink-0 rounded-full transition-colors"
                            title={t("composer.voiceMessage", "Voice message")}
                          >
                            <Mic size={16} strokeWidth={2} />
                          </button>
                        </div>
                        {isStreaming ? (
                          <button
                            type="button"
                            onClick={onStop}
                            className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-red-600 text-white hover:bg-red-700 transition-colors cursor-pointer"
                            title={t("composer.stopGeneration", "Stop generation")}
                          >
                            <Square size={15} fill="currentColor" strokeWidth={0} />
                          </button>
                        ) : (
                          <button
                            type="submit"
                            disabled={!canSend}
                            className="inline-flex items-center justify-center w-8 h-8 rounded-full cursor-pointer transition-colors hover:opacity-90"
                            style={{
                              backgroundColor: canSend ? "var(--text-primary)" : "var(--surface-hover-strong)",
                              color: canSend ? "var(--app-bg)" : "var(--text-secondary)",
                              opacity: canSend ? 1 : 0.6,
                              cursor: canSend ? "pointer" : "not-allowed",
                            }}
                            title={t("composer.sendMessage", "Send message")}
                          >
                            <ArrowUp size={15} strokeWidth={2.5} />
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <>
                <div className="relative shrink-0" ref={menuRef}>
                  <button
                    type="button"
                    onClick={() => setMenuOpen((o) => !o)}
                    className={`flex items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-soft)] text-[var(--text-faint)] transition-all hover:border-[var(--border-strong)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-secondary)] cursor-pointer h-10 w-10`}
                    title={t("composer.addAttachment", "Add attachment or action")}
                  >
                    <Plus size={16} strokeWidth={1.75} />
                  </button>

                  {menuOpen ? (
                    <div className="absolute bottom-full left-0 z-50 mb-2 w-56 rounded-xl border border-[var(--border-strong)] bg-[var(--panel-elevated)] py-1.5 shadow-xl" style={{ boxShadow: `0 20px 45px var(--shadow-panel)` }}>
                      {[
                        {
                          id: "drive",
                          label: t("composer.googleDrive", "Google Drive"),
                          icon: <Cloud size={16} strokeWidth={1.8} />,
                        },
                        {
                          id: "onedrive",
                          label: t("composer.oneDrive", "OneDrive"),
                          icon: <HardDrive size={16} strokeWidth={1.8} />,
                        },
                        {
                          id: "figma",
                          label: t("composer.figma", "Figma"),
                          icon: <PenTool size={16} strokeWidth={1.8} />,
                        },
                        {
                          id: "skills",
                          label: t("composer.useSkills", "Use Skills"),
                          icon: <Puzzle size={16} strokeWidth={1.8} />,
                        },
                        {
                          id: "local",
                          label: t("composer.addFromLocal", "Add from local files"),
                          icon: <Paperclip size={16} strokeWidth={1.8} />,
                        },
                      ].map((item) => (
                        <button
                          key={item.id}
                          type="button"
                          onClick={() => {
                            if (item.id === "local") {
                              handleLocalFileClick();
                            }
                            setMenuOpen(false);
                          }}
                          className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] cursor-pointer"
                        >
                          {item.icon}
                          <span>{item.label}</span>
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>

                <textarea
                  ref={textareaRef}
                  value={draft}
                  onChange={(e) => onChange(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={placeholder}
                  rows={1}
                  className="flex-1 resize-none bg-transparent text-[var(--text-primary)] outline-none placeholder:text-[var(--text-fainter)] min-h-[76px] max-h-64 leading-8"
                  style={{ fontSize: "1.05rem" }}
                />

                <div className="flex shrink-0 items-end gap-2">
                  {modelControls}
                </div>

                {isStreaming ? (
                  <button
                    type="button"
                    onClick={onStop}
                    className="flex shrink-0 items-center justify-center rounded-lg border text-[var(--danger)] transition-all cursor-pointer h-10 w-10"
                    style={{ background: "color-mix(in oklab, var(--danger) 12%, transparent)", borderColor: "color-mix(in oklab, var(--danger) 30%, transparent)" }}
                    title={t("composer.stopGeneration", "Stop generation")}
                  >
                    <Square size={16} fill="currentColor" strokeWidth={0} />
                  </button>
                ) : (
                  <button
                    type="submit"
                    disabled={!canSend}
                    className="flex shrink-0 items-center justify-center rounded-lg bg-[var(--text-primary)] text-[var(--app-bg)] transition-all hover:opacity-90 cursor-pointer disabled:cursor-not-allowed disabled:opacity-20 h-10 w-10"
                    title={t("composer.sendMessage", "Send message")}
                  >
                    <ArrowUp size={16} strokeWidth={1.9} />
                  </button>
                )}
              </>
            )}
          </div>

          {isLanding ? (
            <div className="mt-2 border-t border-[var(--border-subtle)] px-4 pb-3 pt-3 sm:px-5">
              <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-[var(--text-soft)]">
                <div className="min-w-0">
                  <span className="font-medium text-[var(--text-muted)]">{t("emptyState.useYourApps", "Use your apps with Ethos")}</span>
                </div>
                <div className="flex max-w-full flex-wrap items-center justify-end gap-2">
                  {landingApps.map(({ label, icon: Icon, tint }) => (
                    <span
                      key={label}
                      className={`flex shrink-0 items-center gap-2 rounded-full border px-2.5 py-1 text-xs text-[var(--text-secondary)] shadow-[inset_0_1px_0_color-mix(in_oklab,var(--text-primary)_5%,transparent)] ${tint}`}
                    >
                      <Icon />
                      {label}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          ) : null}
        </div>

        {variant !== "chat" && (
          <div className="mt-3 flex items-center justify-between px-1 text-xs text-[var(--text-faint)]">
            <span className={noProfile ? "text-[var(--danger)]" : undefined}>
              {noProfile ? t("composer.addProfileToChat", "Add a profile in Settings to start chatting") : activeModel}
            </span>
            <span>{t("composer.helpText", "Enter to send, Shift+Enter for a new line")}</span>
          </div>
        )}
      </form>
    </div>
  );
}
