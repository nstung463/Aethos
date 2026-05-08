import { useMemo } from "react";
import { Languages, MonitorCog, MoonStar, PanelsTopLeft, Sparkles, SunMedium, Waypoints, Zap } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useTheme, type ThemeMode } from "../../context/ThemeContext";
import {
  type ComposerSendShortcut,
  type GeneralPreferences,
  type SidebarDefaultState,
  updateGeneralPreferences,
} from "../../utils/generalPreferences";

type GeneralSettingsProps = {
  localRootDir: string;
  generalPreferences: GeneralPreferences;
};

type BehaviorOption<T extends string | boolean> = {
  value: T;
  label: string;
  description: string;
};

function SegmentedOptions<T extends string | boolean>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: BehaviorOption<T>[];
  onChange: (value: T) => void;
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={String(option.value)}
            type="button"
            onClick={() => onChange(option.value)}
            className={`rounded-[18px] border p-4 text-left transition ${
              active
                ? "border-[var(--border-strong)] bg-[var(--surface-hover)]"
                : "border-[var(--border-subtle)] bg-[var(--panel-bg-soft)]"
            }`}
          >
            <div className="text-[13px] font-medium text-[var(--text-primary)]">{option.label}</div>
            <div className="mt-2 text-[12px] leading-5 text-[var(--text-secondary)]">{option.description}</div>
          </button>
        );
      })}
    </div>
  );
}

