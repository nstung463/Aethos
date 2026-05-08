import { Check, Languages, LaptopMinimal, MoonStar, SunMedium } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useTheme, type ThemeMode } from "../../context/ThemeContext";

export default function GeneralSettings() {
  const { t, i18n } = useTranslation();
  const { themeMode, setThemeMode } = useTheme();

  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <h1 className="text-[26px] font-semibold tracking-tight text-[var(--text-primary)]">
          {t("settings.general", "General")}
        </h1>
        <p className="text-[12px] leading-5 text-[var(--text-secondary)]">
          {t("settings.generalDesc", "Choose how the settings experience looks and which language the interface uses.")}
        </p>
      </div>

      <section className="rounded-[24px] border border-[var(--border-subtle)] bg-[var(--panel-elevated)] p-6">
        <div className="space-y-6">
          <div>
            <div className="mb-2 flex items-center gap-2 text-[12px] font-medium text-[var(--text-primary)]">
              <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-[var(--panel-bg-soft)] text-[var(--text-primary)]">
                <Languages size={16} />
              </span>
              <label htmlFor="settings-language">{t("settings.language", "Language")}</label>
            </div>
            <select
              id="settings-language"
              value={i18n.language || "en"}
              onChange={(event) => i18n.changeLanguage(event.target.value)}
              className="h-11 w-full rounded-[14px] border border-[var(--border-subtle)] bg-[var(--panel-bg-soft)] px-3 text-[13px] text-[var(--text-primary)]"
              style={{ colorScheme: "inherit" }}
            >
              <option value="en">{t("common.english", "English")}</option>
              <option value="vi">{t("common.vietnamese", "Tieng Viet")}</option>
            </select>
          </div>

          <div>
            <div className="mb-3 flex items-center gap-2 text-[12px] font-medium text-[var(--text-primary)]">
              <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-[var(--panel-bg-soft)] text-[var(--text-primary)]">
                {themeMode === "light" ? <SunMedium size={16} /> : themeMode === "dark" ? <MoonStar size={16} /> : <LaptopMinimal size={16} />}
              </span>
              <span>{t("settings.theme", "Theme")}</span>
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              {(["light", "dark", "auto"] as ThemeMode[]).map((option) => {
                const active = themeMode === option;
                const icon =
                  option === "light" ? <SunMedium size={16} /> : option === "dark" ? <MoonStar size={16} /> : <LaptopMinimal size={16} />;
                return (
                  <button
                    key={option}
                    type="button"
                    onClick={() => setThemeMode(option)}
                    className={`rounded-[18px] border p-4 text-left transition ${
                      active ? "border-[var(--border-strong)] bg-[var(--surface-hover)]" : "border-[var(--border-subtle)] bg-[var(--panel-bg-soft)]"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-[var(--panel-elevated)] text-[var(--text-primary)]">
                          {icon}
                        </span>
                        <span className="text-[12px] font-medium text-[var(--text-primary)]">
                          {option === "light"
                            ? t("settings.light", "Light")
                            : option === "dark"
                              ? t("settings.dark", "Dark")
                              : t("settings.auto", "Auto")}
                        </span>
                      </div>
                      {active ? <Check size={16} className="text-[var(--text-primary)]" /> : null}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
