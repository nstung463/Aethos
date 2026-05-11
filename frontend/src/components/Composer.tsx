import { ChangeEvent, FormEvent, KeyboardEvent, ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowUp,
  Cable,
  Check,
  ChevronDown,
  Cloud,
  FileText,
  HardDrive,
  Mic,
  Monitor,
  Paperclip,
  PenTool,
  Plus,
  Puzzle,
  Settings2,
  Square,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type {
  Attachment,
  ComposerMode,
  ConnectionInfo,
  ContextStatus,
  ExtensionSkill,
  ModeConfig,
  ProviderProfile,
  ReasoningEffort,
} from "../types";
import type { ComposerSendShortcut } from "../utils/generalPreferences";
import {
  getModelReasoningCapabilities,
  type ThinkingBudgetPreset,
} from "../utils/reasoning";
import {
  authorizeConnection,
  fetchConnections,
  updateConnectionTools,
} from "../utils/extensions";
import {
  filterSlashCommands,
  buildSlashCommands,
  getSlashMenuQuery,
  parseSlashCommand,
  COMPOSER_MODES,
  REASONING_EFFORT_VALUES,
  getReasoningEffortOptions,
  type SlashCommandDef,
  type SlashCommandOptionDef,
} from "../utils/slashCommands";
import SlashCommandMenu from "./SlashCommandMenu";
import { useThreadActions } from "../context/ThreadActionsContext";
import { isTrustedConnectionAuthMessage } from "./settings/oauthPopup";
import {
  GitHubLogo,
  GmailLogo,
  GoogleCalendarLogo,
  GoogleDocsLogo,
  GoogleDriveLogo,
  GoogleSheetsLogo,
  NotionLogo,
  OutlookLogo,
  SlackLogo,
} from "./ConnectorLogos";

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

const CONTEXT_CATEGORY_CLASS_NAMES: Record<string, string> = {
  system_prompt: "bg-[var(--accent)]",
  environment: "bg-[color-mix(in_oklab,var(--success)_78%,var(--text-primary))]",
  memory: "bg-[var(--warning,#f59e0b)]",
  mcp_instructions: "bg-[color-mix(in_oklab,var(--accent)_50%,var(--success))]",
  skills: "bg-[color-mix(in_oklab,var(--danger)_50%,var(--accent))]",
  messages: "bg-[color-mix(in_oklab,var(--accent)_58%,var(--text-primary))]",
  tools: "bg-[var(--danger)]",
  free: "bg-[color-mix(in_oklab,var(--surface-soft)_58%,var(--border-strong))]",
};

function getContextCategoryClassName(key: string): string {
  return CONTEXT_CATEGORY_CLASS_NAMES[key] ?? "bg-[var(--text-faint)]";
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
  localRootDir,
  composerSendShortcut,
  attachments,
  skills,
  contextStatus,
  status,
  error,
  suggestionPrompts,
  onChange,
  onSubmit,
  onStop,
  onUploadFiles,
  onRemoveAttachment,
  onUseSkills,
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
  localRootDir: string;
  composerSendShortcut: ComposerSendShortcut;
  attachments: Attachment[];
  skills: ExtensionSkill[];
  contextStatus: ContextStatus | null;
  status: string;
  error: string;
  suggestionPrompts: string[];
  onChange: (value: string) => void;
  onSubmit: (e?: FormEvent) => void;
  onStop: () => void;
  onUploadFiles: (files: File[]) => void;
  onRemoveAttachment: (attachmentId: string) => void;
  onUseSkills: () => void;
  onModeChange: (mode: ComposerMode) => void;
  onProfileChange: (profileId: string) => void;
  onReasoningEffortChange: (reasoningEffort: ReasoningEffort) => void;
  onThinkingBudgetChange: (tokens: number) => void;
  onSuggestion: (text: string) => void;
}) {
  const { t } = useTranslation();
  const { activeThreadId, onOpenSettings, onRenameThread, onToggleFavoriteThread, onMoveThreadToProject } = useThreadActions();
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [connectorsMenuOpen, setConnectorsMenuOpen] = useState(false);
  const [slashSelectedIndex, setSlashSelectedIndex] = useState(0);
  const [slashOptionCommand, setSlashOptionCommand] = useState<SlashCommandDef | null>(null);
  const [localDraft, setLocalDraft] = useState(draft);

  const slashQuery = getSlashMenuQuery(localDraft);
  const allSlashCommands = useMemo(() => buildSlashCommands(skills), [skills]);
  const slashCommands = slashQuery !== null ? filterSlashCommands(slashQuery, allSlashCommands) : [];
  const menuRef = useRef<HTMLDivElement | null>(null);
  const connectorsMenuRef = useRef<HTMLDivElement | null>(null);
  const [profileMenuOpen, setProfileMenuOpen] = useState(false);
  const profileMenuRef = useRef<HTMLDivElement | null>(null);
  const [reasoningMenuOpen, setReasoningMenuOpen] = useState(false);
  const reasoningMenuRef = useRef<HTMLDivElement | null>(null);
  const [contextMenuOpen, setContextMenuOpen] = useState(false);
  const contextMenuRef = useRef<HTMLDivElement | null>(null);
  const contextMenuCloseTimerRef = useRef<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const authPopupRef = useRef<Window | null>(null);
  const authPopupTimerRef = useRef<number | null>(null);
  const [connections, setConnections] = useState<ConnectionInfo[]>([]);
  const [connectionActionId, setConnectionActionId] = useState<string | null>(null);
  const isLanding = variant === "landing";
  const composerHelpText =
    composerSendShortcut === "mod_enter"
      ? t("composer.helpTextShortcut", "Enter for a new line, Ctrl/Cmd+Enter to send")
      : t("composer.helpText", "Enter to send, Shift+Enter for a new line");
  const loadNativeConnections = useCallback(async (signal?: AbortSignal) => {
    const items = await fetchConnections(localRootDir.trim() || undefined, signal);
    setConnections(items);
  }, [localRootDir]);

  useEffect(() => {
    const controller = new AbortController();
    loadNativeConnections(controller.signal).catch(() => setConnections([]));
    return () => controller.abort();
  }, [loadNativeConnections]);

  useEffect(() => {
    if (draft !== localDraft) {
      setLocalDraft(draft);
    }
  }, [draft, localDraft]);

  useEffect(() => {
    function handleConnectionUpdated(event: MessageEvent) {
      if (!isTrustedConnectionAuthMessage(event, authPopupRef.current, window.location.origin)) return;
      if (authPopupTimerRef.current !== null) {
        window.clearInterval(authPopupTimerRef.current);
        authPopupTimerRef.current = null;
      }
      authPopupRef.current = null;
      setConnectionActionId(null);
      void loadNativeConnections();
    }
    window.addEventListener("message", handleConnectionUpdated);
    return () => window.removeEventListener("message", handleConnectionUpdated);
  }, [loadNativeConnections]);

  useEffect(() => (
    () => {
      if (authPopupTimerRef.current !== null) {
        window.clearInterval(authPopupTimerRef.current);
      }
    }
  ), []);

  const providerMatchesConnection = useCallback((connection: ConnectionInfo, provider?: string) => {
    if (!provider) return false;
    if (provider === "google") {
      return connection.provider === "google" || connection.provider.startsWith("google-");
    }
    if (provider.startsWith("google-")) {
      return connection.provider === provider || connection.provider === "google";
    }
    return connection.provider === provider;
  }, []);

  const connectorItems = useMemo(() => {
    const defs = [
      {
        id: "gmail",
        label: t("composer.connectors.gmail", "Gmail"),
        provider: "google-gmail" as const,
        website: "https://mail.google.com",
        icon: <GmailLogo />,
      },
      {
        id: "drive",
        label: t("composer.connectors.googleDrive", "Google Drive"),
        provider: "google-drive" as const,
        website: "https://drive.google.com",
        icon: <GoogleDriveLogo />,
      },
      {
        id: "github",
        label: t("composer.connectors.github", "GitHub"),
        provider: null,
        website: "https://github.com",
        icon: <GitHubLogo />,
      },
      {
        id: "calendar",
        label: t("composer.connectors.googleCalendar", "Google Calendar"),
        provider: "google-calendar" as const,
        website: "https://calendar.google.com",
        icon: <GoogleCalendarLogo />,
      },
      {
        id: "sheets",
        label: t("composer.connectors.googleSheets", "Google Sheets"),
        provider: "google-sheets" as const,
        website: "https://sheets.google.com",
        icon: <GoogleSheetsLogo />,
      },
      {
        id: "outlook-mail",
        label: t("composer.connectors.outlookMail", "Outlook Mail"),
        provider: "microsoft-outlook-mail" as const,
        website: "https://outlook.live.com",
        icon: <OutlookLogo />,
      },
      {
        id: "outlook-calendar",
        label: t("composer.connectors.outlookCalendar", "Outlook Calendar"),
        provider: "microsoft-outlook-calendar" as const,
        website: "https://outlook.live.com/calendar",
        icon: <OutlookLogo />,
      },
      {
        id: "notion",
        label: t("composer.connectors.notion", "Notion"),
        provider: null,
        website: "https://www.notion.so",
        icon: <NotionLogo />,
      },
      {
        id: "slack",
        label: t("composer.connectors.slack", "Slack"),
        provider: null,
        website: "https://slack.com",
        icon: <SlackLogo />,
      },
      {
        id: "figma",
        label: t("composer.connectors.figmaApp", "Figma"),
        provider: null,
        website: "https://www.figma.com",
        icon: <PenTool size={14} strokeWidth={1.9} />,
      },
    ];
    const items = defs.map((connector) => {
      const connection = connector.provider
        ? connections.find((item) => item.provider === connector.provider)
          ?? connections.find((item) => providerMatchesConnection(item, connector.provider))
        : null;
      const isConnected = Boolean(connection && connection.status === "active");
      const toolsEnabled = Boolean(isConnected && connection?.tools_enabled);
      return {
        ...connector,
        connection,
        isConnected,
        toolsEnabled,
        action: connector.provider
          ? (isConnected ? t("composer.connectors.connected", "Connected") : t("composer.connectors.connect", "Connect"))
          : t("composer.connectors.connecting", "Coming soon"),
        actionTone: isConnected
          ? "bg-[color-mix(in_oklab,var(--success)_18%,transparent)] text-[var(--success)]"
          : connector.provider
            ? "text-[var(--text-secondary)]"
            : "text-[var(--text-tertiary)]",
      };
    });
    return items.sort((a, b) => {
      const aRank = a.isConnected ? 0 : a.provider ? 1 : 2;
      const bRank = b.isConnected ? 0 : b.provider ? 1 : 2;
      if (aRank !== bRank) return aRank - bRank;
      return a.label.localeCompare(b.label);
    });
  }, [connections, providerMatchesConnection, t]);
  const connectedConnectors = connectorItems.filter((connector) => connector.isConnected);
  const connectedConnectorIcons = connectedConnectors.slice(0, 2);
  const remainingConnectorCount = Math.max(0, connectedConnectors.length - connectedConnectorIcons.length);
  const popoverAnchorClassName = isLanding ? "top-full mt-2" : "bottom-full mb-2";
  const popoverShadowStyle = { boxShadow: "0 20px 45px var(--shadow-panel)" };
  const popoverMotionClassName = isLanding ? "popover-enter-down" : "popover-enter-up";
  const slashMenuMaxHeightClassName = isLanding
    ? "max-h-[min(18rem,calc(100vh-18rem))]"
    : "max-h-[min(24rem,calc(100vh-12rem))]";
  const contextMenuMaxHeightClassName = isLanding
    ? "max-h-[min(20rem,calc(100vh-18rem))]"
    : "max-h-[min(34rem,calc(100vh-10rem))]";
  const landingPopoverLayerClassName = isLanding ? "z-[80]" : "z-50";

  const handleOpenConnectionsSettings = useCallback(() => {
    setConnectorsMenuOpen(false);
    onOpenSettings("connections");
  }, [onOpenSettings]);

  const handleOpenConnectorSite = useCallback((url: string) => {
    window.open(url, "_blank", "noopener,noreferrer");
  }, []);

  const handleAuthorizeConnector = useCallback(async (provider: "google-gmail" | "google-drive" | "google-calendar" | "google-sheets" | "microsoft-outlook-mail" | "microsoft-outlook-calendar" | "slack") => {
    setConnectionActionId(provider);
    const popup = window.open("", "_blank");
    if (popup) {
      authPopupRef.current = popup;
    }
    try {
      const payload = await authorizeConnection(
        provider,
        localRootDir.trim() || undefined,
        popup ? undefined : window.location.href,
      );
      if (popup && !popup.closed) {
        popup.location.replace(payload.authorization_url);
        popup.focus();
      } else {
        window.location.assign(payload.authorization_url);
      }
      if (authPopupTimerRef.current !== null) {
        window.clearInterval(authPopupTimerRef.current);
      }
      authPopupTimerRef.current = window.setInterval(() => {
        if (authPopupRef.current && authPopupRef.current.closed) {
          window.clearInterval(authPopupTimerRef.current ?? undefined);
          authPopupTimerRef.current = null;
          authPopupRef.current = null;
          setConnectionActionId(null);
          void loadNativeConnections();
        }
      }, 600);
    } catch {
      if (popup && !popup.closed) {
        popup.close();
      }
      authPopupRef.current = null;
      setConnectionActionId(null);
      handleOpenConnectionsSettings();
    }
  }, [handleOpenConnectionsSettings, loadNativeConnections, localRootDir]);

  const handleToggleConnectorTools = useCallback(async (connection: ConnectionInfo, enabled: boolean) => {
    setConnectionActionId(connection.id);
    try {
      await updateConnectionTools(connection.id, enabled, localRootDir.trim() || undefined);
      await loadNativeConnections();
    } finally {
      setConnectionActionId(null);
    }
  }, [handleOpenConnectionsSettings, loadNativeConnections, localRootDir]);
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
  const slashOptionValues = reasoningEffortOptions.length > 0
    ? reasoningEffortOptions
    : REASONING_EFFORT_VALUES;
  const slashCommandOptions = slashOptionCommand?.name === "think"
    ? getReasoningEffortOptions(slashOptionValues)
    : [];
  const slashMenuVisible = slashOptionCommand
    ? slashCommandOptions.length > 0
    : slashCommands.length > 0;
  const slashMenuItemCount = slashOptionCommand
    ? slashCommandOptions.length
    : slashCommands.length;
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

  const syncDraft = useCallback((value: string) => {
    setLocalDraft(value);
    onChange(value);
  }, [onChange]);

  const doExecuteSlashCommand = useCallback((command: SlashCommandDef, args: string) => {
    if (COMPOSER_MODES.includes(command.name as ComposerMode)) {
      onModeChange(command.name as ComposerMode);
    } else if (command.name === "rename" && args && activeThreadId) {
      onRenameThread(activeThreadId, args);
    } else if (command.name === "favorite" && activeThreadId) {
      onToggleFavoriteThread(activeThreadId);
    } else if (command.name === "project" && args && activeThreadId) {
      onMoveThreadToProject(activeThreadId, args);
    } else if (command.name === "think") {
      const effort = args.toLowerCase() as ReasoningEffort;
      if (REASONING_EFFORT_VALUES.includes(effort)) {
        onReasoningEffortChange(effort);
      }
    } else if (command.name === "context") {
      setContextMenuOpen(true);
      setProfileMenuOpen(false);
      setReasoningMenuOpen(false);
    }
    setSlashOptionCommand(null);
    syncDraft("");
  }, [
    activeThreadId,
    onModeChange,
    onRenameThread,
    onToggleFavoriteThread,
    onMoveThreadToProject,
    onReasoningEffortChange,
    syncDraft,
  ]);

  const handleSlashSelect = useCallback((command: SlashCommandDef) => {
    if (command.type === "immediate") {
      doExecuteSlashCommand(command, "");
    } else if (command.argInput === "select") {
      setSlashOptionCommand(command);
      setSlashSelectedIndex(0);
      syncDraft(`/${command.name}`);
      textareaRef.current?.focus();
    } else {
      syncDraft(`/${command.name} `);
      setSlashSelectedIndex(0);
      textareaRef.current?.focus();
    }
  }, [doExecuteSlashCommand, syncDraft]);

  const handleSlashOptionSelect = useCallback((option: SlashCommandOptionDef) => {
    if (!slashOptionCommand) return;
    doExecuteSlashCommand(slashOptionCommand, option.value);
  }, [doExecuteSlashCommand, slashOptionCommand]);

  const executeDraftSlashCommand = useCallback(() => {
    const parsed = parseSlashCommand(localDraft.trim(), allSlashCommands);
    if (!parsed) return false;
    if (parsed.command.category === "skill") return false;

    if (parsed.command.type === "with-args") {
      if (parsed.command.argInput === "select") {
        const selectedValue = parsed.args.toLowerCase() as ReasoningEffort;
        if (slashOptionValues.includes(selectedValue)) {
          doExecuteSlashCommand(parsed.command, selectedValue);
        } else {
          setSlashOptionCommand(parsed.command);
          setSlashSelectedIndex(0);
        }
        return true;
      }
      if (parsed.args) {
        doExecuteSlashCommand(parsed.command, parsed.args);
      }
      return true;
    }

    if (parsed.args) return false;
    doExecuteSlashCommand(parsed.command, "");
    return true;
  }, [allSlashCommands, doExecuteSlashCommand, localDraft, slashOptionValues]);

  useEffect(() => {
    const node = textareaRef.current;
    if (!node) return;

    const frame = window.requestAnimationFrame(() => {
      const maxHeight = isLanding ? 260 : 200;
      node.style.height = "auto";
      const nextHeight = Math.min(node.scrollHeight, maxHeight);
      if (node.style.height !== `${nextHeight}px`) {
        node.style.height = `${nextHeight}px`;
      }
    });

    return () => window.cancelAnimationFrame(frame);
  }, [localDraft, isLanding]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
      if (connectorsMenuRef.current && !connectorsMenuRef.current.contains(e.target as Node)) {
        setConnectorsMenuOpen(false);
      }
      if (profileMenuRef.current && !profileMenuRef.current.contains(e.target as Node)) {
        setProfileMenuOpen(false);
      }
      if (reasoningMenuRef.current && !reasoningMenuRef.current.contains(e.target as Node)) {
        setReasoningMenuOpen(false);
      }
      if (contextMenuRef.current && !contextMenuRef.current.contains(e.target as Node)) {
        setContextMenuOpen(false);
      }
    }
    if (menuOpen || connectorsMenuOpen || profileMenuOpen || reasoningMenuOpen || contextMenuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [connectorsMenuOpen, contextMenuOpen, menuOpen, profileMenuOpen, reasoningMenuOpen]);

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (slashMenuVisible) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSlashSelectedIndex((i) => Math.min(i + 1, slashMenuItemCount - 1));
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setSlashSelectedIndex((i) => Math.max(i - 1, 0));
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        setSlashOptionCommand(null);
        syncDraft("");
        return;
      }
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (slashOptionCommand) {
          const selectedOption = slashCommandOptions[slashSelectedIndex];
          if (selectedOption) handleSlashOptionSelect(selectedOption);
        } else {
          const selected = slashCommands[slashSelectedIndex];
          if (selected) handleSlashSelect(selected);
        }
        return;
      }
      if (e.key === "Tab") {
        e.preventDefault();
        if (slashOptionCommand) {
          const selectedOption = slashCommandOptions[slashSelectedIndex];
          if (selectedOption) handleSlashOptionSelect(selectedOption);
        } else {
          const selected = slashCommands[slashSelectedIndex];
          if (selected) handleSlashSelect(selected);
        }
        return;
      }
    }

    if (e.key === "Enter" && !e.shiftKey) {
      if (executeDraftSlashCommand()) {
        e.preventDefault();
        return;
      }
    }

    const shouldSend =
      composerSendShortcut === "enter"
        ? e.key === "Enter" && !e.shiftKey
        : e.key === "Enter" && (e.metaKey || e.ctrlKey);

    if (shouldSend) {
      e.preventDefault();
      onSubmit();
    }
  }

  function handleSubmit(e: FormEvent) {
    if (slashOptionCommand) {
      const selectedOption = slashCommandOptions[slashSelectedIndex];
      if (selectedOption) {
        e.preventDefault();
        handleSlashOptionSelect(selectedOption);
        return;
      }
    }
    if (executeDraftSlashCommand()) {
      e.preventDefault();
      return;
    }
    onSubmit(e);
  }

  function handleDraftChange(value: string) {
    const parsed = parseSlashCommand(value.trim(), allSlashCommands);
    const nextOptionCommand = parsed?.command.argInput === "select" && value.includes(" ")
      ? parsed.command
      : (!slashOptionCommand || value !== `/${slashOptionCommand.name}` ? null : slashOptionCommand);

    if (nextOptionCommand !== slashOptionCommand) {
      setSlashOptionCommand(nextOptionCommand);
    }
    setSlashSelectedIndex((index) => (index === 0 ? index : 0));
    syncDraft(value);
  }

  function handleLocalFileClick() {
    fileInputRef.current?.click();
  }

  const connectorsMenu = (
    <div
      className={`absolute left-0 ${landingPopoverLayerClassName} ${popoverMotionClassName} flex w-[320px] max-w-[min(420px,calc(100vw-2rem))] flex-col overflow-hidden rounded-[14px] border border-[var(--border-strong)] bg-[var(--panel-elevated)] shadow-xl ${popoverAnchorClassName}`}
      style={popoverShadowStyle}
    >
      <div className={`${isLanding ? "max-h-[min(16rem,calc(100vh-20rem))]" : "max-h-[320px]"} overflow-y-auto p-1.5`}>
        {connectorItems.map((connector) => (
          <div
            key={connector.id}
            className="group flex items-center justify-between gap-3 rounded-[10px] px-2 py-1.5 transition-colors hover:bg-[var(--surface-hover)]"
          >
            <div className="flex min-w-0 items-center gap-2">
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[8px] border border-[var(--border-subtle)] bg-[var(--surface-soft)] text-[var(--text-primary)]">
                {connector.icon}
              </div>
              <span className="truncate text-sm text-[var(--text-primary)]">{connector.label}</span>
            </div>

            <div className="flex shrink-0 items-center gap-1">
              <button
                type="button"
                onClick={handleOpenConnectionsSettings}
                className="flex h-7 w-7 items-center justify-center rounded-[8px] text-[var(--text-faint)] opacity-0 transition-all group-hover:opacity-100 hover:bg-[var(--surface-soft)] hover:text-[var(--text-primary)] cursor-pointer"
                title={t("composer.connectors.manageInSettings", "Manage in Connections settings")}
                aria-label={t("composer.connectors.manageInSettings", "Manage in Connections settings")}
              >
                <Settings2 size={15} strokeWidth={1.9} />
              </button>
              {connector.isConnected ? (
                <button
                  type="button"
                  role="switch"
                  aria-checked={connector.toolsEnabled}
                  onClick={() => {
                    if (connector.connection) {
                      void handleToggleConnectorTools(connector.connection, !connector.toolsEnabled);
                    }
                  }}
                  disabled={connectionActionId === connector.connection?.id}
                  className="group flex items-center gap-2 cursor-pointer disabled:cursor-wait disabled:opacity-80"
                  tabIndex={-1}
                  title={connector.toolsEnabled
                    ? t("composer.connectors.disableTools", "Disable tools for this connection")
                    : t("composer.connectors.enableTools", "Enable tools for this connection")}
                  aria-label={connector.toolsEnabled
                    ? t("composer.connectors.disableTools", "Disable tools for this connection")
                    : t("composer.connectors.enableTools", "Enable tools for this connection")}
                >
                  <div className={`h-[16px] w-[26px] rounded-[16px] px-[1px] transition-colors ${connector.toolsEnabled ? "bg-[var(--icon-blue)]" : "bg-[var(--surface-hover-strong)]"}`}>
                    <span className={`block size-3.5 translate-y-[1px] rounded-full bg-[var(--text-white)] shadow-[0_1px_3px_color-mix(in_oklab,var(--shadow-panel)_45%,transparent)] ring-1 ring-[color-mix(in_oklab,var(--text-white)_70%,transparent)] transition-transform pointer-events-none ${connector.toolsEnabled ? "translate-x-2.5 rtl:-translate-x-2.5" : "translate-x-0"}`} />
                  </div>
                </button>
              ) : (
                connector.provider ? (
                  <button
                    type="button"
                    onClick={() => {
                      void handleAuthorizeConnector(connector.provider);
                    }}
                    className={`rounded-full px-2.5 py-1 text-[12px] font-medium transition-colors cursor-pointer hover:bg-[var(--surface-soft)] ${connector.actionTone}`}
                  >
                    {connectionActionId === connector.provider ? t("composer.connectors.connecting", "Connecting...") : connector.action}
                  </button>
                ) : (
                  <span className={`rounded-full px-2.5 py-1 text-[12px] font-medium ${connector.actionTone}`}>
                    {connector.action}
                  </span>
                )
              )}
              <button
                type="button"
                onClick={() => handleOpenConnectorSite(connector.website)}
                className="flex h-7 w-7 items-center justify-center rounded-[8px] text-[var(--text-faint)] transition-colors hover:bg-[var(--surface-soft)] hover:text-[var(--text-primary)] cursor-pointer"
                title={t("composer.connectors.openSite", "Open")}
                aria-label={`${t("composer.connectors.openSite", "Open")} ${connector.label}`}
              >
                <ArrowUp size={14} strokeWidth={1.9} className="rotate-45" />
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className="border-t border-[var(--border-subtle)] p-1.5">
        <button
          type="button"
          onClick={handleOpenConnectionsSettings}
          className="flex h-10 w-full items-center justify-between rounded-[10px] px-2.5 text-left transition-colors hover:bg-[var(--surface-hover)] cursor-pointer"
        >
          <div className="flex items-center gap-2">
            <div className="flex h-5 w-5 items-center justify-center text-[var(--text-primary)]">
              <Plus size={15} strokeWidth={2} />
            </div>
            <span className="text-sm text-[var(--text-primary)]">
              {t("composer.connectors.addConnectors", "Add connectors")}
            </span>
          </div>
          <div className="flex items-center -space-x-1.5">
            {connectedConnectorIcons.map((connector) => (
              <div
                key={connector.id}
                className="flex h-6 w-6 items-center justify-center rounded-full border border-[var(--border-strong)] bg-[var(--panel-elevated)] text-[var(--text-primary)]"
              >
                {connector.icon}
              </div>
            ))}
            {remainingConnectorCount > 0 ? (
              <div className="flex h-6 min-w-6 items-center justify-center rounded-full border border-[var(--border-strong)] bg-[var(--panel-elevated)] px-1.5 text-[10px] text-[var(--text-tertiary)]">
                {`+${remainingConnectorCount}`}
              </div>
            ) : null}
          </div>
        </button>
        <button
          type="button"
          onClick={handleOpenConnectionsSettings}
          className="flex h-10 w-full items-center gap-2 rounded-[10px] px-2.5 text-left transition-colors hover:bg-[var(--surface-hover)] cursor-pointer"
        >
          <div className="flex h-5 w-5 items-center justify-center text-[var(--text-primary)]">
            <Cable size={15} strokeWidth={1.9} />
          </div>
          <span className="text-sm text-[var(--text-primary)]">
            {t("composer.connectors.manageConnectors", "Manage connectors")}
          </span>
        </button>
      </div>
    </div>
  );

  function handleFileInputChange(e: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    if (files.length > 0) {
      onUploadFiles(files);
    }
    e.target.value = "";
  }

  const canSend = (!!draft.trim() || attachments.length > 0) && !!activeModel && !isStreaming && !isUploading;
  const noProfile = !activeModel;
  const placeholder = isLanding ? t("composer.placeholder", "Delegate a task or ask a question...") : t("composer.placeholderChat", "Send message to Aethos");
  const contextPercent = contextStatus?.percent_used ?? 0;
  const contextRingColor = contextPercent >= 85
    ? "var(--danger)"
    : contextPercent >= 65
      ? "var(--warning, #f59e0b)"
      : "var(--text-secondary)";
  const formatTokenCount = (value: number | undefined) => {
    if (value === undefined) return t("composer.contextTokenUnknown", "Unknown");
    if (value === 0) return "0";
    if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(value >= 10_000_000 ? 0 : 1)}M`;
    if (value >= 1_000) return `${Math.round(value / 1_000)}k`;
    return String(value);
  };
  const contextCategories = contextStatus?.categories ?? [];
  const visibleContextCategories = contextCategories.filter((category) => category.key !== "free" && category.tokens > 0);
  const freeContextCategory = contextCategories.find((category) => category.key === "free");
  const contextGridRows = contextStatus?.grid_rows ?? [];
  const contextSuggestions = contextStatus?.suggestions ?? [];
  const cancelContextMenuClose = () => {
    if (contextMenuCloseTimerRef.current !== null) {
      window.clearTimeout(contextMenuCloseTimerRef.current);
      contextMenuCloseTimerRef.current = null;
    }
  };
  const scheduleContextMenuClose = () => {
    cancelContextMenuClose();
    contextMenuCloseTimerRef.current = window.setTimeout(() => {
      setContextMenuOpen(false);
      contextMenuCloseTimerRef.current = null;
    }, 140);
  };
  const contextControls = (
    <div
      className="relative"
      ref={contextMenuRef}
      onMouseEnter={() => {
        cancelContextMenuClose();
        setContextMenuOpen(true);
        setProfileMenuOpen(false);
        setReasoningMenuOpen(false);
      }}
      onMouseLeave={scheduleContextMenuClose}
    >
      <button
        type="button"
        onFocus={() => {
          cancelContextMenuClose();
          setContextMenuOpen(true);
          setProfileMenuOpen(false);
          setReasoningMenuOpen(false);
        }}
        onBlur={scheduleContextMenuClose}
        className="flex size-8 shrink-0 items-center justify-center rounded-full text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
        title={t("composer.contextStatus", "Context status")}
        aria-label={t("composer.contextStatus", "Context status")}
      >
        <span
          className="flex size-5 items-center justify-center rounded-full"
          style={{
            background: `conic-gradient(${contextRingColor} ${Math.max(4, contextPercent)}%, var(--border-subtle) 0)`,
          }}
        >
          <span className="size-3 rounded-full bg-[var(--panel-raised)]" />
        </span>
      </button>

      {contextMenuOpen ? (
        <div
          className={`absolute left-1/2 ${landingPopoverLayerClassName} ${contextMenuMaxHeightClassName} ${popoverMotionClassName} w-[min(30rem,calc(100vw-2rem))] -translate-x-1/2 overflow-y-auto rounded-2xl border border-[var(--border-strong)] bg-[var(--panel-elevated)] p-3 text-left shadow-xl ${popoverAnchorClassName}`}
          style={popoverShadowStyle}
          onMouseEnter={cancelContextMenuClose}
          onMouseLeave={scheduleContextMenuClose}
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-xs font-semibold text-[var(--text-soft)]">
                {t("composer.contextWindow", "Context window")}
              </div>
              <div className="mt-0.5 text-lg font-semibold text-[var(--text-primary)]">
                {contextStatus ? t("composer.contextPercentFull", "{{percent}}% full", { percent: contextStatus.percent_used }) : t("composer.contextUnavailable", "Unavailable")}
              </div>
              <div className="mt-1 text-xs font-medium text-[var(--text-primary)]">
                {contextStatus
                  ? t("composer.contextTokensUsed", "{{used}} / {{total}} tokens used", {
                      used: formatTokenCount(contextStatus.used_tokens),
                      total: formatTokenCount(contextStatus.context_window),
                    })
                  : t("composer.contextSelectProject", "Select a local project to inspect context.")}
              </div>
            </div>
            {contextStatus?.is_estimated ? (
              <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-soft)] px-2 py-1 text-[11px] font-medium text-[var(--text-faint)]">
                {t("composer.contextEstimated", "Estimated")}
              </span>
            ) : null}
          </div>

          {contextStatus ? (
            <div className="mt-3 flex gap-4">
              <div className="grid shrink-0 grid-cols-10 gap-0.5 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-soft)] p-2">
                {contextGridRows.flatMap((row, rowIndex) =>
                  row.map((square, colIndex) => (
                    <span
                      key={`${rowIndex}-${colIndex}`}
                      className={`size-2.5 rounded-[3px] border border-[color-mix(in_oklab,var(--text-primary)_16%,transparent)] ${getContextCategoryClassName(square.category_key)}`}
                      title={t(`context.categories.${square.category_key}`, square.category_label)}
                    />
                  )),
                )}
              </div>
              <div className="min-w-0 flex-1">
                <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-faint)]">
                  {t("context.usageByCategory", "Estimated usage by category")}
                </div>
                <div className="space-y-1">
                  {visibleContextCategories.map((category) => (
                    <div key={category.key} className="flex items-center gap-2 text-xs">
                      <span className={`size-2.5 rounded-full border border-[color-mix(in_oklab,var(--text-primary)_18%,transparent)] ${getContextCategoryClassName(category.key)}`} />
                      <span className="min-w-0 flex-1 truncate text-[var(--text-primary)]">
                        {t(`context.categories.${category.key}`, category.label)}
                      </span>
                      <span className="shrink-0 text-[var(--text-faint)]">
                        {formatTokenCount(category.tokens)} ({category.percent.toFixed(1)}%)
                      </span>
                    </div>
                  ))}
                  {freeContextCategory ? (
                    <div className="flex items-center gap-2 text-xs">
                      <span className={`size-2.5 rounded-full border border-[color-mix(in_oklab,var(--text-primary)_18%,transparent)] ${getContextCategoryClassName("free")}`} />
                      <span className="min-w-0 flex-1 truncate text-[var(--text-soft)]">
                        {t("context.categories.free", freeContextCategory.label)}
                      </span>
                      <span className="shrink-0 text-[var(--text-faint)]">
                        {formatTokenCount(freeContextCategory.tokens)} ({freeContextCategory.percent.toFixed(1)}%)
                      </span>
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
          ) : null}

          <div className="mt-3 rounded-xl bg-[var(--surface-soft)] px-3 py-2 text-xs font-medium leading-5 text-[var(--text-primary)]">
            {t("composer.contextCompaction", "Aethos automatically compacts its context")}
          </div>

          {contextSuggestions.length > 0 ? (
            <div className="mt-3 border-t border-[var(--border-subtle)] pt-2">
              <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-faint)]">
                {t("context.suggestions.title", "Suggestions")}
              </div>
              <div className="space-y-1.5">
                {contextSuggestions.map((suggestion) => (
                  <div key={`${suggestion.title_key}-${suggestion.tokens}`} className="flex gap-2 rounded-lg bg-[var(--surface-soft)] px-2 py-1.5 text-xs">
                    <AlertTriangle
                      size={14}
                      strokeWidth={1.9}
                      className={suggestion.severity === "warning" ? "mt-0.5 shrink-0 text-[var(--danger)]" : "mt-0.5 shrink-0 text-[var(--text-soft)]"}
                    />
                    <div className="min-w-0">
                      <div className="font-semibold text-[var(--text-primary)]">
                        {t(suggestion.title_key, t("context.suggestions.defaultTitle", "Context suggestion"))}
                        {suggestion.tokens > 0 ? ` · ${formatTokenCount(suggestion.tokens)}` : ""}
                      </div>
                      <div className="text-[var(--text-soft)]">
                        {t(suggestion.detail_key, t("context.suggestions.defaultDetail", "Review context usage before continuing."))}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <div className="mt-3 border-t border-[var(--border-subtle)] pt-2 text-left">
            <div className="mb-1.5 text-[11px] font-semibold uppercase text-[var(--text-faint)]">
              {t("composer.activatedRules", "Activated rules")}
            </div>
            {contextStatus?.activated_rules.length ? (
              <div className="max-h-32 space-y-0.5 overflow-y-auto pr-1">
                {contextStatus.activated_rules.map((rule) => (
                  <div key={`${rule.path}-${rule.source}`} className="flex items-start gap-1.5 rounded-md px-1.5 py-1 text-[11px] text-[var(--text-secondary)]">
                    <FileText size={12} strokeWidth={1.8} className="mt-0.5 shrink-0 text-[var(--text-faint)]" />
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-medium text-[var(--text-primary)]">{rule.name}</div>
                      <div className="truncate text-[var(--text-faint)]">{rule.path}</div>
                    </div>
                    <span className="shrink-0 text-[var(--text-faint)]">{formatTokenCount(rule.tokens)}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-lg bg-[var(--surface-soft)] px-2 py-1.5 text-[11px] text-[var(--text-soft)]">
                {t("composer.noActivatedRules", "No project rule files loaded.")}
              </div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
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
            className={`absolute right-0 ${landingPopoverLayerClassName} ${popoverMotionClassName} ${isLanding ? "max-h-[min(16rem,calc(100vh-20rem))] overflow-y-auto" : ""} w-72 rounded-2xl border border-[var(--border-strong)] bg-[var(--panel-elevated)] p-2 shadow-xl ${popoverAnchorClassName}`}
            style={popoverShadowStyle}
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
              className={`absolute right-0 ${landingPopoverLayerClassName} ${popoverMotionClassName} ${isLanding ? "max-h-[min(16rem,calc(100vh-20rem))] overflow-y-auto" : ""} w-56 rounded-2xl border border-[var(--border-strong)] bg-[var(--panel-elevated)] p-2 shadow-xl ${popoverAnchorClassName}`}
              style={popoverShadowStyle}
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

      <form onSubmit={handleSubmit} className={variant === "chat" ? "relative px-3 pb-2 sm:px-4 sm:pb-3 max-w-4xl mx-auto" : "relative px-0 py-0"}>
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
                : "flex-col items-stretch rounded-[26px] border-transparent px-4 py-4 shadow-[0_4px_18px_var(--shadow-panel)] sm:gap-3 sm:px-5 sm:py-5"
            }`}
          >
            {variant === "chat" ? (
              <>
                <div className="relative w-full">
                  {slashMenuVisible ? (
                    <SlashCommandMenu
                      commands={slashCommands}
                      options={slashCommandOptions}
                      optionCommand={slashOptionCommand}
                      selectedIndex={slashSelectedIndex}
                      onSelect={handleSlashSelect}
                      onSelectOption={handleSlashOptionSelect}
                      direction="up"
                      maxHeightClassName={slashMenuMaxHeightClassName}
                    />
                  ) : null}
                  <div className="overflow-auto ps-4 pe-2 bg-transparent pt-[1px] border-0 focus-visible:ring-0 focus-visible:ring-offset-0 w-full placeholder:text-[var(--text-secondary)]">
                    <textarea
                      ref={textareaRef}
                      value={localDraft}
                      onChange={(e) => {
                        handleDraftChange(e.target.value);
                      }}
                      onKeyDown={handleKeyDown}
                      placeholder={placeholder}
                      rows={1}
                      className={`relative z-10 flex-1 resize-none bg-transparent caret-[var(--text-primary)] outline-none placeholder:text-[var(--text-secondary)] min-h-6 max-h-48 leading-6 w-full text-[var(--text-primary)]`}
                      style={{ fontSize: "var(--message-text-size)" }}
                    />
                  </div>
                </div>

                <div className="px-3">
                  <div className="mb-[8px]"></div>
                  <div className="flex gap-2 items-center">
                    <div className="flex items-center flex-shrink-0 gap-2">
                      <div className="relative" ref={menuRef}>
                        <button
                          type="button"
                          onClick={() => {
                            setMenuOpen((open) => !open);
                            setConnectorsMenuOpen(false);
                          }}
                          className="rounded-full border border-[var(--border-subtle)] inline-flex items-center justify-center w-8 h-8 p-0 cursor-pointer hover:bg-[var(--surface-hover)] transition-colors"
                          style={{ color: "var(--text-secondary)" }}
                          title={t("composer.addAttachment", "Add attachment or action")}
                        >
                          <Plus size={16} strokeWidth={1.75} />
                        </button>

                        {menuOpen ? (
                          <div className={`absolute left-0 ${landingPopoverLayerClassName} ${popoverMotionClassName} w-56 rounded-xl border border-[var(--border-strong)] bg-[var(--panel-elevated)] py-1.5 shadow-xl ${popoverAnchorClassName}`} style={popoverShadowStyle}>
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
                                  } else if (item.id === "skills") {
                                    onUseSkills();
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

                      <div className="relative" ref={connectorsMenuRef}>
                        <button
                          type="button"
                          onClick={() => {
                            setConnectorsMenuOpen((open) => !open);
                            setMenuOpen(false);
                          }}
                          className="flex items-center rounded-full border border-[var(--border-subtle)] p-2 transition-colors hover:bg-[var(--surface-hover)] cursor-pointer"
                          style={{ color: "var(--text-secondary)" }}
                          title={t("composer.connectors.title", "Connect apps")}
                          aria-label={t("composer.connectors.title", "Connect apps")}
                        >
                          <Cable size={16} strokeWidth={1.9} />
                        </button>
                        {connectorsMenuOpen ? connectorsMenu : null}
                      </div>

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
                        {contextControls}
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
                <div className="relative flex min-w-0 flex-1 self-stretch">
                  {slashMenuVisible ? (
                    <SlashCommandMenu
                      commands={slashCommands}
                      options={slashCommandOptions}
                      optionCommand={slashOptionCommand}
                      selectedIndex={slashSelectedIndex}
                      onSelect={handleSlashSelect}
                      onSelectOption={handleSlashOptionSelect}
                      direction="down"
                      maxHeightClassName={slashMenuMaxHeightClassName}
                    />
                  ) : null}
                  <textarea
                    ref={textareaRef}
                    value={localDraft}
                    onChange={(e) => {
                      handleDraftChange(e.target.value);
                    }}
                    onKeyDown={handleKeyDown}
                    placeholder={placeholder}
                    rows={1}
                    className={`relative min-w-0 w-full resize-none bg-transparent p-0 caret-[var(--text-primary)] outline-none placeholder:text-[var(--text-fainter)] min-h-[56px] max-h-64 leading-8 text-[var(--text-primary)]`}
                    style={{ fontSize: "1.05rem" }}
                  />
                </div>

                <div className="flex w-full flex-col gap-3 border-t border-[var(--border-subtle)] pt-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex items-center gap-3">
                    <div className="relative shrink-0" ref={menuRef}>
                      <button
                        type="button"
                        onClick={() => {
                          setMenuOpen((open) => !open);
                          setConnectorsMenuOpen(false);
                        }}
                        className="flex h-10 w-10 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-soft)] text-[var(--text-faint)] transition-all hover:border-[var(--border-strong)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-secondary)] cursor-pointer"
                        title={t("composer.addAttachment", "Add attachment or action")}
                      >
                        <Plus size={16} strokeWidth={1.75} />
                      </button>

                      {menuOpen ? (
                        <div className={`absolute left-0 ${landingPopoverLayerClassName} ${popoverMotionClassName} w-56 rounded-xl border border-[var(--border-strong)] bg-[var(--panel-elevated)] py-1.5 shadow-xl ${popoverAnchorClassName}`} style={popoverShadowStyle}>
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
                                } else if (item.id === "skills") {
                                  onUseSkills();
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

                    <div className="relative shrink-0" ref={connectorsMenuRef}>
                      <button
                        type="button"
                        onClick={() => {
                          setConnectorsMenuOpen((open) => !open);
                          setMenuOpen(false);
                        }}
                        className="flex h-10 w-10 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-soft)] text-[var(--text-faint)] transition-all hover:border-[var(--border-strong)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-secondary)] cursor-pointer"
                        title={t("composer.connectors.title", "Connect apps")}
                        aria-label={t("composer.connectors.title", "Connect apps")}
                      >
                        <Cable size={16} strokeWidth={1.9} />
                      </button>
                      {connectorsMenuOpen ? connectorsMenu : null}
                    </div>
                  </div>

                  <div className="flex w-full flex-wrap items-center justify-end gap-2 sm:w-auto sm:flex-nowrap">
                    {contextControls}
                    {modelControls}
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
                  </div>
                </div>
              </>
            )}
          </div>

          {isLanding ? (
            <div className="mt-2 border-t border-[var(--border-subtle)] px-4 pb-3 pt-3 sm:px-5">
              <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-[var(--text-soft)]">
                <div className="min-w-0">
                  <span className="font-medium text-[var(--text-muted)]">{t("emptyState.useYourApps", "Use your apps with Aethos")}</span>
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
            <span>{composerHelpText}</span>
          </div>
        )}
      </form>
    </div>
  );
}
