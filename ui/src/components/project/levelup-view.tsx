'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { CheckCircle2, Circle, ExternalLink, FileText, ShieldAlert, ShieldCheck } from 'lucide-react';
import { Breadcrumbs } from '@/components/breadcrumbs';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ProgressBar, StatusBadge } from '@/components/stage-badge';
import { StageControl } from './stage-control';
import { ProjectNav } from './project-nav';
import { useLocale } from '@/components/locale-provider';
import { cn } from '@/lib/utils';
import type { ChecklistItem, ProjectDetail } from '@/lib/types';

function ChecklistRow({ item, projectId, docPath }: { item: ChecklistItem; projectId: string; docPath?: string }) {
  const { t } = useLocale();
  return (
    <li className="flex items-center gap-2 py-1 text-sm">
      {item.done ? <CheckCircle2 className="size-4 text-green-600 dark:text-green-400 shrink-0" /> : <Circle className="size-4 text-zinc-300 dark:text-zinc-600 shrink-0" />}
      {item.done && docPath ? (
        <Link href={`/projects/${projectId}/docs?doc=${encodeURIComponent(docPath)}`} className="hover:underline font-mono text-[13px]">
          {item.label}
        </Link>
      ) : (
        <span className={cn('font-mono text-[13px]', !item.done && 'text-zinc-400')}>{item.label}</span>
      )}
      {item.detail && <span className="text-xs text-zinc-500 ml-auto whitespace-nowrap">{item.detail}</span>}
      {!item.done && !item.detail && <span className="text-xs text-zinc-400 ml-auto">{t('common.missing')}</span>}
    </li>
  );
}

