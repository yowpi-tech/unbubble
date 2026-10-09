'use client';

import { useState } from 'react';
import { ExternalLink } from 'lucide-react';
import { Breadcrumbs } from '@/components/breadcrumbs';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { StatusBadge } from '@/components/stage-badge';
import { StageControl } from './stage-control';
import { ProjectNav } from './project-nav';
import { useLocale } from '@/components/locale-provider';
import { cn } from '@/lib/utils';
import type { AuditRound, ProjectDetail } from '@/lib/types';
import type { TKey } from '@/lib/i18n';

const CONF_CLS = {
  high: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
  review: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
  destructive: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
};

export function AuditView({ project }: { project: ProjectDetail }) {
  const { t } = useLocale();
  const a = project.audit;
  const rounds = a.rounds;
  const [selected, setSelected] = useState<AuditRound | undefined>(a.latest);
  const [lang, setLang] = useState<'pt' | 'en'>('pt');

  const reportPath = selected ? (lang === 'en' && selected.htmlEn ? selected.htmlEn : selected.html ?? selected.htmlEn) : undefined;
  const reportUrl = reportPath ? `/api/projects/${project.id}/file?path=${encodeURIComponent(reportPath)}` : undefined;
  const maxFindings = Math.max(1, ...rounds.map((r) => r.totalFindings ?? 0));

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: t('nav.projects'), href: '/projects' }, { label: project.name, href: `/projects/${project.id}` }, { label: t('project.audit') }]} />
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">{t('audit.title')}</h1>
          <p className="text-zinc-500 mt-1 text-sm">{project.name}</p>
        </div>
        <StatusBadge status={a.status} manual={!!a.override?.status} />
      </div>
      <ProjectNav id={project.id} />

      {rounds.length === 0 ? (
        <Card>
          <CardContent className="pt-6 text-sm text-zinc-500">{t('audit.noRounds')}</CardContent>
        </Card>
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">{t('audit.trend')}</CardTitle>
              </CardHeader>
              <CardContent>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-zinc-500">
                      <th className="py-1 pr-2 font-medium">{t('audit.round')}</th>
                      <th className="py-1 pr-2 font-medium">{t('audit.date')}</th>
                      <th className="py-1 pr-2 font-medium w-1/2">{t('audit.findings')}</th>
                      <th className="py-1 font-medium">{t('audit.report')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rounds.map((r) => {
                      const n = r.totalFindings;
                      const isSel = selected === r;
                      return (
                        <tr
                          key={r.label + r.date}
                          className={cn('border-t border-zinc-100 dark:border-zinc-800 cursor-pointer', isSel && 'bg-zinc-50 dark:bg-zinc-900/60')}
                          onClick={() => setSelected(r)}
                        >
                          <td className="py-2 pr-2 font-medium">{r.label}</td>
                          <td className="py-2 pr-2 text-zinc-500 tabular-nums">{r.date}</td>
                          <td className="py-2 pr-2">
                            {n === null ? (
                              <span className="text-xs text-zinc-400">JSON {t('common.missing')}</span>
                            ) : (
                              <div className="flex items-center gap-2">
                                <div className="h-2 flex-1 rounded-full bg-zinc-100 dark:bg-zinc-800 overflow-hidden">
                                  <div className={cn('h-full rounded-full', n === 0 ? 'bg-green-500' : 'bg-amber-500')} style={{ width: `${Math.max(2, (n / maxFindings) * 100)}%` }} />
                                </div>
                                <span className="tabular-nums w-10 text-right">{n}</span>
                              </div>
                            )}
                          </td>
                          <td className="py-2">
                            {(r.html || r.htmlEn) && (
                              <a
                                href={`/api/projects/${project.id}/file?path=${encodeURIComponent(r.html ?? r.htmlEn ?? '')}`}
                                target="_blank"
                                rel="noreferrer"
                                className="text-xs inline-flex items-center gap-1 text-blue-600 dark:text-blue-400 hover:underline"
                                onClick={(e) => e.stopPropagation()}
                              >
                                HTML <ExternalLink className="size-3" />
                              </a>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                {a.latest && a.latest.totalFindings === 0 && (
                  <p className="mt-3 text-sm text-green-700 dark:text-green-400">{t('audit.clean')}</p>
                )}
                {a.latest && a.latest.totalFindings !== null && a.latest.totalFindings > 0 && (
                  <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-300">
                    <span className="font-semibold tabular-nums">{a.latest.totalFindings}</span> {t('audit.remaining')}
                  </p>
                )}
                {a.latest && a.latest.totalFindings !== null && a.latest.totalFindings > 0 && a.derivedStatus === 'done' && (
                  <p className="mt-2 text-sm text-green-700 dark:text-green-400">{t('audit.signedOff')}</p>
                )}
                {a.progressFile && (
                  <div className="mt-2 text-xs text-zinc-500 space-y-0.5">
                    <p>
                      {t('audit.tracker')}: <span className="font-mono">{a.progressFile.path.replace('audit/', '')}</span>
                      {a.progressFile.updated ? ` · ${a.progressFile.updated}` : ''} · {a.progressFile.deleted} {t('audit.deletedCount')}
                    </p>
                    {a.sectionsWithFindings > 0 && (
                      <p>
                        {t('audit.sections')}: <span className="font-semibold tabular-nums">{a.sectionsResolved}/{a.sectionsWithFindings}</span>
                        {a.progressFile.kept.length > 0 && (
                          <>
                            {' · '}
                            <span className="font-semibold tabular-nums">{a.progressFile.kept.length}</span> {t('audit.keptShort')}
                          </>
                        )}
                      </p>
                    )}
                  </div>
                )}
                {a.journal && (
                  <div className="mt-2 text-xs text-zinc-500 space-y-0.5">
                    <p>
                      {t('audit.journal')}: <span className="font-mono">{a.journal.path.replace('audit/', '')}</span> ·{' '}
                      <span className="font-semibold tabular-nums">{a.journal.applied}</span> {t('audit.journal.applied')}
                      {a.journal.verified > 0 && (
                        <>
                          {' · '}
                          <span className="tabular-nums">{a.journal.verified}</span> {t('audit.journal.verified')}
                        </>
                      )}
                      {a.journal.failed > 0 && (
                        <>
                          {' · '}
                          <span className="tabular-nums text-red-600 dark:text-red-400">{a.journal.failed}</span> {t('audit.journal.failed')}
                        </>
                      )}
                    </p>
                    {a.journal.pending > 0 && (
                      <p className="text-amber-700 dark:text-amber-400">
                        {t('audit.journal.pending', {
                          n: a.journal.pending,
                          branches: a.journal.versions.filter((v) => v.pending > 0).map((v) => v.appVersion).join(', '),
                        })}
                      </p>
                    )}
                  </div>
                )}
                <p className="mt-2 text-xs text-zinc-400">{t('audit.trackerHint')}</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">
                  {t('audit.byCategory')} {selected && <span className="text-zinc-400 font-normal">· {selected.label}</span>}
                </CardTitle>
              </CardHeader>
              <CardContent>
                {selected && selected.categories.length > 0 ? (
                  <ul className="space-y-1.5">
                    {selected.categories.map((c) => {
                      const signedOff = c.count > 0 && c.resolved;
                      return (
                        <li key={c.key} className="flex items-center justify-between gap-2 text-sm">
                          <span className={cn('flex items-center gap-1.5 min-w-0', c.count === 0 && 'text-zinc-400')}>
                            <span className="truncate">{t(`audit.cat.${c.key}` as TKey)}</span>
                            {signedOff && (
                              <span className="shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-medium bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300">
                                ✓ {t('audit.sectionDone')}
                                {c.kept.length > 0 ? ` · ${c.kept.length} ${t('audit.keptShort')}` : ''}
                              </span>
                            )}
                          </span>
                          <span className="flex items-center gap-2 shrink-0">
                            <span className={cn('rounded-full px-1.5 py-0.5 text-[10px] font-medium', CONF_CLS[c.confidence])}>{t(`audit.confidence.${c.confidence}` as TKey)}</span>
                            <span className={cn('tabular-nums w-8 text-right font-medium', c.count === 0 ? 'text-zinc-400' : 'text-zinc-900 dark:text-zinc-100')}>{c.count}</span>
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                ) : (
                  <p className="text-sm text-zinc-400">JSON {t('common.missing')}</p>
                )}
                {selected?.totals && (
                  <div className="mt-4 pt-3 border-t">
                    <p className="text-xs font-semibold text-zinc-500 mb-2">{t('audit.totals')}</p>
                    <div className="flex flex-wrap gap-1.5">
                      <Badge variant="outline">{selected.totals.pages} {t('projects.pages')}</Badge>
                      <Badge variant="outline">{selected.totals.reusables} reusables</Badge>
                      <Badge variant="outline">{selected.totals.backend} backend WFs</Badge>
                      <Badge variant="outline">{selected.totals.dataTables} {t('projects.tables')}</Badge>
                      <Badge variant="outline">{selected.totals.dataFields} fields</Badge>
                      <Badge variant="outline">{selected.totals.plugins} {t('projects.plugins')}</Badge>
                      <Badge variant="outline">{selected.totals.optionSets} option sets</Badge>
                      <Badge variant="outline">{selected.totals.apiCalls} API calls</Badge>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {a.progressFile && a.progressFile.kept.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">
                  {t('audit.kept')} <span className="text-zinc-400 font-normal tabular-nums">· {a.progressFile.kept.length}</span>
                </CardTitle>
                <p className="text-xs text-zinc-500">{t('audit.keptHint')}</p>
              </CardHeader>
              <CardContent>
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                  {(a.latest?.categories ?? [])
                    .filter((c) => c.kept.length > 0)
                    .map((c) => (
                      <div key={c.key}>
                        <p className="text-xs font-semibold text-zinc-600 dark:text-zinc-300 mb-1">
                          {t(`audit.cat.${c.key}` as TKey)} <span className="text-zinc-400 font-normal tabular-nums">({c.kept.length})</span>
                        </p>
                        <ul className="space-y-0.5">
                          {c.kept.map((k) => (
                            <li key={k.key} className="text-sm flex items-baseline gap-2 min-w-0">
                              <span className="truncate">{k.label || k.key}</span>
                              <span className="font-mono text-[11px] text-zinc-400 shrink-0">{k.key}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                </div>
              </CardContent>
            </Card>
          )}

          <StageControl projectId={project.id} stage="audit" derived={a.derivedStatus} override={a.override} />

          {reportUrl && (
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0">
                <CardTitle className="text-base">
                  {t('audit.embedded')} <span className="text-zinc-400 font-normal">· {selected?.label}</span>
                </CardTitle>
                <div className="flex items-center gap-2">
                  {selected?.html && selected?.htmlEn && (
                    <div className="flex rounded-md border overflow-hidden text-xs">
                      {(['pt', 'en'] as const).map((l) => (
                        <button key={l} onClick={() => setLang(l)} className={cn('px-2 py-1 uppercase', lang === l ? 'bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900' : 'text-zinc-500')}>
                          {l}
                        </button>
                      ))}
                    </div>
                  )}
                  <Button variant="outline" size="sm" nativeButton={false} render={<a href={reportUrl} target="_blank" rel="noreferrer" />}>
                    <ExternalLink className="size-3.5" />
                    {t('common.openNewTab')}
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="p-0 overflow-hidden rounded-b-xl">
                <iframe title="audit report" src={reportUrl} className="report-frame" />
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
