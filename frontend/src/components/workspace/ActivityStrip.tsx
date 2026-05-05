import { CheckCircle2, LoaderCircle, Sparkles, XCircle } from "lucide-react";
import { useId } from "react";
import { useTranslation } from "react-i18next";
import type { WorkspaceFrame } from "../../types";
import { getWorkspaceActionLabel, getWorkspaceToolIcon } from "./utils";

function getActionVerbKey(toolName: string): string {
  const verbs: Record<string, string> = {
    read_file: "workspace.actionVerbs.read_file",
    write_file: "workspace.actionVerbs.write_file",
    edit_file: "workspace.actionVerbs.edit_file",
    bash: "workspace.actionVerbs.bash",
    powershell: "workspace.actionVerbs.powershell",
    ls: "workspace.actionVerbs.ls",
    glob: "workspace.actionVerbs.glob",
    grep: "workspace.actionVerbs.grep",
    tavily_search: "workspace.actionVerbs.tavily_search",
    web_fetch: "workspace.actionVerbs.web_fetch",
    browser_action: "workspace.actionVerbs.browser_action",
    ask_user: "workspace.actionVerbs.ask_user",
    send_user_message: "workspace.actionVerbs.send_user_message",
  };
  return verbs[toolName] ?? "workspace.actionVerbs.default";
}

