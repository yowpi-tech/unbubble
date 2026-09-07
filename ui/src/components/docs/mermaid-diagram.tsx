'use client';

import { useEffect, useId, useState } from 'react';
import { useTheme } from 'next-themes';

/** Same component as BubbleDocs, plus dark-theme awareness. */
export function MermaidDiagram({ chart }: { chart: string }) {
  const [svg, setSvg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { resolvedTheme } = useTheme();
  const uniqueId = useId().replace(/:/g, '-');

  useEffect(() => {
    let cancelled = false;
    async function render() {
      try {
        const mermaid = (await import('mermaid')).default;
        mermaid.initialize({
          startOnLoad: false,
          theme: resolvedTheme === 'dark' ? 'dark' : 'default',
          securityLevel: 'strict',
          fontFamily: 'inherit',
        });
        const { svg: out } = await mermaid.render(`mermaid-${uniqueId}-${resolvedTheme ?? 'l'}`, chart);
        if (!cancelled) {
          setSvg(out);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Mermaid error');
          setSvg(null);
        }
      }
    }
    render();
    return () => {
      cancelled = true;
    };
  }, [chart, uniqueId, resolvedTheme]);

  if (error) {
    return (
      <div className="my-4 rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 p-4">
        <p className="text-sm text-red-600 dark:text-red-400 mb-2 font-medium">Mermaid</p>
        <pre className="text-xs text-red-500 dark:text-red-300 whitespace-pre-wrap">{chart}</pre>
      </div>
    );
  }
  if (!svg) {
    return (
      <div className="my-4 rounded-lg border bg-zinc-50 dark:bg-zinc-900 p-8 flex items-center justify-center">
        <div className="h-5 w-5 border-2 border-zinc-300 dark:border-zinc-600 border-t-zinc-600 dark:border-t-zinc-300 rounded-full animate-spin" />
      </div>
    );
  }
  return (
    <div
      className="my-4 rounded-lg border bg-white dark:bg-zinc-900 p-4 overflow-x-auto [&_svg]:mx-auto [&_svg]:max-w-full"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
