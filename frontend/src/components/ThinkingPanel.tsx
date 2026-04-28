import { useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

function SpinnerIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 14 14" fill="none" className="shrink-0 animate-spin text-[var(--accent)]">
      <circle cx="7" cy="7" r="5.5" stroke="currentColor" strokeWidth="1.5" strokeOpacity="0.25" />
      <path d="M7 1.5A5.5 5.5 0 0112.5 7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 14 14" fill="none" className="shrink-0 text-[var(--success)]">
      <circle cx="7" cy="7" r="5.5" stroke="currentColor" strokeWidth="1.5" />
      <path d="M4.5 7l2 2 3-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 12 12"
      fill="none"
      className={`shrink-0 text-[var(--text-faint)] transition-transform duration-200 ${open ? "rotate-180" : ""}`}
    >
      <path d="M2.5 4.5l3.5 3 3.5-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

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
    <div style={{ height, overflow: "hidden", transition: "height 0.28s cubic-bezier(0.4, 0, 0.2, 1)" }}>
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
  const hasReasoning = !!reasoning?.trim();
  const [open, setOpen] = useState(isStreaming);
  const prevStreamingRef = useRef(isStreaming);

  useEffect(() => {
    if (isStreaming && !prevStreamingRef.current) {
      setOpen(true);
    }
    prevStreamingRef.current = isStreaming;
  }, [isStreaming]);

  if (!hasReasoning && !isStreaming) return null;

  function getHeaderLabel() {
    if (isStreaming) return t("chat.thinking", "Thinking...");
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
        className="group flex items-center gap-1.5 text-xs text-[var(--text-soft)] transition-colors hover:text-[var(--text-muted)] cursor-pointer"
      >
        {isStreaming ? <SpinnerIcon /> : <CheckIcon />}
        <span className={isStreaming ? "thinking-shimmer" : "text-[var(--text-soft)]"}>{getHeaderLabel()}</span>
        <ChevronIcon open={open} />
      </button>

      <SlidePanel open={open}>
        <div className="mt-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--panel-bg-soft)] overflow-hidden">
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
