import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { PermissionProfile, SettingsSection } from "../types";
import type { GeneralPreferences } from "../utils/generalPreferences";
import SettingsSubSidebar from "./SettingsSubSidebar";
import AccountSettings from "./settings/AccountSettings";
import GeneralSettings from "./settings/GeneralSettings";
import UsageBillingSettings from "./settings/UsageBillingSettings";
import PersonalizationSettings from "./settings/PersonalizationSettings";
import ProfilesSettings from "./settings/ProfilesSettings";
import SecuritySettings from "./settings/SecuritySettings";
import ConnectionsSettings from "./settings/ConnectionsSettings";
import ExtensionsSettings from "./settings/ExtensionsSettings";

export default function SettingsPage({
  onClose,
  initialSection = "account",
  userPermissions,
  permissionsLoading,
  permissionsError,
  onPermissionsSave,
  localRootDir,
  generalPreferences,
}: {
  onClose: () => void;
  initialSection?: SettingsSection;
  userPermissions: PermissionProfile | null;
  permissionsLoading: boolean;
  permissionsError: string;
  onPermissionsSave: (profile: PermissionProfile) => Promise<void>;
  localRootDir: string;
  generalPreferences: GeneralPreferences;
}) {
  const { t } = useTranslation();
  const [section, setSection] = useState<SettingsSection>(initialSection);
  const [visible, setVisible] = useState(false);
  const modalRef = useRef<HTMLDivElement | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    previousFocusRef.current = document.activeElement as HTMLElement;
    requestAnimationFrame(() => {
      setVisible(true);
      window.setTimeout(() => closeButtonRef.current?.focus(), 50);
    });
    return () => previousFocusRef.current?.focus();
  }, []);

  useEffect(() => {
    setSection(initialSection);
  }, [initialSection]);

  const handleClose = useCallback(() => {
    setVisible(false);
    window.setTimeout(onClose, 180);
  }, [onClose]);

  const renderSection = () => {
    switch (section) {
      case "account":
        return <AccountSettings />;
      case "general":
        return <GeneralSettings localRootDir={localRootDir} generalPreferences={generalPreferences} />;
      case "usage-billing":
        return <UsageBillingSettings />;
      case "personalization":
        return <PersonalizationSettings />;
      case "profiles":
        return <ProfilesSettings />;
      case "security":
        return (
          <SecuritySettings
            value={userPermissions}
            isLoading={permissionsLoading}
            error={permissionsError}
            onSave={onPermissionsSave}
          />
        );
      case "connections":
        return <ConnectionsSettings rootDir={localRootDir} />;
      case "extensions":
        return <ExtensionsSettings rootDir={localRootDir} />;
      default:
        return <AccountSettings />;
    }
  };

  const contentWidthClass =
    section === "connections"
      ? "max-w-none"
      : section === "extensions"
        ? "mx-auto max-w-5xl"
        : section === "usage-billing"
          ? "max-w-none"
          : section === "profiles"
            ? "mx-auto max-w-[1040px]"
          : "mx-auto max-w-[820px]";

  const keepFocusInDialog = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      handleClose();
      return;
    }
    if (event.key !== "Tab") return;

    const modal = modalRef.current;
    if (!modal) return;
    const focusable = Array.from(
      modal.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
      )
    ).filter((element) => !element.hasAttribute("disabled") && element.offsetParent !== null);

    if (focusable.length === 0) {
      event.preventDefault();
      modal.focus();
      return;
    }

    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  return (
    <div
      className={`fixed inset-0 z-[80] flex items-center justify-center p-4 backdrop-blur-sm transition-opacity duration-200 ${
        visible ? "bg-black/60 opacity-100" : "pointer-events-none bg-black/0 opacity-0"
      }`}
      onClick={(event) => {
        if (event.target === event.currentTarget) handleClose();
      }}
      onKeyDown={keepFocusInDialog}
    >
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-label={t("settings.title", "Settings")}
        tabIndex={-1}
        className={`relative flex h-[min(700px,calc(100vh-3rem))] w-full max-w-[1200px] flex-col overflow-hidden rounded-[28px] border border-[var(--border-subtle)] bg-[var(--panel-elevated)] shadow-2xl transition-all duration-200 ${
          visible ? "scale-100 opacity-100" : "scale-95 opacity-0"
        }`}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex min-h-0 flex-1 overflow-hidden bg-[var(--panel-bg-soft)]">
          <button
            ref={closeButtonRef}
            type="button"
            onClick={handleClose}
            title={t("settings.closeSettings", "Close settings")}
            className="absolute right-4 top-4 z-10 flex h-9 w-9 items-center justify-center rounded-xl border border-[var(--border-subtle)] bg-[var(--panel-elevated)] text-[var(--text-soft)] shadow-sm transition hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
          >
            <X size={16} strokeWidth={1.8} />
          </button>
          <SettingsSubSidebar section={section} onSectionChange={setSection} />
          <div className="flex-1 overflow-y-auto">
            <div className="px-8 py-7">
              <div className={contentWidthClass}>{renderSection()}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
