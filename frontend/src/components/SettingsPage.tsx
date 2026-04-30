import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import type { PermissionProfile, SettingsSection } from "../types";
import SettingsSubSidebar from "./SettingsSubSidebar";
import GeneralSettings from "./settings/GeneralSettings";
import AppearanceSettings from "./settings/AppearanceSettings";
import ProfilesSettings from "./settings/ProfilesSettings";
import ModelSettings from "./settings/ModelSettings";
import SecuritySettings from "./settings/SecuritySettings";
import ExtensionsSettings from "./settings/ExtensionsSettings";

export default function SettingsPage({
  onClose,
  initialSection = "general",
  userPermissions,
  permissionsLoading,
  permissionsError,
  onPermissionsSave,
  localRootDir,
}: {
  onClose: () => void;
  initialSection?: SettingsSection;
  userPermissions: PermissionProfile | null;
  permissionsLoading: boolean;
  permissionsError: string;
  onPermissionsSave: (profile: PermissionProfile) => Promise<void>;
  localRootDir: string;
}) {
  const { t } = useTranslation();
  const [section, setSection] = useState<SettingsSection>(initialSection);
  const [visible, setVisible] = useState(false);
  const modalRef = useRef<HTMLDivElement | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  /** Save the element that was focused before the modal opened so we can restore focus */
  const previousFocusRef = useRef<HTMLElement | null>(null);

  // Trigger animation on mount + save previous focus + auto-focus close button
  useEffect(() => {
    previousFocusRef.current = document.activeElement as HTMLElement;
    requestAnimationFrame(() => {
      setVisible(true);
      // Small delay so the modal is visible before we shift focus
      window.setTimeout(() => closeButtonRef.current?.focus(), 50);
    });
    return () => {
      // Restore focus to the element that triggered the modal
      previousFocusRef.current?.focus();
    };
  }, []);

  useEffect(() => {
    setSection(initialSection);
  }, [initialSection]);

  const handleClose = useCallback(() => {
    setVisible(false);
    setTimeout(onClose, 200); // Wait for animation to complete
  }, [onClose]);

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      handleClose();
    }
  };

  /** Focus trap: keep Tab/Shift+Tab cycling inside the modal */
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault();
      handleClose();
      return;
    }
    if (e.key !== "Tab") return;

    const modal = modalRef.current;
    if (!modal) return;

    const focusable = Array.from(
      modal.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      )
    ).filter((el) => !el.hasAttribute("disabled") && el.offsetParent !== null);

    if (focusable.length === 0) return;

    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    if (e.shiftKey) {
      if (document.activeElement === first) {
        e.preventDefault();
        last.focus();
      }
    } else {
      if (document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  }, [handleClose]);

  const renderSection = () => {
      switch (section) {
        case "general":
          return <GeneralSettings />;
        case "appearance":
          return <AppearanceSettings />;
        case "profiles":
          return <ProfilesSettings />;
      case "model-settings":
        return <ModelSettings />;
      case "security":
        return (
          <SecuritySettings
            value={userPermissions}
            isLoading={permissionsLoading}
            error={permissionsError}
            onSave={onPermissionsSave}
          />
        );
      case "extensions":
        return <ExtensionsSettings rootDir={localRootDir} />;
      default:
        return <GeneralSettings />;
    }
  };

  return (
    // Layer 1: Backdrop with blur
    <div
      className={`fixed inset-0 z-[80] flex items-center justify-center p-4 backdrop-blur-sm transition-opacity duration-200 ${
        visible ? "opacity-100 bg-black/60" : "opacity-0 pointer-events-none bg-black/0"
      }`}
      onClick={handleBackdropClick}
      onKeyDown={handleKeyDown}
    >
      {/* Layer 2: Modal Container */}
      <div
        ref={modalRef}
        className={`relative flex flex-col bg-[var(--panel-elevated)] rounded-2xl shadow-2xl border border-[var(--border-subtle)] w-full max-w-[880px] h-[520px] overflow-hidden transition-all duration-200 ${
          visible ? "opacity-100 scale-100" : "opacity-0 scale-95"
        }`}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={t("settings.title", "Settings")}
      >
        {/* Modal Header */}
        <div className="flex items-center justify-between shrink-0 px-6 py-4 border-b border-[var(--border-subtle)]">
          <h2 className="text-base font-semibold text-[var(--text-primary)]">{t("settings.title", "Settings")}</h2>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={handleClose}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-[var(--text-soft)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] transition"
            title={t("settings.closeSettings", "Close settings")}
          >
            <X size={16} strokeWidth={1.8} />
          </button>
        </div>

        {/* Layer 3: Modal Body (Nested Layout) - Fixed height */}
        <div className="flex flex-1 min-h-0 overflow-hidden">
          {/* Sidebar */}
          <SettingsSubSidebar section={section} onSectionChange={setSection} />

          {/* Content Area - Scrollable */}
          <div className="flex-1 overflow-y-auto bg-[var(--panel-bg-soft)]">
            <div className="px-8 py-6">
              <div className={section === "extensions" ? "max-w-4xl" : "max-w-[500px]"}>{renderSection()}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
