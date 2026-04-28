import { Folder, File } from "lucide-react";
import type { WorkspaceFrame } from "../../../types";

function parseToolOutput(raw: string): string {
  const marker = "content=";
  const start = raw.indexOf(marker);
  if (start === -1) return raw;

  const quote = raw[start + marker.length];
  if (quote !== "'" && quote !== '"') return raw;

  let value = "";
  let escaped = false;

  for (let i = start + marker.length + 1; i < raw.length; i++) {
    const char = raw[i];
    if (escaped) {
      if (char === "n") value += "\n";
      else if (char === "t") value += "\t";
      else if (char === "r") value += "\r";
      else if (char === "\\") value += "\\";
      else if (char === "'") value += "'";
      else if (char === '"') value += '"';
      else value += char;
      escaped = false;
    } else if (char === "\\") {
      escaped = true;
    } else if (char === quote) {
      return value;
    } else {
      value += char;
    }
  }

  return value || raw;
}

export default function FileTreeView({ frame }: { frame: WorkspaceFrame }) {
  const rawOutput = frame.output;
  const resolved = rawOutput ? parseToolOutput(rawOutput) : "";
  const lines = resolved ? resolved.split("\n").filter(Boolean) : [];

  const label =
    frame.toolName === "glob"
      ? `Pattern: ${(frame.input.pattern as string | undefined) ?? ""}`
      : `Path: ${(frame.input.path as string | undefined) ?? "."}`;

  return (
    <div className="flex h-full flex-col">
      <div className="shrink-0 border-b border-[var(--border-subtle)] px-4 py-2 text-xs text-[var(--text-secondary)]">
        {label}
      </div>
      <div className="flex-1 p-2 font-mono text-xs" style={{ overflowY: 'scroll', scrollbarGutter: 'stable' }}>
        {lines.length === 0 && (
          <div className="p-2 text-[var(--text-tertiary,#666)] italic">
            {rawOutput === undefined ? "Running…" : "No results"}
          </div>
        )}
        {lines.map((line) => {
          const isDir = line.endsWith("/");
          return (
            <div
              key={line}
              className="flex items-center gap-1.5 rounded px-2 py-0.5 text-[var(--text-primary)] hover:bg-[var(--surface-soft)]"
            >
              {isDir ? (
                <Folder size={13} className="shrink-0 text-[var(--accent,#4d7cf4)]" />
              ) : (
                <File size={13} className="shrink-0 text-[var(--text-secondary)]" />
              )}
              <span className="truncate">{line}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
