import { useDeferredValue, useEffect, useState, type ReactNode } from "react";
import {
  Bot,
  ChevronDown,
  FolderPlus,
  Library,
  LayoutPanelLeft,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Search,
  Settings,
  Sparkles,
} from "lucide-react";
import ThreadItem from "./ThreadItem";
import { ThreadListSkeleton } from "./Skeleton";
import { useTranslation } from "react-i18next";
import { useThreads } from "../context/ThreadsContext";
import { useThreadActions } from "../context/ThreadActionsContext";
import logo from "../assets/aethos.svg";

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
  action,
}: {
  title: string;
  expanded: boolean;
  onToggle: () => void;
  action?: ReactNode;
}) {
  return (
    <div className="mb-2 flex items-center gap-2 px-2">
      <button
        type="button"
        onClick={onToggle}
        className="flex min-w-0 flex-1 items-center gap-2 rounded-lg px-2 py-1 text-[11px] font-medium text-[var(--text-muted)] transition hover:bg-[var(--surface-soft)] hover:text-[var(--text-primary)] cursor-pointer"
      >
        <ChevronDown size={14} strokeWidth={2} className={expanded ? "rotate-0 transition-transform" : "-rotate-90 transition-transform"} />
        <span className="truncate">{title}</span>
      </button>
      {action}
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

function ProjectItem({
  label,
  count,
  active = false,
}: {
  label: string;
  count: string;
  active?: boolean;
}) {
  return (
    <button
      type="button"
      className={[
        "flex h-9 w-full items-center gap-2 rounded-[10px] px-3 text-left transition cursor-pointer",
        active
          ? "bg-[var(--surface-active)] text-[var(--surface-active-text)]"
          : "text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]",
      ].join(" ")}
    >
      <span className="min-w-0 flex-1 truncate text-[12px] font-medium">{label}</span>
      <span className={active ? "text-[10px] text-[var(--text-muted)]" : "text-[10px] text-[var(--text-soft)]"}>{count}</span>
    </button>
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
}: {
  collapsed: boolean;
  onToggle: () => void;
}) {
  const { t } = useTranslation();
  const { threads } = useThreads();
  const { activeThreadId, onNewChat, onOpenSettings } = useThreadActions();
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const [projectsExpanded, setProjectsExpanded] = useState(false);
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
  const filtered = threads.filter((thread) => {
    if (!needle) return true;
    return (
      thread.title.toLowerCase().includes(needle) ||
      thread.messages.some((message) => message.content.toLowerCase().includes(needle))
    );
  });

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
              <>
                <ProjectItem label="Build system" count="4" />
                <ProjectItem label="Ethos rollout" count="2" active />
                <ProjectItem label="Research notes" count="9" />
              </>
            }
          >
            <FolderPlus size={16} strokeWidth={1.8} />
          </SidebarGlyph>

          <SidebarGlyph
            title={t("sidebar.allTasks", "All tasks")}
            popoverContent={
              filtered.length > 0 ? (
                filtered.map((thread) => (
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
            className="group flex min-w-0 items-center gap-3 transition-opacity hover:opacity-80 cursor-pointer text-left"
          >
            <div className="relative flex h-11 w-11 items-center justify-center transform transition-transform group-hover:-translate-y-0.5 drop-shadow-md">
              <img
                src={logo}
                alt="Ethos Logo"
                className="h-full w-full object-contain transform scale-[1.25]"
              />
            </div>
            <div className="min-w-0 flex items-baseline">
              <span
                className="text-[23px] font-bold tracking-[-0.04em] bg-gradient-to-br from-[var(--text-primary)] to-[var(--brand-text)] bg-clip-text text-transparent -ml-1"
                style={{ fontFamily: "'Space Grotesk', sans-serif" }}
              >
                Ethos
              </span>
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
              <SidebarGlyph title={t("sidebar.addProject", "Add project")}>
                <FolderPlus size={14} strokeWidth={1.9} />
              </SidebarGlyph>
            }
          />
          <CollapsibleSection expanded={projectsExpanded}>
            <div className="space-y-1 pb-2 pt-0.5">
              <ProjectItem label="Build system" count="4" />
              <ProjectItem label="Ethos rollout" count="2" active />
              <ProjectItem label="Research notes" count="9" />
            </div>
          </CollapsibleSection>

          <SectionHeader
            title={t("sidebar.allTasks", "All tasks")}
            expanded={tasksExpanded}
            onToggle={() => setTasksExpanded((v) => !v)}
          />
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
          <CollapsibleSection expanded={tasksExpanded}>
            <div className="space-y-1 pt-0.5">
              {showSkeleton ? (
                <ThreadListSkeleton />
              ) : filtered.length > 0 ? (
                filtered.map((thread) => (
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
            <div className="ml-auto rounded-full border border-[var(--border-subtle)] bg-[var(--surface-badge)] px-2 py-1 text-[11px] font-medium text-[var(--text-muted)]">
              {t("sidebar.systemOnline", "System online")}
            </div>
          </div>

          <div className="flex items-center gap-2 rounded-[12px] border border-[var(--border-subtle)] bg-[var(--surface-badge)] px-2.5 py-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[#f59e0b] text-[#111110]">
              <Bot size={15} strokeWidth={2} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-[12px] font-medium text-[var(--text-primary)]">
                {t("sidebar.ethosApp", "Ethos App")}
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
