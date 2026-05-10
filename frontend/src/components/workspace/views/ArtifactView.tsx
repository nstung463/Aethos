import JSZip from "jszip";
import { Download, ExternalLink } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { API_BASE_URL } from "../../../constants";
import type { OutputArtifact, WorkspaceFrame } from "../../../types";
import { authFetch } from "../../../utils/auth";
import FileTypeLogo from "../../FileTypeLogo";

type PreviewState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "blob"; url: string; kind: "image" | "pdf" }
  | { status: "table"; rows: string[][] }
  | { status: "unsupported" };

const MAX_ROWS = 40;
const MAX_COLUMNS = 12;

function contentUrlFor(artifact: OutputArtifact): string {
  return `${API_BASE_URL}/api/files/${encodeURIComponent(artifact.file_id)}/content`;
}

function parseDelimited(text: string): string[][] {
  const delimiter = text.includes("\t") && !text.includes(",") ? "\t" : ",";
  return text
    .split(/\r?\n/)
    .filter((line) => line.trim().length > 0)
    .slice(0, MAX_ROWS)
    .map((line) => line.split(delimiter).slice(0, MAX_COLUMNS).map((cell) => cell.replace(/^"|"$/g, "")));
}

function columnNameToIndex(name: string): number {
  return name.split("").reduce((acc, char) => acc * 26 + char.charCodeAt(0) - 64, 0) - 1;
}

function decodeXml(value: string): string {
  return value
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'");
}

async function parseXlsxRows(blob: Blob): Promise<string[][]> {
  const zip = await JSZip.loadAsync(blob);
  const sharedXml = await zip.file("xl/sharedStrings.xml")?.async("text");
  const sharedStrings = sharedXml
    ? Array.from(sharedXml.matchAll(/<si>[\s\S]*?<\/si>/g)).map((match) =>
        decodeXml(Array.from(match[0].matchAll(/<t[^>]*>([\s\S]*?)<\/t>/g)).map((part) => part[1]).join("")),
      )
    : [];
  const sheetPath = Object.keys(zip.files).find((name) => /^xl\/worksheets\/sheet\d+\.xml$/.test(name));
  const sheetXml = sheetPath ? await zip.file(sheetPath)?.async("text") : null;
  if (!sheetXml) return [];
  return Array.from(sheetXml.matchAll(/<row[^>]*>([\s\S]*?)<\/row>/g))
    .slice(0, MAX_ROWS)
    .map((rowMatch) => {
      const row: string[] = [];
      for (const cellMatch of rowMatch[1].matchAll(/<c([^>]*)>([\s\S]*?)<\/c>/g)) {
        const attrs = cellMatch[1];
        const body = cellMatch[2];
        const ref = attrs.match(/r="([A-Z]+)\d+"/)?.[1];
        const index = ref ? columnNameToIndex(ref) : row.length;
        if (index >= MAX_COLUMNS) continue;
        const rawValue = body.match(/<v>([\s\S]*?)<\/v>/)?.[1] ?? body.match(/<t[^>]*>([\s\S]*?)<\/t>/)?.[1] ?? "";
        row[index] = attrs.includes('t="s"') ? sharedStrings[Number(rawValue)] ?? rawValue : decodeXml(rawValue);
      }
      return Array.from({ length: Math.min(MAX_COLUMNS, Math.max(row.length, 1)) }, (_, index) => row[index] ?? "");
    });
}

