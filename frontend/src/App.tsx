import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { Navigate, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { MonitorSmartphone, Presentation, Shapes, Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { AppView, ComposerMode, SettingsSection } from "./types";
import { CHAT_SUGGESTIONS, QUICK_ACTIONS, getModeConfig } from "./constants";
import { ensureAuthToken } from "./utils/auth";
import { fetchModels, importLocalProjectFolder } from "./utils/stream";
import Sidebar from "./components/Sidebar";
import Header from "./components/Header";
import ChatArea from "./components/ChatArea";
import WorkspacePanel from "./components/workspace/WorkspacePanel";
import Composer from "./components/Composer";
import EmptyState from "./components/EmptyState";
import SettingsPage from "./components/SettingsPage";
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

const quickActionIcons = [Presentation, Shapes, MonitorSmartphone, Sparkles];

function ChatWorkspace() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { threadId = "" } = useParams<{ threadId: string }>();

  // ── Contexts ──────────────────────────────────────────────────────────────
  useTheme();
  const { profiles, activeProfileId, setActiveProfileId } = useProfiles();
  const { threads, setThreads, updateThread } = useThreads();
  const { history: projectHistory, addProject, removeProject } = useProjectHistory();

  // ── Local state ───────────────────────────────────────────────────────────
  const [status, setStatus] = useState(t("chat.connecting", "Connecting..."));
  const [error, setError] = useState("");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [workspaceMessageId, setWorkspaceMessageId] = useState<string | null>(null);
  const [selectedWorkspaceFrameId, setSelectedWorkspaceFrameId] = useState<string | null>(null);
  const [workspaceDisplayMode, setWorkspaceDisplayMode] = useState<"side" | "center">("side");
  const [workspaceSideWidth, setWorkspaceSideWidth] = useState(640);
  const [appView, setAppView] = useState<AppView>("chat");
  const [settingsSection, setSettingsSection] = useState<SettingsSection>("general");
  const [landingMode, setLandingMode] = useState<ComposerMode>("build");
  const [defaultBackendMode, setDefaultBackendMode] = useState<"sandbox" | "local">("local");
  const [defaultLocalRootDir, setDefaultLocalRootDir] = useState(() => projectHistory[0] ?? "");

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
  const activeBackendMode = activeThread?.backendMode ?? defaultBackendMode;
  const activeLocalRootDir = activeThread?.localRootDir ?? defaultLocalRootDir;
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
      document.title = `${activeThread.title} | Ethos`;
    } else {
      document.title = "Ethos";
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
    if (threadId && threads.length > 0 && !threads.some((t) => t.id === threadId)) {
      navigate("/app", { replace: true });
    }
  }, [navigate, threadId, threads]);

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

  const openSettings = useCallback((section: SettingsSection = "general") => {
    setSettingsSection(section);
    setAppView("settings");
  }, []);

  const closeSettings = useCallback(() => setAppView("chat"), []);
  const handleCloseWorkspace = useCallback(() => {
    setWorkspaceMessageId(null);
    setSelectedWorkspaceFrameId(null);
  }, []);
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
    permissions.setThreadPermissions(null);
    navigate("/app");
  }, [chat.handleStop, chat.setDraft, permissions.setThreadPermissions, navigate, t]);

  const handleSelectThread = useCallback((id: string) => {
    setError("");
    navigate(`/app/${id}`);
  }, [navigate]);

  const handleDeleteThread = useCallback((id: string) => {
    setThreads((current) => current.filter((t) => t.id !== id));
    if (threadId === id) navigate("/app");
  }, [threadId, setThreads, navigate]);

  const handleRenameThread = useCallback((id: string, title: string) => {
    const next = title.trim();
    if (!next) return;
    updateThread(id, (t) => ({ ...t, title: next, updatedAt: new Date().toISOString() }));
  }, [updateThread]);

  const handleToggleFavoriteThread = useCallback((id: string) => {
    updateThread(id, (t) => ({ ...t, isFavorite: !t.isFavorite, updatedAt: new Date().toISOString() }));
  }, [updateThread]);

  const handleMoveThreadToProject = useCallback((id: string, project: string) => {
    updateThread(id, (t) => ({ ...t, project: project.trim(), updatedAt: new Date().toISOString() }));
  }, [updateThread]);

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
    }
  }

  function handleModeChange(mode: ComposerMode) {
    if (activeThread) {
      updateThread(activeThread.id, (t) => ({ ...t, mode, updatedAt: new Date().toISOString() }));
    } else {
      setLandingMode(mode);
    }
  }

  function handleBackendModeChange(mode: "sandbox" | "local") {
    if (activeThread) {
      updateThread(activeThread.id, (t) => ({
        ...t,
        backendMode: mode,
        localRootDir: "",
        updatedAt: new Date().toISOString(),
      }));
    } else {
      setDefaultBackendMode(mode);
      if (mode === "local") setDefaultLocalRootDir("");
    }
  }

  async function handleImportLocalProject() {
    setError("");
    setStatus(t("chat.selectingLocalProject", "Selecting local project folder..."));
    try {
      const { root_dir } = await importLocalProjectFolder();
      addProject(root_dir);
      if (activeThread) {
        updateThread(activeThread.id, (t) => ({
          ...t,
          backendMode: "local",
          localRootDir: root_dir,
          updatedAt: new Date().toISOString(),
        }));
      } else {
        setDefaultBackendMode("local");
        setDefaultLocalRootDir(root_dir);
      }
      setStatus(t("chat.localProjectSelected", "Local project selected"));
    } catch (err) {
      if (activeThread) {
        updateThread(activeThread.id, (t) => ({
          ...t,
          localRootDir: "",
          updatedAt: new Date().toISOString(),
        }));
      } else {
        setDefaultLocalRootDir("");
      }
      const message = err instanceof Error ? err.message : t("chat.folderSelectionFailed", "Folder selection failed");
      setError(message);
      setStatus(t("chat.folderSelectionFailed", "Folder selection failed"));
    }
  }

  function handleSelectExistingProject(path: string) {
    setError("");
    addProject(path);
    if (activeThread) {
      updateThread(activeThread.id, (t) => ({
        ...t,
        backendMode: "local",
        localRootDir: path,
        updatedAt: new Date().toISOString(),
      }));
    } else {
      setDefaultBackendMode("local");
      setDefaultLocalRootDir(path);
    }
    setStatus("Local project selected");
  }

  function handleRemoveProject(path: string) {
    removeProject(path);
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
          />
        </ErrorBoundary>

        {/* ── Col 2: Header + Chat (self-contained, never touches workspace) */}
        <div
          className="flex min-w-0 flex-1 flex-col overflow-hidden chat-area-shift"
          data-shift={isSideWorkspaceVisible}
        >
          <Header
            thread={activeThread}
            onProfileChange={handleProfileChange}
            backendMode={activeBackendMode}
            localRootDir={activeLocalRootDir}
            onBackendModeChange={handleBackendModeChange}
            onImportLocalProject={handleImportLocalProject}
            projectHistory={projectHistory}
            onSelectExistingProject={handleSelectExistingProject}
            onRemoveProject={handleRemoveProject}
            showConversationActions={hasMessages}
          />

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
                      permissions.handlePromoteThreadPermissions(activeThread?.remoteId ?? "")
                    }
                    onOpenSecuritySettings={() => openSettings("security")}
                    onAnswerAskUser={chat.handleAnswerAskUser}
                    onOpenWorkspaceFrame={(messageId, frameId) => {
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
                    activeModel={activeProfile?.name ?? activeModel}
                    attachments={activeThread?.attachments ?? []}
                    status={status}
                    error={error}
                    suggestionPrompts={CHAT_SUGGESTIONS}
                    onChange={chat.setDraft}
                    onSubmit={chat.handleSubmit}
                    onStop={chat.handleStop}
                    onUploadFiles={fileUpload.handleUploadFiles}
                    onRemoveAttachment={fileUpload.handleRemoveAttachment}
                    onModeChange={handleModeChange}
                    onSuggestion={chat.setDraft}
                  />
                </ErrorBoundary>
              </>
            ) : (
              <div className="flex flex-1 items-center justify-center overflow-y-auto px-4 pb-4 sm:px-6 landing-bg">
                <div className="w-full max-w-5xl relative z-10 flex flex-col">
                  <div className="w-full flex justify-center mb-2 drop-shadow-md">
                    <EmptyState />
                  </div>

                  <div className="mx-auto max-w-3xl w-full p-2 lg:p-3 rounded-[36px] composer-landing-container">
                    <ErrorBoundary label="Composer">
                      <Composer
                        draft={chat.draft}
                        mode={activeMode}
                        modeConfig={modeConfig}
                        variant="landing"
                        isStreaming={chat.isStreaming}
                        isUploading={fileUpload.isUploading}
                        activeModel={activeProfile?.name ?? activeModel}
                        attachments={activeThread?.attachments ?? []}
                        status={status}
                        error={error}
                        suggestionPrompts={CHAT_SUGGESTIONS}
                        onChange={chat.setDraft}
                        onSubmit={chat.handleSubmit}
                        onStop={chat.handleStop}
                        onUploadFiles={fileUpload.handleUploadFiles}
                        onRemoveAttachment={fileUpload.handleRemoveAttachment}
                        onModeChange={handleModeChange}
                        onSuggestion={chat.setDraft}
                      />
                    </ErrorBoundary>
                  </div>

                  <div className="mx-auto mt-3 flex max-w-4xl flex-wrap items-center justify-center gap-2 px-2">
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

                  <div className="mx-auto mt-3 grid max-w-4xl grid-cols-1 gap-3 px-6 text-left sm:grid-cols-2 xl:grid-cols-4">
                    {QUICK_ACTIONS.map((action, index) => {
                      const Icon = quickActionIcons[index % quickActionIcons.length];
                      return (
                        <button
                          key={action.title}
                          onClick={() => chat.setDraft(action.prompt)}
                          type="button"
                          className={`group rounded-[1.4rem] border p-4 transition-all duration-200 hover:-translate-y-0.5 cursor-pointer quick-action-card quick-action-card-${index}`}
                        >
                          <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-2xl quick-action-badge">
                            <Icon size={18} strokeWidth={1.9} />
                          </div>
                          <div className="mb-1 text-sm font-semibold quick-action-title">{action.title}</div>
                          <div className="text-xs leading-5 quick-action-body">{action.prompt}</div>
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
              permissions.handlePermissionsSave(profile, activeThread?.remoteId)
            }
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
