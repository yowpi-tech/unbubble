'use client';

import { useEffect, useMemo, useState } from 'react';
import GithubSlugger from 'github-slugger';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Markdown } from './markdown';
import { cn } from '@/lib/utils';

interface Heading {
  level: number;
  text: string;
  id: string;
}

/** Same slugging as rehype-slug (github-slugger) so TOC anchors match the rendered ids. */
function extractHeadings(content: string): Heading[] {
  const slugger = new GithubSlugger();
  const headings: Heading[] = [];
  let inFence = false;
  for (const line of content.split('\n')) {
    if (/^\s*(```|~~~)/.test(line)) inFence = !inFence;
    if (inFence) continue;
    const match = line.match(/^(#{1,3})\s+(.+)/);
    if (match) {
      const text = match[2].replace(/[*_`[\]]/g, '').trim();
      headings.push({ level: match[1].length, text, id: slugger.slug(text) });
    }
  }
  return headings;
}

export function DocViewer({
  content,
  tocTitle = 'On this page',
  onRelativeLink,
}: {
  content: string;
  tocTitle?: string;
  onRelativeLink?: (href: string) => boolean;
}) {
  // The active heading is keyed by the content it belongs to, so switching documents resets it
  // without a synchronous setState inside the effect.
  const [active, setActive] = useState<{ content: string; id: string } | null>(null);
  const activeId = active && active.content === content ? active.id : '';
  const headings = useMemo(() => extractHeadings(content), [content]);

  useEffect(() => {
    if (headings.length === 0) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting);
        if (visible.length > 0) setActive({ content, id: visible[0].target.id });
      },
      { rootMargin: '-5% 0% -70% 0%', threshold: 0 },
    );
    const timer = setTimeout(() => {
      headings.forEach(({ id }) => {
        const el = document.getElementById(id);
        if (el) observer.observe(el);
      });
    }, 80);
    return () => {
      clearTimeout(timer);
      observer.disconnect();
    };
  }, [headings, content]);

  return (
    <div className="flex h-full overflow-hidden">
      <ScrollArea className="flex-1 min-w-0">
        <article className="prose prose-zinc dark:prose-invert max-w-4xl mx-auto px-8 py-6">
          <Markdown source={content} onRelativeLink={onRelativeLink} />
        </article>
      </ScrollArea>
      {headings.length > 1 && (
        <aside className="w-60 shrink-0 hidden xl:block border-l border-zinc-200 dark:border-zinc-800">
          <ScrollArea className="h-full">
            <nav className="p-4 pt-6">
              <p className="text-xs font-semibold text-zinc-400 dark:text-zinc-500 uppercase tracking-wider mb-3 px-1">{tocTitle}</p>
              <ul className="space-y-0.5 list-none p-0 m-0">
                {headings.map((h, i) => (
                  <li key={i} className="p-0 m-0">
                    <a
                      href={`#${h.id}`}
                      className={cn(
                        'block text-sm py-0.5 px-1 rounded truncate transition-colors no-underline',
                        h.level === 1 && 'pl-1',
                        h.level === 2 && 'pl-3',
                        h.level === 3 && 'pl-5 text-xs',
                        activeId === h.id
                          ? 'text-zinc-900 dark:text-zinc-100 font-medium'
                          : 'text-zinc-400 dark:text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300',
                      )}
                    >
                      {h.text}
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
          </ScrollArea>
        </aside>
      )}
    </div>
  );
}
