import { Download, ExternalLink } from "lucide-react";
import { useTranslation } from "react-i18next";
import { API_BASE_URL } from "../constants";
import type { OutputArtifact } from "../types";
import { authFetch } from "../utils/auth";
import FileTypeLogo from "./FileTypeLogo";

function formatBytes(value?: number | null): string {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return "";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

export default function ArtifactCard({ artifact, onOpenPreview }: { artifact: OutputArtifact; onOpenPreview?: () => void }) {
  const { t } = useTranslation();
  const size = formatBytes(artifact.size);
  const contentUrl = `${API_BASE_URL}/api/files/${encodeURIComponent(artifact.file_id)}/content`;

  async function downloadArtifact() {
    const response = await authFetch(contentUrl);
    if (!response.ok) return;
    const blob = await response.blob();
    const blobUrl = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = blobUrl;
    anchor.download = artifact.filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000);
  }

  async function previewArtifact() {
    if (onOpenPreview) {
      onOpenPreview();
      return;
    }
    const response = await authFetch(contentUrl);
    if (!response.ok) return;
    const blob = await response.blob();
    const blobUrl = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = blobUrl;
    anchor.target = "_blank";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000);
  }

  return (
    <div className="not-prose inline-flex max-w-md items-center gap-2 rounded-xl border border-[var(--border-main)] bg-[var(--panel-elevated)] px-2.5 py-2 shadow-sm">
      <FileTypeLogo artifact={artifact} className="h-9 w-9" />
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] font-medium leading-4 text-[var(--text-primary)]">{artifact.title || artifact.filename}</div>
        <div className="truncate text-[11px] leading-4 text-[var(--text-secondary)]">
          {artifact.filename}{size ? ` - ${size}` : ""}
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-1">
        <button
          type="button"
          onClick={() => void previewArtifact()}
          className="flex h-7 items-center gap-1 rounded-md px-1.5 text-[11px] font-medium text-[var(--text-blue)] transition-colors hover:bg-[var(--fill-tsp-white-light)]"
          aria-label={t("artifact.preview", "Preview")}
          title={t("artifact.preview", "Preview")}
        >
          <ExternalLink size={14} />
          <span>{t("artifact.preview", "Preview")}</span>
        </button>
        <button
          type="button"
          onClick={() => void downloadArtifact()}
          className="flex h-7 w-7 items-center justify-center rounded-md text-[var(--text-primary)] transition-colors hover:bg-[var(--fill-tsp-white-light)]"
          aria-label={t("artifact.download", "Download")}
          title={t("artifact.download", "Download")}
        >
          <Download size={14} />
        </button>
      </div>
    </div>
  );
}