export function LevelUpView({ project }: { project: ProjectDetail }) {
  const { t } = useLocale();
  const router = useRouter();
  const lu = project.levelup;
  const [done, setDone] = useState<Set<string>>(new Set(project.state.stories_done ?? []));
  const [filter, setFilter] = useState<'all' | 'open' | 'done'>('all');
  const [busy, setBusy] = useState(false);

  async function persist(next: Set<string>) {
    setBusy(true);
    try {
      await fetch(`/api/projects/${project.id}/state`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ storiesDone: Array.from(next) }),
      });
      router.refresh();
    } finally {
      setBusy(false);
    }
  }
  function toggle(id: string) {
    const next = new Set(done);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setDone(next);
    void persist(next);
  }
  function setAll(epicIds: string[], value: boolean) {
    const next = new Set(done);
    for (const id of epicIds) {
      if (value) next.add(id);
      else next.delete(id);
    }
    setDone(next);
    void persist(next);
  }

  const total = lu.backlog?.total ?? 0;
  const doneCount = useMemo(() => (lu.backlog ? lu.backlog.epics.flatMap((e) => e.stories).filter((s) => done.has(s.id)).length : 0), [lu.backlog, done]);
  const sc = lu.specCoverage;
  const pr = lu.parityReport;

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: t('nav.projects'), href: '/projects' }, { label: project.name, href: `/projects/${project.id}` }, { label: t('project.levelup') }]} />
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">{t('levelup.title')}</h1>
          <p className="text-zinc-500 mt-1 text-sm">{project.name}</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-zinc-500">{t('stage.levelup_docs')}</span>
          <StatusBadge status={lu.docsStatus} manual={!!lu.docsOverride?.status} />
          <span className="text-xs text-zinc-500 ml-2">{t('stage.levelup_impl')}</span>
          <StatusBadge status={lu.implStatus} manual={!!lu.implOverride?.status} />
        </div>
      </div>
      <ProjectNav id={project.id} />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t('levelup.pack')}</CardTitle>
            <ProgressBar value={lu.docsProgress} stage="levelup_docs" className="mt-2" />
          </CardHeader>
          <CardContent>
            <ul>
              {lu.docs.map((d) => (
                <ChecklistRow key={d.key} item={d} projectId={project.id} docPath={d.file?.path} />
              ))}
            </ul>
            {lu.extraDocs.length > 0 && (
              <div className="mt-3 pt-2 border-t">
                <p className="text-xs text-zinc-500 mb-1">{t('clone.extraDocs')}</p>
                <ul className="space-y-0.5">
                  {lu.extraDocs.map((f) => (
                    <li key={f.path} className="text-xs flex items-center gap-1.5">
                      <FileText className="size-3 text-zinc-400" />
                      <Link href={`/projects/${project.id}/docs?doc=${encodeURIComponent(f.path)}`} className="font-mono hover:underline">
                        {f.path.replace('levelup/', '')}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              {sc ? sc.gate === 'PASS' ? <ShieldCheck className="size-4 text-green-600" /> : <ShieldAlert className="size-4 text-red-600" /> : null}
              {t('levelup.gate')}
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm space-y-2">
            {!sc ? (
              <p className="text-zinc-500">{t('levelup.gate.none')}</p>
            ) : (
              <>
                <div className="flex items-center gap-2">
                  <Badge className={sc.gate === 'PASS' ? 'bg-green-600 text-white' : 'bg-red-600 text-white'}>{sc.gate}</Badge>
                  {sc.strict_acceptance && <Badge variant="outline">--strict-acceptance</Badge>}
                  <span className="text-xs text-zinc-500 ml-auto">{sc.coverage_pct.toFixed(1)}%</span>
                </div>
                <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                  <dt className="text-zinc-500">{t('levelup.requirements')}</dt>
                  <dd className="tabular-nums">
                    {sc.requirements_covered}/{sc.requirements_total} {t('levelup.covered')}
                  </dd>
                  <dt className="text-zinc-500">{t('levelup.stories')}</dt>
                  <dd className="tabular-nums">{sc.stories_total}</dd>
                  <dt className="text-zinc-500">{t('levelup.orphans')}</dt>
                  <dd className={cn('tabular-nums', sc.orphan_stories > 0 && 'text-red-600')}>{sc.orphan_stories}</dd>
                  <dt className="text-zinc-500">{t('levelup.nonAtomic')}</dt>
                  <dd className={cn('tabular-nums', sc.non_atomic_stories > 0 && 'text-red-600')}>{sc.non_atomic_stories}</dd>
                  <dt className="text-zinc-500">{t('levelup.unverifiable')}</dt>
                  <dd className={cn('tabular-nums', sc.requirements_missing_acceptance > 0 && 'text-red-600')}>{sc.requirements_missing_acceptance}</dd>
                </dl>
                <Link href={`/projects/${project.id}/docs?doc=${encodeURIComponent('levelup/spec-coverage.md')}`} className="text-xs inline-flex items-center gap-1 text-blue-600 dark:text-blue-400 hover:underline">
                  spec-coverage.md <ExternalLink className="size-3" />
                </Link>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t('levelup.parity')}</CardTitle>
          </CardHeader>
          <CardContent className="text-sm space-y-2">
            {!pr ? (
              <p className="text-zinc-500">{t('levelup.parity.none')}</p>
            ) : (
              <>
                <div className="flex items-center gap-2">
                  <span className="text-2xl font-bold tabular-nums">{pr.column_coverage_pct.toFixed(1)}%</span>
                  <span className="text-xs text-zinc-500">{t('levelup.parity.coverage')}</span>
                </div>
                <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                  <dt className="text-zinc-500">{t('levelup.parity.orphanTables')}</dt>
                  <dd className={cn('tabular-nums', pr.tables_orphaned > 0 && 'text-amber-600')}>
                    {pr.tables_orphaned}/{pr.tables_total}
                  </dd>
                  <dt className="text-zinc-500">{t('levelup.parity.orphanColumns')}</dt>
                  <dd className={cn('tabular-nums', pr.columns_orphaned_high_confidence > 0 && 'text-amber-600')}>
                    {pr.columns_orphaned_high_confidence}/{pr.columns_considered}
                  </dd>
                </dl>
                {pr.app_dir && <p className="text-[11px] text-zinc-400 font-mono break-all">{pr.app_dir}</p>}
                <Link href={`/projects/${project.id}/docs?doc=${encodeURIComponent('levelup/parity-report.md')}`} className="text-xs inline-flex items-center gap-1 text-blue-600 dark:text-blue-400 hover:underline">
                  parity-report.md <ExternalLink className="size-3" />
                </Link>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      <StageControl projectId={project.id} stage="levelup_docs" derived={lu.docsDerivedStatus} override={lu.docsOverride} />

      {/* `#implementation` is the anchor the dashboard's "Level-up · implementation" cells point to. */}
      <Card id="implementation" className="scroll-mt-4">
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <CardTitle className="text-base">{t('levelup.impl')}</CardTitle>
              <p className="text-xs text-zinc-500 mt-1">{t('levelup.implHint')}</p>
            </div>
            {lu.backlog && (
              <div className="flex items-center gap-3">
                <span className="text-sm tabular-nums">
                  <span className="font-semibold">{doneCount}</span>/{total}
                </span>
                <div className="flex rounded-md border overflow-hidden text-xs">
                  {(['all', 'open', 'done'] as const).map((f) => (
                    <button key={f} onClick={() => setFilter(f)} className={cn('px-2 py-1', filter === f ? 'bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900' : 'text-zinc-500')}>
                      {t(`levelup.filter.${f}`)}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
          {lu.backlog && <ProgressBar value={total ? doneCount / total : 0} stage="levelup_impl" className="mt-3" />}
        </CardHeader>
        <CardContent>
          {!lu.backlog ? (
            <p className="text-sm text-zinc-500">{t('levelup.noBacklog')}</p>
          ) : (
            <div className="space-y-5">
              {lu.backlog.epics.map((epic) => {
                const ids = epic.stories.map((s) => s.id);
                const epicDone = ids.filter((id) => done.has(id)).length;
                const visible = epic.stories.filter((s) => (filter === 'all' ? true : filter === 'done' ? done.has(s.id) : !done.has(s.id)));
                if (visible.length === 0) return null;
                return (
                  <div key={epic.title}>
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <h3 className="text-sm font-semibold">
                        {epic.title} <span className="text-zinc-400 font-normal tabular-nums">({epicDone}/{ids.length})</span>
                      </h3>
                      <div className="flex gap-1">
                        <Button variant="ghost" size="xs" disabled={busy} onClick={() => setAll(ids, true)}>
                          {t('levelup.markAll')}
                        </Button>
                        <Button variant="ghost" size="xs" disabled={busy} onClick={() => setAll(ids, false)}>
                          {t('levelup.unmarkAll')}
                        </Button>
                      </div>
                    </div>
                    <ul className="divide-y divide-zinc-100 dark:divide-zinc-800 rounded-lg border">
                      {visible.map((s) => {
                        const isDone = done.has(s.id);
                        return (
                          <li key={s.id} className={cn('flex items-start gap-3 px-3 py-2 text-sm', isDone && 'bg-green-50/50 dark:bg-green-900/10')}>
                            <input type="checkbox" className="mt-1 size-4 accent-green-600 cursor-pointer" checked={isDone} onChange={() => toggle(s.id)} aria-label={s.id} />
                            <div className="min-w-0 flex-1">
                              <div className="flex flex-wrap items-center gap-1.5">
                                <span className="font-mono text-xs font-semibold">{s.id}</span>
                                {s.size && <Badge variant="outline" className="text-[10px] px-1 py-0">{s.size}</Badge>}
                                {s.infra && <Badge variant="secondary" className="text-[10px] px-1 py-0">{t('levelup.infra')}</Badge>}
                                {s.nonAtomic && <Badge className="text-[10px] px-1 py-0 bg-red-600 text-white">{t('levelup.nonAtomic')}</Badge>}
                                {s.cites.length > 0 && (
                                  <span className="text-[10px] text-zinc-400">
                                    {t('levelup.cites')}: {s.cites.slice(0, 6).join(', ')}
                                    {s.cites.length > 6 ? '…' : ''}
                                  </span>
                                )}
                              </div>
                              <p className={cn('text-[13px] leading-snug mt-0.5 text-zinc-700 dark:text-zinc-300', isDone && 'line-through text-zinc-400 dark:text-zinc-500')}>{s.text}</p>
                            </div>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      <StageControl projectId={project.id} stage="levelup_impl" derived={lu.implDerivedStatus} override={lu.implOverride} />
    </div>
  );
}
