import { useDeferredValue, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import {
  Bot,
  ChevronDown,
  ChevronRight,
  Cloud,
  FolderPlus,
  FolderOpen,
  HardDrive,
  Library,
  LayoutPanelLeft,
  MessageSquarePlus,
  MoreHorizontal,
  PanelLeftClose,
  PanelLeftOpen,
  Pin,
  Plus,
  Search,
  Settings,
  X,
} from "lucide-react";
import ThreadItem from "./ThreadItem";
import { ThreadListSkeleton } from "./Skeleton";
import { useTranslation } from "react-i18next";
import { useThreads } from "../context/ThreadsContext";
import { useThreadActions } from "../context/ThreadActionsContext";
import type { ChatThread } from "../types";
import logoMark from "../assets/aethos-logo.svg";
import logoText from "../assets/aethos-text.svg";

function SidebarGlyph({
  children,
  title,
  onClick,
  popoverContent,
}: {
  children: ReactNode;
  title: string;
  onClick?: () => void;
  popoverContent?: ReactNode;
}) {
  return (
    <div className="relative group">
      <button
        type="button"
        onClick={onClick}
        className="flex h-9 w-9 items-center justify-center rounded-[10px] text-[var(--text-soft)] transition hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] cursor-pointer"
        title={!popoverContent ? title : undefined}
        aria-label={title}
      >
        {children}
      </button>
      {popoverContent && (
        <div className="absolute left-[calc(100%+8px)] top-0 z-[100] max-h-[300px] w-[240px] overflow-y-auto rounded-xl border border-[var(--border-subtle)] bg-[var(--panel-bg-soft)] p-2 shadow-lg opacity-0 -translate-x-2 pointer-events-none transition-all duration-200 ease-out group-hover:opacity-100 group-hover:translate-x-0 group-hover:pointer-events-auto">
          <div className="mb-2 px-2 text-[11px] font-medium text-[var(--text-muted)]">{title}</div>
          <div className="space-y-1">{popoverContent}</div>
        </div>
      )}
    </div>
  );
}

function SectionHeader({
  title,
  expanded,
  onToggle,
  onSelect,
  action,
  active = false,
}: {
  title: string;
  expanded: boolean;
  onToggle: () => void;
  onSelect?: () => void;
  action?: ReactNode;
  active?: boolean;
}) {
  return (
    <div
      className={[
        "group mb-1 flex items-center gap-2 rounded-[10px] py-1 transition",
        active ? "bg-[var(--surface-soft)]" : "hover:bg-[var(--surface-soft)]",
      ].join(" ")}
    >
      <button
        type="button"
        onClick={() => {
          onSelect?.();
          onToggle();
        }}
        className={[
          "flex min-w-0 flex-1 items-center gap-2 rounded-lg px-2 py-1 text-left text-[12px] font-medium transition cursor-pointer",
          active
            ? "text-[var(--text-primary)]"
            : "text-[var(--text-muted)] hover:text-[var(--text-primary)]",
        ].join(" ")}
      >
        <span className="truncate">{title}</span>
      </button>
      {action ? <div className="ml-auto shrink-0">{action}</div> : null}
      <button
        type="button"
        onClick={() => {
          onSelect?.();
          onToggle();
        }}
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] text-[var(--text-soft)] transition hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] cursor-pointer"
        aria-expanded={expanded}
        aria-label={title}
      >
        <ChevronDown
          size={14}
          strokeWidth={2}
          className={[
            "shrink-0 transition-transform",
            expanded ? "rotate-0" : "-rotate-90",
          ].join(" ")}
          aria-hidden="true"
        />
      </button>
    </div>
  );
}

function QuickAction({
  label,
  hint,
  onClick,
  icon,
}: {
  label: string;
  hint?: string;
  onClick?: () => void;
  icon: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex h-7 w-full items-center gap-3 rounded-[10px] px-3 text-[8px] text-[var(--text-secondary)] transition hover:bg-[var(--surface-hover)] cursor-pointer"
    >
      <span className="flex size-[15px] items-center justify-center text-[var(--text-soft)]">{icon}</span>
      <span className="truncate">{label}</span>
      {hint ? (
        <span className="ml-auto rounded-md border border-[var(--border-subtle)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--text-faint)] transition group-hover:border-[var(--border-strong)] group-hover:text-[var(--text-muted)]">
          {hint}
        </span>
      ) : null}
    </button>
  );
}

