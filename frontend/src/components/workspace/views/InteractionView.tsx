import type { WorkspaceFrame } from "../../../types";

export default function InteractionView({ frame }: { frame: WorkspaceFrame }) {
  if (frame.toolName === "send_user_message") {
    const message = (frame.input.message as string | undefined) ?? "";
    return (
      <div className="p-4">
        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-soft)] p-4 text-sm text-[var(--text-primary)] leading-relaxed">
          {message || <span className="italic text-[var(--text-tertiary,#666)]">No message content</span>}
        </div>
      </div>
    );
  }

  // ask_user
  const questions = (
    frame.input.questions as
      | Array<{ question: string; header: string; options: { label: string; description: string }[] }>
      | undefined
  ) ?? [];

  if (questions.length === 0) {
    return (
      <div className="p-4 text-xs italic text-[var(--text-tertiary,#666)]">Waiting for question data…</div>
    );
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      {questions.map((q, qi) => (
        <div
          key={`${q.header}-${qi}`}
          className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-soft)] p-4 flex flex-col gap-3"
        >
          <div className="text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]">
            {q.header}
          </div>
          <div className="text-sm font-medium text-[var(--text-primary)]">{q.question}</div>
          <div className="flex flex-col gap-2">
            {q.options.map((opt, oi) => (
              <div
                key={`${opt.label}-${oi}`}
                className="rounded-lg border border-[var(--border-subtle)] px-3 py-2"
              >
                <div className="text-xs font-medium text-[var(--text-primary)]">{opt.label}</div>
                <div className="text-xs text-[var(--text-secondary)]">{opt.description}</div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
