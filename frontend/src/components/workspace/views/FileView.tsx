import type { editor } from "monaco-editor";
import { startTransition, useDeferredValue, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { codeToHtml } from "shiki";
import { useTheme } from "../../../context/ThemeContext";
import type { WorkspaceFrame } from "../../../types";
import editorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";
import jsonWorker from "monaco-editor/esm/vs/language/json/json.worker?worker";
import cssWorker from "monaco-editor/esm/vs/language/css/css.worker?worker";
import htmlWorker from "monaco-editor/esm/vs/language/html/html.worker?worker";
import tsWorker from "monaco-editor/esm/vs/language/typescript/ts.worker?worker";

type DiffMode = "diff" | "original" | "modified";

type MonacoModule = typeof import("@monaco-editor/react");

let monacoModulePromise: Promise<MonacoModule> | null = null;

function ensureMonacoEnvironment() {
  const scope = globalThis as typeof globalThis & {
    MonacoEnvironment?: {
      getWorker?: (_workerId: string, label: string) => Worker;
    };
  };

  if (scope.MonacoEnvironment?.getWorker) return;

  scope.MonacoEnvironment = {
    getWorker(_workerId: string, label: string) {
      switch (label) {
        case "json":
          return new jsonWorker();
        case "css":
        case "scss":
        case "less":
          return new cssWorker();
        case "html":
        case "handlebars":
        case "razor":
          return new htmlWorker();
        case "typescript":
        case "javascript":
          return new tsWorker();
        default:
          return new editorWorker();
      }
    },
  };
}

function loadMonacoModule() {
  if (!monacoModulePromise) {
    monacoModulePromise = Promise.all([
      import("@monaco-editor/react"),
      import("monaco-editor"),
    ]).then(([module, monaco]) => {
      ensureMonacoEnvironment();
      module.loader.config({ monaco });
      return module;
    });
  }
  return monacoModulePromise;
}

const SHIKI_THEMES = {
  dark: "github-dark",
  light: "github-light",
} as const;

const EDITOR_OPTIONS: editor.IStandaloneEditorConstructionOptions = {
  readOnly: true,
  minimap: { enabled: false },
  glyphMargin: false,
  folding: false,
  lineNumbersMinChars: 3,
  overviewRulerBorder: false,
  overviewRulerLanes: 0,
  renderLineHighlight: "none",
  scrollBeyondLastLine: false,
  scrollbar: {
    verticalScrollbarSize: 8,
    horizontalScrollbarSize: 8,
  },
  smoothScrolling: true,
  padding: { top: 16, bottom: 16 },
};

const DIFF_OPTIONS: editor.IStandaloneDiffEditorConstructionOptions = {
  ...EDITOR_OPTIONS,
  renderSideBySide: true,
  enableSplitViewResizing: true,
  originalEditable: false,
  diffWordWrap: "on",
  lineDecorationsWidth: 12,
};

function resolveCodeLanguage(frame: WorkspaceFrame) {
  const path = typeof frame.input.path === "string" ? frame.input.path.toLowerCase() : "";
  const extension = path.includes(".") ? path.split(".").pop() ?? "" : "";

  switch (extension) {
    case "ts":
    case "tsx":
      return "typescript";
    case "js":
    case "jsx":
    case "mjs":
    case "cjs":
      return "javascript";
    case "py":
      return "python";
    case "json":
      return "json";
    case "md":
      return "markdown";
    case "html":
    case "htm":
      return "html";
    case "css":
      return "css";
    case "scss":
      return "scss";
    case "yml":
    case "yaml":
      return "yaml";
    case "sh":
      return "shell";
    case "ps1":
      return "powershell";
    case "sql":
      return "sql";
    case "xml":
      return "xml";
    case "rs":
      return "rust";
    case "go":
      return "go";
    case "java":
      return "java";
    case "rb":
      return "ruby";
    case "php":
      return "php";
    default:
      return "plaintext";
  }
}

function resolveShikiLanguage(language: string) {
  switch (language) {
    case "plaintext":
      return "text";
    case "shell":
      return "bash";
    default:
      return language;
  }
}

function decodeEscapedToolString(value: string) {
  return value
    .replace(/\\\\/g, "\u0000")
    .replace(/\\n/g, "\n")
    .replace(/\\t/g, "\t")
    .replace(/\\r/g, "\r")
    .replace(/\\'/g, "'")
    .replace(/\\"/g, "\"")
    .replace(/\u0000/g, "\\");
}

function extractToolMessageContent(raw: string) {
  const marker = "content=";
  const start = raw.indexOf(marker);
  if (start === -1) return null;

  const quote = raw[start + marker.length];
  if (quote !== "'" && quote !== "\"") return null;

  let value = "";
  let escaped = false;

  for (let index = start + marker.length + 1; index < raw.length; index += 1) {
    const char = raw[index];

    if (escaped) {
      value += `\\${char}`;
      escaped = false;
      continue;
    }

    if (char === "\\") {
      escaped = true;
      continue;
    }

    if (char === quote) {
      return decodeEscapedToolString(value);
    }

    value += char;
  }

  return null;
}

function resolveFrameContent(frame: WorkspaceFrame) {
  const output = typeof frame.output === "string" ? frame.output : "";
  const parsedOutput = output ? extractToolMessageContent(output) : null;

  if (frame.toolName === "write_file") {
    const inputContent = typeof frame.input.content === "string" ? frame.input.content : "";
    return inputContent || parsedOutput || output;
  }

  return parsedOutput || output;
}

function useShikiHtml(code: string, language: string, theme: keyof typeof SHIKI_THEMES) {
  const deferredCode = useDeferredValue(code);
  const [html, setHtml] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    void codeToHtml(deferredCode || " ", {
      lang: resolveShikiLanguage(language),
      theme: SHIKI_THEMES[theme],
    })
      .then((nextHtml) => {
        if (cancelled) return;
        startTransition(() => setHtml(nextHtml));
      })
      .catch(() => {
        if (cancelled) return;
        startTransition(() => {
          setHtml(null);
        });
      });

    return () => {
      cancelled = true;
    };
  }, [deferredCode, language, theme]);

  return html;
}