export default function GeneralSettings({ localRootDir, generalPreferences }: GeneralSettingsProps) {
  const { t, i18n } = useTranslation();
  const { themeMode, setThemeMode } = useTheme();

  const languageOptions = useMemo(
    () => [
      { value: "en", label: t("common.english", "English") },
      { value: "vi", label: t("common.vietnamese", "Tieng Viet") },
    ],
    [t],
  );

  const normalizedLanguage = (i18n.resolvedLanguage || i18n.language || "en").split("-")[0];
  const currentLanguageLabel =
    languageOptions.find((option) => option.value === normalizedLanguage)?.label ?? t("common.english", "English");
  const themeModeLabel =
    themeMode === "dark" ? t("settings.dark", "Dark") : themeMode === "light" ? t("settings.light", "Light") : t("settings.auto", "Auto");

  const autoOpenOptions = useMemo<BehaviorOption<boolean>[]>(
    () => [
      {
        value: true,
        label: t("settings.behaviorOn", "On"),
        description: t("settings.autoOpenWorkspaceOnDesc", "Open the workspace automatically when tool output includes a live frame."),
      },
      {
        value: false,
        label: t("settings.behaviorOff", "Off"),
        description: t("settings.autoOpenWorkspaceOffDesc", "Keep workspace frames available in chat until you open them manually."),
      },
    ],
    [t],
  );

  const sidebarOptions = useMemo<BehaviorOption<SidebarDefaultState>[]>(
    () => [
      {
        value: "expanded",
        label: t("settings.sidebarExpanded", "Expanded"),
        description: t("settings.sidebarExpandedDesc", "Show the full navigation rail when the app opens."),
      },
      {
        value: "collapsed",
        label: t("settings.sidebarCollapsed", "Collapsed"),
        description: t("settings.sidebarCollapsedDesc", "Start with the compact icon rail to maximize chat space."),
      },
    ],
    [t],
  );

  const motionOptions = useMemo<BehaviorOption<boolean>[]>(
    () => [
      {
        value: false,
        label: t("settings.motionStandard", "Standard"),
        description: t("settings.motionStandardDesc", "Use the full set of transitions, overlays, and workspace motion."),
      },
      {
        value: true,
        label: t("settings.motionReduced", "Reduced"),
        description: t("settings.motionReducedDesc", "Minimize non-essential animation across the interface."),
      },
    ],
    [t],
  );

  const shortcutOptions = useMemo<BehaviorOption<ComposerSendShortcut>[]>(
    () => [
      {
        value: "enter",
        label: t("settings.sendShortcutEnter", "Enter to send"),
        description: t("settings.sendShortcutEnterDesc", "Press Shift + Enter when you want a new line."),
      },
      {
        value: "mod_enter",
        label: t("settings.sendShortcutModEnter", "Ctrl/Cmd + Enter"),
        description: t("settings.sendShortcutModEnterDesc", "Press Enter for new lines and use Ctrl/Cmd + Enter to send."),
      },
    ],
    [t],
  );

  return (
    <div className="space-y-6 md:space-y-8">
      <div className="space-y-2">
        <h1 className="text-[26px] font-semibold tracking-tight text-[var(--text-primary)]">
          {t("settings.general", "General")}
        </h1>
        <p className="text-[12px] leading-5 text-[var(--text-secondary)]">
          {t("settings.generalDesc", "Choose how the settings experience looks and which language the interface uses.")}
        </p>
      </div>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <article className="rounded-[24px] border border-[var(--border-subtle)] bg-[var(--panel-elevated)] p-5 md:p-6">
          <div className="space-y-5">
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-[12px] font-medium text-[var(--text-primary)]">
                <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-[var(--panel-bg-soft)] text-[var(--text-primary)]">
                  <Languages size={16} />
                </span>
                <label htmlFor="settings-language">{t("settings.language", "Language")}</label>
              </div>
              <p className="text-[12px] leading-5 text-[var(--text-secondary)]">
                {t("settings.languageDesc", "Select your preferred language for the interface.")}
              </p>
            </div>

            <select
              id="settings-language"
              value={normalizedLanguage}
              onChange={(event) => i18n.changeLanguage(event.target.value)}
              className="h-11 w-full rounded-[14px] border border-[var(--border-subtle)] bg-[var(--panel-bg-soft)] px-3 text-[13px] text-[var(--text-primary)]"
              style={{ colorScheme: "inherit" }}
            >
              {languageOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>

            <div className="rounded-[18px] border border-[var(--border-subtle)] bg-[var(--panel-bg-soft)] p-4">
              <div className="text-[12px] font-medium text-[var(--text-primary)]">
                {t("settings.languageAppliesTo", "Where this applies")}
              </div>
              <div className="mt-2 text-[12px] leading-5 text-[var(--text-secondary)]">
                {t(
                  "settings.languageAppliesToDesc",
                  "Menus, settings labels, chat controls, and supporting interface text switch instantly.",
                )}
              </div>
            </div>
          </div>
        </article>

        <article className="rounded-[24px] border border-[var(--border-subtle)] bg-[var(--panel-elevated)] p-5 md:p-6">
          <div className="space-y-5">
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-[12px] font-medium text-[var(--text-primary)]">
                <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-[var(--panel-bg-soft)] text-[var(--text-primary)]">
                  {themeMode === "light" ? <SunMedium size={16} /> : themeMode === "dark" ? <MoonStar size={16} /> : <Sparkles size={16} />}
                </span>
                <span>{t("settings.theme", "Theme")}</span>
              </div>
              <p className="text-[12px] leading-5 text-[var(--text-secondary)]">
                {t("settings.themePickerDesc", "Pick a fixed appearance or let Aethos follow your device setting.")}
              </p>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              {(["light", "dark", "auto"] as ThemeMode[]).map((option) => {
                const active = themeMode === option;
                const icon =
                  option === "light" ? <SunMedium size={16} /> : option === "dark" ? <MoonStar size={16} /> : <Sparkles size={16} />;
                const label =
                  option === "light"
                    ? t("settings.light", "Light")
                    : option === "dark"
                      ? t("settings.dark", "Dark")
                      : t("settings.auto", "Auto");
                const description =
                  option === "light"
                    ? t("settings.themeOptionLightDesc", "Bright surfaces for daytime work.")
                    : option === "dark"
                      ? t("settings.themeOptionDarkDesc", "Lower-glare contrast for focused sessions.")
                      : t("settings.themeOptionAutoDesc", "Match your system theme automatically.");

                return (
                  <button
                    key={option}
                    type="button"
                    onClick={() => setThemeMode(option)}
                    className={`rounded-[18px] border p-4 text-left transition ${
                      active
                        ? "border-[var(--border-strong)] bg-[var(--surface-hover)] shadow-[0_0_0_1px_var(--border-subtle)]"
                        : "border-[var(--border-subtle)] bg-[var(--panel-bg-soft)]"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-2">
                        <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-[var(--panel-elevated)] text-[var(--text-primary)]">
                          {icon}
                        </span>
                        <span className="text-[12px] font-medium text-[var(--text-primary)]">{label}</span>
                      </div>
                    </div>
                    <p className="mt-3 text-[12px] leading-5 text-[var(--text-secondary)]">{description}</p>
                    <div className="mt-4 flex h-10 items-end gap-2 rounded-[14px] border border-[var(--border-subtle)] bg-[var(--panel-elevated)] p-2">
                      <span className="h-full flex-1 rounded-[10px] bg-[var(--surface-hover)]" />
                      <span className="h-3/4 w-7 rounded-[8px] bg-[var(--panel-bg-soft)]" />
                      <span className="h-1/2 w-7 rounded-[8px] bg-[var(--surface-hover)]" />
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </article>
      </section>

      <section className="rounded-[24px] border border-[var(--border-subtle)] bg-[var(--panel-elevated)] p-5 md:p-6">
        <div className="space-y-6">
          <div className="space-y-2">
            <h2 className="text-[20px] font-semibold text-[var(--text-primary)]">{t("settings.appBehavior", "App behavior")}</h2>
            <p className="text-[12px] leading-5 text-[var(--text-secondary)]">
              {t("settings.appBehaviorDesc", "Tune how the app opens, moves, and responds during day-to-day work.")}
            </p>
          </div>

          <div className="grid gap-5">
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-[13px] font-medium text-[var(--text-primary)]">
                <Waypoints size={16} />
                {t("settings.autoOpenWorkspace", "Auto-open workspace when tools run")}
              </div>
              <SegmentedOptions
                value={generalPreferences.autoOpenWorkspace}
                options={autoOpenOptions}
                onChange={(value) => updateGeneralPreferences({ autoOpenWorkspace: value })}
              />
            </div>

            <div className="space-y-3">
              <div className="flex items-center gap-2 text-[13px] font-medium text-[var(--text-primary)]">
                <PanelsTopLeft size={16} />
                {t("settings.sidebarDefaultState", "Sidebar default state")}
              </div>
              <SegmentedOptions
                value={generalPreferences.sidebarDefaultState}
                options={sidebarOptions}
                onChange={(value) => updateGeneralPreferences({ sidebarDefaultState: value })}
              />
            </div>

            <div className="space-y-3">
              <div className="flex items-center gap-2 text-[13px] font-medium text-[var(--text-primary)]">
                <Zap size={16} />
                {t("settings.reduceMotion", "Reduce motion")}
              </div>
              <SegmentedOptions
                value={generalPreferences.reduceMotion}
                options={motionOptions}
                onChange={(value) => updateGeneralPreferences({ reduceMotion: value })}
              />
            </div>

            <div className="space-y-3">
              <div className="flex items-center gap-2 text-[13px] font-medium text-[var(--text-primary)]">
                <MonitorCog size={16} />
                {t("settings.composerSendShortcut", "Composer send shortcut")}
              </div>
              <SegmentedOptions
                value={generalPreferences.composerSendShortcut}
                options={shortcutOptions}
                onChange={(value) => updateGeneralPreferences({ composerSendShortcut: value })}
              />
            </div>
          </div>
        </div>
      </section>

      <section className="rounded-[24px] border border-[var(--border-subtle)] bg-[var(--panel-elevated)] p-5 md:p-6">
        <div className="space-y-4">
          <div className="space-y-2">
            <h2 className="text-[20px] font-semibold text-[var(--text-primary)]">
              {t("settings.aboutWorkspace", "About this workspace")}
            </h2>
            <p className="text-[12px] leading-5 text-[var(--text-secondary)]">
              {t("settings.aboutWorkspaceDesc", "A quick readout of the environment this app session is currently using.")}
            </p>
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            <div className="rounded-[18px] border border-[var(--border-subtle)] bg-[var(--panel-bg-soft)] p-4">
              <div className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                {t("settings.currentProjectPath", "Current project path")}
              </div>
              <div className="mt-3 break-all text-[13px] leading-6 text-[var(--text-primary)]">
                {localRootDir || t("settings.noProjectSelected", "No project selected")}
              </div>
            </div>
            <div className="rounded-[18px] border border-[var(--border-subtle)] bg-[var(--panel-bg-soft)] p-4">
              <div className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                {t("settings.currentThemeMode", "Current theme mode")}
              </div>
              <div className="mt-3 text-[13px] leading-6 text-[var(--text-primary)]">{themeModeLabel}</div>
            </div>
            <div className="rounded-[18px] border border-[var(--border-subtle)] bg-[var(--panel-bg-soft)] p-4">
              <div className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                {t("settings.currentAppLanguage", "Current app language")}
              </div>
              <div className="mt-3 text-[13px] leading-6 text-[var(--text-primary)]">{currentLanguageLabel}</div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
