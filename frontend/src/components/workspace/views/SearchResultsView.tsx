import type { WorkspaceFrame } from "../../../types";

function GrepResults({ output }: { output: string }) {
  const lines = output.split("\n").filter(Boolean);
  const grouped: Record<string, { line: string; content: string }[]> = {};

  for (const raw of lines) {
    const match = raw.match(/^(.+?):(\d+):(.*)$/);
    if (match) {
      const [, file, lineNum, content] = match;
      if (!grouped[file]) grouped[file] = [];
      grouped[file].push({ line: lineNum, content });
    } else {
      if (!grouped["matches"]) grouped["matches"] = [];
      grouped["matches"].push({ line: "", content: raw });
    }
  }

  if (Object.keys(grouped).length === 0) {
    return <div className="p-4 text-xs italic text-[var(--text-tertiary,#666)]">No matches found</div>;
  }

  return (
    <div className="flex flex-col gap-3 p-4">
      {Object.entries(grouped).map(([file, rows]) => (
        <div key={file} className="rounded-lg border border-[var(--border-subtle)] overflow-hidden">
          <div className="bg-[var(--surface-soft)] px-3 py-1.5 text-xs font-medium text-[var(--accent,#4d7cf4)] truncate" title={file}>
            {file}
          </div>
          {rows.map((r, i) => (
            <div key={`${file}-${r.line}-${i}`} className="flex gap-2 border-t border-[var(--border-subtle)] px-3 py-1 font-mono text-xs">
              {r.line && (
                <span className="w-8 shrink-0 text-right text-[var(--text-tertiary,#666)] select-none">{r.line}</span>
              )}
              <span className="text-[var(--text-primary)] break-all">{r.content}</span>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

type SearchResult = { title: string; url: string; snippet: string };

function parseWebResults(output: string): SearchResult[] {
  const lines = output.split("\n");
  const results: SearchResult[] = [];
  let current: Partial<SearchResult> = {};

  for (const line of lines) {
    if (/^\d+\.\s/.test(line)) {
      if (current.title) results.push(current as SearchResult);
      current = { title: line.replace(/^\d+\.\s/, "").trim(), url: "", snippet: "" };
    } else if (line.startsWith("URL:")) {
      current.url = line.replace("URL:", "").trim();
    } else if (line.trim()) {
      current.snippet = current.snippet ? `${current.snippet} ${line.trim()}` : line.trim();
    }
  }
  if (current.title) results.push(current as SearchResult);
  return results;
}

function WebSearchResults({ output }: { output: string }) {
  const results = parseWebResults(output);

  if (results.length === 0) {
    return (
      <pre className="p-4 whitespace-pre-wrap text-xs text-[var(--text-primary)]">{output}</pre>
    );
  }

  return (
    <div className="flex flex-col gap-3 p-4">
      {results.map((r, i) => (
        <div key={`${r.url || r.title}-${i}`} className="rounded-lg border border-[var(--border-subtle)] p-3 flex flex-col gap-1">
          <div className="text-sm font-medium text-[var(--text-primary)]">{r.title}</div>
          {r.url && (
            <div className="text-xs text-[var(--accent,#4d7cf4)] truncate" title={r.url}>{r.url}</div>
          )}
          {r.snippet && (
            <div className="text-xs text-[var(--text-secondary)] leading-relaxed">{r.snippet}</div>
          )}
        </div>
      ))}
    </div>
  );
}

export default function SearchResultsView({ frame }: { frame: WorkspaceFrame }) {
  const isWeb = frame.toolName === "tavily_search";
  const query = isWeb
    ? (frame.input.query as string | undefined) ?? ""
    : (frame.input.pattern as string | undefined) ?? "";

  return (
    <div className="flex h-full flex-col">
      <div className="shrink-0 border-b border-[var(--border-subtle)] px-4 py-2 text-xs text-[var(--text-secondary)]">
        {isWeb ? "Query" : "Pattern"}:{" "}
        <span className="font-mono text-[var(--text-primary)]">{query}</span>
      </div>
      <div className="flex-1 ws-scrollbar">
        {frame.output === undefined ? (
          <div className="p-4 text-xs italic text-[var(--text-tertiary,#666)]">Searching…</div>
        ) : isWeb ? (
          <WebSearchResults output={frame.output} />
        ) : (
          <GrepResults output={frame.output} />
        )}
      </div>
    </div>
  );
}
