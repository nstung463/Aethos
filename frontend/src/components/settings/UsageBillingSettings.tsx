import { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  BadgeCheck,
  Building2,
  CalendarDays,
  Check,
  Clock3,
  Globe,
  Microscope,
  ShieldCheck,
  Sparkles,
  WandSparkles,
} from "lucide-react";
import { useTranslation } from "react-i18next";

type BillingCycle = "monthly" | "annual";

type PlanCard = {
  id: string;
  nameKey: string;
  nameFallback: string;
  descriptionKey: string;
  descriptionFallback: string;
  monthlyPrice: number;
  annualPrice: number;
  highlight?: boolean;
  badgeKey?: string;
  badgeFallback?: string;
  monthlyCreditsKey: string;
  monthlyCreditsFallback: string;
  features: Array<{
    key: string;
    fallback: string;
    icon: typeof Clock3;
  }>;
};

const plans: PlanCard[] = [
  {
    id: "starter",
    nameKey: "settings.planStarter",
    nameFallback: "Starter",
    descriptionKey: "settings.planStarterDesc",
    descriptionFallback: "Standard monthly usage for solo builders.",
    monthlyPrice: 20,
    annualPrice: 16,
    monthlyCreditsKey: "settings.planStarterCredits",
    monthlyCreditsFallback: "4,000 credits per month",
    features: [
      {
        key: "settings.planFeatureDailyRefresh",
        fallback: "300 refresh credits every day",
        icon: Clock3,
      },
      {
        key: "settings.planFeatureResearchEveryday",
        fallback: "In-depth research for everyday tasks",
        icon: Microscope,
      },
      {
        key: "settings.planFeatureWebsitesStandard",
        fallback: "Professional websites for standard output",
        icon: Globe,
      },
      {
        key: "settings.planFeatureScheduledTasks",
        fallback: "20 scheduled tasks",
        icon: CalendarDays,
      },
    ],
  },
  {
    id: "pro",
    nameKey: "settings.planPro",
    nameFallback: "Pro",
    descriptionKey: "settings.planProDesc",
    descriptionFallback: "Customizable monthly usage for focused teams and power users.",
    monthlyPrice: 40,
    annualPrice: 33,
    highlight: true,
    badgeKey: "settings.planMostPopular",
    badgeFallback: "Most popular",
    monthlyCreditsKey: "settings.planProCredits",
    monthlyCreditsFallback: "8,000 credits per month",
    features: [
      {
        key: "settings.planFeatureDailyRefresh",
        fallback: "300 refresh credits every day",
        icon: Clock3,
      },
      {
        key: "settings.planFeatureResearchFlexible",
        fallback: "In-depth research with self-set usage",
        icon: Microscope,
      },
      {
        key: "settings.planFeatureWebsitesFlexible",
        fallback: "Professional websites for changing needs",
        icon: Globe,
      },
      {
        key: "settings.planFeatureBetaAccess",
        fallback: "Early access to beta features",
        icon: WandSparkles,
      },
    ],
  },
  {
    id: "scale",
    nameKey: "settings.planScale",
    nameFallback: "Scale",
    descriptionKey: "settings.planScaleDesc",
    descriptionFallback: "Extended usage for sustained productivity and larger workloads.",
    monthlyPrice: 120,
    annualPrice: 99,
    monthlyCreditsKey: "settings.planScaleCredits",
    monthlyCreditsFallback: "40,000 credits per month",
    features: [
      {
        key: "settings.planFeatureDailyRefresh",
        fallback: "300 refresh credits every day",
        icon: Clock3,
      },
      {
        key: "settings.planFeatureResearchScale",
        fallback: "In-depth research for large-scale tasks",
        icon: Microscope,
      },
      {
        key: "settings.planFeatureAnalytics",
        fallback: "Professional websites with data analytics",
        icon: Globe,
      },
      {
        key: "settings.planFeatureConcurrentTasks",
        fallback: "20 concurrent tasks",
        icon: BadgeCheck,
      },
    ],
  },
];

function formatPrice(value: number) {
  return `$${value}`;
}

