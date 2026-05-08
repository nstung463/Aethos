import { X } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import type { WorkspaceFrame } from "../../types";
import ActivityStrip from "./ActivityStrip";
import ContentArea from "./ContentArea";
import TaskStepBar from "./TaskStepBar";

type WorkspaceDisplayMode = "side" | "center";

/** Custom monitor icon matching Manus's exact SVG */
function MonitorIcon() {
  const clipPathId = useId().replace(/:/g, "_");
  return (
    <svg width="20" height="20" viewBox="0 0 21 20" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-5 h-5">
      <g clipPath={`url(#${clipPathId})`}>
        <path fillRule="evenodd" clipRule="evenodd" d="M3.38477 3.33341C2.92453 3.33341 2.55143 3.70651 2.55143 4.16675V12.5001C2.55143 12.9603 2.92453 13.3334 3.38477 13.3334H16.7181C17.1783 13.3334 17.5514 12.9603 17.5514 12.5001V4.16675C17.5514 3.70651 17.1783 3.33341 16.7181 3.33341H3.38477ZM0.884766 4.16675C0.884766 2.78604 2.00405 1.66675 3.38477 1.66675H16.7181C18.0988 1.66675 19.2181 2.78604 19.2181 4.16675V12.5001C19.2181 13.8808 18.0988 15.0001 16.7181 15.0001H3.38477C2.00405 15.0001 0.884766 13.8808 0.884766 12.5001V4.16675Z" fill="currentColor" />
        <path fillRule="evenodd" clipRule="evenodd" d="M5.88477 17.5001C5.88477 17.0398 6.25786 16.6667 6.7181 16.6667H13.3848C13.845 16.6667 14.2181 17.0398 14.2181 17.5001C14.2181 17.9603 13.845 18.3334 13.3848 18.3334H6.7181C6.25786 18.3334 5.88477 17.9603 5.88477 17.5001Z" fill="currentColor" />
        <path fillRule="evenodd" clipRule="evenodd" d="M10.0501 13.3333C10.5104 13.3333 10.8835 13.7063 10.8835 14.1666V17.4999C10.8835 17.9602 10.5104 18.3333 10.0501 18.3333C9.58989 18.3333 9.2168 17.9602 9.2168 17.4999V14.1666C9.2168 13.7063 9.58989 13.3333 10.0501 13.3333Z" fill="currentColor" />
        <path d="M8.11331 6.25002C8.10195 6.22379 8.09873 6.19475 8.10408 6.16666C8.10943 6.13858 8.1231 6.11275 8.14332 6.09254C8.16353 6.07232 8.18936 6.05865 8.21744 6.0533C8.24553 6.04795 8.27457 6.05117 8.3008 6.06253L12.9088 7.93453C12.9368 7.94595 12.9605 7.9659 12.9766 7.99155C12.9926 8.01721 13.0002 8.04726 12.9982 8.07745C12.9961 8.10764 12.9847 8.13643 12.9654 8.15973C12.9461 8.18303 12.9199 8.19967 12.8907 8.20727L11.1269 8.66231C11.0273 8.68793 10.9363 8.73977 10.8635 8.81245C10.7907 8.88513 10.7386 8.97599 10.7128 9.07559L10.2581 10.8399C10.2504 10.8692 10.2338 10.8953 10.2105 10.9146C10.1872 10.9339 10.1584 10.9454 10.1282 10.9474C10.098 10.9494 10.068 10.9418 10.0423 10.9258C10.0167 10.9098 9.99673 10.886 9.98531 10.858L8.11331 6.25002Z" fill="currentColor" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" />
      </g>
      <defs>
        <clipPath id={clipPathId}>
          <rect width="20" height="20" fill="white" transform="translate(0.0507812)" />
        </clipPath>
      </defs>
    </svg>
  );
}

