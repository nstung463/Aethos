import type { WorkspaceFrame } from "../../../types";

export default function GenericView({ frame }: { frame: WorkspaceFrame }) {
  return (
    <div className="flex flex-col gap-3 p-4 font-mono text-xs text-[var(--text-secondary)]">
      <div className="text-[var(--text-primary)] font-semibold">{frame.toolName}</div>
      <pre className="whitespace-pre-wrap break-all rounded-lg bg-[var(--surface-soft)] p-3">
        {JSON.stringify(frame.input, null, 2)}
      </pre>
      {frame.output && (
        <pre className="whitespace-pre-wrap break-all rounded-lg bg-[var(--surface-soft)] p-3 text-[var(--text-primary)]">
          {frame.output}
        </pre>
      )}
    </div>
  );
}