const DIGIT_REEL = Array.from({ length: 20 }, (_, index) => String(index % 10));
const PRICE_ROLL_MS = 720;

function padDigits(value: number, minDigits: number) {
  return String(value).padStart(minDigits, "0");
}

function isLeadingZeroColumn(digits: string, index: number) {
  return index < digits.length - 1 && /^0+$/.test(digits.slice(0, index + 1));
}

function AnimatedPlanPrice({ value, minDigits }: { value: number; minDigits: number }) {
  const reducedMotion = useMemo(
    () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    [],
  );
  const nextDigits = useMemo(() => padDigits(value, minDigits), [minDigits, value]);
  const [fromDigits, setFromDigits] = useState(nextDigits);
  const [toDigits, setToDigits] = useState(nextDigits);
  const [isAnimating, setIsAnimating] = useState(false);

  useEffect(() => {
    if (nextDigits === toDigits) return;
    if (reducedMotion) {
      setFromDigits(nextDigits);
      setToDigits(nextDigits);
      setIsAnimating(false);
      return;
    }

    setFromDigits(toDigits);
    setToDigits(nextDigits);
    setIsAnimating(true);

    const timeoutId = window.setTimeout(() => {
      setFromDigits(nextDigits);
      setToDigits(nextDigits);
      setIsAnimating(false);
    }, PRICE_ROLL_MS);

    return () => window.clearTimeout(timeoutId);
  }, [nextDigits, reducedMotion, toDigits]);

  return (
    <span className="inline-flex items-end gap-0.5 tabular-nums">
      <span className="pb-[0.08em]">$</span>
      <span className="inline-flex">
        {toDigits.split("").map((digit, index) => {
          const startDigit = Number(fromDigits[index] ?? "0");
          const endDigit = Number(digit);
          const reelIndex = isAnimating && startDigit !== endDigit ? endDigit + 10 : endDigit;

          return (
            <span
              key={`${index}-${minDigits}`}
              aria-hidden="true"
              className={`relative inline-flex h-[1em] w-[0.66em] overflow-hidden ${
                isLeadingZeroColumn(toDigits, index) ? "opacity-0" : "opacity-100"
              }`}
            >
              <span
                className={`flex flex-col ${
                  isAnimating ? "transition-transform duration-700 ease-[cubic-bezier(0.22,1,0.36,1)]" : ""
                }`}
                style={{ transform: `translateY(-${reelIndex * 100}%)` }}
              >
                {DIGIT_REEL.map((reelDigit, reelDigitIndex) => (
                  <span key={`${index}-${reelDigitIndex}`} className="flex h-[1em] items-center justify-center">
                    {reelDigit}
                  </span>
                ))}
              </span>
            </span>
          );
        })}
      </span>
      <span className="sr-only">{formatPrice(value)}</span>
    </span>
  );
}