function getProjectName(path: string) {
  return path.split(/[/\\]/).filter(Boolean).at(-1) || path;
}

function ProjectConversationRow({
  thread,
}: {
  thread: ChatThread;
}) {
  return (
    <div className="relative pl-6">
      <span
        className="pointer-events-none absolute left-[11px] top-1/2 h-px w-3 -translate-y-1/2 bg-[var(--border-subtle)]"
        aria-hidden="true"
      />
      <ThreadItem thread={thread} compact />
    </div>
  );
}

function ProjectGroup({
  path,
  threads,
  activeProject,
  onSelectProject,
  onRemoveProject,
  onStartProjectChat,
}: {
  path: string;
  threads: ChatThread[];
  activeProject: boolean;
  onSelectProject: (path: string) => void;
  onRemoveProject: (path: string) => void;
  onStartProjectChat: (path: string) => void;
}) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(true);
  const [showAll, setShowAll] = useState(false);
  const [optionsOpen, setOptionsOpen] = useState(false);
  const [optionsPosition, setOptionsPosition] = useState({ top: 0, left: 0 });
  const [pinned, setPinned] = useState(false);
  const optionsButtonRef = useRef<HTMLButtonElement>(null);
  const visibleThreads = showAll ? threads : threads.slice(0, 5);
  const projectName = getProjectName(path);

  const openOptions = () => {
    const rect = optionsButtonRef.current?.getBoundingClientRect();
    if (rect) {
      setOptionsPosition({
        top: rect.bottom + 6,
        left: Math.min(rect.right - 220, window.innerWidth - 232),
      });
    }
    setOptionsOpen((value) => !value);
  };

  const handleOption = (action: () => void) => {
    action();
    setOptionsOpen(false);
  };

  return (
    <div className="space-y-1">
      <div
        className={[
          "group flex items-center gap-2 rounded-[10px] px-2 py-1 transition",
          activeProject ? "bg-[var(--surface-soft)]" : "hover:bg-[var(--surface-soft)]",
        ].join(" ")}
      >
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="flex h-8 w-6 shrink-0 items-center justify-center rounded-lg text-[var(--text-soft)] transition hover:text-[var(--text-primary)] cursor-pointer"
          aria-label={projectName}
        >
          <ChevronRight
            size={14}
            strokeWidth={2}
            className={expanded ? "rotate-90 transition-transform" : "rotate-0 transition-transform"}
          />
        </button>
        <button
          type="button"
          onClick={() => {
            setExpanded((value) => !value);
            onSelectProject(path);
          }}
          title={path}
          className={[
            "flex h-8 min-w-0 flex-1 items-center gap-2 rounded-[10px] pr-1 text-left transition cursor-pointer",
            activeProject
              ? "text-[var(--text-primary)]"
              : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
          ].join(" ")}
        >
          <FolderOpen
            size={16}
            strokeWidth={1.8}
            className={activeProject ? "shrink-0 text-[var(--text-primary)]" : "shrink-0 text-[var(--text-soft)]"}
          />
          <span className="min-w-0 flex-1 truncate text-[12px] font-semibold">{projectName}</span>
          <span className="shrink-0 rounded-full bg-[var(--surface-badge)] px-1.5 py-0.5 text-[10px] text-[var(--text-soft)]">
            {threads.length}
          </span>
        </button>
        <button
          type="button"
          onClick={() => onStartProjectChat(path)}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-[var(--text-soft)] opacity-60 transition hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] hover:opacity-100 focus-visible:opacity-100 group-hover:opacity-100 cursor-pointer"
          aria-label={t("sidebar.newProjectChat", "New chat in {{name}}", { name: projectName })}
          title={t("sidebar.newProjectChat", "New chat in {{name}}", { name: projectName })}
        >
          <MessageSquarePlus size={14} strokeWidth={1.9} />
        </button>
        <div className="relative shrink-0">
          <button
            ref={optionsButtonRef}
            type="button"
            onClick={openOptions}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-[var(--text-soft)] opacity-60 transition hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] hover:opacity-100 focus-visible:opacity-100 group-hover:opacity-100 cursor-pointer"
            aria-label={t("sidebar.projectOptions", "Project options")}
            title={t("sidebar.projectOptions", "Project options")}
            aria-expanded={optionsOpen}
          >
            <MoreHorizontal size={15} strokeWidth={2} />
          </button>
          {optionsOpen ? createPortal(
            <>
              <button
                type="button"
                className="fixed inset-0 z-[119] cursor-default"
                aria-label={t("sidebar.closeProjectOptions", "Close project options")}
                onClick={() => setOptionsOpen(false)}
              />
              <div
                className="fixed z-[120] min-w-[220px] rounded-xl border border-[var(--border-subtle)] bg-[var(--panel-elevated)] p-1 shadow-[0_8px_24px_var(--shadow-panel)] transition-all duration-180 ease-out origin-top translate-y-0 scale-100 opacity-100 pointer-events-auto"
                style={{ top: optionsPosition.top, left: optionsPosition.left }}
              >
              <button
                type="button"
                onClick={() => handleOption(() => setPinned((value) => !value))}
                className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-[12px] text-[var(--text-secondary)] transition hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] cursor-pointer"
              >
                <Pin size={13} strokeWidth={1.9} className={pinned ? "text-[var(--text-primary)]" : "text-[var(--text-soft)]"} />
                <span className="min-w-0 flex-1 truncate">
                  {pinned ? t("sidebar.unpinProject", "Unpin project") : t("sidebar.pinProject", "Pin project")}
                </span>
              </button>
              <button
                type="button"
                onClick={() => handleOption(() => onStartProjectChat(path))}
                className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-[12px] text-[var(--text-secondary)] transition hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] cursor-pointer"
              >
                <MessageSquarePlus size={13} strokeWidth={1.9} className="text-[var(--text-soft)]" />
                <span className="min-w-0 flex-1 truncate">{t("sidebar.startProjectChat", "Start new chat")}</span>
              </button>
              <button
                type="button"
                onClick={() => handleOption(() => onRemoveProject(path))}
                className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-[12px] text-[var(--text-secondary)] transition hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] cursor-pointer"
              >
                <X size={13} strokeWidth={1.9} className="text-[var(--text-soft)]" />
                <span className="min-w-0 flex-1 truncate">{t("sidebar.removeProject", "Remove project")}</span>
              </button>
              </div>
            </>,
            document.body
          ) : null}
        </div>
      </div>
      <CollapsibleSection expanded={expanded}>
        <div className="relative ml-5 space-y-0.5 pb-1">
          <span className="pointer-events-none absolute left-0 top-0 h-full w-px bg-[var(--border-subtle)]" aria-hidden="true" />
          {visibleThreads.map((thread) => (
            <ProjectConversationRow
              key={thread.id}
              thread={thread}
            />
          ))}
          {threads.length === 0 ? (
            <div className="pl-6">
              <div className="flex h-9 items-center rounded-[10px] px-3 text-[12px] text-[var(--text-soft)]">
                {t("sidebar.noTasks", "No tasks yet")}
              </div>
            </div>
          ) : null}
          {threads.length > visibleThreads.length ? (
            <button
              type="button"
              onClick={() => setShowAll(true)}
              className="ml-6 rounded-lg px-2 py-1 text-left text-[12px] font-medium text-[var(--text-soft)] transition hover:bg-[var(--surface-hover)] hover:text-[var(--text-secondary)] cursor-pointer"
            >
              {t("sidebar.showMore", "Show more")}
            </button>
          ) : null}
          {showAll && threads.length > 5 ? (
            <button
              type="button"
              onClick={() => setShowAll(false)}
              className="ml-6 rounded-lg px-2 py-1 text-left text-[12px] font-medium text-[var(--text-soft)] transition hover:bg-[var(--surface-hover)] hover:text-[var(--text-secondary)] cursor-pointer"
            >
              {t("sidebar.showLess", "Show less")}
            </button>
          ) : null}
        </div>
      </CollapsibleSection>
    </div>
  );
}