function normalizeActionLabel(label: string): string {
  return label.replace(/\s+/g, " ").replace(/^https?:\/\//, "").trim();
}

/** Manus-style tool icon: unique gradient fill + inner shadow bevel */
function ToolIconBadge({ toolName }: { toolName: string }) {
  const Icon = getWorkspaceToolIcon(toolName, "activity");
  const iconId = useId().replace(/:/g, "_");
  const filterId = `${iconId}-filter`;
  const gradientId = `${iconId}-gradient`;
  return (
    <div className="relative flex items-center justify-center flex-shrink-0" style={{ width: 18, height: 18 }}>
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width="18"
        height="18"
        viewBox="0 0 18 18"
        fill="none"
        style={{ minHeight: 18, minWidth: 18, position: "absolute", inset: 0 }}
      >
        <defs>
          <filter id={filterId} x="1.5" y="1.5" width="15" height="15" filterUnits="userSpaceOnUse" colorInterpolationFilters="sRGB">
            <feFlood floodOpacity="0" result="BackgroundImageFix" />
            <feBlend mode="normal" in="SourceGraphic" in2="BackgroundImageFix" result="shape" />
            <feColorMatrix in="SourceAlpha" type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 127 0" result="hardAlpha" />
            <feOffset dx="1" dy="1" />
            <feGaussianBlur stdDeviation="0.25" />
            <feComposite in2="hardAlpha" operator="arithmetic" k2="-1" k3="1" />
            <feColorMatrix type="matrix" values="0 0 0 0 1 0 0 0 0 1 0 0 0 0 1 0 0 0 0.6 0" />
            <feBlend mode="normal" in2="shape" result="effect1_innerShadow" />
            <feColorMatrix in="SourceAlpha" type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 127 0" result="hardAlpha" />
            <feOffset dx="-1" dy="-1" />
            <feGaussianBlur stdDeviation="0.25" />
            <feComposite in2="hardAlpha" operator="arithmetic" k2="-1" k3="1" />
            <feColorMatrix type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0.08 0" />
            <feBlend mode="normal" in2="effect1_innerShadow" result="effect2_innerShadow" />
          </filter>
          <linearGradient id={gradientId} x1="9" y1="2" x2="9" y2="16" gradientUnits="userSpaceOnUse">
            <stop stopColor="white" stopOpacity="0" />
            <stop offset="1" stopOpacity="0.16" />
          </linearGradient>
        </defs>
        <g filter={`url(#${filterId})`}>
          <path
            d="M5 2H13C14.6569 2 16 3.34315 16 5V13C16 14.6569 14.6569 16 13 16H5C3.34315 16 2 14.6569 2 13V5C2 3.34315 3.34315 2 5 2Z"
            fill={`url(#${gradientId})`}
          />
        </g>
        <path
          d="M5 2.5H13C14.3807 2.5 15.5 3.61929 15.5 5V13C15.5 14.3807 14.3807 15.5 13 15.5H5C3.61929 15.5 2.5 14.3807 2.5 13V5C2.5 3.61929 3.61929 2.5 5 2.5Z"
          stroke="var(--border-strong)"
          strokeWidth="1"
        />
      </svg>
      <span className="absolute flex items-center justify-center" style={{ width: 18, height: 18 }}>
        <Icon size={11} strokeWidth={2} className="text-[var(--text-secondary)]" />
      </span>
    </div>
  );
}

export default function ActivityStrip({
  frame,
  isStreaming,
}: {
  frame: WorkspaceFrame | null;
  isStreaming?: boolean;
}) {
  const { t } = useTranslation();
  if (!frame) return null;

  const actionLabel = normalizeActionLabel(getWorkspaceActionLabel(frame));
  const toolLabel = t(`workspace.tools.${frame.toolName}`, frame.toolName);
  const actionVerb = t(getActionVerbKey(frame.toolName), "Working on");
  const statusTone = isStreaming || frame.status === "in_progress"
    ? "text-[var(--accent)] bg-[color:color-mix(in_srgb,var(--accent)_12%,var(--background-menu-white))] border-[color:color-mix(in_srgb,var(--accent)_22%,transparent)]"
    : frame.status === "failed" || frame.status === "interrupted"
      ? "text-[var(--danger)] bg-[color:color-mix(in_srgb,var(--danger)_10%,var(--background-menu-white))] border-[color:color-mix(in_srgb,var(--danger)_18%,transparent)]"
    : frame.status === "completed"
      ? "text-[var(--success)] bg-[color:color-mix(in_srgb,var(--success)_10%,var(--background-menu-white))] border-[color:color-mix(in_srgb,var(--success)_18%,transparent)]"
      : "text-[var(--text-tertiary)] bg-[var(--surface-soft)] border-[var(--border-subtle)]";
  const StatusIcon = isStreaming || frame.status === "in_progress"
    ? LoaderCircle
    : frame.status === "failed" || frame.status === "interrupted"
      ? XCircle
    : frame.status === "completed"
      ? CheckCircle2
      : Sparkles;
  const statusLabel = isStreaming || frame.status === "in_progress"
    ? t("workspace.activityState.live", "Live")
    : frame.status === "failed" || frame.status === "interrupted"
      ? t(`workspace.status.${frame.status}`, frame.status)
    : frame.status === "completed"
      ? t("workspace.activityState.ready", "Ready")
      : t("workspace.activityState.idle", "Idle");

  return (
    <div className="rounded-[16px] border border-[var(--border-subtle)] bg-[color:color-mix(in_srgb,var(--background-menu-white)_90%,var(--surface-soft))] px-3 py-2 shadow-[0_8px_18px_rgba(15,23,42,0.035)]">
      <div className="flex flex-wrap items-start gap-2">
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <ToolIconBadge toolName={frame.toolName} />
          <div className="min-w-0">
            <div className="truncate text-[12px] font-medium text-[var(--text-secondary)]">
              {toolLabel}
            </div>
            <div className="truncate text-[11px] uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
              {t("workspace.using", "Ethos is using")} {toolLabel}
            </div>
          </div>
        </div>

        <div className={`inline-flex items-center gap-1 rounded-full border px-2 py-[5px] text-[10px] font-medium uppercase tracking-[0.08em] ${statusTone}`}>
          <StatusIcon size={12} strokeWidth={2} className={isStreaming || frame.status === "in_progress" ? "animate-spin" : ""} />
          <span>{statusLabel}</span>
        </div>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <div className="inline-flex max-w-full items-center gap-1 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-soft)] px-2.5 py-[5px] text-[10px] font-medium uppercase tracking-[0.1em] text-[var(--text-tertiary)]">
          <span>{actionVerb}</span>
        </div>

        {actionLabel ? (
          <code
            className="inline-flex min-w-0 max-w-full items-center truncate rounded-full border border-[var(--border-subtle)] bg-[var(--background-menu-white)] px-2.5 py-[5px] font-mono text-[11px] text-[var(--text-secondary)]"
            title={actionLabel}
          >
            {actionLabel}
          </code>
        ) : (
          <span className="text-[12px] text-[var(--text-soft)]">
            {t("workspace.activityFallback", "Waiting for the next workspace step")}
          </span>
        )}
      </div>
    </div>
  );
}