function ShikiPreview({
  code,
  language,
  emptyLabel,
}: {
  code: string;
  language: string;
  emptyLabel: string;
}) {
  const { theme } = useTheme();
  const html = useShikiHtml(code, language, theme);

  return (
    <div className="ws-scrollbar h-full workspace-code-preview">
      {html !== null ? (
        <div
          className="min-h-full"
          dangerouslySetInnerHTML={{ __html: html }}
        />
      ) : code ? (
        <pre className="min-h-full whitespace-pre-wrap break-words px-5 py-4 font-mono text-[13px] leading-[1.7] text-[var(--text-primary)]">
          {code}
        </pre>
      ) : (
        <div className="px-5 py-5 italic text-[var(--text-tertiary)] opacity-60">
          {emptyLabel}
        </div>
      )}
    </div>
  );
}

function MonacoReadOnlyEditor({
  language,
  value,
  loading,
}: {
  language: string;
  value: string;
  loading: React.ReactNode;
}) {
  const { theme } = useTheme();
  const [EditorComponent, setEditorComponent] = useState<MonacoModule["default"] | null>(null);
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    let cancelled = false;

    setIsReady(false);
    void loadMonacoModule().then((module) => {
      if (cancelled) return;
      setEditorComponent(() => module.default);
    });

    return () => {
      cancelled = true;
    };
  }, []);

  if (!EditorComponent) return <>{loading}</>;

  return (
    <div className="relative h-full">
      {!isReady && (
        <div className="absolute inset-0 z-0">
          {loading}
        </div>
      )}
      <div className={`absolute inset-0 z-10 ${isReady ? "opacity-100" : "opacity-0 pointer-events-none"}`}>
        <EditorComponent
          height="100%"
          defaultLanguage={language}
          language={language}
          theme={theme === "dark" ? "vs-dark" : "vs"}
          value={value}
          loading={loading}
          options={EDITOR_OPTIONS}
          onMount={() => setIsReady(true)}
        />
      </div>
    </div>
  );
}

