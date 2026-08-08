"use client";

import React, { memo, useCallback, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { Check, Copy } from "lucide-react";

/**
 * Assistant message body (HOS-074).
 *
 * Replaces a two-line regex renderer piped through `dangerouslySetInnerHTML`
 * — a real XSS hole, since a model is perfectly capable of emitting
 * `<img src=x onerror=...>` and the cockpit would have executed it. It also
 * only understood `**bold**` and newlines: code blocks, tables and lists,
 * i.e. most of what a development assistant actually replies with, rendered
 * as flat text.
 *
 * react-markdown builds a React tree instead of injecting HTML, so raw HTML
 * in model output is inert by default (no `rehype-raw` here, deliberately).
 */

/** Language label for the code block header, from the `language-x` class
 *  rehype-highlight puts on `<code>`. Empty when the model didn't annotate
 *  the fence — shown as "code" rather than guessing wrong. */
function languageOf(className?: string): string {
  const match = /language-([\w+-]+)/.exec(className ?? "");
  return match ? match[1] : "";
}

function CodeBlock({ className, children }: {
  className?: string;
  children: React.ReactNode;
}) {
  const [copied, setCopied] = useState(false);
  const language = languageOf(className);

  const copy = useCallback(() => {
    // The rendered text, not the markdown source: what the user sees in the
    // block is exactly what lands on the clipboard.
    const text = String(children ?? "");
    void navigator.clipboard?.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    });
  }, [children]);

  return (
    <div className="group/code relative my-3 overflow-hidden rounded-xl border border-hermes-border/70 bg-hermes-bg-deep/80">
      <div className="flex items-center justify-between border-b border-hermes-border/60 bg-hermes-elevated/40 px-3 py-1.5">
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-hermes-muted">
          {language || "code"}
        </span>
        <button
          onClick={copy}
          aria-label="Copier le code"
          className="flex items-center gap-1.5 rounded-md px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider
            text-hermes-muted opacity-0 transition-all hover:bg-hermes-cyan/10 hover:text-hermes-cyan
            focus:opacity-100 focus:outline-none focus-visible:ring-1 focus-visible:ring-hermes-cyan/60
            group-hover/code:opacity-100"
        >
          {copied ? <Check size={11} /> : <Copy size={11} />}
          {copied ? "Copié" : "Copier"}
        </button>
      </div>
      <pre className="overflow-x-auto p-3.5 text-[12.5px] leading-relaxed">
        <code className={className}>{children}</code>
      </pre>
    </div>
  );
}

/** Streaming means this re-renders on every token; memoising on the text
 *  keeps the parse off the hot path for messages that are already final. */
export const MarkdownMessage = memo(function MarkdownMessage({
  content,
}: {
  content: string;
}) {
  return (
    <div className="hermes-md text-[13.5px] leading-[1.7] text-hermes-text">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeHighlight, { detect: true, ignoreMissing: true }]]}
        components={{
          pre: ({ children }) => <>{children}</>,
          code({ className, children, ...props }) {
            // A fenced block arrives wrapped in <pre>; inline code does not.
            // react-markdown v9 dropped the `inline` flag, so the fence is
            // identified by the language class rehype-highlight adds.
            const isBlock = /language-/.test(className ?? "") ||
              String(children ?? "").includes("\n");
            if (isBlock) {
              return <CodeBlock className={className}>{children}</CodeBlock>;
            }
            return (
              <code
                className="rounded border border-hermes-border/60 bg-hermes-elevated/70 px-1.5 py-0.5
                  font-mono text-[12px] text-hermes-cyan"
                {...props}
              >
                {children}
              </code>
            );
          },
          a: ({ children, href }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-hermes-cyan underline decoration-hermes-cyan/30 underline-offset-2
                transition-colors hover:decoration-hermes-cyan"
            >
              {children}
            </a>
          ),
          table: ({ children }) => (
            <div className="my-3 overflow-x-auto rounded-lg border border-hermes-border/70">
              <table className="w-full border-collapse text-[12.5px]">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border-b border-hermes-border/70 bg-hermes-elevated/40 px-3 py-2 text-left
              font-mono text-[10px] uppercase tracking-wider text-hermes-muted">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border-b border-hermes-border/40 px-3 py-2 align-top">{children}</td>
          ),
          ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>,
          ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>,
          h1: ({ children }) => (
            <h1 className="mb-2 mt-4 text-[17px] font-semibold text-hermes-text-bright first:mt-0">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="mb-2 mt-4 text-[15px] font-semibold text-hermes-text-bright first:mt-0">{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 className="mb-1.5 mt-3 text-[13.5px] font-semibold text-hermes-text-bright first:mt-0">{children}</h3>
          ),
          p: ({ children }) => <p className="my-2 first:mt-0 last:mb-0">{children}</p>,
          blockquote: ({ children }) => (
            <blockquote className="my-3 border-l-2 border-hermes-cyan/40 bg-hermes-cyan/[0.04] py-1 pl-3 text-hermes-muted">
              {children}
            </blockquote>
          ),
          hr: () => <hr className="my-4 border-hermes-border/60" />,
          strong: ({ children }) => (
            <strong className="font-semibold text-hermes-text-bright">{children}</strong>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
});
