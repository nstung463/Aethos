import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { Navigate, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { MonitorSmartphone, Presentation, Shapes, Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { AppView, ComposerMode, ContextStatus, ExtensionSkill, ReasoningEffort, SettingsSection } from "./types";
import { CHAT_SUGGESTIONS, QUICK_ACTIONS, getModeConfig } from "./constants";
import { ensureAuthToken } from "./utils/auth";
import { fetchModels, importLocalProjectFolder } from "./utils/stream";
import { deleteBackendThread, fetchBackendThread, updateBackendThread } from "./utils/backendThreads";
import { fetchSkills } from "./utils/extensions";
import { fetchContextStatus } from "./utils/contextStatus";
import { loadGeneralPreferences, subscribeToGeneralPreferences, type GeneralPreferences } from "./utils/generalPreferences";
import Sidebar from "./components/Sidebar";
import Header from "./components/Header";
import ChatArea from "./components/ChatArea";
import WorkspacePanel from "./components/workspace/WorkspacePanel";
import Composer from "./components/Composer";
import EmptyState from "./components/EmptyState";
import SettingsPage from "./components/SettingsPage";
import SkillPickerModal from "./components/SkillPickerModal";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { useTheme } from "./context/ThemeContext";
import { useProfiles } from "./context/ProfilesContext";
import { useThreads } from "./context/ThreadsContext";
import { ThreadActionsContext } from "./context/ThreadActionsContext";
import { usePermissions } from "./hooks/usePermissions";
import { useChat } from "./hooks/useChat";
import { useFileUpload } from "./hooks/useFileUpload";
import { useKeyboardShortcuts } from "./hooks/useKeyboardShortcuts";
import { useProjectHistory } from "./hooks/useProjectHistory";
import {
  hasHydrationBlockingLocalState,
  hasIncompleteWorkspaceFrames,
  hasLiveLocalState,
} from "./utils/threadState";

const quickActionIcons = [Presentation, Shapes, MonitorSmartphone, Sparkles];

function ChatWorkspace() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { threadId = "" } = useParams<{ threadId: string }>();

  // ── Contexts ──────────────────────────────────────────────────────────────
  useTheme();
  const { profiles, activeProfileId, setActiveProfileId, updateProfile } = useProfiles();
  const { threads, setThreads, updateThread } = useThreads();
  const { history: projectHistory, addProject, removeProject } = useProjectHistory();

  // ── Local state ───────────────────────────────────────────────────────────
  const [status, setStatus] = useState(t("chat.connecting", "Connecting..."));
  const [error, setError] = useState("");
  const [generalPreferences, setGeneralPreferences] = useState<GeneralPreferences>(() => loadGeneralPreferences());
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => loadGeneralPreferences().sidebarDefaultState === "collapsed");
  const [workspaceMessageId, setWorkspaceMessageId] = useState<string | null>(null);
  const [selectedWorkspaceFrameId, setSelectedWorkspaceFrameId] = useState<string | null>(null);
  const [workspaceDisplayMode, setWorkspaceDisplayMode] = useState<"side" | "center">("side");
  const [workspaceSideWidth, setWorkspaceSideWidth] = useState(640);
  const [appView, setAppView] = useState<AppView>("chat");
  const [skillPickerOpen, setSkillPickerOpen] = useState(false);
  const [settingsSection, setSettingsSection] = useState<SettingsSection>("account");
  const [landingMode, setLandingMode] = useState<ComposerMode>("build");
  const [selectedProjectPath, setSelectedProjectPath] = useState("");
  const [slashSkills, setSlashSkills] = useState<ExtensionSkill[]>([]);
  const [contextStatus, setContextStatus] = useState<ContextStatus | null>(null);

  // ── Derived ───────────────────────────────────────────────────────────────
  const activeThread = threads.find((t) => t.id === threadId) ?? null;
  const hasMessages = (activeThread?.messages.length ?? 0) > 0;
  const activeProfile =
    profiles.find((p) => p.id === (activeThread?.profileId ?? activeProfileId)) ??
    profiles.find((p) => p.id === activeProfileId) ??
    profiles[0] ??
    null;
  const activeModel = activeProfile?.model ?? activeThread?.model ?? "";
  const activeMode = activeThread?.mode ?? landingMode;
  const activeBackendMode = activeThread?.backendMode ?? (selectedProjectPath ? "local" : "sandbox");
  const activeLocalRootDir = activeThread?.localRootDir ?? selectedProjectPath;
  const modeConfig = getModeConfig(activeMode);
  const workspaceSourceMessage =
    activeThread?.messages.find((message) => message.id === workspaceMessageId) ?? null;
  const workspaceFrames = workspaceSourceMessage?.workspaceFrames ?? [];
  const selectedWorkspaceFrame =
    workspaceFrames.find((frame) => frame.id === selectedWorkspaceFrameId) ??
    workspaceFrames.at(-1) ??
    null;
  const isWorkspaceOpen = Boolean(workspaceMessageId && selectedWorkspaceFrame);
  const resizeStateRef = useRef<{ startX: number; startWidth: number } | null>(null);
  const fetchedThreadDetailsRef = useRef<Set<string>>(new Set());
  const dismissedWorkspaceKeyRef = useRef<string | null>(null);
  /** Ref mirror of sidebarCollapsed — read in event handlers to avoid closure staleness */
  const sidebarCollapsedRef = useRef(false);
  /** True only when sidebar was auto-collapsed by us (not user) */
  const autoCollapsedRef = useRef(false);

  // Sidebar pixel widths — must match Sidebar.tsx (w-16 = 64px, w-[280px])
  const SIDEBAR_EXPANDED_W = 280;
  const SIDEBAR_COLLAPSED_W = 64;
  const RESIZE_HANDLE_W = 12;
  /**
   * Threshold logic (based on workspace width, NOT chatW):
   *   collapse when workspaceW > (windowW - SIDEBAR_EXPANDED_W - CHAT_MIN_W - handle)
   *   restore  when workspaceW < (windowW - SIDEBAR_COLLAPSED_W - CHAT_RESTORE_W - handle)
   *
   * For hysteresis: CHAT_RESTORE_W must be > SIDEBAR_EXPANDED_W - SIDEBAR_COLLAPSED_W + CHAT_MIN_W
   *   i.e. > 280 - 64 + 400 = 616 → we use 700 so hysteresis gap ≈ 84px workspace travel
   */
  const CHAT_MIN_W = 400;     // collapse when chat would be narrower than this
  const CHAT_RESTORE_W = 700; // restore  when chat would be wider  than this (> 616 required)

  // ── Hooks ─────────────────────────────────────────────────────────────────
  const permissions = usePermissions({ activeThread });

  const fileUpload = useFileUpload({
    activeThread,
    activeModel,
    activeMode,
    activeProfileId,
    activeBackendMode,
    activeLocalRootDir,
    setStatus,
    setError,
  });

  const chat = useChat({
    activeThread,
    activeProfile,
    activeProfileId,
    activeModel,
    activeMode,
    activeBackendMode,
    activeLocalRootDir,
    modeConfig,
    isUploading: fileUpload.isUploading,
    pendingRetriesRef: permissions.pendingRetriesRef,
    threadPermissions: permissions.threadPermissions,
    setThreadPermissions: permissions.setThreadPermissions,
    setStatus,
    setError,
  });

  // ── Effects ───────────────────────────────────────────────────────────────

  useEffect(() => {
    if (activeThread?.title && activeThread.title !== "New Thread") {
      document.title = `${activeThread.title} | Aethos`;
    } else {
      document.title = "Aethos";
    }
  }, [activeThread?.title]);

  useEffect(() => {
    const controller = new AbortController();
    ensureAuthToken()
      .then(() => fetchModels(controller.signal))
      .then((items) => {
        setStatus(
          items.length > 0
            ? t("chat.connected", "Connected")
            : t("chat.connectedNoModels", "Connected (no server models)"),
        );
      })
      .catch(() => setStatus(t("chat.apiUnavailable", "API unavailable")));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (threadId && !threadId.startsWith("thread_") && threads.length > 0 && !threads.some((t) => t.id === threadId)) {
      navigate("/app", { replace: true });
    }
  }, [navigate, threadId, threads]);

  useEffect(() => {
    if (!threadId.startsWith("thread_")) return;
    const current = threads.find((thread) => thread.id === threadId);
    if (current && hasHydrationBlockingLocalState(current)) return;
    if (
      current &&
      current.messages.length > 0 &&
      current.status !== "running" &&
      current.status !== "interrupted" &&
      !hasIncompleteWorkspaceFrames(current)
    ) {
      return;
    }

    const hasIncompleteFrames = current ? hasIncompleteWorkspaceFrames(current) : false;
    const fetchKey = [
      threadId,
      current?.updatedAt ?? "",
      current?.activeRunId ?? "",
      current?.status ?? "",
      hasIncompleteFrames ? "incomplete" : "complete",
    ].join(":");
    if (fetchedThreadDetailsRef.current.has(fetchKey)) return;

    const controller = new AbortController();
    fetchedThreadDetailsRef.current.add(fetchKey);
    fetchBackendThread(threadId, controller.signal)
      .then((serverThread) => {
        setThreads((items) => {
          const existing = items.find((thread) => thread.id === threadId);
          if (existing && hasLiveLocalState(existing)) {
            return items;
          }
          if (!existing) return [serverThread, ...items];
          return items.map((thread) =>
            thread.id === threadId
              ? {
                  ...thread,
                  ...serverThread,
                  messages: serverThread.messages.length > 0 ? serverThread.messages : thread.messages,
                }
              : thread,
          );
        });
      })
      .catch(() => {
        fetchedThreadDetailsRef.current.delete(fetchKey);
        // The route guard above will keep the user on /app if the thread truly does not exist.
      });
    return () => controller.abort();
  }, [setThreads, threadId, threads]);

  useEffect(() => {
    const remoteThreadId = activeThread?.remoteId ?? (activeThread?.id.startsWith("thread_") ? activeThread.id : "");
    if (!remoteThreadId || !activeModel) {
      setContextStatus(null);
      return;
    }
    const rawContextWindow = activeProfile?.modelKwargs?.context_window_tokens;
    const contextWindow = typeof rawContextWindow === "number" && rawContextWindow > 0
      ? rawContextWindow
      : undefined;
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => {
      fetchContextStatus({
        threadId: remoteThreadId,
        model: activeModel,
        contextWindow,
        signal: controller.signal,
      })
        .then(setContextStatus)
        .catch(() => setContextStatus(null));
    }, 150);
    return () => {
      window.clearTimeout(timeoutId);
      controller.abort();
    };
  }, [activeModel, activeProfile?.modelKwargs, activeThread?.id, activeThread?.remoteId, activeThread?.updatedAt]);

  useEffect(() => {
    const rootDir = activeBackendMode === "local" ? activeLocalRootDir : undefined;
    const controller = new AbortController();
    fetchSkills(rootDir, controller.signal)
      .then(setSlashSkills)
      .catch(() => setSlashSkills([]));
    return () => controller.abort();
  }, [activeBackendMode, activeLocalRootDir]);

  useEffect(() => subscribeToGeneralPreferences(setGeneralPreferences), []);

  useEffect(() => {
    document.documentElement.dataset.motion = generalPreferences.reduceMotion ? "reduce" : "normal";
  }, [generalPreferences.reduceMotion]);

  useEffect(() => {
    if (!workspaceMessageId) return;

    const message = activeThread?.messages.find((item) => item.id === workspaceMessageId);
    if (!message) {
      setWorkspaceMessageId(null);
      setSelectedWorkspaceFrameId(null);
      return;
    }

    const frames = message.workspaceFrames ?? [];
    if (frames.length === 0) {
      setWorkspaceMessageId(null);
      setSelectedWorkspaceFrameId(null);
      return;
    }

    if (!selectedWorkspaceFrameId || !frames.some((frame) => frame.id === selectedWorkspaceFrameId)) {
      setSelectedWorkspaceFrameId(frames.at(-1)?.id ?? null);
    }
  }, [activeThread, selectedWorkspaceFrameId, workspaceMessageId]);

  // Keep ref in sync with state so event handlers always see latest value
  useEffect(() => {
    sidebarCollapsedRef.current = sidebarCollapsed;
  }, [sidebarCollapsed]);

  useEffect(() => {
    const nextCollapsed = generalPreferences.sidebarDefaultState === "collapsed";
    autoCollapsedRef.current = false;
    sidebarCollapsedRef.current = nextCollapsed;
    setSidebarCollapsed(nextCollapsed);
  }, [generalPreferences.sidebarDefaultState]);

  useEffect(() => {
    if (!generalPreferences.autoOpenWorkspace || !activeThread) return;
    const candidateMessage = [...activeThread.messages].reverse().find((message) => (message.workspaceFrames?.length ?? 0) > 0);
    if (!candidateMessage) return;
    const latestFrame = candidateMessage.workspaceFrames?.at(-1);
    if (!latestFrame) return;

    const nextWorkspaceKey = `${candidateMessage.id}:${latestFrame.id}`;
    if (dismissedWorkspaceKeyRef.current === nextWorkspaceKey) return;
    if (workspaceMessageId === candidateMessage.id && selectedWorkspaceFrameId === latestFrame.id) return;

    setWorkspaceMessageId(candidateMessage.id);
    setSelectedWorkspaceFrameId(latestFrame.id);
    setWorkspaceDisplayMode(window.innerWidth >= 1280 ? "side" : "center");
  }, [activeThread, generalPreferences.autoOpenWorkspace, selectedWorkspaceFrameId, workspaceMessageId]);

  useEffect(() => {
    let throttleTimeoutId: ReturnType<typeof setTimeout> | null = null;

    function handlePointerMove(event: PointerEvent) {
      const state = resizeStateRef.current;
      if (!state) return;

      const delta = state.startX - event.clientX;
      const nextWidth = Math.min(920, Math.max(460, state.startWidth + delta));

      // ── Smart sidebar auto-collapse — runs every event (no throttle) ──
      // Using workspace width avoids feedback loops: the threshold doesn't jump
      // when sidebar collapses because we don't use sidebarW in the formula.
      const windowW = window.innerWidth;
      const collapseAt = windowW - SIDEBAR_EXPANDED_W - CHAT_MIN_W - RESIZE_HANDLE_W;
      const restoreAt  = windowW - SIDEBAR_COLLAPSED_W - CHAT_RESTORE_W - RESIZE_HANDLE_W;

      if (nextWidth > collapseAt && !sidebarCollapsedRef.current) {
        autoCollapsedRef.current = true;
        sidebarCollapsedRef.current = true;
        setSidebarCollapsed(true);
      } else if (nextWidth < restoreAt && sidebarCollapsedRef.current && autoCollapsedRef.current) {
        autoCollapsedRef.current = false;
        sidebarCollapsedRef.current = false;
        setSidebarCollapsed(false);
      }

      // Throttle width updates to ~60fps
      if (throttleTimeoutId !== null) return;
      setWorkspaceSideWidth(nextWidth);
      throttleTimeoutId = setTimeout(() => { throttleTimeoutId = null; }, 16);
    }

    function handlePointerUp() {
      if (!resizeStateRef.current) return;
      resizeStateRef.current = null;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      document.documentElement.removeAttribute("data-resizing");
      if (throttleTimeoutId !== null) {
        clearTimeout(throttleTimeoutId);
        throttleTimeoutId = null;
      }
    }

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);
    window.addEventListener("pointercancel", handlePointerUp);
    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
      window.removeEventListener("pointercancel", handlePointerUp);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // intentionally empty — we use refs for all mutable values

  // ── Handlers ──────────────────────────────────────────────────────────────

  const openSettings = useCallback((section: SettingsSection = "account") => {
    setSettingsSection(section);
    setAppView("settings");
  }, []);

  const closeSettings = useCallback(() => setAppView("chat"), []);
  const handleCloseWorkspace = useCallback(() => {
    if (workspaceMessageId && selectedWorkspaceFrameId) {
      dismissedWorkspaceKeyRef.current = `${workspaceMessageId}:${selectedWorkspaceFrameId}`;
    }
    setWorkspaceMessageId(null);
    setSelectedWorkspaceFrameId(null);
  }, [selectedWorkspaceFrameId, workspaceMessageId]);
  const handleWorkspaceDisplayModeChange = useCallback((nextMode: "side" | "center") => {
    if (!isWorkspaceOpen || nextMode === workspaceDisplayMode) return;
    setWorkspaceDisplayMode(nextMode);
  }, [isWorkspaceOpen, workspaceDisplayMode]);
  const handleStartWorkspaceResize = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    resizeStateRef.current = {
      startX: event.clientX,
      startWidth: workspaceSideWidth,
    };
    document.body.style.cursor = "ew-resize";
    document.body.style.userSelect = "none";
    document.documentElement.setAttribute("data-resizing", "true");
  }, [workspaceSideWidth]);

  /** Called when user manually toggles the sidebar — clears auto-collapse flag */
  const handleToggleSidebar = useCallback(() => {
    autoCollapsedRef.current = false;
    setSidebarCollapsed((v) => !v);
  }, []);

  const handleNewChat = useCallback(() => {
    chat.handleStop();
    chat.setDraft("");
    setError("");
    setStatus(t("chat.newConversationReady", "New conversation ready"));
    setSelectedProjectPath("");
    permissions.setThreadPermissions(null);
    navigate("/app");
  }, [chat.handleStop, chat.setDraft, navigate, permissions.setThreadPermissions, t]);

  const handleSelectThread = useCallback((id: string) => {
    setError("");
    const selected = threads.find((thread) => thread.id === id);
    setSelectedProjectPath(selected?.backendMode === "local" ? selected.localRootDir ?? "" : "");
    navigate(`/app/${id}`);
  }, [navigate, threads]);

  const handleSelectProject = useCallback((path: string) => {
    setError("");
    addProject(path);
    setSelectedProjectPath(path);
    permissions.setThreadPermissions(null);
    navigate("/app");
  }, [addProject, navigate, permissions.setThreadPermissions]);

  const handleSelectAllTasks = useCallback(() => {
    setError("");
    setSelectedProjectPath("");
    permissions.setThreadPermissions(null);
    navigate("/app");
  }, [navigate, permissions.setThreadPermissions]);

  const handleRemoveProject = useCallback((path: string) => {
    removeProject(path);
    if (selectedProjectPath === path) {
      setSelectedProjectPath("");
      permissions.setThreadPermissions(null);
      navigate("/app");
    }
  }, [navigate, permissions.setThreadPermissions, removeProject, selectedProjectPath]);

  const handleDeleteThread = useCallback(async (id: string) => {
    const thread = threads.find((item) => item.id === id);
    const remoteThreadId = thread?.remoteId ?? (id.startsWith("thread_") ? id : undefined);
    if (remoteThreadId) {
      try {
        await deleteBackendThread(remoteThreadId);
      } catch (error) {
        setError(t("chat.deleteThreadFailed", "Failed to delete thread on the server"));
        throw error;
      }
    }
    setThreads((current) => current.filter((t) => t.id !== id));
    if (threadId === id || threadId === remoteThreadId) navigate("/app");
  }, [threadId, threads, setThreads, navigate, t]);

  const handleRenameThread = useCallback((id: string, title: string) => {
    const next = title.trim();
    if (!next) return;
    updateThread(id, (t) => ({ ...t, title: next, updatedAt: new Date().toISOString() }));
    if (id.startsWith("thread_")) {
      updateBackendThread(id, { title: next }).catch(() => {
        setError(t("chat.renameThreadFailed", "Failed to rename thread on the server"));
      });
    }
  }, [updateThread, t]);

  const handleToggleFavoriteThread = useCallback((id: string) => {
    updateThread(id, (t) => ({ ...t, isFavorite: !t.isFavorite, updatedAt: new Date().toISOString() }));
    if (id.startsWith("thread_")) {
      const current = threads.find((thread) => thread.id === id);
      updateBackendThread(id, { is_favorite: !current?.isFavorite }).catch(() => {
        setError(t("chat.updateThreadFailed", "Failed to update thread on the server"));
      });
    }
  }, [threads, updateThread, t, setError]);

  const handleMoveThreadToProject = useCallback((id: string, project: string) => {
    const next = project.trim();
    updateThread(id, (t) => ({ ...t, project: next, updatedAt: new Date().toISOString() }));
    if (id.startsWith("thread_")) {
      updateBackendThread(id, { project: next }).catch(() => {
        setError(t("chat.updateThreadFailed", "Failed to update thread on the server"));
      });
    }
  }, [updateThread, t, setError]);

  function handleProfileChange(profileId: string) {
    setActiveProfileId(profileId);
    if (activeThread) {
      const p = profiles.find((x) => x.id === profileId);
      updateThread(activeThread.id, (t) => ({
        ...t,
        profileId,
        model: p?.model ?? t.model,
        updatedAt: new Date().toISOString(),
      }));
      if (activeThread.id.startsWith("thread_")) {
        updateBackendThread(activeThread.id, {
          profile_id: profileId,
          model: p?.model ?? activeThread.model,
        }).catch(() => {
          setError(t("chat.updateThreadFailed", "Failed to update thread on the server"));
        });
      }
    }
  }

  function handleReasoningEffortChange(reasoningEffort: ReasoningEffort) {
    if (!activeProfile) return;
    updateProfile(activeProfile.id, (profile) => ({
      ...profile,
      reasoningEnabled: reasoningEffort === "none" ? false : true,
      reasoningEffort,
    }));
  }

  function handleThinkingBudgetChange(thinkingBudgetTokens: number) {
    if (!activeProfile) return;
    updateProfile(activeProfile.id, (profile) => ({
      ...profile,
      reasoningEnabled: true,
      thinkingBudgetTokens,
    }));
  }

  function handleModeChange(mode: ComposerMode) {
    if (activeThread) {
      updateThread(activeThread.id, (t) => ({ ...t, mode, updatedAt: new Date().toISOString() }));
      if (activeThread.id.startsWith("thread_")) {
        updateBackendThread(activeThread.id, { mode }).catch(() => {
          setError(t("chat.updateThreadFailed", "Failed to update thread on the server"));
        });
      }
    } else {
      setLandingMode(mode);
    }
  }

  async function handleImportLocalProject() {
    setError("");
    setStatus(t("chat.selectingLocalProject", "Selecting local project folder..."));
    try {
      const { root_dir } = await importLocalProjectFolder();
      addProject(root_dir);
      setSelectedProjectPath(root_dir);
      permissions.setThreadPermissions(null);
      navigate("/app");
      setStatus(t("chat.localProjectSelected", "Local project selected"));
    } catch (err) {
      const message = err instanceof Error ? err.message : t("chat.folderSelectionFailed", "Folder selection failed");
      setError(message);
      setStatus(t("chat.folderSelectionFailed", "Folder selection failed"));
    }
  }

  function handleSelectExistingProject(path: string) {
    handleSelectProject(path);
    setStatus(t("chat.localProjectSelected", "Local project selected"));
  }

  function handleUseSkill(skillName: string) {
    const trigger = skillName.startsWith("mcp:")
      ? `Use skill ${skillName}: `
      : `/${skillName} `;
    chat.setDraft((current) => `${current}${current.trim() ? "\n" : ""}${trigger}`);
    setSkillPickerOpen(false);
  }

  // ── Keyboard Shortcuts ────────────────────────────────────────────────────

  useKeyboardShortcuts({
    appView,
    isStreaming: chat.isStreaming,
    onNewChat: handleNewChat,
    onOpenSettings: openSettings,
    onToggleSidebar: () => setSidebarCollapsed((v) => !v),
    onStop: chat.handleStop,
    onCloseSettings: closeSettings,
  });

  // ── Render ────────────────────────────────────────────────────────────────

  const threadActionsValue = useMemo(() => ({
    activeThreadId: threadId,
    onNewChat: handleNewChat,
    onSelectThread: handleSelectThread,
    onRenameThread: handleRenameThread,
    onToggleFavoriteThread: handleToggleFavoriteThread,
    onMoveThreadToProject: handleMoveThreadToProject,
    onDeleteThread: handleDeleteThread,
    onOpenSettings: openSettings,
  }), [
    threadId,
    handleNewChat,
    handleSelectThread,
    handleRenameThread,
    handleToggleFavoriteThread,
    handleMoveThreadToProject,
    handleDeleteThread,
    openSettings,
  ]);

  const isSideWorkspaceVisible = isWorkspaceOpen && workspaceDisplayMode === "side";

  return (
    <ThreadActionsContext.Provider value={threadActionsValue}>
      {/*
        Root: flex row with 3 independent columns
        ┌──────────┬──────────────────────┬────────────────────────┐
        │ Sidebar  │ Header + Chat        │ Workspace AI           │
        └──────────┴──────────────────────┴────────────────────────┘
      */}
      <div className="flex h-screen overflow-hidden bg-[var(--app-bg)] text-[var(--text-primary)] app-layout-root">

        {/* ── Col 1: Sidebar ─────────────────────────────────────────────── */}
        <ErrorBoundary label="Sidebar">
          <Sidebar
            collapsed={sidebarCollapsed}
            onToggle={handleToggleSidebar}
            projectHistory={projectHistory}
            selectedProjectPath={selectedProjectPath}
            onImportLocalProject={handleImportLocalProject}
            onSelectExistingProject={handleSelectExistingProject}
            onRemoveProject={handleRemoveProject}
            onSelectAllTasks={handleSelectAllTasks}
          />
        </ErrorBoundary>

        {/* ── Col 2: Header + Chat (self-contained, never touches workspace) */}
        <div
          className="flex min-w-0 flex-1 flex-col overflow-hidden chat-area-shift"
          data-shift={isSideWorkspaceVisible}
        >
          {hasMessages ? (
            <Header
              thread={activeThread}
              showConversationActions={hasMessages}
            />
          ) : null}

          <div className="flex min-h-0 flex-1 flex-col">
            {hasMessages ? (
              <>
                <ErrorBoundary label="Chat area">
                  <ChatArea
                    thread={activeThread}
                    onFollowUpClick={chat.setDraft}
                    threadPermissions={permissions.threadPermissions}
                    onApproveOnce={chat.handleApproveOnce}
                    onApproveForChat={chat.handleApproveForChat}
                    onBypassForChat={chat.handleBypassForChat}
                    onPromoteThreadPermissions={() =>
                      permissions.handlePromoteThreadPermissions(
                        activeThread?.remoteId ??
                          (activeThread?.id.startsWith("thread_") ? activeThread.id : ""),
                      )
                    }
                    onOpenSecuritySettings={() => openSettings("security")}
                    onAnswerAskUser={chat.handleAnswerAskUser}
                    onOpenWorkspaceFrame={(messageId, frameId) => {
                      dismissedWorkspaceKeyRef.current = null;
                      setWorkspaceMessageId(messageId);
                      setSelectedWorkspaceFrameId(frameId);
                      setWorkspaceDisplayMode(window.innerWidth >= 1280 ? "side" : "center");
                    }}
                  />
                </ErrorBoundary>

                <ErrorBoundary label="Composer">
                  <Composer
                    draft={chat.draft}
                    mode={activeMode}
                    modeConfig={modeConfig}
                    variant="chat"
                    isStreaming={chat.isStreaming}
                    isUploading={fileUpload.isUploading}
                    profiles={profiles}
                    activeProfile={activeProfile}
                    activeProfileId={activeProfileId}
                    activeModel={activeProfile?.name ?? activeModel}
                    localRootDir={activeLocalRootDir}
                    composerSendShortcut={generalPreferences.composerSendShortcut}
                    attachments={activeThread?.attachments ?? []}
                    skills={slashSkills}
                    contextStatus={contextStatus}
                    status={status}
                    error={error}
                    suggestionPrompts={CHAT_SUGGESTIONS}
                    onChange={chat.setDraft}
                    onSubmit={chat.handleSubmit}
                    onStop={chat.handleStop}
                    onUploadFiles={fileUpload.handleUploadFiles}
                    onRemoveAttachment={fileUpload.handleRemoveAttachment}
                    onUseSkills={() => setSkillPickerOpen(true)}
                    onModeChange={handleModeChange}
                    onProfileChange={handleProfileChange}
                    onReasoningEffortChange={handleReasoningEffortChange}
                    onThinkingBudgetChange={handleThinkingBudgetChange}
                    onSuggestion={chat.setDraft}
                  />
                </ErrorBoundary>
              </>
            ) : (
              <div className="flex flex-1 overflow-y-auto px-4 pb-8 pt-6 sm:px-6 sm:pb-10 sm:pt-10 landing-bg">
                <div className="relative z-10 mx-auto flex w-full max-w-5xl flex-col pt-4 sm:pt-6 lg:pt-10">
                  <div className="mb-4 flex w-full justify-center drop-shadow-md sm:mb-5">
                    <EmptyState />
                  </div>

                  <div className="relative z-30 mx-auto max-w-3xl w-full p-2 lg:p-3 rounded-[36px] composer-landing-container">
                    <ErrorBoundary label="Composer">
                      <Composer
                        draft={chat.draft}
                        mode={activeMode}
                        modeConfig={modeConfig}
                        variant="landing"
                        isStreaming={chat.isStreaming}
                        isUploading={fileUpload.isUploading}
                        profiles={profiles}
                        activeProfile={activeProfile}
                        activeProfileId={activeProfileId}
                        activeModel={activeProfile?.name ?? activeModel}
                        localRootDir={activeLocalRootDir}
                        composerSendShortcut={generalPreferences.composerSendShortcut}
                        attachments={activeThread?.attachments ?? []}
                        skills={slashSkills}
                        contextStatus={contextStatus}
                        status={status}
                        error={error}
                        suggestionPrompts={CHAT_SUGGESTIONS}
                        onChange={chat.setDraft}
                        onSubmit={chat.handleSubmit}
                        onStop={chat.handleStop}
                        onUploadFiles={fileUpload.handleUploadFiles}
                        onRemoveAttachment={fileUpload.handleRemoveAttachment}
                        onUseSkills={() => setSkillPickerOpen(true)}
                        onModeChange={handleModeChange}
                        onProfileChange={handleProfileChange}
                        onReasoningEffortChange={handleReasoningEffortChange}
                        onThinkingBudgetChange={handleThinkingBudgetChange}
                        onSuggestion={chat.setDraft}
                      />
                    </ErrorBoundary>
                  </div>

                  <div className="relative z-0 mx-auto mt-4 flex max-w-4xl flex-wrap items-center justify-center gap-2 px-2 sm:mt-5">
                    {CHAT_SUGGESTIONS.map((prompt) => (
                      <button
                        key={prompt}
                        type="button"
                        onClick={() => chat.setDraft(prompt)}
                        className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-soft)] px-3 py-1.5 text-xs text-[var(--text-secondary)] transition-all hover:border-[var(--border-strong)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] cursor-pointer"
                      >
                        {prompt}
                      </button>
                    ))}
                  </div>

                  <div className="relative z-0 mx-auto mt-5 grid max-w-3xl grid-cols-1 gap-2 px-4 text-left sm:mt-6 sm:grid-cols-2 sm:px-0">
                    {QUICK_ACTIONS.map((action, index) => {
                      const Icon = quickActionIcons[index % quickActionIcons.length];
                      return (
                        <button
                          key={action.title}
                          onClick={() => chat.setDraft(action.prompt)}
                          type="button"
                          className={`group rounded-[1rem] border px-3 py-2.5 transition-all duration-200 hover:-translate-y-0.5 cursor-pointer quick-action-card quick-action-card-${index}`}
                        >
                          <div className="mb-2 flex h-8 w-8 items-center justify-center rounded-lg quick-action-badge">
                            <Icon size={15} strokeWidth={1.9} />
                          </div>
                          <div className="mb-0.5 text-[0.78rem] font-semibold leading-4 quick-action-title">{action.title}</div>
                          <div className="text-[0.68rem] leading-[1.1rem] quick-action-body">{action.prompt}</div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* ── Col 3: Workspace AI spacer + resize handle ─────────────── */}
        <div
          className="workspace-slide-container relative z-40 hidden xl:flex shrink-0"
          data-open={isSideWorkspaceVisible}
          style={{ width: isSideWorkspaceVisible ? workspaceSideWidth + 12 : 0 }}
        >
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label={t("workspace.resizeHandle", "Resize workspace panel")}
            onPointerDown={handleStartWorkspaceResize}
            className="workspace-shell-handle group absolute inset-y-0 left-0 flex w-3 cursor-ew-resize justify-center"
          >
            <div className="workspace-shell-handle-rail my-4 flex h-auto w-full items-center justify-center rounded-full">
              <div className="workspace-shell-handle-grip h-14 w-[3px] rounded-full" />
            </div>
          </div>
        </div>

        {/* ── Settings overlay ───────────────────────────────────────────── */}
        {appView === "settings" ? (
          <SettingsPage
            onClose={closeSettings}
            initialSection={settingsSection}
            userPermissions={permissions.userPermissions}
            permissionsLoading={permissions.permissionsLoading}
            permissionsError={permissions.permissionsError}
            onPermissionsSave={(profile) =>
              permissions.handlePermissionsSave(
                profile,
                activeThread?.remoteId ??
                  (activeThread?.id.startsWith("thread_") ? activeThread.id : undefined),
              )
            }
            localRootDir={activeLocalRootDir}
            generalPreferences={generalPreferences}
          />
        ) : null}

        {skillPickerOpen ? (
          <SkillPickerModal
            rootDir={activeBackendMode === "local" ? activeLocalRootDir : ""}
            onClose={() => setSkillPickerOpen(false)}
            onSelect={(skill) => handleUseSkill(skill.name)}
          />
        ) : null}

        {/* ── Center modal workspace ─────────────────────────────────────── */}
        {isWorkspaceOpen ? (
          <WorkspacePanel
            frame={selectedWorkspaceFrame}
            allFrames={workspaceFrames}
            isStreaming={chat.isStreaming}
            displayMode={workspaceDisplayMode}
            sideWidth={workspaceSideWidth}
            onClose={handleCloseWorkspace}
            onSelectFrame={setSelectedWorkspaceFrameId}
            onDisplayModeChange={handleWorkspaceDisplayModeChange}
          />
        ) : null}
      </div>
    </ThreadActionsContext.Provider>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/app" replace />} />
      <Route path="/app" element={<ChatWorkspace />} />
      <Route path="/app/:threadId" element={<ChatWorkspace />} />
      <Route path="*" element={<Navigate to="/app" replace />} />
    </Routes>
  );
}