function CollapsibleSection({
  expanded,
  children,
}: {
  expanded: boolean;
  children: ReactNode;
}) {
  return (
    <div
      className={[
        "grid transition-[grid-template-rows,opacity] duration-220 ease-out",
        expanded ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0",
      ].join(" ")}
    >
      <div className="overflow-hidden">{children}</div>
    </div>
  );
}

export default function Sidebar({
  collapsed,
  onToggle,
  projectHistory,
  selectedProjectPath,
  onImportLocalProject,
  onSelectExistingProject,
  onRemoveProject,
  onSelectAllTasks,
}: {
  collapsed: boolean;
  onToggle: () => void;
  projectHistory: string[];
  selectedProjectPath: string;
  onImportLocalProject: () => void;
  onSelectExistingProject: (path: string) => void;
  onRemoveProject: (path: string) => void;
  onSelectAllTasks: () => void;
}) {
  const { t } = useTranslation();
  const { threads } = useThreads();
  const { activeThreadId, onNewChat, onSelectThread, onOpenSettings } = useThreadActions();
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const [projectsExpanded, setProjectsExpanded] = useState(true);
  const [tasksExpanded, setTasksExpanded] = useState(true);
  /**
   * Show the skeleton for up to 600 ms on first mount if threads aren't
   * already loaded. This handles the brief window between React hydration
   * and localStorage being read in ThreadsContext.
   */
  const [showSkeleton, setShowSkeleton] = useState(threads.length === 0);

  useEffect(() => {
    if (!showSkeleton) return;
    const id = window.setTimeout(() => setShowSkeleton(false), 600);
    return () => window.clearTimeout(id);
  }, [showSkeleton]);

  // If threads arrive before the timer fires, dismiss skeleton immediately
  useEffect(() => {
    if (threads.length > 0) setShowSkeleton(false);
  }, [threads.length]);

  const needle = deferredSearch.trim().toLowerCase();
  const matchesSearch = (thread: ChatThread) => {
    if (!needle) return true;
    return (
      thread.title.toLowerCase().includes(needle) ||
      thread.messages.some((message) => message.content.toLowerCase().includes(needle))
    );
  };
  const projectPaths = useMemo(() => {
    const paths = new Set(projectHistory);
    threads.forEach((thread) => {
      if (thread.backendMode === "local" && thread.localRootDir) paths.add(thread.localRootDir);
    });
    return Array.from(paths);
  }, [projectHistory, threads]);
  const projectGroups = useMemo(() => {
    const groups = projectPaths.map((path) => ({
      path,
      threads: threads
        .filter((thread) => thread.backendMode === "local" && thread.localRootDir === path && matchesSearch(thread))
        .sort((a, b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt)),
    }));
    return needle ? groups.filter((group) => group.threads.length > 0) : groups;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [needle, projectPaths, threads]);
  const sandboxThreads = threads
    .filter((thread) => thread.backendMode !== "local" && matchesSearch(thread))
    .sort((a, b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt));
  const activeThread = threads.find((thread) => thread.id === activeThreadId);
  const activeProjectPath = selectedProjectPath || (activeThread?.backendMode === "local" ? activeThread.localRootDir ?? "" : "");
  const activeProjectName = activeProjectPath ? getProjectName(activeProjectPath) : "";

  return (
    <aside
      className={`relative z-30 h-full shrink-0 overflow-visible border-r border-[var(--border-subtle)] bg-[var(--panel-bg)] text-[var(--text-primary)] transition-[width] duration-300 ease-out ${
        collapsed ? "w-16" : "w-[280px]"
      }`}
    >
      {/* Collapsed icon rail */}
      <div
        className={`absolute inset-0 flex h-full flex-col items-center py-3 transition-all duration-300 ease-out ${
          collapsed ? "translate-x-0 opacity-100" : "-translate-x-4 opacity-0 pointer-events-none"
        }`}
      >
        <div className="mb-3 flex w-full flex-col items-center gap-2">
          <SidebarGlyph title={t("sidebar.expand", "Expand sidebar")} onClick={onToggle}>
            <PanelLeftOpen size={16} strokeWidth={1.8} />
          </SidebarGlyph>
          <SidebarGlyph title={t("sidebar.newTask", "New task")} onClick={onNewChat}>
            <Plus size={16} strokeWidth={1.9} />
          </SidebarGlyph>

          <div className="w-8 border-t border-[var(--border-subtle)] my-1" />

          <SidebarGlyph title={t("sidebar.agents", "Agents")}>
            <Bot size={16} strokeWidth={1.8} />
          </SidebarGlyph>

          <SidebarGlyph title={t("sidebar.library", "Library")}>
            <Library size={16} strokeWidth={1.8} />
          </SidebarGlyph>

          <SidebarGlyph
            title={t("sidebar.projects", "Projects")}
            popoverContent={
              projectGroups.length > 0 ? (
                <>
                  {projectGroups.map((project) => (
                    <button
                      key={project.path}
                      type="button"
                      onClick={() => onSelectExistingProject(project.path)}
                      className="flex h-8 w-full items-center gap-2 rounded-lg px-2 text-left text-[12px] text-[var(--text-secondary)] transition hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] cursor-pointer"
                      title={project.path}
                    >
                      <FolderOpen size={14} strokeWidth={1.8} className="shrink-0 text-[var(--text-soft)]" />
                      <span className="min-w-0 flex-1 truncate">{getProjectName(project.path)}</span>
                      <span className="text-[10px] text-[var(--text-soft)]">{project.threads.length}</span>
                    </button>
                  ))}
                </>
              ) : (
                <div className="px-3 py-4 text-center text-[11px] text-[var(--text-soft)]">
                  {t("sidebar.noProjects", "No projects yet")}
                </div>
              )
            }
          >
            <FolderPlus size={16} strokeWidth={1.8} />
          </SidebarGlyph>

          <SidebarGlyph
            title={t("sidebar.allTasks", "All tasks")}
            popoverContent={
              sandboxThreads.length > 0 ? (
                sandboxThreads.map((thread) => (
                  <ThreadItem key={thread.id} thread={thread} />
                ))
              ) : (
                <div className="px-3 py-4 text-center text-[11px] text-[var(--text-soft)]">
                  {t("sidebar.noTasksFound", "No tasks found")}
                </div>
              )
            }
          >
            <LayoutPanelLeft size={16} strokeWidth={1.8} />
          </SidebarGlyph>
        </div>

        <div className="mt-auto flex flex-col items-center gap-2">
          <SidebarGlyph title={t("sidebar.settings", "Settings")} onClick={() => onOpenSettings()}>
            <Settings size={16} strokeWidth={1.8} />
          </SidebarGlyph>
        </div>
      </div>

      {/* Expanded panel */}
      <div
        className={`absolute inset-0 flex h-full flex-col transition-all duration-300 ease-out ${
          collapsed ? "translate-x-6 opacity-0 pointer-events-none" : "translate-x-0 opacity-100"
        }`}
      >
        <header className="flex h-14 shrink-0 items-center justify-between px-3 mt-1 mb-1">
          <button
            type="button"
            onClick={onNewChat}
            className="group flex min-w-0 items-center gap-1 transition-opacity hover:opacity-80 cursor-pointer text-left"
          >
            <div className="relative flex h-11 w-11 items-center justify-center transform transition-transform group-hover:-translate-y-0.5 drop-shadow-md">
              <img
                src={logoMark}
                alt="Aethos Logo Mark"
                className="h-full w-full object-contain transform scale-[1.25]"
              />
            </div>
            <div className="relative flex h-30 flex-1 items-center min-w-0">
              <img
                src={logoText}
                alt="Aethos Logo Text"
                className="h-full w-auto object-contain"
              />
            </div>
          </button>

          <SidebarGlyph title={t("sidebar.collapse", "Collapse sidebar")} onClick={onToggle}>
            <PanelLeftClose size={16} strokeWidth={1.8} />
          </SidebarGlyph>
        </header>

        <nav className="shrink-0 space-y-1 px-2 pb-2 pt-1">
          <QuickAction
            label={t("sidebar.newTask", "New task")}
            onClick={onNewChat}
            icon={<Plus size={15} strokeWidth={1.9} />}
          />
          <QuickAction
            label={t("sidebar.agents", "Agents")}
            icon={<Bot size={15} strokeWidth={1.8} />}
          />
          <div className="rounded-[10px] border border-[var(--border-subtle)] bg-[var(--surface-soft)] px-3">
            <div className="flex h-7 items-center gap-3">
              <span className="flex size-[18px] items-center justify-center text-[var(--text-soft)]">
                <Search size={16} strokeWidth={1.8} />
              </span>
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={t("sidebar.search", "Search")}
                style={{ colorScheme: "inherit" }}
                className="min-w-0 flex-1 bg-transparent text-[13px] text-[var(--text-secondary)] outline-none placeholder:text-[var(--text-faint)]"
              />
              <span className="rounded-md border border-[var(--border-subtle)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--text-faint)]">
                Ctrl+K
              </span>
            </div>
          </div>
          <QuickAction
            label={t("sidebar.library", "Library")}
            icon={<Library size={15} strokeWidth={1.8} />}
          />
        </nav>

        <div className="shrink-0 px-2 pt-2">
          <SectionHeader
            title={t("sidebar.projects", "Projects")}
            expanded={projectsExpanded}
            onToggle={() => setProjectsExpanded((v) => !v)}
            action={
              <SidebarGlyph title={t("sidebar.addProject", "Add project")} onClick={onImportLocalProject}>
                <FolderPlus size={14} strokeWidth={1.9} />
              </SidebarGlyph>
            }
          />
          <CollapsibleSection expanded={projectsExpanded}>
            <div className="space-y-1 pb-3 pt-0.5">
              {projectGroups.length > 0 ? (
                projectGroups.map((project) => (
                  <ProjectGroup
                    key={project.path}
                    path={project.path}
                    threads={project.threads}
                    activeProject={selectedProjectPath === project.path || activeThread?.localRootDir === project.path}
                    onSelectProject={onSelectExistingProject}
                    onRemoveProject={onRemoveProject}
                    onStartProjectChat={(path) => {
                      onSelectExistingProject(path);
                      onNewChat();
                    }}
                  />
                ))
              ) : (
                <div className="px-4 py-3 text-center text-[11px] text-[var(--text-soft)]">
                  {t("sidebar.noProjects", "No projects yet")}
                </div>
              )}
            </div>
          </CollapsibleSection>

          <SectionHeader
            title={t("sidebar.allTasks", "All tasks")}
            expanded={tasksExpanded}
            onToggle={() => setTasksExpanded((v) => !v)}
            onSelect={onSelectAllTasks}
            active={!selectedProjectPath && activeThread?.backendMode !== "local"}
          />
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
          <CollapsibleSection expanded={tasksExpanded}>
            <div className="space-y-1 pt-0.5">
              {showSkeleton ? (
                <ThreadListSkeleton />
              ) : sandboxThreads.length > 0 ? (
                sandboxThreads.map((thread) => (
                  <ThreadItem key={thread.id} thread={thread} />
                ))
              ) : (
                <div className="px-3 py-4 text-center text-[11px] text-[var(--text-soft)]">
                  {search
                    ? t("sidebar.noTasksFound", "No tasks found")
                    : t("sidebar.noTasks", "No tasks yet")}
                </div>
              )}
            </div>
          </CollapsibleSection>
        </div>

        <footer className="shrink-0 border-t border-[var(--border-subtle)] bg-[var(--surface-soft)] px-3 pb-3 pt-2 backdrop-blur-sm">
          <div className="mb-2 flex items-center gap-1">
            <SidebarGlyph title={t("sidebar.settings", "Settings")} onClick={() => onOpenSettings()}>
              <Settings size={16} strokeWidth={1.8} />
            </SidebarGlyph>
            <SidebarGlyph title={t("sidebar.layout", "Layout")}>
              <LayoutPanelLeft size={16} strokeWidth={1.8} />
            </SidebarGlyph>
            <div
              className="ml-auto inline-flex min-w-0 items-center gap-1.5 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-badge)] px-2.5 py-1 text-[11px] font-medium text-[var(--text-muted)]"
              title={
                activeProjectName
                  ? t("sidebar.projectChatStatus", "Project: {{name}}", { name: activeProjectPath })
                  : t("sidebar.generalChatStatus", "General")
              }
            >
              {activeProjectName ? (
                <HardDrive size={12} strokeWidth={1.9} className="shrink-0 text-[var(--text-soft)]" />
              ) : (
                <Cloud size={12} strokeWidth={1.9} className="shrink-0 text-[var(--text-soft)]" />
              )}
              <span className="truncate max-w-[92px]">
                {activeProjectName || t("sidebar.generalChatStatus", "General")}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2 rounded-[12px] border border-[var(--border-subtle)] bg-[var(--surface-badge)] px-2.5 py-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[#f59e0b] text-[#111110]">
              <Bot size={15} strokeWidth={2} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-[12px] font-medium text-[var(--text-primary)]">
                {t("sidebar.aethosApp", "Aethos App")}
              </div>
              <div className="truncate text-[10px] text-[var(--text-soft)]">
                {t("sidebar.version", "frontend v0.1.0")}
              </div>
            </div>
          </div>
        </footer>
      </div>
    </aside>
  );
}

