import { Ellipsis, FolderSync, PenLine, Share2, SquareArrowOutUpRight, Star, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { createPortal } from "react-dom";
import type { ChatThread } from "../types";
import { getLatestPreview } from "../utils/threads";
import { useThreadActions } from "../context/ThreadActionsContext";
import { useToast } from "./Toast";

type Tf = (key: string, defaultValue: string, options?: Record<string, unknown>) => string;

function formatTime(dateString: string, t: Tf) {
  const d = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return t("time.justNow", "just now");
  if (diffMins < 60) return t("time.minutesAgo", "{{count}}m ago", { count: diffMins });
  if (diffHours < 24) return t("time.hoursAgo", "{{count}}h ago", { count: diffHours });
  if (diffDays < 7) return t("time.daysAgo", "{{count}}d ago", { count: diffDays });
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export default function ThreadItem({
  thread,
  compact = false,
}: {
  thread: ChatThread;
  compact?: boolean;
}) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const {
    activeThreadId,
    onSelectThread,
    onRenameThread,
    onToggleFavoriteThread,
    onMoveThreadToProject,
    onDeleteThread,
  } = useThreadActions();

  const isActive = thread.id === activeThreadId;
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuMounted, setMenuMounted] = useState(false);
  const [menuVisible, setMenuVisible] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const menuButtonRef = useRef<HTMLButtonElement | null>(null);
  const [menuPosition, setMenuPosition] = useState<{ top: number; left: number } | null>(null);
  const [menuPlacement, setMenuPlacement] = useState<"top" | "bottom">("bottom");
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const latest = thread.messages.at(-1);
  const isRunning = latest?.role === "assistant" && latest.status === "streaming";
  const hasError = thread.messages.some((m) => m.status === "error");
  const preview = getLatestPreview(thread);
  const isFavorite = thread.isFavorite === true;

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      const target = event.target as Node;
      const clickedInsideMenu = menuRef.current?.contains(target) ?? false;
      const clickedTrigger = menuButtonRef.current?.contains(target) ?? false;
      if (!clickedInsideMenu && !clickedTrigger) setMenuOpen(false);
    }
    if (menuOpen) window.addEventListener("mousedown", handleClickOutside);
    return () => window.removeEventListener("mousedown", handleClickOutside);
  }, [menuOpen]);

  useEffect(() => {
    let timeoutId: number | undefined;
    if (menuOpen) {
      setMenuVisible(false);
      setMenuMounted(true);
    } else {
      setMenuVisible(false);
      timeoutId = window.setTimeout(() => setMenuMounted(false), 180);
    }
    return () => { if (timeoutId) window.clearTimeout(timeoutId); };
  }, [menuOpen]);

  useEffect(() => {
    if (!menuOpen || !menuMounted || !menuPosition) return;
    const frameId = window.requestAnimationFrame(() => setMenuVisible(true));
    return () => window.cancelAnimationFrame(frameId);
  }, [menuOpen, menuMounted, menuPosition]);

  useEffect(() => {
    if (!menuOpen) return;

    function updateMenuPosition() {
      const button = menuButtonRef.current;
      if (!button) return;
      const rect = button.getBoundingClientRect();
      const estimatedMenuHeight = 260;
      const menuWidth = 220; // matches min-w-[220px]
      const gap = 6;
      const shouldOpenUpward = rect.bottom + gap + estimatedMenuHeight > window.innerHeight - 8;
      setMenuPlacement(shouldOpenUpward ? "top" : "bottom");
      // Horizontal: center on button but clamp so menu never overflows viewport
      const rawLeft = rect.left + rect.width / 2;
      const clampedLeft = Math.min(rawLeft, window.innerWidth - menuWidth / 2 - 8);
      setMenuPosition({
        top: shouldOpenUpward ? rect.top - gap : rect.bottom + gap,
        left: clampedLeft,
      });
    }

    updateMenuPosition();
    window.addEventListener("resize", updateMenuPosition);
    window.addEventListener("scroll", updateMenuPosition, true);
    return () => {
      window.removeEventListener("resize", updateMenuPosition);
      window.removeEventListener("scroll", updateMenuPosition, true);
    };
  }, [menuOpen]);

  function handleShare() {
    const url = `${window.location.origin}/app/${thread.id}`;
    void navigator.clipboard
      .writeText(url)
      .then(() => toast.success(t("chat.linkCopied", "Link copied to clipboard")))
      .catch(() => {
        // Fallback for browsers that block clipboard access
        window.prompt(t("chat.copyLink", "Copy conversation link"), url);
      });
    setMenuOpen(false);
  }

  function handleRename() {
    const nextTitle = window.prompt(t("chat.renameConversation", "Rename conversation"), thread.title)?.trim();
    if (nextTitle) onRenameThread(thread.id, nextTitle);
    setMenuOpen(false);
  }

  function handleOpenInNewTab() {
    window.open(`/app/${thread.id}`, "_blank", "noopener,noreferrer");
    setMenuOpen(false);
  }

  function handleMoveToProject() {
    const nextProject = window.prompt(t("chat.moveToProject", "Move to project"), thread.project ?? "");
    if (nextProject !== null) onMoveThreadToProject(thread.id, nextProject.trim());
    setMenuOpen(false);
  }

  async function handleConfirmDelete() {
    if (deleting) return;
    setDeleting(true);
    setConfirmDeleteOpen(false);
    try {
      await onDeleteThread(thread.id);
    } catch {
      toast.error(t("chat.deleteThreadFailed", "Failed to delete conversation"));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div
      className={`group relative w-full rounded-[10px] px-3 py-2 text-left transition-colors ${
        isActive
          ? "bg-[var(--surface-hover)] text-[var(--text-primary)] hover:bg-[var(--surface-hover-strong)]"
          : "text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
      } ${compact ? "min-h-9 py-0" : ""}`}
    >
      <button type="button" onClick={() => onSelectThread(thread.id)} className="w-full text-left">
        {compact ? (
          <div className="flex h-9 items-center justify-between gap-2 pr-7">
            <span className="flex min-w-0 items-center gap-1.5">
              {isFavorite ? <Star size={11} className="shrink-0 text-[var(--accent)]" fill="currentColor" /> : null}
              <span className="truncate text-[12px] font-medium leading-5">{thread.title}</span>
            </span>
            <div className="flex shrink-0 items-center gap-1.5">
              {isRunning ? <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--success)]" /> : null}
              {hasError && !isRunning ? <span className="h-1.5 w-1.5 rounded-full bg-[var(--danger)]" /> : null}
              <span
                className={`text-[10px] transition-opacity duration-150 group-hover:opacity-0 ${
                  isActive ? "text-[var(--text-muted)]" : "text-[var(--text-soft)]"
                }`}
              >
                {formatTime(thread.updatedAt, t)}
              </span>
            </div>
          </div>
        ) : (
          <>
            <div className="mb-0.5 flex items-center justify-between gap-2">
              <span className="flex min-w-0 items-center gap-1.5">
                {isFavorite ? <Star size={12} className="shrink-0 text-[var(--accent)]" fill="currentColor" /> : null}
                <span className="truncate text-[13px] font-medium leading-5">{thread.title}</span>
              </span>
              <div className="flex shrink-0 items-center gap-1.5">
                {isRunning ? <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--success)]" /> : null}
                {hasError && !isRunning ? <span className="h-1.5 w-1.5 rounded-full bg-[var(--danger)]" /> : null}
                <span
                  className={`text-[10px] transition-opacity duration-150 group-hover:opacity-0 ${
                    isActive ? "text-[var(--text-muted)]" : "text-[var(--text-soft)]"
                  }`}
                >
                  {formatTime(thread.updatedAt, t)}
                </span>
              </div>
            </div>
            <p className={`truncate text-[11px] leading-4 ${isActive ? "text-[var(--text-muted)]" : "text-[var(--text-soft)]"}`}>
              {preview.slice(0, 80)}
            </p>
          </>
        )}
      </button>

      <div className={`absolute right-2 ${compact ? "top-1/2 -translate-y-1/2" : "top-2"}`}>
        <button
          ref={menuButtonRef}
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            setMenuOpen((v) => !v);
          }}
          className={`flex h-6 w-6 items-center justify-center rounded-md opacity-0 transition-opacity duration-150 group-hover:opacity-100 ${
            isActive ? "text-[var(--text-muted)] hover:bg-[var(--surface-soft)]" : "text-[var(--text-soft)] hover:bg-[var(--surface-soft)]"
          }`}
          title={t("chat.conversationOptions", "Conversation options")}
          aria-label={t("chat.conversationOptions", "Conversation options")}
        >
          <Ellipsis size={14} />
        </button>

        {menuMounted && menuPosition
          ? createPortal(
              <div
                ref={menuRef}
                className={`fixed z-[120] min-w-[220px] -translate-x-1/2 rounded-xl border border-[var(--border-subtle)] bg-[var(--panel-elevated)] p-1 shadow-[0_8px_24px_var(--shadow-panel)] transition-all duration-180 ease-out ${
                  menuPlacement === "bottom" ? "origin-top" : "origin-bottom"
                } ${
                  menuVisible
                    ? menuPlacement === "bottom"
                      ? "translate-y-0 scale-100 opacity-100 pointer-events-auto"
                      : "-translate-y-full scale-100 opacity-100 pointer-events-auto"
                    : menuPlacement === "bottom"
                      ? "-translate-y-1 scale-95 opacity-0 pointer-events-none"
                      : "-translate-y-[calc(100%+4px)] scale-95 opacity-0 pointer-events-none"
                }`}
                style={{ top: `${menuPosition.top}px`, left: `${menuPosition.left}px` }}
                onClick={(event) => event.stopPropagation()}
              >
                <button type="button" onClick={handleShare} className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-sm text-[var(--text-primary)] hover:bg-[var(--surface-hover)]">
                  <Share2 size={16} />
                  <span>{t("chat.share", "Share")}</span>
                </button>
                <button type="button" onClick={handleRename} className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-sm text-[var(--text-primary)] hover:bg-[var(--surface-hover)]">
                  <PenLine size={16} />
                  <span>{t("chat.rename", "Rename")}</span>
                </button>
                <button type="button" onClick={() => { onToggleFavoriteThread(thread.id); setMenuOpen(false); }} className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-sm text-[var(--text-primary)] hover:bg-[var(--surface-hover)]">
                  <Star size={16} />
                  <span>{isFavorite ? t("chat.removeFromFavorites", "Remove from favorites") : t("chat.addToFavorites", "Add to favorites")}</span>
                </button>
                <button type="button" onClick={handleOpenInNewTab} className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-sm text-[var(--text-primary)] hover:bg-[var(--surface-hover)]">
                  <SquareArrowOutUpRight size={16} />
                  <span>{t("chat.openInNewTab", "Open in new tab")}</span>
                </button>
                <button type="button" onClick={handleMoveToProject} className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-sm text-[var(--text-primary)] hover:bg-[var(--surface-hover)]">
                  <FolderSync size={16} />
                  <span>{t("chat.moveToProject", "Move to project")}</span>
                </button>
                <button
                  type="button"
                  onClick={() => { setConfirmDeleteOpen(true); setMenuOpen(false); }}
                  className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-sm text-[var(--danger)] hover:bg-[var(--surface-hover)]"
                >
                  <Trash2 size={16} />
                  <span>{t("chat.delete", "Delete")}</span>
                </button>
              </div>,
              document.body,
            )
          : null}
      {confirmDeleteOpen
        ? createPortal(
            <div
              className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/50 px-4 backdrop-blur-sm"
              role="presentation"
              onClick={() => { if (!deleting) setConfirmDeleteOpen(false); }}
            >
              <div
                role="dialog"
                aria-modal="true"
                aria-labelledby={`delete-thread-title-${thread.id}`}
                className="w-full max-w-md rounded-2xl border border-[var(--border-subtle)] bg-[var(--panel-elevated)] p-5 shadow-2xl"
                onClick={(event) => event.stopPropagation()}
              >
                <div className="flex items-start gap-3">
                  <div className="rounded-full bg-[color:color-mix(in_srgb,var(--danger)_14%,transparent)] p-2 text-[var(--danger)]">
                    <Trash2 size={20} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <h2 id={`delete-thread-title-${thread.id}`} className="text-base font-semibold text-[var(--text-primary)]">
                      {t("chat.deleteConversationTitle", "Delete conversation?")}
                    </h2>
                    <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
                      {t(
                        "chat.deleteConversationDescription",
                        "This will permanently delete this conversation from the workspace, including its backend checkpoint data. This action cannot be undone.",
                      )}
                    </p>
                    <div className="mt-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-soft)] px-3 py-2 text-sm text-[var(--text-primary)]">
                      {thread.title || t("chat.newConversation", "New conversation")}
                    </div>
                  </div>
                </div>
                <div className="mt-5 flex justify-end gap-2">
                  <button
                    type="button"
                    disabled={deleting}
                    onClick={() => setConfirmDeleteOpen(false)}
                    className="rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-sm text-[var(--text-primary)] hover:bg-[var(--surface-hover)] disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {t("common.cancel", "Cancel")}
                  </button>
                  <button
                    type="button"
                    disabled={deleting}
                    onClick={handleConfirmDelete}
                    className="rounded-lg bg-[var(--danger)] px-3 py-2 text-sm font-medium text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {deleting ? t("chat.deletingConversation", "Deleting...") : t("chat.deletePermanently", "Delete permanently")}
                  </button>
                </div>
              </div>
            </div>,
            document.body,
          )
        : null}
      </div>
    </div>
  );
}
