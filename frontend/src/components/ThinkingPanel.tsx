import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { CheckCircle2, ChevronDown, LoaderCircle } from "lucide-react";

function SlidePanel({ open, children }: { open: boolean; children: ReactNode }) {
  const innerRef = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState(0);

  useEffect(() => {
    const el = innerRef.current;
    if (!el) return;
    setHeight(open ? el.scrollHeight : 0);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const el = innerRef.current;
    if (!el) return;
    const observer = new ResizeObserver(() => {
      setHeight(el.scrollHeight);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [open]);

  return (
    <div className="thinking-slide-panel" style={{ height, overflow: "hidden" }}>
      <div ref={innerRef}>{children}</div>
    </div>
  );
}

export default function ThinkingPanel({
  reasoning,
  isStreaming,
  thinkingDuration,
}: {
  reasoning?: string;
  isStreaming: boolean;
  thinkingDuration?: number;
}) {
  const { t } = useTranslation();
  const panelId = useId();
  const hasReasoning = !!reasoning?.trim();
  const [open, setOpen] = useState(false);

  if (!hasReasoning && !isStreaming) return null;

  function getHeaderLabel() {
    if (isStreaming) return t("chat.thinking", "Thinking…");
    if (thinkingDuration !== undefined) {
      if (thinkingDuration < 1) return t("chat.thoughtLessThanSecond", "Thought for less than a second");
      if (thinkingDuration === 1) return t("chat.thoughtOneSecond", "Thought for 1 second");
      return t("chat.thoughtSeconds", "Thought for {{count}} seconds", { count: thinkingDuration });
    }
    return t("chat.thought", "Thought");
  }

  return (
    <div className="mb-4">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={panelId}
        className="group flex items-center gap-1.5 rounded-md text-xs text-[var(--text-soft)] transition-colors hover:text-[var(--text-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--app-bg)] cursor-pointer"
      >
        {isStreaming ? (
          <LoaderCircle size={12} strokeWidth={1.8} aria-hidden="true" className="shrink-0 animate-spin text-[var(--accent)]" />
        ) : (
          <CheckCircle2 size={12} strokeWidth={1.8} aria-hidden="true" className="shrink-0 text-[var(--success)]" />
        )}
        <span className={isStreaming ? "thinking-shimmer" : "text-[var(--text-soft)]"} aria-live={isStreaming ? "polite" : undefined}>
          {getHeaderLabel()}
        </span>
        <ChevronDown
          size={12}
          strokeWidth={1.8}
          aria-hidden="true"
          className={`shrink-0 text-[var(--text-faint)] transition-transform duration-200 ${open ? "rotate-180" : ""}`}
        />
      </button>

      <SlidePanel open={open}>
        <div id={panelId} className="mt-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--panel-bg-soft)] overflow-hidden">
          {hasReasoning ? (
            <div className="px-3 py-2.5">
              <pre className="text-[11px] leading-relaxed whitespace-pre-wrap break-words font-mono text-[var(--text-muted)]">
                {reasoning}
              </pre>
            </div>
          ) : null}

          {isStreaming ? (
            <div className="flex items-center gap-1.5 px-3 py-2 border-t border-[var(--border-subtle)]">
              <span className="inline-flex gap-1">
                <span className="typing-dot" />
                <span className="typing-dot" style={{ animationDelay: "0.18s" }} />
                <span className="typing-dot" style={{ animationDelay: "0.36s" }} />
              </span>
            </div>
          ) : null}
        </div>
      </SlidePanel>
    </div>
  );
}
