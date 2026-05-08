import { useEffect, useId, useRef, useState } from "react";
import { Check, ChevronDown } from "lucide-react";

export type StyledSelectOption<T extends string> = {
  value: T;
  label: string;
};

type StyledSelectProps<T extends string> = {
  id?: string;
  value: T;
  options: StyledSelectOption<T>[];
  onValueChange: (value: T) => void;
  className?: string;
  buttonClassName?: string;
  label?: string;
};

export default function StyledSelect<T extends string>({
  id,
  value,
  options,
  onValueChange,
  className = "",
  buttonClassName = "",
  label,
}: StyledSelectProps<T>) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const listboxId = useId();
  const selectedOption = options.find((option) => option.value === value) ?? options[0];

  useEffect(() => {
    if (!open) return;

    const handlePointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  return (
    <div ref={rootRef} className={`relative ${className}`}>
      <button
        id={id}
        type="button"
        aria-label={label}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listboxId}
        onClick={() => setOpen((current) => !current)}
        className={`flex w-full items-center justify-between rounded-xl border border-[var(--border-subtle)] bg-[var(--panel-elevated)] py-2 pl-3 pr-2 text-left text-sm text-[var(--text-primary)] outline-none transition hover:border-[var(--border-strong)] focus:border-[var(--accent)] ${buttonClassName}`}
      >
        <span className="truncate">{selectedOption?.label}</span>
        <ChevronDown
          aria-hidden="true"
          size={15}
          strokeWidth={1.8}
          className={`ml-2 shrink-0 text-[var(--text-faint)] transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open ? (
        <div
          id={listboxId}
          role="listbox"
          className="absolute left-0 right-0 top-[calc(100%+6px)] z-30 max-h-64 overflow-y-auto rounded-2xl border border-[var(--border-subtle)] bg-[var(--panel-elevated)] p-1 shadow-[0_18px_45px_var(--shadow-panel)]"
        >
          {options.map((option) => {
            const active = option.value === value;

            return (
              <button
                key={option.value}
                type="button"
                role="option"
                aria-selected={active}
                onClick={() => {
                  onValueChange(option.value);
                  setOpen(false);
                }}
                className={`flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2 text-left text-sm transition ${
                  active
                    ? "bg-[var(--surface-hover)] text-[var(--text-primary)]"
                    : "text-[var(--text-secondary)] hover:bg-[var(--surface-soft)] hover:text-[var(--text-primary)]"
                }`}
              >
                <span className="truncate">{option.label}</span>
                {active ? <Check size={14} strokeWidth={1.9} className="shrink-0 text-[var(--accent)]" /> : null}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
