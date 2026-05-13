import { memo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import CodeBlock from "./CodeBlock";

function MessageContent({ content }: { content: string }) {
  if (!content.trim()) return null;

  return (
    <div className="prose-dark">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a(props) {
            return (
              <a {...props} rel="noreferrer" target="_blank" className="text-[var(--accent)] hover:underline" />
            );
          },
          code({ children, className, ...props }) {
            const value = String(children).replace(/\n$/, "");
            const language = className?.replace("language-", "");
            const isInline = !className;

            if (isInline) {
              return (
                <code
                  className="rounded bg-[var(--surface-hover-strong)] px-1.5 py-0.5 font-mono text-sm text-[var(--text-primary)]"
                  {...props}
                >
                  {children}
                </code>
              );
            }

            return <CodeBlock language={language} value={value} />;
          },
          pre({ children }) {
            return <>{children}</>;
          },
          p({ children }) {
            return <p className="mb-2 leading-7 last:mb-0 sm:mb-3">{children}</p>;
          },
          ul({ children }) {
            return <ul className="mb-2 list-disc space-y-1 pl-4 sm:mb-3 sm:pl-5">{children}</ul>;
          },
          ol({ children }) {
            return <ol className="mb-2 list-decimal space-y-1 pl-4 sm:mb-3 sm:pl-5">{children}</ol>;
          },
          li({ children }) {
            return <li className="leading-7">{children}</li>;
          },
          h1({ children }) {
            return <h1 className="mt-3 mb-2 text-[clamp(1rem,2.5vw,1.3rem)] font-semibold text-[var(--text-primary)] sm:mt-4 sm:mb-3">{children}</h1>;
          },
          h2({ children }) {
            return <h2 className="mt-3 mb-2 text-[clamp(0.95rem,2.2vw,1.1rem)] font-semibold text-[var(--text-primary)] sm:mt-4">{children}</h2>;
          },
          h3({ children }) {
            return <h3 className="mt-2.5 mb-1.5 text-[clamp(0.9rem,2vw,1rem)] font-semibold text-[var(--text-primary)] sm:mt-3 sm:mb-2">{children}</h3>;
          },
          blockquote({ children }) {
            return (
              <blockquote className="my-3 border-l-2 border-[color:color-mix(in_oklab,var(--accent)_40%,transparent)] pl-4 italic text-[var(--text-muted)]">
                {children}
              </blockquote>
            );
          },
          table({ children }) {
            return (
              <div className="my-3 overflow-x-auto">
                <table className="w-full border-collapse text-sm">{children}</table>
              </div>
            );
          },
          th({ children }) {
            return (
              <th className="border border-[var(--border-subtle)] bg-[var(--surface-soft)] px-3 py-2 text-left font-semibold text-[var(--text-primary)]">
                {children}
              </th>
            );
          },
          td({ children }) {
            return <td className="border border-[var(--border-subtle)] px-3 py-2 text-[var(--text-secondary)]">{children}</td>;
          },
          hr() {
            return <hr className="my-4 border-[var(--border-subtle)]" />;
          },
          strong({ children }) {
            return <strong className="font-semibold text-[var(--text-primary)]">{children}</strong>;
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

export default memo(MessageContent);
