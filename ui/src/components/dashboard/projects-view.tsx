'use client';

import { Breadcrumbs } from '@/components/breadcrumbs';
import { ProjectCard } from './project-card';
import { Card, CardContent } from '@/components/ui/card';
import { useT } from '@/components/locale-provider';
import type { ProjectSummary } from '@/lib/types';

export function ProjectsView({ projects, root }: { projects: ProjectSummary[]; root: string }) {
  const t = useT();
  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: t('nav.projects') }]} />
      <div>
        <h1 className="text-2xl font-bold">{t('projects.title')}</h1>
        <p className="text-zinc-500 mt-1">
          {t('projects.subtitle')} <span className="font-mono text-sm">{root}</span>
        </p>
      </div>
      {projects.length === 0 ? (
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-zinc-600 dark:text-zinc-300">{t('projects.empty')}</p>
            <p className="text-xs text-zinc-500 mt-1">{t('projects.emptyHint')}</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
          {projects.map((p) => (
            <ProjectCard key={p.id} project={p} />
          ))}
        </div>
      )}
    </div>
  );
}
