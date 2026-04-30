import { AlertTriangle, LockKeyhole, ShieldAlert, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { PermissionMode, PermissionRequest, ThreadPermissionsBundle } from "../types";

export default function PermissionPromptCard({
  prompt,
  threadPermissions,
  onApproveOnce,
  onApproveForChat,
  onBypassForChat,
  onPromoteThreadPermissions,
  onOpenSecuritySettings,
}: {
  prompt: PermissionRequest;
  threadPermissions: ThreadPermissionsBundle | null;
  onApproveOnce: () => Promise<void>;
  onApproveForChat: (mode: PermissionMode) => Promise<void>;
  onBypassForChat: () => Promise<void>;
  onPromoteThreadPermissions: () => Promise<void>;
  onOpenSecuritySettings: () => void;
}) {
  const { t } = useTranslation();
  const [status, setStatus] = useState("");
  const [busyAction, setBusyAction] = useState<"" | "approve_once" | "approve_chat" | "bypass_chat" | "promote">("");

  async function runAction(
    action: "" | "approve_once" | "approve_chat" | "bypass_chat" | "promote",
    fn: () => Promise<void>,
  ) {
    try {
      setBusyAction(action);
      setStatus("");
      await fn();
      if (action === "promote") {
        setStatus(t("permissions.savedDefault", "Saved as your default permission profile."));
      } else {
        setStatus(t("permissions.approvalApplied", "Approval applied. Retrying the blocked action..."));
      }
    } catch (error) {
      setStatus(error instanceof Error ? error.message : t("permissions.updateFailed", "Permission update failed."));
    } finally {
      setBusyAction("");
    }
  }

  const effectiveMode = threadPermissions?.effective.mode ?? null;
  const skillDetails = prompt.subject === "skill"
    ? [
        prompt.skill,
        prompt.source,
        prompt.server,
        prompt.path,
      ].filter(Boolean)
    : [];
  const icon =
    prompt.behavior === "ask" ? (
      <ShieldAlert size={18} strokeWidth={1.9} />
    ) : (
      <LockKeyhole size={18} strokeWidth={1.9} />
    );

  return (
    <div className="mt-3 rounded-2xl border border-[var(--border-strong)] bg-[var(--panel-elevated)] p-4 shadow-[0_16px_40px_var(--shadow-panel)]">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[color:color-mix(in_oklab,var(--accent)_18%,var(--panel-raised))] text-[var(--accent)]">
          {icon}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              {prompt.behavior === "ask" ? t("permissions.needsPermission", "This chat needs permission") : t("permissions.blockedByPermissions", "This chat is blocked by permissions")}
            </p>
            {effectiveMode ? (
              <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-soft)] px-2 py-0.5 text-[10px] uppercase tracking-[0.16em] text-[var(--text-soft)]">
                {effectiveMode.replace("_", " ")}
              </span>
            ) : null}
          </div>
          <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">{prompt.reason}</p>
          {skillDetails.length > 0 || (prompt.allowed_tools?.length ?? 0) > 0 ? (
            <div className="mt-3 grid gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-soft)] px-3 py-2 text-xs text-[var(--text-soft)]">
              {skillDetails.length > 0 ? (
                <div>
                  <span className="font-medium text-[var(--text-secondary)]">{t("permissions.skillRequest", "Skill request")}:</span>{" "}
                  {skillDetails.join(" - ")}
                </div>
              ) : null}
              {(prompt.allowed_tools?.length ?? 0) > 0 ? (
                <div>
                  <span className="font-medium text-[var(--text-secondary)]">{t("permissions.requestedTools", "Requested tools")}:</span>{" "}
                  {prompt.allowed_tools?.join(", ")}
                </div>
              ) : null}
            </div>
          ) : null}
          <p className="mt-2 text-xs leading-5 text-[var(--text-soft)]">
            {t("permissions.approvalsTemporary", "Approvals here are temporary for this thread. Use settings only if you want to change your defaults.")}
          </p>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => runAction("approve_once", onApproveOnce)}
          disabled={busyAction !== ""}
          className="rounded-xl border border-[var(--border-subtle)] px-3 py-2 text-sm font-medium text-[var(--text-primary)] transition hover:border-[var(--border-strong)] hover:bg-[var(--surface-hover)] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busyAction === "approve_once" ? t("permissions.retrying", "Retrying...") : t("permissions.approveOnce", "Approve once")}
        </button>
        <button
          type="button"
          onClick={() =>
            runAction(
              "approve_chat",
              () => onApproveForChat(prompt.suggested_mode ?? "bypass_permissions"),
            )
          }
          disabled={busyAction !== ""}
          className="rounded-xl border border-[var(--accent)]/40 bg-[color:color-mix(in_oklab,var(--accent)_10%,transparent)] px-3 py-2 text-sm font-medium text-[var(--text-primary)] transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busyAction === "approve_chat" ? t("permissions.retrying", "Retrying...") : t("permissions.approveChat", "Approve for this chat")}
        </button>
        <button
          type="button"
          onClick={() => runAction("bypass_chat", onBypassForChat)}
          disabled={busyAction !== ""}
          className="rounded-xl border border-[var(--border-subtle)] px-3 py-2 text-sm font-medium text-[var(--text-secondary)] transition hover:border-[var(--border-strong)] hover:bg-[var(--surface-hover)] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busyAction === "bypass_chat" ? t("permissions.retrying", "Retrying...") : t("permissions.bypassChat", "Bypass for this chat")}
        </button>
        <button
          type="button"
          onClick={() => runAction("promote", onPromoteThreadPermissions)}
          disabled={busyAction !== ""}
          className="rounded-xl border border-[var(--border-subtle)] px-3 py-2 text-sm font-medium text-[var(--text-secondary)] transition hover:border-[var(--border-strong)] hover:bg-[var(--surface-hover)] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busyAction === "promote" ? t("permissions.saving", "Saving...") : t("permissions.saveCurrentThread", "Save current thread defaults")}
        </button>
        <button
          type="button"
          onClick={onOpenSecuritySettings}
          className="rounded-xl px-3 py-2 text-sm font-medium text-[var(--accent)] transition hover:bg-[color:color-mix(in_oklab,var(--accent)_10%,transparent)]"
        >
          {t("permissions.openSecuritySettings", "Open Security Settings")}
        </button>
      </div>

      {status ? (
        <div className="mt-3 flex items-center gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-soft)] px-3 py-2 text-xs text-[var(--text-secondary)]">
          {status.includes("failed") ? <AlertTriangle size={14} strokeWidth={1.8} /> : <ShieldCheck size={14} strokeWidth={1.8} />}
          <span>{status}</span>
        </div>
      ) : null}
    </div>
  );
}
