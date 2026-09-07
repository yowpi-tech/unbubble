'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { BookOpen, ChevronRight, Database, ExternalLink, FileJson, FileText, Globe, KeyRound, Rocket, Search, SearchCheck, Shield } from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { DocViewer } from './doc-viewer';
import { useT } from '@/components/locale-provider';
import { cn } from '@/lib/utils';
import type { DocEntry } from '@/lib/types';
import type { TKey } from '@/lib/i18n';

const GROUP_ORDER = ['clone-docs', 'clone-prd', 'levelup', 'audit', 'secrets', 'inventory', 'other'];
const GROUP_ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  'clone-docs': BookOpen,
  'clone-prd': Shield,
  levelup: Rocket,
  audit: SearchCheck,
  secrets: KeyRound,
  inventory: Database,
  other: FileText,
};

function dirname(p: string): string {
  const i = p.lastIndexOf('/');
  return i === -1 ? '' : p.slice(0, i);
}
function resolveRelative(from: string, href: string): string {
  const clean = href.split('#')[0].split('?')[0];
  const parts = (dirname(from) ? dirname(from) + '/' : '').split('/').filter(Boolean);
  for (const seg of clean.split('/')) {
    if (seg === '' || seg === '.') continue;
    if (seg === '..') parts.pop();
    else parts.push(seg);
  }
  return parts.join('/');
}

