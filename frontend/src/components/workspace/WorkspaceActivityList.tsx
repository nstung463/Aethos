import { CheckCircle2, Clock3, LoaderCircle, XCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { WorkspaceFrame, WorkspaceFrameStatus } from "../../types";
import { getWorkspaceActionLabel, getWorkspaceToolIcon } from "./utils";

function getStatusIcon(status?: WorkspaceFrameStatus) {
  switch (status) {
    case "completed":
      return CheckCircle2;
    case "interrupted":
    case "failed":
      return XCircle;
    case "in_progress":
      return LoaderCircle;
    default:
      return Clock3;
  }
}

function getStatusTone(status?: WorkspaceFrameStatus) {
  switch (status) {
    case "completed":
      return "bg-[color:color-mix(in_oklab,var(--success)_9%,var(--panel-raised))] text-[var(--success)] border-[color:color-mix(in_srgb,var(--success)_10%,transparent)]";
    case "interrupted":
      return "bg-[color:color-mix(in_oklab,var(--danger)_7%,var(--panel-raised))] text-[var(--text-secondary)] border-[color:color-mix(in_srgb,var(--danger)_10%,transparent)]";
    case "failed":
      return "bg-[color:color-mix(in_oklab,var(--danger)_9%,var(--panel-raised))] text-[var(--danger)] border-[color:color-mix(in_srgb,var(--danger)_10%,transparent)]";
    case "in_progress":
      return "bg-[color:color-mix(in_oklab,var(--accent)_10%,var(--panel-raised))] text-[var(--accent)] border-[color:color-mix(in_srgb,var(--accent)_12%,transparent)]";
    default:
      return "bg-[color:color-mix(in_oklab,var(--text-primary)_8%,var(--panel-raised))] text-[var(--text-tertiary)] border-[var(--border-subtle)]";
  }
}

function normalizeActionLabel(label: string) {
  return label.replace(/\s+/g, " ").replace(/^https?:\/\//, "").trim();
}

function getGroupStatus(frames: WorkspaceFrame[]): WorkspaceFrameStatus {
  if (frames.some((frame) => frame.status === "in_progress")) return "in_progress";
  if (frames.some((frame) => frame.status === "failed")) return "failed";
  if (frames.some((frame) => frame.status === "interrupted")) return "interrupted";
  if (frames.every((frame) => frame.status === "completed")) return "completed";
  return "pending";
}

export function WorkspaceActivityRow({
  messageId,
  frame,
  onOpenFrame,
}: {
  messageId: string;
  frame: WorkspaceFrame;
  onOpenFrame?: (messageId: string, frameId: string) => void;
}) {
  const { t } = useTranslation();
  const Icon = getWorkspaceToolIcon(frame.toolName, "timeline");
  const label = normalizeActionLabel(getWorkspaceActionLabel(frame));
  const StatusIcon = getStatusIcon(frame.status);
  const statusTone = getStatusTone(frame.status);
  const statusLabel = t(`workspace.status.${frame.status ?? "pending"}`, frame.status ?? "pending");
  const timestampLabel = new Date(frame.timestamp).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
  const buttonTitle = label
    ? t("workspace.openActivityWithLabel", "Open workspace for {{tool}}: {{label}}", {
        tool: t(`workspace.tools.${frame.toolName}`, frame.toolName),
        label,
      })
    : t("workspace.openActivity", "Open workspace for {{tool}}", {
        tool: t(`workspace.tools.${frame.toolName}`, frame.toolName),
      });

  return (
    <div className="group w-full">
      <button
        type="button"
        onClick={() => onOpenFrame?.(messageId, frame.id)}
        title={buttonTitle}
        aria-label={buttonTitle}
        className="w-full rounded-full border border-[color:color-mix(in_srgb,var(--border-subtle)_72%,transparent)] bg-[color:color-mix(in_srgb,var(--background-menu-white)_46%,transparent)] px-1.5 py-[3px] text-left transition-colors hover:border-[color:color-mix(in_srgb,var(--border-subtle)_92%,transparent)] hover:bg-[color:color-mix(in_srgb,var(--background-menu-white)_62%,var(--surface-soft))]"
      >
        <div className="flex min-w-0 items-center gap-1.5">
          <div className="flex h-4.5 w-4.5 shrink-0 items-center justify-center rounded-full border border-[var(--border-subtle)] bg-[color:color-mix(in_srgb,var(--background-menu-white)_84%,var(--surface-soft))] text-[var(--text-secondary)]">
            <Icon size={9} strokeWidth={1.9} />
          </div>

          <div className="flex min-w-0 flex-1 items-center gap-1.5">
            <span className="shrink-0 text-[10px] font-medium leading-4 text-[var(--text-primary)]">
              {t(`workspace.tools.${frame.toolName}`, frame.toolName)}
            </span>
            <span className="min-w-0 truncate text-[9px] leading-4 text-[var(--text-tertiary)]" title={buttonTitle}>
              {label || t("workspace.clickToOpen", "Click to open workspace")}
            </span>
          </div>

          <div className="flex shrink-0 items-center gap-0.5 pl-0.5">
            <span className={`inline-flex items-center gap-0.5 rounded-full border px-[5px] py-0 text-[7px] font-medium uppercase tracking-[0.03em] ${statusTone}`}>
              <StatusIcon size={7} strokeWidth={2} className={frame.status === "in_progress" ? "animate-spin" : ""} />
              <span>{statusLabel}</span>
            </span>
            <span className="text-[9px] leading-4 text-[var(--text-soft)]">{timestampLabel}</span>
          </div>
        </div>
      </button>
    </div>
  );
}

export function WorkspaceActivityGroupRow({
  messageId,
  frames,
  onOpenFrame,
}: {
  messageId: string;
  frames: WorkspaceFrame[];
  onOpenFrame?: (messageId: string, frameId: string) => void;
}) {
  const { t } = useTranslation();
  const latestFrame = frames.at(-1);
  if (!latestFrame) return null;

  const groupStatus = getGroupStatus(frames);
  const StatusIcon = getStatusIcon(groupStatus);
  const statusTone = getStatusTone(groupStatus);
  const statusLabel = t(`workspace.status.${groupStatus}`, groupStatus);
  const timestampLabel = new Date(latestFrame.timestamp).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
  const toolPreview = Array.from(
    new Set(frames.map((frame) => t(`workspace.tools.${frame.toolName}`, frame.toolName))),
  )
    .slice(0, 3)
    .join(", ");
  const buttonTitle = t("workspace.openActivityGroup", "Open workspace for {{count}} tool calls", {
    count: frames.length,
  });

  return (
    <div className="group w-full">
      <button
        type="button"
        onClick={() => onOpenFrame?.(messageId, latestFrame.id)}
        title={buttonTitle}
        aria-label={buttonTitle}
        className="w-full rounded-full border border-[color:color-mix(in_srgb,var(--border-subtle)_72%,transparent)] bg-[color:color-mix(in_srgb,var(--background-menu-white)_46%,transparent)] px-1.5 py-[3px] text-left transition-colors hover:border-[color:color-mix(in_srgb,var(--border-subtle)_92%,transparent)] hover:bg-[color:color-mix(in_srgb,var(--background-menu-white)_62%,var(--surface-soft))]"
      >
        <div className="flex min-w-0 items-center gap-1.5">
          <div className="flex h-4.5 w-4.5 shrink-0 items-center justify-center rounded-full border border-[var(--border-subtle)] bg-[color:color-mix(in_srgb,var(--background-menu-white)_84%,var(--surface-soft))] text-[var(--text-secondary)]">
            <Clock3 size={9} strokeWidth={1.9} />
          </div>

          <div className="flex min-w-0 flex-1 items-center gap-1.5">
            <span className="shrink-0 text-[10px] font-medium leading-4 text-[var(--text-primary)]">
              {t("workspace.groupSummary", "Used {{count}} tools", { count: frames.length })}
            </span>
            <span className="min-w-0 truncate text-[9px] leading-4 text-[var(--text-tertiary)]" title={toolPreview}>
              {toolPreview}
            </span>
          </div>

          <div className="flex shrink-0 items-center gap-0.5 pl-0.5">
            <span className={`inline-flex items-center gap-0.5 rounded-full border px-[5px] py-0 text-[7px] font-medium uppercase tracking-[0.03em] ${statusTone}`}>
              <StatusIcon size={7} strokeWidth={2} className={groupStatus === "in_progress" ? "animate-spin" : ""} />
              <span>{statusLabel}</span>
            </span>
            <span className="text-[9px] leading-4 text-[var(--text-soft)]">{timestampLabel}</span>
          </div>
        </div>
      </button>
    </div>
  );
}

export default function WorkspaceActivityList({
  messageId,
  frames,
  onOpenFrame,
}: {
  messageId: string;
  frames: WorkspaceFrame[];
  onOpenFrame?: (messageId: string, frameId: string) => void;
}) {
  if (frames.length === 0) return null;

  return (
    <div className="mt-2 space-y-1.5">
      {frames.map((frame) => (
        <WorkspaceActivityRow
          key={frame.id}
          messageId={messageId}
          frame={frame}
          onOpenFrame={onOpenFrame}
        />
      ))}
    </div>
  );
}
