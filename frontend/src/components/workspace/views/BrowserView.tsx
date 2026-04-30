import { CheckCircle, ExternalLink, Globe, XCircle } from "lucide-react";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { WorkspaceFrame } from "../../../types";

interface ParsedOutput {
  status?: string;
  statusCode?: number;
  size?: string;
  elapsed?: string;
  content: string;
}

function parseBrowserOutput(output: string): ParsedOutput {
  const lines = output.split("\n");
  const result: ParsedOutput = { content: "" };
  let contentStart = 0;
  let sawMeta = false;

  for (let i = 0; i < Math.min(lines.length, 15); i++) {
    const line = lines[i];
    if (line.startsWith("URL:")) {
      sawMeta = true;
    } else if (line.startsWith("Status:")) {
      sawMeta = true;
      result.status = line.slice("Status:".length).trim();
      const m = result.status.match(/^(\d+)/);
      if (m) result.statusCode = parseInt(m[1], 10);
    } else if (line.startsWith("Size:")) {
      sawMeta = true;
      result.size = line.slice("Size:".length).trim();
    } else if (line.startsWith("Elapsed:")) {
      sawMeta = true;
      result.elapsed = line.slice("Elapsed:".length).trim();
    } else if (line.startsWith("Prompt hint:")) {
      sawMeta = true;
    } else if (line.trim() === "" && i > 0) {
      contentStart = i + 1;
      break;
    }
  }

  result.content = contentStart > 0
    ? lines.slice(contentStart).join("\n").trim()
    : sawMeta ? "" : output;

  return result;
}

function stripHtml(html: string): string {
  if (!/<[a-z][\s\S]*>/i.test(html)) return html;
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/<style[\s\S]*?<\/style>/gi, "")
    .replace(/<\/(p|div|li|h[1-6]|tr)>/gi, "\n")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&nbsp;/g, " ")
    .replace(/&#(\d+);/g, (_, n) => String.fromCharCode(parseInt(n, 10)))
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function formatSize(raw: string): string {
  const bytes = parseInt(raw, 10);
  if (isNaN(bytes)) return raw;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function statusClass(code: number | undefined): string {
  if (code === undefined) return "text-[var(--text-secondary)]";
  if (code < 400) return "text-green-500";
  return "text-red-500";
}

export default function BrowserView({ frame }: { frame: WorkspaceFrame }) {
  const { t } = useTranslation();
  const url = (frame.input.url as string | undefined) ?? "";
  const isValidUrl = /^https?:\/\/.+/.test(url);

  const parsed = useMemo(
    () => (frame.output !== undefined ? parseBrowserOutput(frame.output) : null),
    [frame.output],
  );

  const displayContent = useMemo(
    () => (parsed ? stripHtml(parsed.content) : ""),
    [parsed],
  );

  return (
    <div className="flex h-full flex-col bg-[var(--background-menu-white)]">
      {/* URL bar */}
      <div className="flex shrink-0 items-center gap-2 border-b border-[var(--border-main)] bg-[var(--background-menu-white)] px-4 py-2.5">
        <div className="flex h-8 items-center justify-center px-1 text-[var(--icon-secondary)]">
          <Globe size={14} />
        </div>
        <div
          className="flex-1 min-w-0 h-8 flex items-center px-3 rounded-md bg-[var(--fill-tsp-gray-main)] border border-[var(--border-main)] overflow-hidden"
          title={url}
        >
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

      {/* Metadata bar */}
      {parsed && (parsed.status || parsed.size || parsed.elapsed) && (
        <div className="flex shrink-0 items-center gap-3 border-b border-[var(--border-main)] bg-[var(--fill-tsp-gray-main)] px-4 py-1.5">
          {parsed.status && (
            <div className={`flex items-center gap-1 text-[11px] font-medium ${statusClass(parsed.statusCode)}`}>
              {parsed.statusCode !== undefined && parsed.statusCode < 400
                ? <CheckCircle size={11} />
                : parsed.statusCode !== undefined && parsed.statusCode >= 400
                ? <XCircle size={11} />
                : null}
              {parsed.status}
            </div>
          )}
          {parsed.size && (
            <div className="text-[11px] text-[var(--text-tertiary,#9ca3af)]">
              {formatSize(parsed.size)}
            </div>
          )}
          {parsed.elapsed && (
            <div className="text-[11px] text-[var(--text-tertiary,#9ca3af)]">
              {parsed.elapsed}
            </div>
          )}
        </div>
      )}

      {/* Content */}
      <div className="custom-scrollbar flex-1 overflow-y-scroll p-5">
        {frame.output === undefined ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-[var(--text-tertiary)] opacity-60">
            <div className="w-8 h-8 rounded-full border-2 border-t-[var(--text-blue)] border-[var(--border-main)] animate-spin" />
            <div className="text-[12px] font-medium uppercase tracking-wider">
              {t("workspace.browser.fetching", "Fetching content...")}
            </div>
          </div>
        ) : displayContent === "" ? (
          <div className="flex items-center justify-center h-full text-[12px] text-[var(--text-tertiary)]">
            {t("workspace.browser.empty", "No content returned from this URL")}
          </div>
        ) : (
          <div className="max-w-[800px] mx-auto">
            <pre className="whitespace-pre-wrap break-words text-[13px] leading-[1.6] text-[var(--text-primary)] font-sans">
              {displayContent}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
