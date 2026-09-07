'use client';

import Link from 'next/link';
import { CheckCircle2, Circle, KeyRound, ShieldAlert } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ProgressBar, StatusBadge } from '@/components/stage-badge';
import { StageControl } from './stage-control';
import { useLocale } from '@/components/locale-provider';
import { cn } from '@/lib/utils';
import type { ChecklistItem, ProjectDetail } from '@/lib/types';
import type { TKey } from '@/lib/i18n';

function Row({ item, projectId }: { item: ChecklistItem; projectId: string }) {
  const { t } = useLocale();
  const viewable = item.file && /\.md$/i.test(item.file.path);
  return (
    <li className="flex items-center gap-2 py-1 text-sm">
      {item.done ? <CheckCircle2 className="size-4 text-green-600 dark:text-green-400 shrink-0" /> : <Circle className="size-4 text-zinc-300 dark:text-zinc-600 shrink-0" />}
      {viewable ? (
        <Link href={`/projects/${projectId}/docs?doc=${encodeURIComponent(item.file!.path)}`} className="hover:underline font-mono text-[13px]">
          {item.label}
        </Link>
      ) : (
        <span className={cn('font-mono text-[13px]', !item.done && 'text-zinc-400')}>{item.label}</span>
      )}
      <span className="text-xs text-zinc-500 ml-auto whitespace-nowrap">{item.detail ?? (!item.done ? t('common.missing') : '')}</span>
    </li>
  );
}

/** Clone stage summary, shown on top of the docs page. */
export function ClonePanel({ project }: { project: ProjectDetail }) {
  const { t } = useLocale();
  const c = project.clone;
  const flags = c.summary?.security_flags ?? {};
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">{t('clone.title')}</h2>
        <StatusBadge status={c.status} manual={!!c.override?.status} />
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t('clone.checklist')}</CardTitle>
            <ProgressBar value={c.progress} stage="clone" className="mt-2" />
          </CardHeader>
          <CardContent>
            <ul>
              {c.items.map((i) => (
                <Row key={i.key} item={i} projectId={project.id} />
              ))}
            </ul>
            {c.matrix && (
              <p className="mt-2 text-xs text-zinc-500">
                {t('clone.matrix')}: {c.matrix.rows} {t('clone.matrix.rows')} ·{' '}
                {c.matrix.blank === 0 ? <span className="text-green-700 dark:text-green-400">{t('clone.matrix.ok')}</span> : <span className="text-red-600">{c.matrix.blank} {t('clone.matrix.blank')}</span>}
                {' · '}
                {Object.entries(c.matrix.byDisposition)
                  .map(([k, v]) => `${k} ${v}`)
                  .join(' · ')}
              </p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t('clone.docs')}</CardTitle>
          </CardHeader>
          <CardContent>
            <ul>
              {c.docs.map((d) => (
                <Row key={d.key} item={d} projectId={project.id} />
              ))}
            </ul>
            {c.extraDocs.length > 0 && (
              <p className="mt-2 text-xs text-zinc-500">
                {t('clone.extraDocs')}: {c.extraDocs.map((f) => f.path.replace('docs/', '')).join(', ')}
              </p>
            )}
          </CardContent>
        </Card>
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t('clone.openQuestions')}</CardTitle>
            </CardHeader>
            <CardContent className="text-sm space-y-1">
              {c.openQuestions ? (
                <>
                  <p>
                    <span className="font-semibold tabular-nums">{c.openQuestions.blocking}</span> {t('clone.blocking')} ·{' '}
                    <span className="font-semibold tabular-nums">{c.openQuestions.nonBlocking}</span> {t('clone.nonBlocking')}
                  </p>
                  <p className="text-xs text-zinc-500">
                    {c.openQuestions.hasDecisions ? `${c.openQuestions.decisionDates.length} ${t('clone.decisions')}: ${c.openQuestions.decisionDates.join(', ')}` : t('clone.noDecisions')}
                  </p>
                </>
              ) : (
                <p className="text-zinc-400 text-xs">{t('common.missing')}</p>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <KeyRound className="size-4" />
                {t('clone.secrets')}
              </CardTitle>
            </CardHeader>
            <CardContent className="text-sm space-y-1">
              <p>
                .env: <Badge variant={c.secrets?.envPresent ? 'default' : 'secondary'}>{c.secrets?.envPresent ? t('common.present') : t('common.missing')}</Badge>{' '}
                ENV-KEYS.md: <Badge variant={c.secrets?.keysDoc ? 'default' : 'secondary'}>{c.secrets?.keysDoc ? t('common.present') : t('common.missing')}</Badge>
                {c.secrets?.varCount !== undefined && <span className="text-xs text-zinc-500 ml-2">{c.secrets.varCount} vars</span>}
              </p>
              <p className="text-xs text-zinc-500">{t('clone.secretsHint')}</p>
            </CardContent>
          </Card>
          {Object.values(flags).some((v) => v.length > 0) && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <ShieldAlert className="size-4 text-amber-600" />
                  {t('clone.security')}
                </CardTitle>
              </CardHeader>
              <CardContent className="text-xs space-y-1">
                {Object.entries(flags).map(([k, v]) =>
                  v.length ? (
                    <p key={k}>
                      <span className="font-semibold tabular-nums">{v.length}</span> {t(`clone.sec.${k}` as TKey) ?? k}: <span className="font-mono text-zinc-500">{v.slice(0, 8).join(', ')}{v.length > 8 ? '…' : ''}</span>
                    </p>
                  ) : null,
                )}
              </CardContent>
            </Card>
          )}
        </div>
      </div>
      <StageControl projectId={project.id} stage="clone" derived={c.derivedStatus} override={c.override} />
    </div>
  );
}
