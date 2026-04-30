import { useState } from "react";
import { useTranslation } from "react-i18next";
import { MessageSquareQuote, Send } from "lucide-react";
import type { AskUserQuestion, AskUserRequest } from "../types";

type Answers = Record<string, string>;
type Notes = Record<string, string>;

function QuestionBlock({
  q,
  answers,
  notes,
  onSelect,
  onNote,
}: {
  q: AskUserQuestion;
  answers: Answers;
  notes: Notes;
  onSelect: (question: string, label: string) => void;
  onNote: (question: string, note: string) => void;
}) {
  const selectedLabels = q.multi_select
    ? (answers[q.question] ?? "").split(",").filter(Boolean)
    : [(answers[q.question] ?? "")].filter(Boolean);
  const selectedOpts = q.options.filter((o) => selectedLabels.includes(o.label));
  const selectedPreviewOpt = selectedOpts.find((o) => o.preview) ?? null;
  const hasAnyPreview = q.options.some((o) => o.preview);

  return (
    <div className="space-y-3">
      {/* Header chip + question */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-soft)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-widest text-[var(--text-soft)]">
          {q.header}
        </span>
        <p className="text-sm font-semibold text-[var(--text-primary)]">{q.question}</p>
      </div>

      {/* Side-by-side: options list + active preview panel */}
      <div className={`flex gap-3 ${hasAnyPreview ? "items-start" : ""}`}>
        {/* Options */}
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          {q.options.map((opt) => {
            const isSelected = q.multi_select
              ? (answers[q.question] ?? "").split(",").includes(opt.label)
              : answers[q.question] === opt.label;

            function toggle() {
              if (q.multi_select) {
                const current = (answers[q.question] ?? "").split(",").filter(Boolean);
                const next = isSelected
                  ? current.filter((l) => l !== opt.label)
                  : [...current, opt.label];
                onSelect(q.question, next.join(","));
              } else {
                onSelect(q.question, opt.label);
              }
            }

            return (
              <button
                key={opt.label}
                type="button"
                onClick={toggle}
                className={`flex w-full items-start gap-3 rounded-xl border px-3 py-2.5 text-left transition-all
                  ${isSelected
                    ? "border-[var(--accent)]/60 bg-[color:color-mix(in_oklab,var(--accent)_8%,transparent)]"
                    : "border-[var(--border-subtle)] hover:border-[var(--border-strong)] hover:bg-[var(--surface-hover)]"
                  }`}
              >
                {/* Checkbox / radio indicator */}
                <span
                  className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-${q.multi_select ? "sm" : "full"} border transition-colors
                    ${isSelected
                      ? "border-[var(--accent)] bg-[var(--accent)]"
                      : "border-[var(--border-strong)]"
                    }`}
                >
                  {isSelected && (
                    <svg className="h-2.5 w-2.5 text-white" viewBox="0 0 10 10" fill="none">
                      {q.multi_select ? (
                        <path d="M2 5l2.5 2.5L8 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                      ) : (
                        <circle cx="5" cy="5" r="2.5" fill="currentColor" />
                      )}
                    </svg>
                  )}
                </span>

                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-[var(--text-primary)]">{opt.label}</p>
                  <p className="mt-0.5 text-xs leading-5 text-[var(--text-secondary)]">{opt.description}</p>
                  {opt.preview && !hasAnyPreview && (
                    <pre className="mt-1 overflow-x-auto rounded bg-[var(--surface-soft)] p-2 font-mono text-[11px] text-[var(--text-secondary)]">
                      {opt.preview}
                    </pre>
                  )}
                </div>
              </button>
            );
          })}
        </div>

        {/* Preview panel (when any option has preview) */}
        {hasAnyPreview && selectedPreviewOpt?.preview && (
          <div className="w-56 shrink-0 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-soft)] p-3">
            <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-[var(--text-soft)]">Preview</p>
            <pre className="overflow-x-auto font-mono text-[11px] leading-5 text-[var(--text-primary)] whitespace-pre">
              {selectedPreviewOpt.preview}
            </pre>
          </div>
        )}
      </div>

      {/* Notes textarea (shown when any selected option has a preview) */}
      {selectedPreviewOpt?.preview && (
        <textarea
          className="w-full resize-none rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-soft)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-soft)] focus:border-[var(--accent)]/50 focus:outline-none transition-colors"
          rows={2}
          placeholder="Add notes about this choice (optional)…"
          value={notes[q.question] ?? ""}
          onChange={(e) => onNote(q.question, e.target.value)}
        />
      )}
    </div>
  );
}

export default function AskUserCard({
  request,
  onSubmit,
}: {
  request: AskUserRequest;
  onSubmit: (answers: Answers, notes: Notes) => void;
}) {
  const { t } = useTranslation();
  const [answers, setAnswers] = useState<Answers>({});
  const [notes, setNotes] = useState<Notes>({});
  const [submitted, setSubmitted] = useState(false);

  const allAnswered = request.questions.every((q) => {
    const val = answers[q.question];
    return val !== undefined && val !== "";
  });

  function handleSelect(question: string, label: string) {
    setAnswers((prev) => ({ ...prev, [question]: label }));
  }

  function handleNote(question: string, note: string) {
    setNotes((prev) => ({ ...prev, [question]: note }));
  }

  function handleSubmit() {
    if (!allAnswered || submitted) return;
    setSubmitted(true);
    onSubmit(answers, notes);
  }

  return (
    <div className="mt-3 rounded-2xl border border-[var(--border-strong)] bg-[var(--panel-elevated)] p-4 shadow-[0_16px_40px_var(--shadow-panel)]">
      {/* Title row */}
      <div className="mb-4 flex items-center gap-2.5">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[color:color-mix(in_oklab,var(--accent)_18%,var(--panel-raised))] text-[var(--accent)]">
          <MessageSquareQuote size={15} strokeWidth={1.9} />
        </div>
        <p className="text-sm font-semibold text-[var(--text-primary)]">
          {t("askUser.title", "I need your input")}
        </p>
      </div>

      {/* Questions */}
      <div className="space-y-5">
        {request.questions.map((q) => (
          <QuestionBlock
            key={q.question}
            q={q}
            answers={answers}
            notes={notes}
            onSelect={handleSelect}
            onNote={handleNote}
          />
        ))}
      </div>

      {/* Submit */}
      <div className="mt-5 flex items-center justify-between">
        <p className="text-xs text-[var(--text-soft)]">
          {allAnswered
            ? t("askUser.readyToSubmit", "All questions answered")
            : t("askUser.answerAll", "Answer all questions to continue")}
        </p>
        <button
          type="button"
          onClick={handleSubmit}
          disabled={!allAnswered || submitted}
          className="flex items-center gap-1.5 rounded-xl bg-[var(--accent)] px-4 py-2 text-sm font-medium text-[var(--accent-contrast)] transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Send size={13} strokeWidth={2} />
          {submitted
            ? t("askUser.submitted", "Submitted")
            : t("askUser.submit", "Submit answers")}
        </button>
      </div>
    </div>
  );
}
