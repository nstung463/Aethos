import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type {
  PermissionBehavior,
  PermissionMode,
  PermissionProfile,
  PermissionRuleInput,
  PermissionSubject,
} from "../../types";

const EMPTY_PROFILE: PermissionProfile = {
  mode: null,
  working_directories: [],
  rules: [],
};

const getModeOptions = (t: any): Array<{ value: PermissionMode | null; label: string; description: string }> => [
  {
    value: null,
    label: t("settings.useServerDefault", "Use server default"),
    description: t("settings.useServerDefaultDesc", "No personal override. New chats inherit the backend default mode."),
  },
  {
    value: "default",
    label: t("settings.defaultPerm", "Default"),
    description: t("settings.defaultPermDesc", "Reads are generally allowed. Edits and risky shell actions ask first."),
  },
  {
    value: "accept_edits",
    label: t("settings.acceptEdits", "Accept edits"),
    description: t("settings.acceptEditsDesc", "Workspace edits are allowed, but shell still goes through safety checks."),
  },
  {
    value: "bypass_permissions",
    label: t("settings.bypassPermissions", "Bypass permissions"),
    description: t("settings.bypassPermissionsDesc", "Most asks are auto-allowed unless explicitly denied or safety-blocked."),
  },
  {
    value: "dont_ask",
    label: t("settings.dontAsk", "Don't ask"),
    description: t("settings.dontAskDesc", "Any action that would ask instead becomes a deny."),
  },
];

function normalizeProfile(profile: PermissionProfile | null): PermissionProfile {
  if (!profile) return EMPTY_PROFILE;
  return {
    mode: profile.mode,
    working_directories: [...profile.working_directories],
    rules: profile.rules.map((rule) => ({ ...rule, matcher: rule.matcher ?? null })),
  };
}

function rulesToText(rules: PermissionRuleInput[]): string {
  return rules
    .map((rule) =>
      [rule.subject, rule.behavior, rule.matcher?.trim() || ""]
        .join(" | ")
        .trim(),
    )
    .join("\n");
}

function parseRules(text: string): PermissionRuleInput[] {
  const rules: PermissionRuleInput[] = [];
  for (const rawLine of text.split("\n")) {
    const line = rawLine.trim();
    if (!line) continue;
    const [subjectPart, behaviorPart, ...matcherParts] = line.split("|").map((item) => item.trim());
    if (
      subjectPart !== "read" &&
      subjectPart !== "edit" &&
      subjectPart !== "bash" &&
      subjectPart !== "powershell" &&
      subjectPart !== "skill"
    ) {
      throw new Error(`Unknown subject in rule: ${subjectPart || "(empty)"}`);
    }
    if (behaviorPart !== "allow" && behaviorPart !== "ask" && behaviorPart !== "deny") {
      throw new Error(`Unknown behavior in rule: ${behaviorPart || "(empty)"}`);
    }
    const matcher = matcherParts.join(" | ").trim();
    rules.push({
      subject: subjectPart as PermissionSubject,
      behavior: behaviorPart as PermissionBehavior,
      matcher: matcher || null,
    });
  }
  return rules;
}