export default function UsageBillingSettings() {
  const { t } = useTranslation();
  const [cycle, setCycle] = useState<BillingCycle>("monthly");

  return (
    <div className="space-y-6 md:space-y-8">
      <div className="space-y-2">
        <h1 className="text-[26px] font-semibold tracking-tight text-[var(--text-primary)]">
          {t("settings.usageBilling", "Usage & Billing")}
        </h1>
        <p className="max-w-3xl text-[12px] leading-5 text-[var(--text-secondary)]">
          {t(
            "settings.usageBillingDesc",
            "Track recent product activity and keep the billing layout ready for future backend usage data.",
          )}
        </p>
      </div>

      <section className="rounded-[28px] border border-[var(--border-subtle)] bg-[var(--panel-elevated)] p-4 md:p-6">
        <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-3">
            <div className="inline-flex items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-hover)] px-3 py-1 text-[12px] font-medium text-[var(--text-secondary)]">
              <Sparkles size={14} />
              {t("settings.billingPreviewBadge", "Preview plans")}
            </div>
            <div className="space-y-1">
              <h2 className="text-[22px] font-semibold text-[var(--text-primary)]">
                {t("settings.billingPlansTitle", "Choose the plan that fits your pace")}
              </h2>
              <p className="max-w-2xl text-sm leading-6 text-[var(--text-secondary)]">
                {t(
                  "settings.billingPlansDesc",
                  "This section is a UI placeholder for future checkout flows, so users can already compare plans and understand the upgrade path.",
                )}
              </p>
            </div>
          </div>

          <div className="flex w-full flex-col rounded-[12px] border border-[var(--border-subtle)] bg-[var(--surface-hover)] p-1 sm:inline-flex sm:w-auto sm:flex-row">
            {(["monthly", "annual"] as BillingCycle[]).map((value) => {
              const isActive = cycle === value;
              return (
                <button
                  key={value}
                  type="button"
                  onClick={() => setCycle(value)}
                  className={`flex-1 rounded-[10px] px-4 py-2 text-sm text-left transition-colors sm:text-center ${
                    isActive
                      ? "bg-[var(--panel-elevated)] text-[var(--text-primary)] shadow-sm"
                      : "text-[var(--text-tertiary)]"
                  }`}
                >
                  {value === "monthly"
                    ? t("settings.billingMonthly", "Monthly")
                    : t("settings.billingAnnual", "Annually · Save 17%")}
                </button>
              );
            })}
          </div>
        </div>

        <div className="grid gap-3 lg:grid-cols-3">
          {plans.map((plan) => {
            const price = cycle === "monthly" ? plan.monthlyPrice : plan.annualPrice;
            const priceDigits = Math.max(String(plan.monthlyPrice).length, String(plan.annualPrice).length);

            return (
              <article
                key={plan.id}
                className={`relative flex h-full min-w-0 flex-col overflow-hidden rounded-[24px] border p-4 ${
                  plan.highlight
                    ? "border-[var(--icon-primary)] bg-[var(--surface-hover)]"
                    : "border-[var(--border-subtle)] bg-[var(--panel-bg-soft)]"
                }`}
              >
                {plan.badgeKey ? (
                  <div className="mb-4 self-start rounded-full bg-[var(--surface-hover)] px-3 py-1 text-[11px] font-medium text-[var(--text-primary)] md:absolute md:right-4 md:top-4 md:mb-0">
                    {t(plan.badgeKey, plan.badgeFallback || "")}
                  </div>
                ) : null}

                <div className="flex h-full min-h-0 flex-col gap-3.5">
                  <div className="space-y-2">
                    <div className="text-[17px] font-semibold text-[var(--text-primary)]">
                      {t(plan.nameKey, plan.nameFallback)}
                    </div>
                    <div className="flex flex-wrap items-end gap-x-2 gap-y-1">
                      <div className="break-words text-[30px] font-semibold leading-none text-[var(--text-primary)] sm:text-[32px]">
                        <AnimatedPlanPrice value={price} minDigits={priceDigits} />
                      </div>
                      <div className="pb-1 text-[13px] text-[var(--text-tertiary)]">
                        {t("settings.billingPerMonth", "/ month")}
                      </div>
                    </div>
                    <p className="text-[13px] leading-5 text-[var(--text-secondary)]">
                      {t(plan.descriptionKey, plan.descriptionFallback)}
                    </p>
                  </div>

                  <button
                    type="button"
                    className={`inline-flex h-10 w-full items-center justify-center rounded-full px-4 text-[13px] font-medium ${
                      plan.highlight
                        ? "bg-[var(--Button-blue)] text-[var(--text-white)]"
                        : "bg-[var(--Button-black)] text-[var(--text-onblack)]"
                    }`}
                  >
                    {t("settings.upgrade", "Upgrade")}
                  </button>

                  <div className="rounded-[18px] border border-[var(--border-subtle)] bg-[var(--panel-elevated)] p-3.5">
                    <div className="text-xs uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                      {t("settings.credits", "Credits")}
                    </div>
                    <div className="mt-2 text-[17px] font-semibold text-[var(--text-primary)]">
                      {t(plan.monthlyCreditsKey, plan.monthlyCreditsFallback)}
                    </div>
                  </div>

                  <div className="space-y-2.5">
                    {plan.features.map((feature) => {
                      const Icon = feature.icon;
                      return (
                        <div key={feature.key} className="flex min-w-0 items-start gap-3">
                          <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-[var(--surface-hover)] text-[var(--icon-primary)]">
                            <Icon size={16} />
                          </span>
                          <span className="min-w-0 text-[13px] leading-5 text-[var(--text-secondary)]">
                            {t(feature.key, feature.fallback)}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </article>
            );
          })}
        </div>

        <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div className="flex flex-col gap-4 rounded-[24px] border border-[var(--border-subtle)] bg-[var(--panel-bg-soft)] p-4 sm:flex-row sm:items-start">
            <div className="flex h-12 w-12 items-center justify-center rounded-[16px] bg-[var(--surface-hover)] text-[var(--icon-primary)]">
              <Building2 size={22} />
            </div>
            <div className="min-w-0 flex-1 space-y-1">
              <div className="text-sm font-semibold text-[var(--text-primary)]">
                {t("settings.teamPlansTitle", "Aethos plans for teams & businesses")}
              </div>
              <div className="text-[12px] leading-5 text-[var(--text-secondary)]">
                {t(
                  "settings.teamPlansDesc",
                  "Flexible pricing for growing teams, procurement workflows, and shared usage controls.",
                )}
              </div>
            </div>
            <button
              type="button"
              className="inline-flex h-10 w-full shrink-0 items-center justify-center rounded-[10px] border border-[var(--Button-border-secondary)] px-4 text-sm text-[var(--text-primary)] sm:w-auto"
            >
              {t("settings.teamPlansCta", "Get team plan")}
            </button>
          </div>

          <div className="flex flex-col gap-4 rounded-[24px] border border-[var(--border-subtle)] bg-[var(--panel-bg-soft)] p-4 sm:flex-row sm:items-start">
            <div className="flex h-12 w-12 items-center justify-center rounded-[16px] bg-[var(--surface-hover)] text-[var(--icon-primary)]">
              <ShieldCheck size={22} />
            </div>
            <div className="min-w-0 flex-1 space-y-1">
              <div className="text-sm font-semibold text-[var(--text-primary)]">
                {t("settings.securityComplianceTitle", "Security and compliance")}
              </div>
              <div className="text-[12px] leading-5 text-[var(--text-secondary)]">
                {t(
                  "settings.securityComplianceDesc",
                  "Enterprise-grade controls, approval workflows, and room for future certifications content.",
                )}
              </div>
            </div>
            <button
              type="button"
              className="inline-flex h-10 w-full shrink-0 items-center justify-center gap-2 rounded-[10px] border border-[var(--Button-border-secondary)] px-4 text-sm text-[var(--text-primary)] sm:w-auto"
            >
              {t("settings.learnMore", "Learn more")}
              <ArrowRight size={16} />
            </button>
          </div>
        </div>
      </section>

      <section className="rounded-[24px] border border-[var(--border-subtle)] bg-[var(--panel-elevated)] p-4 md:p-6">
        <div className="mb-4 flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-center">
          <div className="text-[17px] font-semibold text-[var(--text-primary)]">
            {t("settings.usageRecord", "Usage record")}
          </div>
          <div className="inline-flex items-center gap-2 rounded-full bg-[var(--surface-hover)] px-3 py-1 text-xs text-[var(--text-tertiary)]">
            <Check size={14} />
            {t("settings.billingUsageEmptyState", "No charges posted yet")}
          </div>
        </div>
        <div className="overflow-hidden rounded-[18px] border border-[var(--border-subtle)]">
          <div className="overflow-x-auto">
            <div className="min-w-[480px]">
              <div className="grid grid-cols-[minmax(0,1fr)_140px_120px] gap-4 border-b border-[var(--border-subtle)] bg-[var(--panel-bg-soft)] px-4 py-3 text-xs uppercase tracking-wide text-[var(--text-tertiary)]">
                <div>{t("settings.details", "Details")}</div>
                <div>{t("settings.date", "Date")}</div>
                <div className="text-right">{t("settings.creditsChange", "Credits change")}</div>
              </div>
              <div className="px-4 py-10 text-center text-[12px] text-[var(--text-tertiary)]">
                {t("settings.noUsageRecords", "No usage records are available yet.")}
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
