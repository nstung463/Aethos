import { useEffect, useMemo, useState } from "react";
import { Search, Sparkles, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ExtensionSkill } from "../types";
import { fetchSkills } from "../utils/extensions";

export default function SkillPickerModal({
  rootDir,
  onClose,
  onSelect,
}: {
  rootDir: string;
  onClose: () => void;
  onSelect: (skill: ExtensionSkill) => void;
}) {
  const { t } = useTranslation();
  const [skills, setSkills] = useState<ExtensionSkill[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    fetchSkills(rootDir.trim() || undefined, controller.signal)
      .then(setSkills)
      .catch((err) => setError(err instanceof Error ? err.message : t("extensions.loadFailed", "Failed to load extensions.")));
    return () => controller.abort();
  }, [rootDir, t]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return skills.filter((skill) =>
      !needle ||
      skill.name.toLowerCase().includes(needle) ||
      skill.description.toLowerCase().includes(needle),
    );
  }, [query, skills]);

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="w-full max-w-2xl rounded-2xl border border-[var(--border-subtle)] bg-[var(--panel-elevated)] p-5 shadow-2xl">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-[var(--text-primary)]">{t("extensions.useSkill", "Use a skill")}</h2>
            <p className="mt-1 text-xs text-[var(--text-soft)]">
              {t("extensions.useSkillDesc", "Selecting a skill inserts a slash-style trigger. Aethos will still load full instructions through the skill tool.")}
            </p>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg p-2 text-[var(--text-soft)] hover:bg-[var(--surface-hover)]">
            <X size={16} strokeWidth={1.8} />
          </button>
        </div>

        <div className="relative mt-4">
          <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-faint)]" size={15} strokeWidth={1.8} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("extensions.searchSkills", "Search skills")}
            className="w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-soft)] py-2 pl-9 pr-3 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--border-strong)]"
          />
        </div>
        {error ? <div className="mt-3 rounded-xl border border-[var(--danger-border)] bg-[var(--danger-bg)] p-3 text-sm text-[var(--danger)]">{error}</div> : null}
        <div className="mt-4 max-h-[50vh] space-y-2 overflow-auto">
          {filtered.length === 0 ? (
            <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-soft)] p-4 text-sm text-[var(--text-secondary)]">
              {t("extensions.noSkills", "No skills found.")}
            </div>
          ) : filtered.map((skill) => (
            <button
              key={skill.name}
              type="button"
              onClick={() => onSelect(skill)}
              className="flex w-full items-start gap-3 rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-soft)] p-4 text-left transition hover:border-[var(--border-strong)] hover:bg-[var(--surface-hover)]"
            >
              <div className="rounded-xl bg-[var(--panel-elevated)] p-2 text-[var(--accent)]">
                <Sparkles size={16} strokeWidth={1.8} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold text-[var(--text-primary)]">{skill.name}</span>
                  <span className="rounded-full border border-[var(--border-subtle)] px-2 py-0.5 text-[10px] uppercase tracking-[0.14em] text-[var(--text-soft)]">{skill.source}</span>
                </div>
                <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">{skill.description}</p>
                {skill.argument_hint ? <p className="mt-2 text-xs text-[var(--text-soft)]">{skill.argument_hint}</p> : null}
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
