import { Plus, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

type PersonalizationForm = {
  nickname: string;
  occupation: string;
  about: string;
  instructions: string;
};

type PersonalizationTab = "profile" | "knowledge";

const STORAGE_KEY = "ethos-personalization";
const EMPTY_FORM: PersonalizationForm = {
  nickname: "",
  occupation: "",
  about: "",
  instructions: "",
};

function readStoredPersonalization(): PersonalizationForm {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (!stored) return EMPTY_FORM;
    const parsed = JSON.parse(stored) as Partial<PersonalizationForm>;
    return {
      nickname: typeof parsed.nickname === "string" ? parsed.nickname : "",
      occupation: typeof parsed.occupation === "string" ? parsed.occupation : "",
      about: typeof parsed.about === "string" ? parsed.about : "",
      instructions: typeof parsed.instructions === "string" ? parsed.instructions : "",
    };
  } catch {
    return EMPTY_FORM;
  }
}

export default function PersonalizationSettings() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<PersonalizationTab>("profile");
  const [savedForm, setSavedForm] = useState<PersonalizationForm>(EMPTY_FORM);
  const [form, setForm] = useState<PersonalizationForm>(EMPTY_FORM);
  const [savedState, setSavedState] = useState<"idle" | "saved">("idle");
  const [knowledgeSearch, setKnowledgeSearch] = useState("");

  useEffect(() => {
    const stored = readStoredPersonalization();
    setSavedForm(stored);
    setForm(stored);
  }, []);

  const isDirty = useMemo(() => JSON.stringify(form) !== JSON.stringify(savedForm), [form, savedForm]);

  const updateField = (field: keyof PersonalizationForm, value: string) => {
    setForm((current) => ({ ...current, [field]: value }));
    setSavedState("idle");
  };

  const handleSave = () => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(form));
    setSavedForm(form);
    setSavedState("saved");
    window.setTimeout(() => setSavedState("idle"), 1400);
  };

  const handleCancel = () => {
    setForm(savedForm);
    setSavedState("idle");
  };

  return (
    <div className="space-y-7">
      <div className="space-y-2">
        <h1 className="text-[26px] font-semibold tracking-tight text-[var(--text-primary)]">
          {t("settings.personalization", "Personalization")}
        </h1>
        <p className="text-[12px] leading-5 text-[var(--text-secondary)]">
          {t("settings.personalizationDesc", "Manage who you are and what Ethos remembers.")}
        </p>
      </div>

      <div className="border-b border-[var(--border-subtle)]">
        <div className="flex gap-5">
          {(["profile", "knowledge"] as PersonalizationTab[]).map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => setTab(item)}
              className={`relative px-1 py-3 text-[12px] font-medium transition ${
                tab === item ? "text-[var(--text-primary)]" : "text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
              }`}
            >
              {item === "profile" ? t("settings.profile", "Profile") : t("settings.knowledge", "Knowledge")}
              {tab === item ? <span className="absolute inset-x-0 bottom-[-1px] h-[2px] bg-[var(--Button-black)]" /> : null}
            </button>
          ))}
        </div>
      </div>

      {tab === "profile" ? (
        <section className="rounded-[8px] border border-[var(--border-subtle)] bg-[var(--panel-elevated)] p-6">
          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-2">
              <span className="text-[12px] font-medium text-[var(--text-primary)]">{t("settings.nickname", "Nickname")}</span>
              <input
                value={form.nickname}
                onChange={(event) => updateField("nickname", event.target.value)}
                placeholder={t("settings.nicknamePlaceholder", "What should Ethos call you?")}
                maxLength={256}
                className="h-10 w-full rounded-[8px] border border-[var(--border-subtle)] bg-[var(--panel-bg-soft)] px-3 text-[12px] text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)]"
                style={{ colorScheme: "inherit" }}
              />
            </label>
            <label className="space-y-2">
              <span className="text-[12px] font-medium text-[var(--text-primary)]">{t("settings.occupation", "Occupation")}</span>
              <input
                value={form.occupation}
                onChange={(event) => updateField("occupation", event.target.value)}
                placeholder={t("settings.occupationPlaceholder", "e.g., Product Designer, Software Engineer")}
                maxLength={256}
                className="h-10 w-full rounded-[8px] border border-[var(--border-subtle)] bg-[var(--panel-bg-soft)] px-3 text-[12px] text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)]"
                style={{ colorScheme: "inherit" }}
              />
            </label>
          </div>

          <label className="mt-5 block space-y-2">
            <span className="text-[12px] font-medium text-[var(--text-primary)]">{t("settings.moreAboutYou", "More about you")}</span>
            <textarea
              value={form.about}
              onChange={(event) => updateField("about", event.target.value)}
              placeholder={t("settings.moreAboutYouPlaceholder", "Your background, preferences, or location to help Ethos understand you better")}
              maxLength={2000}
              className="min-h-[150px] w-full resize-none rounded-[8px] border border-[var(--border-subtle)] bg-[var(--panel-bg-soft)] px-4 py-3 text-[12px] leading-5 text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)]"
              style={{ colorScheme: "inherit" }}
            />
            <div className="text-right text-xs text-[var(--text-tertiary)]">{form.about.length} / 2000</div>
          </label>

          <div className="my-6 border-t border-[var(--border-subtle)]" />

          <label className="block space-y-2">
            <span className="text-[12px] font-medium text-[var(--text-primary)]">{t("settings.customInstructions", "Custom Instructions")}</span>
            <textarea
              value={form.instructions}
              onChange={(event) => updateField("instructions", event.target.value)}
              placeholder={t(
                "settings.customInstructionsPlaceholder",
                "How would you like Ethos to respond? For example: focus on Python best practices, keep a professional tone, or always provide sources for important conclusions."
              )}
              maxLength={3000}
              className="min-h-[170px] w-full resize-none rounded-[8px] border border-[var(--border-subtle)] bg-[var(--panel-bg-soft)] px-4 py-3 text-[12px] leading-5 text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)]"
              style={{ colorScheme: "inherit" }}
            />
            <div className="text-right text-xs text-[var(--text-tertiary)]">{form.instructions.length} / 3000</div>
          </label>

          <div className="mt-6 flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={handleCancel}
              disabled={!isDirty}
              className="inline-flex h-9 min-w-[72px] items-center justify-center rounded-[8px] border border-[var(--border-subtle)] px-3 text-[12px] font-medium text-[var(--text-primary)] transition hover:bg-[var(--surface-hover)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {t("settings.cancel", "Cancel")}
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={!isDirty}
              className="inline-flex h-9 min-w-[72px] items-center justify-center rounded-[8px] bg-[var(--Button-black)] px-3 text-[12px] font-medium text-[var(--text-onblack)] transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {savedState === "saved" ? t("settings.saved", "Saved") : t("settings.save", "Save")}
            </button>
          </div>
        </section>
      ) : (
        <section className="rounded-[8px] border border-[var(--border-subtle)] bg-[var(--panel-elevated)]">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--border-subtle)] p-4">
            <label className="flex h-9 w-full items-center gap-2 rounded-[8px] border border-[var(--border-subtle)] bg-[var(--panel-bg-soft)] px-3 text-[var(--text-secondary)] sm:w-[240px]">
              <Search size={15} />
              <input
                aria-label={t("settings.searchKnowledge", "Search Knowledge")}
                value={knowledgeSearch}
                onChange={(event) => setKnowledgeSearch(event.target.value)}
                placeholder={t("settings.searchKnowledge", "Search Knowledge")}
                className="h-full min-w-0 flex-1 bg-transparent text-[12px] text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)]"
                style={{ colorScheme: "inherit" }}
              />
            </label>
            <button
              type="button"
              disabled
              title={t("settings.knowledgeAddUnavailable", "Knowledge editing is not available yet")}
              className="inline-flex h-9 items-center justify-center gap-2 rounded-[8px] bg-[var(--Button-black)] px-3 text-[12px] font-medium text-[var(--text-onblack)] opacity-50"
            >
              <Plus size={15} />
              {t("settings.add", "Add")}
            </button>
          </div>
          <div className="flex min-h-[280px] flex-col items-center justify-center gap-3 px-6 py-12 text-center">
            <Search size={28} className="text-[var(--text-tertiary)]" />
            <p className="text-[12px] text-[var(--text-tertiary)]">
              {knowledgeSearch
                ? t("settings.noKnowledgeResults", "No matching knowledge found")
                : t("settings.noKnowledge", "No knowledge yet")}
            </p>
          </div>
        </section>
      )}
    </div>
  );
}
