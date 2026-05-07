import { CheckCircle2, LoaderCircle, Play, SkipBack, SkipForward, XCircle } from "lucide-react";
import { useRef } from "react";
import { useTranslation } from "react-i18next";
import type { WorkspaceFrame, WorkspaceFrameStatus } from "../../types";

function getStatusTone(status?: WorkspaceFrameStatus) {
  if (status === "in_progress") {
    return {
      dot: "bg-[var(--accent)]",
      text: "text-[var(--accent)]",
      chip: "border-[color:color-mix(in_srgb,var(--accent)_20%,transparent)] bg-[color:color-mix(in_srgb,var(--accent)_10%,var(--background-menu-white))]",
      Icon: LoaderCircle,
      animate: true,
    };
  }
  if (status === "completed") {
    return {
      dot: "bg-[var(--success)]",
      text: "text-[var(--success)]",
      chip: "border-[color:color-mix(in_srgb,var(--success)_18%,transparent)] bg-[color:color-mix(in_srgb,var(--success)_9%,var(--background-menu-white))]",
      Icon: CheckCircle2,
      animate: false,
    };
  }
  if (status === "failed" || status === "interrupted") {
    return {
      dot: "bg-[var(--danger)]",
      text: status === "failed" ? "text-[var(--danger)]" : "text-[var(--text-secondary)]",
      chip: "border-[color:color-mix(in_srgb,var(--danger)_16%,transparent)] bg-[color:color-mix(in_srgb,var(--danger)_10%,var(--background-menu-white))]",
      Icon: XCircle,
      animate: false,
    };
  }
  return {
    dot: "bg-[var(--text-tertiary)]",
    text: "text-[var(--text-tertiary)]",
    chip: "border-[var(--border-subtle)] bg-[var(--surface-soft)]",
    Icon: Play,
    animate: false,
  };
}

