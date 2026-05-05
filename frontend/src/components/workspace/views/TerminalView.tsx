import type { WorkspaceFrame } from "../../../types";

const MAX_LINES = 500;

export default function TerminalView({ frame }: { frame: WorkspaceFrame }) {
  const command = (frame.input.command as string | undefined) ?? "";
  const prompt = frame.toolName === "powershell" ? "PS>" : "$";

  const rawLines = frame.output?.split("\n") ?? [];
  const isTruncated = rawLines.length > MAX_LINES;
  const visibleOutput = isTruncated ? rawLines.slice(-MAX_LINES).join("\n") : frame.output;
  const isRunning = frame.status === "in_progress" || (frame.status === undefined && frame.output === undefined);

  return (
    <div
      className="flex h-full flex-col overflow-hidden font-mono text-sm leading-relaxed"
      style={{ backgroundColor: "var(--workspace-terminal-bg)" }}
    >
      <div
        className="flex-1 overflow-y-auto px-4 py-3"
        style={{
          scrollbarWidth: "thin",
          scrollbarColor: "var(--workspace-terminal-scrollbar) transparent",
        }}
      >
        {isTruncated && (
          <div
            className="mb-3 rounded px-2 py-1 text-[10px] uppercase tracking-wider"
            style={{
              background: "var(--workspace-terminal-warning-bg)",
              border: "1px solid var(--workspace-terminal-warning-border)",
              color: "var(--workspace-terminal-warning-text)",
            }}
          >
            Output truncated - showing last {MAX_LINES} lines
          </div>
        )}

        <div className="mb-2 flex items-start gap-2">
          <span className="select-none font-bold" style={{ color: "var(--workspace-terminal-prompt)" }}>
            {prompt}
          </span>
          <span className="break-all" style={{ color: "var(--workspace-terminal-command)" }}>
            {command}
          </span>
        </div>

        {visibleOutput !== undefined && (
          <pre className="whitespace-pre-wrap break-words" style={{ color: "var(--workspace-terminal-output)" }}>
            {visibleOutput}
          </pre>
        )}

        {isRunning && (
          <div className="mt-2 flex items-center gap-2" style={{ color: "var(--workspace-terminal-muted)" }}>
            <span
              className="inline-block h-4 w-2 animate-pulse"
              style={{ backgroundColor: "var(--workspace-terminal-cursor)" }}
            />
            <span className="text-[11px] uppercase tracking-widest opacity-50">Executing...</span>
          </div>
        )}
      </div>
    </div>
  );
}