/** Custom side-panel icon matching Manus's exact SVG */
function SidePanelIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 18 14" fill="none" width="16" height="16" color="currentColor" className="size-5 text-[var(--icon-secondary)]">
      <path d="M3.75 3.85C3.75 3.51863 4.01863 3.25 4.35 3.25L13.65 3.25C13.9814 3.25 14.25 3.51863 14.25 3.85L14.25 10.15C14.25 10.4814 13.9814 10.75 13.65 10.75L4.35 10.75C4.01863 10.75 3.75 10.4814 3.75 10.15L3.75 3.85Z" fill="currentColor" />
      <path d="M15.75 2.5C15.75 2.08579 15.4142 1.75 15 1.75L3 1.75C2.58579 1.75 2.25 2.08579 2.25 2.5L2.25 11.5C2.25 11.9142 2.58579 12.25 3 12.25L15 12.25C15.4142 12.25 15.75 11.9142 15.75 11.5L15.75 2.5ZM17.25 11.5C17.25 12.7426 16.2426 13.75 15 13.75L3 13.75C1.75736 13.75 0.75 12.7426 0.75 11.5L0.75 2.5C0.75 1.25736 1.75736 0.25 3 0.25L15 0.25C16.2426 0.25 17.25 1.25736 17.25 2.5L17.25 11.5Z" fill="currentColor" />
    </svg>
  );
}

/** Custom dock-right icon for the side workspace state/action */
function DockRightIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 18 18" fill="none" width="16" height="16" color="currentColor" className="size-5 text-[var(--icon-secondary)]">
      <path d="M3 2.25C2.58579 2.25 2.25 2.58579 2.25 3V15C2.25 15.4142 2.58579 15.75 3 15.75H15C15.4142 15.75 15.75 15.4142 15.75 15V3C15.75 2.58579 15.4142 2.25 15 2.25H3ZM0.75 3C0.75 1.75736 1.75736 0.75 3 0.75H15C16.2426 0.75 17.25 1.75736 17.25 3V15C17.25 16.2426 16.2426 17.25 15 17.25H3C1.75736 17.25 0.75 16.2426 0.75 15V3Z" fill="currentColor" />
      <path d="M10.75 3.75C10.75 3.33579 11.0858 3 11.5 3H14C14.4142 3 14.75 3.33579 14.75 3.75V14.25C14.75 14.6642 14.4142 15 14 15H11.5C11.0858 15 10.75 14.6642 10.75 14.25V3.75Z" fill="currentColor" />
      <path d="M4 3.75C4 3.33579 4.33579 3 4.75 3H8.25C8.66421 3 9 3.33579 9 3.75V14.25C9 14.6642 8.66421 15 8.25 15H4.75C4.33579 15 4 14.6642 4 14.25V3.75Z" fill="currentColor" fillOpacity="0.28" />
    </svg>
  );
}

function WorkspaceSurface({
  frame,
  allFrames,
  isStreaming,
  displayMode,
  onClose,
  onSelectFrame,
  onDisplayModeChange,
}: {
  frame: WorkspaceFrame | null;
  allFrames: WorkspaceFrame[];
  isStreaming: boolean;
  displayMode: WorkspaceDisplayMode;
  onClose: () => void;
  onSelectFrame?: (frameId: string) => void;
  onDisplayModeChange?: (mode: WorkspaceDisplayMode) => void;
}) {
  const { t } = useTranslation();
  const currentLabel = frame ? getFrameTitle(frame) : t("workspace.noActivity", "No activity");

  return (
    <div
      data-workspace
      role="dialog"
      aria-modal={displayMode === "center" ? "true" : undefined}
      aria-label={t("workspace.title", "Aethos's Computer")}
      className="workspace-surface flex h-full w-full flex-col overflow-hidden rounded-[26px] border border-[var(--border-dark)]"
    >
      <div className="workspace-chrome-header flex shrink-0 items-center gap-3 px-4 py-[14px]">
        <div className="workspace-chrome-badge flex h-10 w-10 shrink-0 items-center justify-center rounded-[15px] text-[var(--text-primary)]">
          {displayMode === "center" ? <MonitorIcon /> : <DockRightIcon />}
        </div>

        <div className="min-w-0 flex-1">
          <div className="mb-0.5 flex items-center gap-2">
            <span className="workspace-header-kicker truncate text-[11px] font-medium uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
              {t("workspace.viewer", "Viewer")}
            </span>
            <span className="workspace-header-divider h-1 w-1 rounded-full bg-[var(--text-faint)]" aria-hidden="true" />
            <span className="truncate text-[11px] font-medium text-[var(--text-tertiary)]">
              {currentLabel}
            </span>
          </div>
          <div className="min-w-0 text-[15px] font-medium leading-[21px] text-[var(--text-primary)]">
            {t("workspace.title", "Aethos's Computer")}
          </div>
          <div className="truncate text-[11px] leading-[17px] text-[var(--text-secondary)]">
            {t("workspace.subtitle", "Live workspace for tools, files, and execution")}
          </div>
        </div>

        <div className="workspace-header-actions flex items-center gap-1">
          <button
            type="button"
            onClick={() => onDisplayModeChange?.(displayMode === "side" ? "center" : "side")}
            className="workspace-header-button flex h-8 items-center justify-center rounded-[10px] px-2 text-[var(--icon-secondary)] transition-colors duration-200 cursor-pointer"
            aria-expanded={displayMode === "center"}
            aria-label={displayMode === "side" ? t("workspace.openCentered", "Open centered workspace") : t("workspace.dockRight", "Dock workspace to the right")}
            title={displayMode === "side" ? t("workspace.openCentered", "Open centered") : t("workspace.dockRight", "Dock right")}
          >
            {displayMode === "side" ? <SidePanelIcon /> : <DockRightIcon />}
          </button>

          <div className="workspace-header-divider-line mx-1 h-4 w-px bg-[var(--border-main)]" />

          <button
            type="button"
            onClick={onClose}
            className="workspace-header-button flex h-8 w-8 items-center justify-center rounded-[10px] text-[var(--icon-secondary)] transition-colors duration-200 cursor-pointer"
            aria-label={t("workspace.close", "Close")}
          >
            <X className="size-[17px]" />
          </button>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col px-4 pb-4">
        <div className="mb-2.5">
          <ActivityStrip frame={frame} />
        </div>

        <div className="workspace-content-box relative flex min-h-0 flex-1 flex-col overflow-hidden rounded-[18px] border border-[var(--border-dark)]">
          <div className="workspace-content-glow pointer-events-none absolute inset-x-5 top-0 h-12" aria-hidden="true" />

          <div className="workspace-title-bar flex h-[38px] w-full items-center border-b border-[var(--border-main)] px-3">
            <div className="flex-1 flex justify-center">
              <span className="max-w-[250px] truncate text-[var(--text-tertiary)] text-sm font-medium text-center">
                {currentLabel}
              </span>
            </div>
          </div>

          <div className="flex-1 min-h-0 relative">
            <ContentArea frame={frame} />
          </div>

          <TaskStepBar
            frames={allFrames}
            selectedFrameId={frame?.id ?? null}
            onSelectFrame={onSelectFrame}
          />
        </div>
      </div>
    </div>
  );
}

