import {
  BookOpenText,
  Bot,
  Brain,
  ChartNoAxesColumnIncreasing,
  FolderInput,
  Hammer,
  PencilLine,
  SearchCheck,
  Puzzle,
  Sparkles,
  Star,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import type { SlashCommandDef, SlashCommandOptionDef } from "../utils/slashCommands";

const COMMAND_ICONS: Record<string, LucideIcon> = {
  build: Hammer,
  review: SearchCheck,
  explain: BookOpenText,
  rename: PencilLine,
  favorite: Star,
  project: FolderInput,
  think: Brain,
  context: ChartNoAxesColumnIncreasing,
  skill: Puzzle,
};

export default function SlashCommandMenu({
  commands,
  options,
  selectedIndex,
  onSelect,
  onSelectOption,
  optionCommand,
}: {
  commands?: SlashCommandDef[];
  options?: SlashCommandOptionDef[];
  selectedIndex: number;
  onSelect?: (command: SlashCommandDef) => void;
  onSelectOption?: (option: SlashCommandOptionDef) => void;
  optionCommand?: SlashCommandDef | null;
}) {
  const { t } = useTranslation();
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const visibleCommands = commands ?? [];
  const visibleOptions = options ?? [];
  const isOptionMenu = !!optionCommand;
  const itemCount = isOptionMenu ? visibleOptions.length : visibleCommands.length;

  useEffect(() => {
    const selectedOption = scrollContainerRef.current?.querySelector<HTMLElement>(
      "[data-selected='true']",
    );
    selectedOption?.scrollIntoView({ block: "nearest" });
  }, [selectedIndex, visibleCommands, visibleOptions]);

  if (itemCount === 0) return null;

  let lastCategory = "";

  return (
    <div
      role="listbox"
      aria-label={t("slashCommands.menuLabel", "Slash commands")}
      className="absolute bottom-full left-0 right-0 z-50 mb-2 max-h-[min(24rem,calc(100vh-12rem))] overflow-hidden rounded-2xl border border-[var(--border-strong)] bg-[color-mix(in_oklab,var(--panel-elevated)_96%,transparent)] p-1.5 shadow-[0_22px_60px_var(--shadow-panel)] ring-1 ring-[color-mix(in_oklab,var(--text-primary)_7%,transparent)] backdrop-blur-xl"
    >
      <div ref={scrollContainerRef} className="max-h-[inherit] overflow-y-auto pr-0.5">
        {isOptionMenu && optionCommand ? (
          <>
            <div className="px-2.5 pb-1 pt-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-faint)]">
              {t("slashCommands.chooseOption", "Choose option")}
            </div>
            {visibleOptions.map((option, index) => {
              const isSelected = index === selectedIndex;

              return (
                <button
                  key={option.value}
                  type="button"
                  role="option"
                  aria-selected={isSelected}
                  data-selected={isSelected ? "true" : undefined}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    onSelectOption?.(option);
                  }}
                  className={`group flex min-h-[3rem] w-full items-center gap-3 rounded-xl px-3 py-2 text-left transition-all ${
                    isSelected
                      ? "bg-[var(--surface-hover)] text-[var(--text-primary)] shadow-[inset_0_0_0_1px_color-mix(in_oklab,var(--text-primary)_8%,transparent)]"
                      : "text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
                  }`}
                >
                  <span
                    className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border transition-colors ${
                      isSelected
                        ? "border-[color-mix(in_oklab,var(--text-primary)_16%,var(--border-subtle))] bg-[var(--panel-raised)] text-[var(--text-primary)]"
                        : "border-[var(--border-subtle)] bg-[var(--surface-soft)] text-[var(--text-soft)] group-hover:text-[var(--text-primary)]"
                    }`}
                  >
                    <Brain size={16} strokeWidth={1.9} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex min-w-0 items-baseline gap-2">
                      <span className="shrink-0 text-sm font-semibold text-[var(--text-primary)]">
                        {t(option.labelKey, option.defaultLabel)}
                      </span>
                      <span className="truncate text-xs text-[var(--text-soft)]">
                        /{optionCommand.name} {option.value}
                      </span>
                    </span>
                    {option.descriptionKey ? (
                      <span className="block truncate text-xs leading-5 text-[var(--text-faint)]">
                        {t(option.descriptionKey, option.defaultDescription ?? option.value)}
                      </span>
                    ) : null}
                  </span>
                </button>
              );
            })}
          </>
        ) : visibleCommands.map((cmd, index) => {
          const showCategory = cmd.category !== lastCategory;
          const Icon = COMMAND_ICONS[cmd.name] ?? (cmd.category === "skill" ? COMMAND_ICONS.skill : Bot);
          const isSelected = index === selectedIndex;
          lastCategory = cmd.category;

          return (
            <div key={cmd.name}>
              {showCategory ? (
                <div className="px-2.5 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-faint)] first:pt-1">
                  {t(`slashCommands.categories.${cmd.category}`, cmd.category)}
                </div>
              ) : null}
              <button
                type="button"
                role="option"
                aria-selected={isSelected}
                data-selected={isSelected ? "true" : undefined}
                onMouseDown={(e) => {
                  e.preventDefault();
                  onSelect?.(cmd);
                }}
                className={`group flex min-h-[3rem] w-full items-center gap-3 rounded-xl px-3 py-2 text-left transition-all ${
                  isSelected
                    ? "bg-[var(--surface-hover)] text-[var(--text-primary)] shadow-[inset_0_0_0_1px_color-mix(in_oklab,var(--text-primary)_8%,transparent)]"
                    : "text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
                }`}
              >
                <span
                  className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border transition-colors ${
                    isSelected
                      ? "border-[color-mix(in_oklab,var(--text-primary)_16%,var(--border-subtle))] bg-[var(--panel-raised)] text-[var(--text-primary)]"
                      : "border-[var(--border-subtle)] bg-[var(--surface-soft)] text-[var(--text-soft)] group-hover:text-[var(--text-primary)]"
                  }`}
                >
                  <Icon size={16} strokeWidth={1.9} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex min-w-0 items-baseline gap-2">
                    <span className="shrink-0 text-sm font-semibold text-[var(--text-primary)]">
                      /{cmd.name}
                    </span>
                    {cmd.argsPlaceholderKey && cmd.defaultArgsPlaceholder ? (
                      <span className="truncate text-xs text-[var(--text-soft)]">
                        {t(cmd.argsPlaceholderKey, cmd.defaultArgsPlaceholder)}
                      </span>
                    ) : null}
                  </span>
                  <span className="block truncate text-xs leading-5 text-[var(--text-faint)]">
                    {t(cmd.descriptionKey, cmd.defaultDescription)}
                  </span>
                </span>
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
