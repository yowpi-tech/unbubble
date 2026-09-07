'use client';

import { isValidElement, type ReactElement, type ReactNode } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeSlug from 'rehype-slug';
import { MermaidDiagram } from './mermaid-diagram';

/**
 * Plain-Markdown renderer (the skills write Markdown, not MDX — angle brackets like
 * `<workdir>` must survive). Styling mirrors BubbleDocs' mdx-components.
 */
export function Markdown({
  source,
  onRelativeLink,
}: {
  source: string;
  /** Called for links to other project files (e.g. `05-backend-workflows.md`). Return true if handled. */
  onRelativeLink?: (href: string) => boolean;
}) {
  const components: Components = {
    h1: ({ children, ...props }) => (
      <h1 className="scroll-mt-6 text-3xl font-bold tracking-tight mt-8 mb-4 pb-2 border-b border-zinc-200 dark:border-zinc-800 first:mt-0" {...props}>
        {children}
      </h1>
    ),
    h2: ({ children, ...props }) => (
      <h2 className="scroll-mt-6 text-2xl font-semibold tracking-tight mt-8 mb-3 pb-1.5 border-b border-zinc-100 dark:border-zinc-800/50" {...props}>
        {children}
      </h2>
    ),
    h3: ({ children, ...props }) => (
      <h3 className="scroll-mt-6 text-xl font-semibold tracking-tight mt-6 mb-2" {...props}>
        {children}
      </h3>
    ),
    h4: ({ children, ...props }) => (
      <h4 className="scroll-mt-6 text-lg font-semibold mt-4 mb-2" {...props}>
        {children}
      </h4>
    ),
    p: ({ children, ...props }) => (
      <p className="leading-7 mb-4" {...props}>
        {children}
      </p>
    ),
    ul: ({ children, ...props }) => (
      <ul className="list-disc pl-6 mb-4 space-y-1.5" {...props}>
        {children}
      </ul>
    ),
    ol: ({ children, ...props }) => (
      <ol className="list-decimal pl-6 mb-4 space-y-1.5" {...props}>
        {children}
      </ol>
    ),
    li: ({ children, ...props }) => (
      <li className="leading-7" {...props}>
        {children}
      </li>
    ),
    blockquote: ({ children, ...props }) => (
      <blockquote className="border-l-4 border-zinc-300 dark:border-zinc-700 pl-4 py-1 my-4 text-zinc-600 dark:text-zinc-400 italic" {...props}>
        {children}
      </blockquote>
    ),
    hr: (props) => <hr className="my-6 border-zinc-200 dark:border-zinc-800" {...props} />,
    a: ({ children, href, ...props }) => {
      const isRelative = !!href && !/^(?:[a-z]+:|#|\/)/i.test(href);
      return (
        <a
          href={href}
          className="text-blue-600 dark:text-blue-400 underline underline-offset-2 decoration-blue-600/30 dark:decoration-blue-400/30 hover:decoration-blue-600 dark:hover:decoration-blue-400 transition-colors"
          target={href && /^https?:/i.test(href) ? '_blank' : undefined}
          rel={href && /^https?:/i.test(href) ? 'noreferrer' : undefined}
          onClick={(e) => {
            if (isRelative && onRelativeLink && href && onRelativeLink(href)) e.preventDefault();
          }}
          {...props}
        >
          {children}
        </a>
      );
    },
    strong: ({ children, ...props }) => (
      <strong className="font-semibold text-zinc-900 dark:text-zinc-100" {...props}>
        {children}
      </strong>
    ),
    table: ({ children, ...props }) => (
      <div className="overflow-x-auto my-4 rounded-lg border border-zinc-200 dark:border-zinc-800">
        <table className="min-w-full text-sm" {...props}>
          {children}
        </table>
      </div>
    ),
    thead: ({ children, ...props }) => (
      <thead className="bg-zinc-50 dark:bg-zinc-800/60 border-b border-zinc-200 dark:border-zinc-700" {...props}>
        {children}
      </thead>
    ),
    th: ({ children, ...props }) => (
      <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-600 dark:text-zinc-300" {...props}>
        {children}
      </th>
    ),
    td: ({ children, ...props }) => (
      <td className="px-4 py-2 border-b border-zinc-100 dark:border-zinc-800 text-zinc-700 dark:text-zinc-300 align-top" {...props}>
        {children}
      </td>
    ),
    tr: ({ children, ...props }) => (
      <tr className="hover:bg-zinc-50 dark:hover:bg-zinc-800/30 transition-colors" {...props}>
        {children}
      </tr>
    ),
    input: ({ ...props }) => <input {...props} className="mr-1 align-middle accent-green-600" disabled />,
    code: ({ children, className, ...props }) => {
      // Fenced blocks arrive wrapped in <pre> (handled below); this styles inline code.
      if (!className) {
        return (
          <code className="bg-zinc-100 dark:bg-zinc-800 rounded px-1.5 py-0.5 text-[0.85em] font-mono text-pink-600 dark:text-pink-400" {...props}>
            {children}
          </code>
        );
      }
      return (
        <code className={className} {...props}>
          {children}
        </code>
      );
    },
    pre: ({ children, ...props }) => {
      const child = (Array.isArray(children) ? children[0] : children) as ReactNode;
      if (isValidElement(child)) {
        const el = child as ReactElement<{ className?: string; children?: ReactNode }>;
        if (el.props.className?.includes('language-mermaid')) {
          return <MermaidDiagram chart={String(el.props.children ?? '').replace(/\n$/, '')} />;
        }
      }
      return (
        <pre className="rounded-lg border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900 p-4 overflow-x-auto text-[13px] leading-relaxed font-mono my-4" {...props}>
          {children}
        </pre>
      );
    },
  };

  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSlug]} components={components}>
      {source}
    </ReactMarkdown>
  );
}