export function DocsView({ projectId, docs }: { projectId: string; docs: DocEntry[] }) {
  const t = useT();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [search, setSearch] = useState('');
  // Loaded text is keyed by path: a doc is "loading" while the loaded path differs from the selection.
  const [loaded, setLoaded] = useState<{ path: string; text: string } | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({ 'clone-docs': true, 'clone-prd': true, levelup: true });

  const selectedPath = searchParams.get('doc') ?? docs.find((d) => d.group === 'clone-docs')?.path ?? docs[0]?.path ?? null;
  const selected = useMemo(() => docs.find((d) => d.path === selectedPath) ?? null, [docs, selectedPath]);

  const select = useCallback(
    (path: string) => {
      const params = new URLSearchParams(searchParams.toString());
      params.set('doc', path);
      router.replace(`${pathname}?${params.toString()}`, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  useEffect(() => {
    if (!selected || selected.kind === 'html') return;
    let cancelled = false;
    const path = selected.path;
    const kind = selected.kind;
    fetch(`/api/projects/${projectId}/file?path=${encodeURIComponent(path)}`)
      .then((r) => (r.ok ? r.text() : Promise.reject(new Error(String(r.status)))))
      .then((txt) => {
        if (cancelled) return;
        let text = txt;
        if (kind === 'json') {
          try {
            text = '```json\n' + JSON.stringify(JSON.parse(txt), null, 2) + '\n```';
          } catch {
            text = '```\n' + txt + '\n```';
          }
        } else if (kind === 'text') text = '```\n' + txt + '\n```';
        setLoaded({ path, text });
      })
      .catch(() => {
        if (!cancelled) setLoaded({ path, text: `_${t('common.notFound')}_` });
      });
    return () => {
      cancelled = true;
    };
  }, [selected, projectId, t]);

  const content = selected && loaded && loaded.path === selected.path ? loaded.text : null;
  const loading = !!selected && selected.kind !== 'html' && content === null;

  const groups = useMemo(() => {
    const q = search.trim().toLowerCase();
    const list = q ? docs.filter((d) => d.title.toLowerCase().includes(q) || d.path.toLowerCase().includes(q)) : docs;
    const map = new Map<string, DocEntry[]>();
    for (const d of list) {
      if (!map.has(d.group)) map.set(d.group, []);
      map.get(d.group)!.push(d);
    }
    return GROUP_ORDER.filter((g) => map.has(g)).map((g) => ({ key: g, docs: map.get(g)! }));
  }, [docs, search]);

  const onRelativeLink = useCallback(
    (href: string) => {
      if (!selected) return false;
      const target = resolveRelative(selected.path, href);
      const hit = docs.find((d) => d.path === target || d.path === `docs/${target}` || d.path === `levelup/${target}`);
      if (!hit) return false;
      select(hit.path);
      return true;
    },
    [docs, select, selected],
  );

  const fileUrl = selected ? `/api/projects/${projectId}/file?path=${encodeURIComponent(selected.path)}` : '';

  return (
    <div className="flex flex-col h-[calc(100vh-11rem)]">
      <div className="flex flex-1 gap-4 overflow-hidden">
        <div className="w-72 shrink-0 rounded-lg border bg-white dark:bg-zinc-950 flex flex-col overflow-hidden">
          <div className="p-2 border-b">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-zinc-400 pointer-events-none" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={t('docs.search')}
                className="pl-8 h-8 text-sm bg-zinc-50 dark:bg-zinc-900 border-0 focus-visible:ring-1"
              />
            </div>
          </div>
          <ScrollArea className="flex-1 overflow-hidden">
            <div className="py-1">
              {groups.length === 0 && <p className="px-2 py-4 text-xs text-zinc-400 text-center">{t('docs.empty')}</p>}
              {groups.map((g) => {
                const Icon = GROUP_ICON[g.key] ?? FileText;
                // A group stays open while it holds the selected doc, without an effect writing state.
                const open = search.trim() ? true : (expanded[g.key] ?? selected?.group === g.key);
                return (
                  <div key={g.key}>
                    <button
                      onClick={() => setExpanded((e) => ({ ...e, [g.key]: !open }))}
                      className="w-full flex items-center gap-2 px-2 pr-2 py-2 text-xs font-semibold text-zinc-500 dark:text-zinc-400 hover:bg-zinc-50 dark:hover:bg-zinc-900 transition-colors tracking-wide"
                    >
                      <ChevronRight className={cn('h-3.5 w-3.5 shrink-0 transition-transform duration-200', open && 'rotate-90')} />
                      <Icon className="h-3.5 w-3.5 shrink-0" />
                      <span className="truncate text-left">{t(`docs.group.${g.key}` as TKey)}</span>
                      <span className="ml-auto shrink-0 text-[10px] font-medium bg-zinc-100 dark:bg-zinc-800 text-zinc-400 rounded-full px-1.5 py-0.5 tabular-nums">
                        {g.docs.length}
                      </span>
                    </button>
                    {open &&
                      g.docs.map((d) => {
                        const isSel = selected?.path === d.path;
                        const KindIcon = d.kind === 'html' ? Globe : d.kind === 'json' ? FileJson : FileText;
                        return (
                          <button
                            key={d.path}
                            onClick={() => select(d.path)}
                            title={d.path}
                            className={cn(
                              'w-full flex items-center gap-1.5 pl-6 pr-2 py-1.5 text-sm transition-colors',
                              isSel
                                ? 'bg-zinc-100 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-50 font-medium'
                                : 'text-zinc-600 dark:text-zinc-400 hover:bg-zinc-50 dark:hover:bg-zinc-900',
                            )}
                          >
                            <KindIcon className="h-3.5 w-3.5 shrink-0 text-zinc-400" />
                            <span className="truncate text-left">{d.title}</span>
                          </button>
                        );
                      })}
                  </div>
                );
              })}
            </div>
          </ScrollArea>
        </div>

        <div className="flex-1 min-w-0 border rounded-lg bg-white dark:bg-zinc-950 overflow-hidden flex flex-col">
          {selected ? (
            <>
              <div className="flex items-center gap-2 px-4 py-2 border-b text-xs text-zinc-500">
                <span className="font-mono truncate">{selected.path}</span>
                <span className="ml-auto flex items-center gap-1 shrink-0">
                  <Button variant="ghost" size="xs" nativeButton={false} render={<a href={fileUrl} target="_blank" rel="noreferrer" />}>
                    <ExternalLink className="size-3.5" />
                    {t('common.openNewTab')}
                  </Button>
                </span>
              </div>
              {selected.kind === 'html' ? (
                <iframe title={selected.title} src={fileUrl} className="flex-1 w-full bg-white" />
              ) : loading || content === null ? (
                <div className="flex-1 flex items-center justify-center text-zinc-400 text-sm">{t('common.loading')}</div>
              ) : (
                <div className="flex-1 min-h-0">
                  <DocViewer content={content} tocTitle={t('docs.toc')} onRelativeLink={onRelativeLink} />
                </div>
              )}
            </>
          ) : (
            <div className="flex items-center justify-center h-full text-zinc-400 text-sm">{t('docs.select')}</div>
          )}
        </div>
      </div>
    </div>
  );
}