/** Returns a human-readable title for the current frame */
function getFrameTitle(frame: WorkspaceFrame): string {
  const input = frame.input;
  if (typeof input.path === "string") return input.path.split(/[/\\]/).pop() || input.path;
  if (typeof input.command === "string") return input.command.split("\n")[0].slice(0, 80);
  if (typeof input.url === "string") return input.url.replace(/^https?:\/\//, "").split("/")[0];
  if (typeof input.query === "string") return input.query;
  return frame.toolName;
}

export default function WorkspacePanel({
  frame,
  allFrames,
  isStreaming,
  displayMode,
  sideWidth,
  onClose,
  onSelectFrame,
  onDisplayModeChange,
}: {
  frame: WorkspaceFrame | null;
  allFrames: WorkspaceFrame[];
  isStreaming: boolean;
  displayMode: WorkspaceDisplayMode;
  sideWidth?: number;
  onClose: () => void;
  onSelectFrame?: (frameId: string) => void;
  onDisplayModeChange?: (mode: WorkspaceDisplayMode) => void;
}) {
  const { t } = useTranslation();
  const [entered, setEntered] = useState(false);

  useEffect(() => {
    const frameId = requestAnimationFrame(() => setEntered(true));
    return () => cancelAnimationFrame(frameId);
  }, []);

  useEffect(() => {
    if (displayMode !== "center") return undefined;
    const handleKeyDown = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [displayMode, onClose]);

  return (
    <div
      className="workspace-stage fixed inset-0 z-50"
      data-mode={displayMode}
      data-entered={entered ? "true" : "false"}
    >
      <div
        className="workspace-stage-backdrop absolute inset-0"
        onClick={displayMode === "center" ? onClose : undefined}
      />
      <div
        className="workspace-shell absolute pr-3"
        data-mode={displayMode}
        style={displayMode === "side" && sideWidth ? { width: `${sideWidth}px` } : undefined}
      >
        <div className="workspace-shell-inner h-full w-full" data-mode={displayMode}>
          <WorkspaceSurface
            frame={frame}
            allFrames={allFrames}
            isStreaming={isStreaming}
            displayMode={displayMode}
            onClose={onClose}
            onSelectFrame={onSelectFrame}
            onDisplayModeChange={onDisplayModeChange}
          />
        </div>
      </div>
    </div>
  );
}
