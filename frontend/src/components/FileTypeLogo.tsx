import type { OutputArtifact } from "../types";
import excelLogo from "../assets/file-logos/excel.svg";
import pdfLogo from "../assets/file-logos/pdf.svg";
import powerpointLogo from "../assets/file-logos/powerpoint.svg";
import wordLogo from "../assets/file-logos/word.svg";

type LogoKind = "excel" | "word" | "powerpoint" | "pdf" | "image" | "csv" | "archive" | "json" | "file";

function extensionFor(filename: string): string {
  const suffix = filename.split(".").pop()?.trim().toLowerCase() ?? "";
  return suffix && suffix !== filename.toLowerCase() ? suffix : "";
}

function logoKindFor(artifact: OutputArtifact): LogoKind {
  const extension = extensionFor(artifact.filename);
  if (["xlsx", "xls", "ods"].includes(extension)) return "excel";
  if (["docx", "doc", "rtf"].includes(extension)) return "word";
  if (["pptx", "ppt", "odp"].includes(extension)) return "powerpoint";
  if (extension === "pdf") return "pdf";
  if (["png", "jpg", "jpeg", "gif", "webp", "svg"].includes(extension)) return "image";
  if (["csv", "tsv"].includes(extension)) return "csv";
  if (extension === "json") return "json";
  if (["zip", "tar", "gz", "rar", "7z"].includes(extension)) return "archive";
  if (artifact.artifact_type === "spreadsheet") return "excel";
  if (artifact.artifact_type === "document") return "word";
  if (artifact.artifact_type === "presentation") return "powerpoint";
  if (artifact.artifact_type === "pdf") return "pdf";
  if (artifact.artifact_type === "image") return "image";
  if (artifact.artifact_type === "archive") return "archive";
  return "file";
}

function ImageLogo() {
  return (
    <svg viewBox="0 0 40 40" className="h-full w-full" aria-hidden="true">
      <rect x="7" y="7" width="26" height="26" rx="4" fill="#eff6ff" stroke="#3b82f6" strokeWidth="2" />
      <circle cx="25" cy="15" r="3" fill="#60a5fa" />
      <path d="M10 29l8-9 5 6 3-4 5 7z" fill="#2563eb" />
    </svg>
  );
}

function DataLogo({ label, color }: { label: string; color: string }) {
  return (
    <svg viewBox="0 0 40 40" className="h-full w-full" aria-hidden="true">
      <path d="M10 4h14l8 8v24H10z" fill="white" stroke={color} strokeWidth="2" />
      <path d="M24 4v8h8" fill={color} opacity="0.18" />
      <rect x="7" y="24" width="26" height="10" rx="2" fill={color} />
      <text x="20" y="32" textAnchor="middle" fontSize="8" fontFamily="Arial, Helvetica, sans-serif" fontWeight="800" fill="white">{label}</text>
    </svg>
  );
}

const brandLogos: Partial<Record<LogoKind, { src: string; alt: string; className?: string }>> = {
  excel: { src: excelLogo, alt: "Excel file" },
  word: { src: wordLogo, alt: "Word file" },
  powerpoint: { src: powerpointLogo, alt: "PowerPoint file" },
  pdf: { src: pdfLogo, alt: "PDF file", className: "h-[82%] w-[82%]" },
};

export default function FileTypeLogo({ artifact, className = "h-9 w-9" }: { artifact: OutputArtifact; className?: string }) {
  const kind = logoKindFor(artifact);
  const brandLogo = brandLogos[kind];
  return (
    <span className={`inline-flex shrink-0 items-center justify-center ${className}`} aria-label={`${extensionFor(artifact.filename).toUpperCase() || "File"} file`}>
      {brandLogo ? <img src={brandLogo.src} alt={brandLogo.alt} className={`${brandLogo.className ?? "h-full w-full"} object-contain`} /> : null}
      {kind === "image" ? <ImageLogo /> : null}
      {kind === "csv" ? <DataLogo label="CSV" color="#0f766e" /> : null}
      {kind === "json" ? <DataLogo label="JSON" color="#7c3aed" /> : null}
      {kind === "archive" ? <DataLogo label="ZIP" color="#a16207" /> : null}
      {kind === "file" ? <DataLogo label="FILE" color="#64748b" /> : null}
    </span>
  );
}