export default function TaskStepBar({
  frames,
  selectedFrameId,
  onSelectFrame,
}: {
  frames: WorkspaceFrame[];
  selectedFrameId: string | null;
  onSelectFrame?: (frameId: string) => void;
}) {
  const { t } = useTranslation();
  const seekerRef = useRef<HTMLSpanElement>(null);

  if (frames.length <= 1) return null;

  const currentIndex = Math.max(
    0,
    selectedFrameId ? frames.findIndex((frame) => frame.id === selectedFrameId) : frames.length - 1,
  );
  const safeIndex = currentIndex === -1 ? frames.length - 1 : currentIndex;
  const isLive = safeIndex === frames.length - 1;
  const progressPct = frames.length > 1 ? (safeIndex / (frames.length - 1)) * 100 : 100;
  const currentFrame = frames[safeIndex];
  const statusTone = getStatusTone(currentFrame?.status);
  const StatusIcon = statusTone.Icon;
  const liveLabel = currentFrame?.status === "in_progress"
    ? t("workspace.footer.streaming", "Streaming")
    : isLive
      ? t("workspace.footer.latest", "Latest")
      : t("workspace.footer.history", "History");

  const selectOffset = (offset: number) => {
    const nextIndex = safeIndex + offset;
    if (nextIndex < 0 || nextIndex >= frames.length) return;
    onSelectFrame?.(frames[nextIndex].id);
  };

  const handleSeekerClick = (e: React.MouseEvent<HTMLSpanElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const targetIndex = Math.round(ratio * (frames.length - 1));
    onSelectFrame?.(frames[targetIndex].id);
  };

  return (
    <div className="relative mt-auto flex shrink-0 items-center gap-3 border-t border-[var(--border-main)] bg-[color:color-mix(in_srgb,var(--background-menu-white)_94%,var(--surface-soft))] px-3.5 py-2">
      <div className="min-w-0">
        <div className="text-[11px] uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
          {t("workspace.footer.steps", "Steps")}
        </div>
        <div className="text-[12px] font-medium text-[var(--text-primary)]">
          {t("workspace.footer.stepCounter", "Step {{current}} of {{total}}", {
            current: safeIndex + 1,
            total: frames.length,
          })}
        </div>
      </div>

      <div className="flex min-w-0 flex-1 items-center gap-3">
        <div className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-[5px] text-[10px] font-medium uppercase tracking-[0.08em] ${statusTone.chip} ${statusTone.text}`}>
          <StatusIcon size={12} strokeWidth={2} className={statusTone.animate ? "animate-spin" : ""} />
          <span>{liveLabel}</span>
        </div>

        <span
          ref={seekerRef}
          className="group relative flex h-1 min-w-0 flex-1 cursor-pointer touch-none select-none items-center"
          onClick={handleSeekerClick}
          role="slider"
          aria-valuemin={0}
          aria-valuemax={frames.length - 1}
          aria-valuenow={safeIndex}
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "ArrowLeft") selectOffset(-1);
            if (e.key === "ArrowRight") selectOffset(1);
          }}
        >
          <div className="absolute -top-10 left-0 hidden h-[28px] items-center whitespace-nowrap rounded-full bg-[var(--text-primary)] px-[10px] text-xs text-[var(--text-white)] shadow-[0_10px_24px_rgba(15,23,42,0.18)] transition-opacity group-hover:flex">
            {currentFrame ? new Date(currentFrame.timestamp).toLocaleString() : ""}
          </div>

          <span className="relative h-full w-full rounded-full bg-[var(--fill-tsp-gray-dark)]">
            <span
              className="absolute h-full rounded-full bg-[var(--text-blue)]"
              style={{ left: "0%", right: `${100 - progressPct}%` }}
            />
          </span>

          <span
            className="pointer-events-none absolute -translate-x-1/2 p-[3px] transition-all duration-150"
            style={{ left: `${progressPct}%` }}
          >
            <span
              role="slider"
              className="relative block h-[14px] w-[14px] rounded-full border-2 border-[var(--background-menu-white)] bg-[var(--text-blue)] drop-shadow-[0px_1px_4px_rgba(0,0,0,0.12)]"
            />
          </span>
        </span>
      </div>

      <div className="flex items-center gap-1" dir="ltr">
        <button
          type="button"
          onClick={() => selectOffset(-1)}
          disabled={safeIndex <= 0}
          className="flex h-7 w-7 items-center justify-center rounded-[9px] text-[var(--icon-secondary)] transition-colors hover:bg-[var(--fill-tsp-white-light)] hover:text-[var(--icon-blue)] disabled:cursor-not-allowed disabled:opacity-30 cursor-pointer"
          aria-label={t("workspace.previous", "Previous")}
        >
          <SkipBack size={16} />
        </button>
        <button
          type="button"
          onClick={() => selectOffset(1)}
          disabled={safeIndex >= frames.length - 1}
          className="flex h-7 w-7 items-center justify-center rounded-[9px] text-[var(--icon-secondary)] transition-colors hover:bg-[var(--fill-tsp-white-light)] hover:text-[var(--icon-blue)] disabled:cursor-not-allowed disabled:opacity-30 cursor-pointer"
          aria-label={t("workspace.next", "Next")}
        >
          <SkipForward size={16} />
        </button>
      </div>

      {!isLive && (
        <button
          type="button"
          onClick={() => onSelectFrame?.(frames[frames.length - 1].id)}
          className="absolute left-[50%] flex h-10 translate-x-[-50%] items-center gap-1 rounded-full border border-[var(--border-main)] bg-[var(--background-menu-white)] px-3 shadow-[0px_8px_24px_rgba(15,23,42,0.14)] transition-colors hover:bg-[var(--fill-tsp-gray-main)] cursor-pointer animate-in slide-in-from-bottom-2 fade-in duration-200"
          style={{ bottom: "calc(100% + 10px)" }}
        >
          <Play size={16} stroke="var(--text-primary)" strokeWidth={2} />
          <span className="text-[var(--text-primary)] text-sm font-medium">
            {t("workspace.jumpToLive", "Jump to live")}
          </span>
        </button>
      )}
    </div>
  );
}
