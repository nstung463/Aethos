import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ExtensionSkill, WorkspaceFrame } from "../../../types";
import { fetchSkill } from "../../../utils/extensions";

type SkillViewProps = {
  frame: WorkspaceFrame;
  rootDir?: string;
};

type SkillState =
  | { status: "loading" }
  | { status: "ready"; skill: ExtensionSkill }
  | { status: "error" };

function extractSkillName(frame: WorkspaceFrame) {
  const value = frame.input.skill;
  return typeof value === "string" ? value.trim() : "";
}

export default function SkillView({ frame, rootDir }: SkillViewProps) {
  const { t } = useTranslation();
  const skillName = useMemo(() => extractSkillName(frame), [frame]);
  const [state, setState] = useState<SkillState>(() => (skillName ? { status: "loading" } : { status: "error" }));

  useEffect(() => {
    if (!skillName) {
      setState({ status: "error" });
      return undefined;
    }

    const controller = new AbortController();
    setState({ status: "loading" });

    void fetchSkill(skillName, rootDir?.trim() || undefined, controller.signal)
      .then((skill) => {
        setState({ status: "ready", skill });
      })
      .catch(() => {
        setState({ status: "error" });
      });

    return () => controller.abort();
  }, [rootDir, skillName]);

  const fallbackContent = frame.output?.trim() || t("workspace.skill.unavailable", "No skill content available.");
  const content = state.status === "ready"
    ? state.skill.body?.trim() || fallbackContent
    : fallbackContent;

  return (
    <div className="flex h-full flex-col bg-[var(--background-menu-white)]">
      <div className="border-b border-[var(--border-main)] px-4 py-2.5">
        <div className="truncate text-sm font-medium text-[var(--text-primary)]">
          {skillName || t("workspace.noActivity", "No activity")}
        </div>
        {state.status === "loading" ? (
          <div className="mt-1 text-xs text-[var(--text-secondary)]">
            {t("workspace.skill.loading", "Loading skill file...")}
          </div>
        ) : null}
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        <pre className="whitespace-pre-wrap break-words rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-soft)] p-4 text-xs leading-6 text-[var(--text-primary)]">
          {content}
        </pre>
      </div>
    </div>
  );
}