function MonacoDiffSurface({
  language,
  original,
  modified,
  loading,
}: {
  language: string;
  original: string;
  modified: string;
  loading: React.ReactNode;
}) {
  const { theme } = useTheme();
  const [DiffEditorComponent, setDiffEditorComponent] = useState<MonacoModule["DiffEditor"] | null>(null);
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    let cancelled = false;

    setIsReady(false);
    void loadMonacoModule().then((module) => {
      if (cancelled) return;
      setDiffEditorComponent(() => module.DiffEditor);
    });

    return () => {
      cancelled = true;
    };
  }, []);

  if (!DiffEditorComponent) return <>{loading}</>;

  return (
    <div className="relative h-full">
      {!isReady && (
        <div className="absolute inset-0 z-0">
          {loading}
        </div>
      )}
      <div className={`absolute inset-0 z-10 ${isReady ? "opacity-100" : "opacity-0 pointer-events-none"}`}>
        <DiffEditorComponent
          height="100%"
          original={original}
          modified={modified}
          language={language}
          theme={theme === "dark" ? "vs-dark" : "vs"}
          loading={loading}
          options={DIFF_OPTIONS}
          onMount={() => setIsReady(true)}
        />
      </div>
    </div>
  );
}

export default function FileView({ frame }: { frame: WorkspaceFrame }) {
  const { t } = useTranslation();
  const [diffMode, setDiffMode] = useState<DiffMode>("diff");
  const isEdit = frame.toolName === "edit_file";
  const language = useMemo(() => resolveCodeLanguage(frame), [frame]);
  const hasNewString = typeof frame.input.new_string === "string";
  const hasWriteContent = typeof frame.input.content === "string";
  const hasOutput = typeof frame.output === "string";
  const resolvedContent = useMemo(() => resolveFrameContent(frame), [frame]);

  const oldString = useDeferredValue((frame.input.old_string as string | undefined) ?? "");
  const newString = useDeferredValue((frame.input.new_string as string | undefined) ?? "");
  const content = useDeferredValue(
    resolvedContent,
  );
  const modifiedContent = hasNewString ? newString : content;
  const isLoading = isEdit ? !hasNewString && !hasOutput : !hasOutput && !(frame.toolName === "write_file" && hasWriteContent);
  const showValue = isEdit || hasOutput || (frame.toolName === "write_file" && hasWriteContent);

  const displayContent = isEdit
    ? diffMode === "original"
      ? oldString
      : modifiedContent
    : content;

  const emptyLabel = isLoading
    ? t("workspace.file.waitingForEditResult", "Waiting for edit result...")
    : "";

  useEffect(() => {
    if (isEdit) return;
    setDiffMode("modified");
  }, [isEdit]);

  const shikiFallback = (
    <ShikiPreview
      code={showValue ? displayContent : ""}
      language={language}
      emptyLabel={emptyLabel}
    />
  );

  return (
    <div className="relative flex h-full flex-col overflow-hidden bg-[var(--background-gray-main)]">
      <div className="flex shrink-0 justify-end px-4 pt-2">
        <div className="workspace-file-tabs inline-flex h-7 items-center rounded-lg p-0.5 backdrop-blur-3xl">
          {(["diff", "original", "modified"] as DiffMode[]).map((mode) => {
            const isDisabled = !isEdit && mode !== "modified";
            return (
              <button
                key={mode}
                type="button"
                data-state={diffMode === mode ? "on" : "off"}
                disabled={isDisabled}
                onClick={() => {
                  if (isDisabled) return;
                  setDiffMode(mode);
                }}
                className="workspace-file-tab inline-flex cursor-pointer items-center justify-center rounded-md px-3 py-1 text-xs transition-colors disabled:cursor-not-allowed"
              >
                {t(`workspace.file.${mode}`, mode.charAt(0).toUpperCase() + mode.slice(1))}
              </button>
            );
          })}
        </div>
      </div>

      <div className="min-h-0 flex-1 pt-2">
        {isEdit && diffMode === "diff" ? (
          <MonacoDiffSurface
            language={language}
            original={oldString}
            modified={modifiedContent}
            loading={
              <ShikiPreview
                code={showValue ? modifiedContent : ""}
                language={language}
                emptyLabel={emptyLabel}
              />
            }
          />
        ) : (
          <MonacoReadOnlyEditor
            language={language}
            value={displayContent}
            loading={shikiFallback}
          />
        )}
      </div>
    </div>
  );
}
