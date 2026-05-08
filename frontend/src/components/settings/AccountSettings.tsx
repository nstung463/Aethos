import { Copy, LogOut } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { API_BASE_URL } from "../../constants";
import { authFetch, clearAuthToken } from "../../utils/auth";

type SessionUser = {
  id: string;
  display_name: string;
};

export default function AccountSettings() {
  const { t } = useTranslation();
  const [user, setUser] = useState<SessionUser | null>(null);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");

  useEffect(() => {
    let cancelled = false;
    authFetch(`${API_BASE_URL}/auth/me`)
      .then((response) => {
        if (!response.ok) throw new Error(`Failed to load current user: ${response.status}`);
        return response.json() as Promise<SessionUser>;
      })
      .then((payload) => {
        if (!cancelled) setUser(payload);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <h1 className="text-[26px] font-semibold tracking-tight text-[var(--text-primary)]">
          {t("settings.account", "Account")}
        </h1>
        <p className="text-[12px] leading-5 text-[var(--text-secondary)]">
          {t("settings.accountDesc", "Review your current session, plan details, and account controls.")}
        </p>
      </div>

      <section className="rounded-[24px] border border-[var(--border-subtle)] bg-[var(--panel-elevated)] p-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="text-[12px] font-medium text-[var(--text-primary)]">{t("settings.fullName", "Full name")}</div>
              <div className="mt-1 text-[12px] text-[var(--text-secondary)]">{user?.display_name ?? t("settings.guest", "Guest")}</div>
            </div>
          <div className="rounded-full bg-[var(--surface-hover)] px-3 py-1 text-xs text-[var(--text-secondary)]">
            {t("settings.freePlan", "Free")}
          </div>
        </div>
      </section>

      <section className="rounded-[24px] border border-[var(--border-subtle)] bg-[var(--panel-elevated)] p-6">
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-[18px] border border-[var(--border-subtle)] bg-[var(--panel-bg-soft)] p-4">
            <div>
              <div className="text-[12px] font-medium text-[var(--text-primary)]">{t("settings.userId", "User ID")}</div>
              <div className="mt-1 text-[12px] text-[var(--text-secondary)]">{user?.id ?? "--"}</div>
            </div>
            <button
              type="button"
              onClick={() => {
                if (!user?.id) return;
                navigator.clipboard
                  .writeText(user.id)
                  .then(() => {
                    setCopyState("copied");
                    window.setTimeout(() => setCopyState("idle"), 1200);
                  })
                  .catch(() => setCopyState("failed"));
              }}
              disabled={!user?.id}
              className="inline-flex h-9 items-center justify-center gap-2 rounded-[10px] border border-[var(--border-subtle)] px-3 text-[12px] text-[var(--text-primary)] transition hover:bg-[var(--surface-hover)]"
            >
              <Copy size={15} />
              {copyState === "copied"
                ? t("common.copied", "Copied!")
                : copyState === "failed"
                  ? t("settings.copyFailed", "Copy failed")
                  : t("common.copy", "Copy")}
            </button>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 rounded-[18px] border border-[var(--border-subtle)] bg-[var(--panel-bg-soft)] p-4">
            <div>
              <div className="text-[12px] font-medium text-[var(--text-primary)]">{t("settings.logoutThisDevice", "Log out of this device")}</div>
              <div className="mt-1 text-[12px] text-[var(--text-secondary)]">{t("settings.logoutDesc", "Clear the local auth token and refresh into a new guest session.")}</div>
            </div>
            <button
              type="button"
              onClick={() => {
                clearAuthToken();
                window.location.reload();
              }}
              className="inline-flex h-9 items-center justify-center gap-2 rounded-[10px] border border-[var(--border-subtle)] px-3 text-[12px] text-[var(--text-primary)] transition hover:bg-[var(--surface-hover)]"
            >
              <LogOut size={15} />
              {t("settings.logout", "Log out")}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
