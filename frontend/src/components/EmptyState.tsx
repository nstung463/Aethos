import { useTranslation } from "react-i18next";

export default function EmptyState() {
  const { t } = useTranslation();

  return (
    <div className="px-6 py-1 text-center sm:py-2">
      <h2 className="mb-2 text-[clamp(1.7rem,3.2vw,2.7rem)] font-semibold tracking-[-0.045em] text-[var(--text-primary)]">
        {t("emptyState.title", "What can I do for you?")}
      </h2>
      <p className="mx-auto mb-1 max-w-2xl text-sm leading-6 text-[var(--text-soft)] sm:text-[0.95rem]">
        {t("emptyState.subtitle", "One workspace to turn ideas into polished output.")}
      </p>
    </div>
  );
}
