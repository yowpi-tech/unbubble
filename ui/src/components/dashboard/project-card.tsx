'use client';

import Link from 'next/link';
import { ArrowRight, Globe } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ProgressBar, StatusIcon, stageHref } from '@/components/stage-badge';
import { formatDate, useLocale } from '@/components/locale-provider';
import type { ProjectSummary, StageKey } from '@/lib/types';

const STAGES: StageKey[] = ['audit', 'clone', 'levelup_docs', 'levelup_impl'];

export function ProjectCard({ project }: { project: ProjectSummary }) {
  const { t, locale } = useLocale();
  const c = project.counts ?? {};
  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardHeader className="flex flex-row items-start justify-between space-y-0">
        <div className="space-y-1 min-w-0 flex-1">
          <CardTitle className="text-lg">
            <Link href={`/projects/${project.id}`} className="hover:underline">
              {project.name}
            </Link>
          </CardTitle>
          <p className="text-xs text-zinc-500 font-mono truncate">{project.id}</p>
        </div>
        {project.domain && (
          <Badge variant="secondary" className="shrink-0 gap-1">
            <Globe className="size-3" />
            {project.domain}
          </Badge>
        )}
      </CardHeader>
      <CardContent>
        <div className="space-y-1 mb-4 -mx-2">
          {STAGES.map((k) => {
            const s = project.stages[k];
            return (
              <Link
                key={k}
                href={stageHref(project.id, k)}
                title={`${t(`stage.${k}`)} · ${project.name}`}
                className="grid grid-cols-[1.25rem_9.5rem_1fr_auto] items-center gap-2 rounded-md px-2 py-1 text-sm transition-colors hover:bg-zinc-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring dark:hover:bg-zinc-800/70"
              >
                <StatusIcon status={s.status} />
                <span className="truncate text-zinc-700 dark:text-zinc-300">{t(`stage.${k}`)}</span>
                <ProgressBar value={s.progress} stage={k} />
                <span className="text-xs text-zinc-500 tabular-nums whitespace-nowrap">{s.detail}</span>
              </Link>
            );
          })}
        </div>
        <div className="flex flex-wrap gap-2 mb-3">
          {c.pages !== undefined && <Badge variant="outline">{c.pages} {t('projects.pages')}</Badge>}
          {c.data_types_active !== undefined && <Badge variant="outline">{c.data_types_active} {t('projects.tables')}</Badge>}
          {c.backend_workflows !== undefined && <Badge variant="outline">{c.backend_workflows} {t('projects.workflows')}</Badge>}
          {c.plugins_installed !== undefined && <Badge variant="outline">{c.plugins_installed} {t('projects.plugins')}</Badge>}
        </div>
        <div className="flex items-center justify-between">
          <p className="text-xs text-zinc-400">
            {t('projects.updated')} {formatDate(project.updatedAt, locale, true)}
          </p>
          <Link href={`/projects/${project.id}`} className="text-xs font-medium inline-flex items-center gap-1 text-zinc-600 dark:text-zinc-300 hover:underline">
            {t('common.nextStep')}: {t(`stage.${project.nextStep}`)}
            <ArrowRight className="size-3" />
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}
