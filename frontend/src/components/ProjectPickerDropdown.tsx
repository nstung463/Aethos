import { ChangeEvent, useEffect, useRef, useState, type InputHTMLAttributes } from "react";
import { FolderOpen, Plus, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";

type FolderInputProps = InputHTMLAttributes<HTMLInputElement> & {
  webkitdirectory?: string;
  directory?: string;
  mozdirectory?: string;
};

export default function ProjectPickerDropdown({
  currentDir,
  history,
  onSelectExisting,
  onBrowse,
  onRemoveProject,
}: {
  currentDir: string;
  history: string[];
  onSelectExisting: (path: string) => void;
  onBrowse: (files: File[]) => void;
  onRemoveProject: (path: string) => void;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [dropdownPos, setDropdownPos] = useState({ top: 0, right: 0 });
  const containerRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      setDropdownPos({
        top: rect.bottom + 8,
        right: window.innerWidth - rect.right,
      });
    }
  }, [open]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }

    if (open) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [open]);

  const displayName = currentDir ? currentDir.split(/[/\\]/).pop() || currentDir : null;
  const folderInputProps: FolderInputProps = {
    type: "file",
    multiple: true,
    className: "hidden",
    onChange: (e: ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(e.target.files ?? []);
      if (files.length > 0) {
        onBrowse(files);
      }
      e.target.value = "";
    },
    webkitdirectory: "",
    directory: "",
    mozdirectory: "",
  };

  return (
    <div className="relative shrink-0" ref={containerRef}>
      <input ref={folderInputRef} {...folderInputProps} />

      {/* Trigger button */}
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex min-w-0 shrink items-center gap-1.5 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-soft)] px-2 py-1 text-[10px] text-[var(--text-secondary)] transition-all hover:border-[var(--border-strong)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] cursor-pointer sm:py-1.5 sm:text-xs"
        style={{ maxWidth: "180px", flexShrink: 1 }}
        title={currentDir ? t("chat.changeFolder", "Change project: {{dir}}", { dir: currentDir }) : t("chat.chooseProject", "Choose project")}
        aria-label={t("chat.chooseProject", "Choose project")}
      >
        <FolderOpen size={12} strokeWidth={1.9} className="shrink-0" />
        <span className="truncate min-w-0 hidden [@media(min-width:640px)]:block">
          {displayName || t("chat.chooseProject", "Choose project")}
        </span>
      </button>

      {/* Dropdown menu - fixed positioning to avoid being hidden under chat content */}
      {open && (
        <div
          className="fixed z-50 w-80
                     rounded-xl border border-[var(--border-strong)]
                     bg-[var(--panel-elevated)] py-1.5 shadow-xl"
          style={{
            top: `${dropdownPos.top}px`,
            right: `${dropdownPos.right}px`,
            boxShadow: "0 20px 45px var(--shadow-panel)",
          }}
        >
          {/* Recent projects section */}
          {history.length > 0 && (
            <>
              <div className="px-3 py-1 text-[10px] font-medium text-[var(--text-faint)]">
                {t("chat.recentProjects", "Recent projects")}
              </div>
              {history.map((path) => {
                const name = path.split(/[/\\]/).pop() || path;
                return (
                  <div
                    key={path}
                    className="group flex items-center gap-2 px-3 py-2 text-[11px] text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]"
                  >
                    <button
                      type="button"
                      onClick={() => {
                        onSelectExisting(path);
                        setOpen(false);
                      }}
                      className="flex min-w-0 flex-1 items-center gap-2 rounded cursor-pointer transition-colors hover:text-[var(--text-primary)]"
                    >
                      <FolderOpen size={13} strokeWidth={1.8} className="shrink-0" />
                      <div className="min-w-0 flex-1">
                        <div className="truncate font-medium">{name}</div>
                        <div className="truncate text-[10px] text-[var(--text-faint)]">{path}</div>
                      </div>
                    </button>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onRemoveProject(path);
                      }}
                      className="shrink-0 rounded p-1 opacity-0 transition-all hover:bg-[var(--surface-soft)] group-hover:opacity-100"
                      title={t("common.remove", "Remove")}
                    >
                      <Trash2 size={11} strokeWidth={2} className="text-[var(--text-faint)]" />
                    </button>
                  </div>
                );
              })}
              <div className="my-1 border-t border-[var(--border-subtle)]" />
            </>
          )}

          {/* Browse for new folder button */}
          <button
            type="button"
            onClick={() => {
              folderInputRef.current?.click();
              setOpen(false);
            }}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] cursor-pointer"
          >
            <Plus size={14} strokeWidth={1.8} />
            <span>{t("chat.browseFolder", "Browse for folder...")}</span>
          </button>
        </div>
      )}
    </div>
  );
}
