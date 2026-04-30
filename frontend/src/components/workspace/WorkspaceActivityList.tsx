import { CheckCircle2, Clock3, LoaderCircle, XCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { WorkspaceFrame, WorkspaceFrameStatus } from "../../types";
import { getWorkspaceActionLabel, getWorkspaceToolIcon } from "./utils";

function getStatusIcon(status?: WorkspaceFrameStatus) {
  switch (status) {
    case "completed":
      return CheckCircle2;
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
      return "bg-[color:color-mix(in_oklab,var(--success)_14%,var(--panel-raised))] text-[var(--success)] border-[color:color-mix(in_srgb,var(--success)_18%,transparent)]";
    case "failed":
      return "bg-[color:color-mix(in_oklab,var(--danger)_14%,var(--panel-raised))] text-[var(--danger)] border-[color:color-mix(in_srgb,var(--danger)_18%,transparent)]";
    case "in_progress":
      return "bg-[color:color-mix(in_oklab,var(--accent)_16%,var(--panel-raised))] text-[var(--accent)] border-[color:color-mix(in_srgb,var(--accent)_20%,transparent)]";
    default:
      return "bg-[color:color-mix(in_oklab,var(--text-primary)_8%,var(--panel-raised))] text-[var(--text-tertiary)] border-[var(--border-subtle)]";
  }
}

function normalizeActionLabel(label: string) {
  return label.replace(/\s+/g, " ").replace(/^https?:\/\//, "").trim();
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
        className="w-full rounded-[10px] border border-[var(--border-subtle)] bg-[color:color-mix(in_srgb,var(--background-menu-white)_76%,var(--surface-soft))] px-2 py-1.5 text-left shadow-[0_2px_8px_rgba(15,23,42,0.02)] transition-colors hover:border-[var(--border-strong)] hover:bg-[color:color-mix(in_srgb,var(--background-menu-white)_88%,var(--surface-soft))]"
      >
        <div className="flex items-center gap-2">
          <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-[var(--border-subtle)] bg-[var(--background-menu-white)] text-[var(--text-primary)]">
            <div className={`flex h-4.5 w-4.5 items-center justify-center rounded-[5px] border ${statusTone}`}>
              <Icon size={11} strokeWidth={1.9} />
            </div>
          </div>

          <div className="min-w-0 flex-1">
            <div className="flex min-w-0 items-center justify-between gap-2">
              <span className="truncate text-[11px] font-medium leading-4 text-[var(--text-primary)]">
                {t(`workspace.tools.${frame.toolName}`, frame.toolName)}
              </span>
              <span className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-1.5 py-px text-[9px] font-medium uppercase tracking-[0.04em] ${statusTone}`}>
                <StatusIcon size={10} strokeWidth={2} className={frame.status === "in_progress" ? "animate-spin" : ""} />
                <span>{statusLabel}</span>
              </span>
            </div>

            <div className="mt-0.5 flex min-w-0 items-center justify-between gap-2 text-[10px] leading-4 text-[var(--text-tertiary)]">
              <span className="truncate" title={buttonTitle}>
                {label || t("workspace.clickToOpen", "Click to open workspace")}
              </span>
              <span className="shrink-0">{timestampLabel}</span>
            </div>
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
    <div className="mt-3 space-y-2">
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
