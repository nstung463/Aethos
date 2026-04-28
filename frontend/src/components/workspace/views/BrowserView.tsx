import { ExternalLink, Globe } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { WorkspaceFrame } from "../../../types";

export default function BrowserView({ frame }: { frame: WorkspaceFrame }) {
  const { t } = useTranslation();
  const url = (frame.input.url as string | undefined) ?? "";
  const isValidUrl = /^https?:\/\/.+/.test(url);

  return (
    <div className="flex h-full flex-col bg-[var(--background-menu-white)]">
      {/* URL bar */}
      <div className="flex shrink-0 items-center gap-2 border-b border-[var(--border-main)] bg-[var(--background-menu-white)] px-4 py-2.5">
        <div className="flex h-8 items-center justify-center px-1 text-[var(--icon-secondary)]">
          <Globe size={14} />
        </div>
        <div className="flex-1 min-w-0 h-8 flex items-center px-3 rounded-md bg-[var(--fill-tsp-gray-main)] border border-[var(--border-main)] overflow-hidden" title={url}>
          <div className="truncate font-mono text-[11px] text-[var(--text-secondary)] opacity-90">
            {url || "about:blank"}
          </div>
        </div>
        {isValidUrl && (
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex h-8 w-8 items-center justify-center shrink-0 text-[var(--icon-secondary)] hover:text-[var(--text-blue)] hover:bg-[var(--fill-tsp-gray-main)] rounded-md transition-all"
            title={t("chat.openInNewTab", "Open in new tab")}
          >
            <ExternalLink size={14} />
          </a>
        )}
      </div>

      {/* Content Rendering (Text/Markdown view for now) */}
      <div className="custom-scrollbar flex-1 overflow-y-scroll p-5">
        {frame.output === undefined ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-[var(--text-tertiary)] opacity-60">
            <div className="w-8 h-8 rounded-full border-2 border-t-[var(--text-blue)] border-[var(--border-main)] animate-spin" />
            <div className="text-[12px] font-medium uppercase tracking-wider">
              {t("workspace.browser.fetching", "Fetching content...")}
            </div>
          </div>
        ) : frame.output === "" ? (
          <div className="flex items-center justify-center h-full text-[12px] text-[var(--text-tertiary)]">
            {t("workspace.browser.empty", "No content returned from this URL")}
          </div>
        ) : (
          <div className="max-w-[800px] mx-auto">
            <pre className="whitespace-pre-wrap break-words text-[13px] leading-[1.6] text-[var(--text-primary)] font-sans">
              {frame.output}
            </pre>
          </div>
        )}
      </div>

    </div>
  );
}