export default function SecuritySettings({
  value,
  isLoading,
  error,
  onSave,
}: {
  value: PermissionProfile | null;
  isLoading: boolean;
  error: string;
  onSave: (profile: PermissionProfile) => Promise<void>;
}) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState<PermissionProfile>(EMPTY_PROFILE);
  const [workingDirectoriesText, setWorkingDirectoriesText] = useState("");
  const [rulesText, setRulesText] = useState("");
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved">("idle");
  const [localError, setLocalError] = useState("");

  useEffect(() => {
    const nextDraft = normalizeProfile(value);
    setDraft(nextDraft);
    setWorkingDirectoriesText(nextDraft.working_directories.join("\n"));
    setRulesText(rulesToText(nextDraft.rules));
  }, [value]);

  const activeError = localError || error;
  const activeMode = draft.mode;

  async function handleSave() {
    try {
      setLocalError("");
      setSaveState("saving");
      const nextProfile: PermissionProfile = {
        mode: draft.mode,
        working_directories: Array.from(
          new Set(
            workingDirectoriesText
              .split("\n")
              .map((item) => item.trim())
              .filter(Boolean),
          ),
        ),
        rules: parseRules(rulesText),
      };
      await onSave(nextProfile);
      setSaveState("saved");
      window.setTimeout(() => setSaveState("idle"), 1200);
    } catch (saveError) {
      setSaveState("idle");
      setLocalError(saveError instanceof Error ? saveError.message : t("settings.failedSaveSecurity", "Failed to save security settings."));
    }
  }

  async function handleResetPermissions() {
    try {
      setLocalError("");
      setSaveState("saving");
      await onSave(EMPTY_PROFILE);
      setSaveState("saved");
      window.setTimeout(() => setSaveState("idle"), 1200);
    } catch (saveError) {
      setSaveState("idle");
      setLocalError(saveError instanceof Error ? saveError.message : t("settings.failedResetSecurity", "Failed to reset security settings."));
    }
  }

  function handleClearLocalData() {
    if (!window.confirm(t("settings.confirmClearLocalData", "Clear local UI state and reload this browser session?"))) return;
    localStorage.clear();
    window.location.reload();
  }

  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <h1 className="text-[26px] font-semibold text-[var(--text-primary)]">{t("settings.security", "Security")}</h1>
        <p className="text-[13px] leading-6 text-[var(--text-secondary)]">
          {t("settings.securityDesc", "Set your default permission profile for new chats. Temporary approvals during a chat still live on the thread until you save them as defaults.")}
        </p>
      </div>

      <section className="space-y-4">
        <label className="block text-xs font-medium uppercase tracking-wider text-[var(--text-soft)]">
          {t("settings.defaultPermissionMode", "Default Permission Mode")}
        </label>
        <div className="grid gap-3">
          {getModeOptions(t).map((option) => {
            const selected = activeMode === option.value;
            return (
              <button
                key={option.label}
                type="button"
                onClick={() => {
                  setDraft((current) => ({ ...current, mode: option.value }));
                  setSaveState("idle");
                }}
                className={`rounded-2xl border px-4 py-3 text-left transition ${
                  selected
                    ? "border-[var(--accent)] bg-[color:color-mix(in_oklab,var(--accent)_14%,var(--panel-elevated))]"
                    : "border-[var(--border-subtle)] bg-[var(--panel-elevated)] hover:border-[var(--border-strong)]"
                }`}
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[13px] font-medium text-[var(--text-primary)]">{option.label}</span>
                  {selected ? (
                    <span className="rounded-full bg-[var(--accent)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-white">
                      {t("settings.active", "Active")}
                    </span>
                  ) : null}
                </div>
                <p className="mt-1 text-xs leading-5 text-[var(--text-soft)]">{option.description}</p>
              </button>
            );
          })}
        </div>
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="space-y-3 rounded-2xl border border-[var(--border-subtle)] bg-[var(--panel-elevated)] p-5">
          <label
            htmlFor="permission-working-directories"
            className="block text-xs font-medium uppercase tracking-wider text-[var(--text-soft)]"
          >
            {t("settings.defaultWorkingDirs", "Default Working Directories")}
          </label>
          <textarea
            id="permission-working-directories"
            value={workingDirectoriesText}
            onChange={(event) => {
              setWorkingDirectoriesText(event.target.value);
              setSaveState("idle");
            }}
            rows={7}
            placeholder={"src\nworkspace/reports"}
            className="w-full rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-soft)] px-4 py-3 text-[13px] leading-6 text-[var(--text-primary)] outline-none transition focus:border-[var(--border-strong)]"
          />
          <p className="text-xs leading-5 text-[var(--text-soft)]">
            {t("settings.defaultWorkingDirsDesc", "One path per line. Relative paths are resolved from the chat workspace root.")}
          </p>
        </section>

        <section className="space-y-3 rounded-2xl border border-[var(--border-subtle)] bg-[var(--panel-elevated)] p-5">
          <label
            htmlFor="permission-rules"
            className="block text-xs font-medium uppercase tracking-wider text-[var(--text-soft)]"
          >
            {t("settings.defaultRules", "Default Rules")}
          </label>
          <textarea
            id="permission-rules"
            value={rulesText}
            onChange={(event) => {
              setRulesText(event.target.value);
              setSaveState("idle");
            }}
            rows={7}
            placeholder={"edit | allow | docs/**\nbash | deny | curl *"}
            className="w-full rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-soft)] px-4 py-3 font-mono text-[13px] leading-6 text-[var(--text-primary)] outline-none transition focus:border-[var(--border-strong)]"
          />
          <p className="text-xs leading-5 text-[var(--text-soft)]">
            {t("settings.formatText", "Format:")} <code>subject | behavior | matcher</code>. {t("settings.matcherOptional", "Matcher is optional.")} {t("settings.subjectsText", "Subjects:")} <code>read</code>, <code>edit</code>, <code>bash</code>, <code>powershell</code>, <code>skill</code>.
          </p>
        </section>
      </div>

      {activeError ? (
        <div className="rounded-2xl border border-[var(--danger-border)] bg-[var(--danger-bg)] px-4 py-3 text-[13px] text-[var(--danger)]">
          {activeError}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={handleSave}
          disabled={isLoading || saveState === "saving"}
          className="rounded-xl bg-[var(--accent)] px-4 py-2.5 text-[13px] font-medium text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {saveState === "saving" ? t("settings.saving", "Saving...") : saveState === "saved" ? t("settings.saved", "Saved") : t("settings.saveDefaults", "Save defaults")}
        </button>
        <button
          type="button"
          onClick={handleResetPermissions}
          disabled={isLoading || saveState === "saving"}
          className="rounded-xl border border-[var(--border-subtle)] px-4 py-2.5 text-[13px] font-medium text-[var(--text-secondary)] transition hover:border-[var(--border-strong)] hover:bg-[var(--surface-hover)] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {t("settings.resetPermissionDefaults", "Reset permission defaults")}
        </button>
      </div>

      <section className="space-y-4">
        <label className="block text-xs font-medium uppercase tracking-wider text-[var(--danger)]">
          {t("settings.dangerZone", "Danger Zone")}
        </label>
        <div className="rounded-2xl border border-[var(--danger-border)] bg-[var(--danger-bg)] p-4">
          <h3 className="text-[13px] font-medium text-[var(--text-primary)]">{t("settings.clearLocalBrowserData", "Clear local browser data")}</h3>
          <p className="mt-2 text-xs leading-5 text-[var(--text-soft)]">
            {t("settings.clearLocalBrowserDataDesc", "Remove cached threads, profile settings, and auth state from this browser only. Server-side files and thread permissions are not deleted.")}
          </p>
          <button
            type="button"
            onClick={handleClearLocalData}
            className="mt-4 rounded-xl border border-[var(--danger)]/40 px-3 py-2 text-[13px] font-medium text-[var(--danger)] transition hover:bg-[var(--danger)]/10"
          >
            {t("settings.clearLocalDataBtn", "Clear local data")}
          </button>
        </div>
      </section>
    </div>
  );
}
