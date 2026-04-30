import { useMemo } from "react";
import type { WorkspaceFrame } from "../../../types";

function getDomain(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}

function formatSearchUrl(url: string): string {
  try {
    const u = new URL(url);
    const parts = [u.hostname, ...u.pathname.split("/").filter(Boolean)];
    return parts.join(" › ");
  } catch {
    return url;
  }
}

function cleanSnippet(text: string): string {
  return text
    .replace(/·\s*/g, "")
    .replace(/translate this page\s*/gi, "")
    .replace(/read more\s*$/gi, "")
    .replace(/\s{2,}/g, " ")
    .trim();
}

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
    if (/^\[(\d+)\]\s/.test(line) || /^\d+\.\s/.test(line)) {
      if (current.title) results.push(current as SearchResult);
      current = {
        title: line.replace(/^\[\d+\]\s/, "").replace(/^\d+\.\s/, "").trim(),
        url: "",
        snippet: "",
      };
    } else if (line.trim().startsWith("URL:")) {
      current.url = line.replace(/^\s*URL:\s*/, "").trim();
    } else if (line.trim() && current.title !== undefined) {
      const text = line.trim();
      if (!text.startsWith("{'") && !text.startsWith('{"') && !text.startsWith("[{")) {
        current.snippet = current.snippet ? `${current.snippet} ${text}` : text;
      }
    }
  }
  if (current.title) results.push(current as SearchResult);
  return results;
}

function WebSearchResults({ output }: { output: string }) {
  const results = useMemo(() => parseWebResults(output), [output]);

  if (results.length === 0) {
    return (
      <pre className="p-4 whitespace-pre-wrap text-xs text-[var(--text-primary)]">{output}</pre>
    );
  }

  return (
    <div className="flex flex-col px-4 py-3">
      {results.map((r, i) => (
        <div
          key={`${r.url || r.title}-${i}`}
          className={`py-3 ${i < results.length - 1 ? "border-b border-[var(--border-subtle)]" : ""}`}
        >
          <a
            href={r.url || undefined}
            target="_blank"
            rel="noopener noreferrer"
            className="block text-[var(--text-primary)] text-sm font-medium hover:underline line-clamp-2 cursor-pointer"
          >
            {r.url && (
              <img
                width="16"
                height="16"
                alt=""
                className="float-left mr-2 mt-0.5 rounded-full border border-[var(--border-subtle)]"
                src={`https://s2.googleusercontent.com/s2/favicons?domain=${getDomain(r.url)}&sz=32`}
                onError={(e) => {
                  (e.target as HTMLImageElement).style.display = "none";
                }}
              />
            )}
            {r.title}
          </a>
          {r.url && (
            <div className="text-[#188038] dark:text-[#34a853] text-[11px] mt-0.5 truncate">
              {formatSearchUrl(r.url)}
            </div>
          )}
          {r.snippet && (
            <div className="text-[var(--text-tertiary,#9ca3af)] text-xs mt-0.5 line-clamp-2 leading-relaxed">
              {cleanSnippet(r.snippet)}
            </div>
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
      <div className="flex-1 ws-scrollbar overflow-y-auto">
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