function PreviewTable({ rows }: { rows: string[][] }) {
  const { t } = useTranslation();
  if (rows.length === 0) return <div className="p-4 text-sm text-[var(--text-secondary)]">{t("artifact.noPreviewRows", "No preview rows.")}</div>;
  return (
    <div className="h-full overflow-auto p-3">
      <table className="min-w-full border-separate border-spacing-0 text-xs">
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {row.map((cell, cellIndex) => (
                <td key={cellIndex} className="max-w-[220px] truncate border-b border-r border-[var(--border-main)] px-2 py-1.5 text-[var(--text-primary)]">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function ArtifactView({ frame }: { frame: WorkspaceFrame }) {
  const { t } = useTranslation();
  const artifact = frame.artifact;
  const [preview, setPreview] = useState<PreviewState>({ status: "loading" });
  const contentUrl = useMemo(() => (artifact ? contentUrlFor(artifact) : ""), [artifact]);

  async function openBlob(download: boolean) {
    if (!artifact) return;
    const response = await authFetch(contentUrl);
    if (!response.ok) return;
    const blob = await response.blob();
    const blobUrl = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = blobUrl;
    anchor.target = "_blank";
    if (download) anchor.download = artifact.filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000);
  }

  useEffect(() => {
    if (!artifact) {
      setPreview({ status: "unsupported" });
      return undefined;
    }
    let revokedUrl: string | null = null;
    let cancelled = false;
    setPreview({ status: "loading" });

    authFetch(contentUrl)
      .then(async (response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const blob = await response.blob();
        if (artifact.artifact_type === "image" || artifact.artifact_type === "pdf") {
          revokedUrl = URL.createObjectURL(blob);
          if (cancelled) {
            URL.revokeObjectURL(revokedUrl);
            revokedUrl = null;
            return;
          }
          if (!cancelled) setPreview({ status: "blob", url: revokedUrl, kind: artifact.artifact_type });
          return;
        }
        if (artifact.artifact_type === "data" || /\.csv$/i.test(artifact.filename) || /\.tsv$/i.test(artifact.filename)) {
          const text = await blob.text();
          if (!cancelled) setPreview({ status: "table", rows: parseDelimited(text) });
          return;
        }
        if (artifact.artifact_type === "spreadsheet" && /\.xlsx$/i.test(artifact.filename)) {
          const rows = await parseXlsxRows(blob);
          if (!cancelled) setPreview({ status: "table", rows });
          return;
        }
        if (!cancelled) setPreview({ status: "unsupported" });
      })
      .catch((error) => {
        if (!cancelled) setPreview({ status: "error", message: error instanceof Error ? error.message : "Preview failed" });
      });

    return () => {
      cancelled = true;
      if (revokedUrl) URL.revokeObjectURL(revokedUrl);
    };
  }, [artifact, contentUrl]);

  if (!artifact) return null;

  return (
    <div className="flex h-full min-h-0 flex-col bg-[var(--panel-elevated)]">
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-[var(--border-main)] px-3 py-2">
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-2">
            <FileTypeLogo artifact={artifact} className="h-8 w-8" />
            <div className="min-w-0">
              <div className="truncate text-sm font-medium text-[var(--text-primary)]">{artifact.title || artifact.filename}</div>
              <div className="truncate text-xs text-[var(--text-secondary)]">{artifact.filename}</div>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button type="button" onClick={() => void openBlob(false)} className="rounded-lg p-2 text-[var(--text-blue)] hover:bg-[var(--fill-tsp-white-light)]" title={t("artifact.open", "Open")}>
            <ExternalLink size={15} />
          </button>
          <button type="button" onClick={() => void openBlob(true)} className="rounded-lg p-2 text-[var(--text-primary)] hover:bg-[var(--fill-tsp-white-light)]" title={t("artifact.download", "Download")}>
            <Download size={15} />
          </button>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-hidden">
        {preview.status === "loading" ? <div className="p-4 text-sm text-[var(--text-secondary)]">{t("artifact.loadingPreview", "Loading preview...")}</div> : null}
        {preview.status === "error" ? <div className="p-4 text-sm text-[var(--danger)]">{preview.message}</div> : null}
        {preview.status === "unsupported" ? <div className="p-4 text-sm text-[var(--text-secondary)]">{t("artifact.previewUnsupported", "Preview is not available for this file type yet. Use Open or Download.")}</div> : null}
        {preview.status === "table" ? <PreviewTable rows={preview.rows} /> : null}
        {preview.status === "blob" && preview.kind === "image" ? <img src={preview.url} alt={artifact.filename} className="h-full w-full object-contain p-3" /> : null}
        {preview.status === "blob" && preview.kind === "pdf" ? <iframe src={preview.url} title={artifact.filename} className="h-full w-full border-0" /> : null}
      </div>
    </div>
  );
}
