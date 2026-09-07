'use client';

import { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { Breadcrumbs } from '@/components/breadcrumbs';
import { Button } from '@/components/ui/button';
import { ClonePanel } from '@/components/project/clone-panel';
import { ProjectNav } from '@/components/project/project-nav';
import { DocsView } from './docs-view';
import { useLocale } from '@/components/locale-provider';
import type { DocEntry, ProjectDetail } from '@/lib/types';

export function DocsPageView({ project, docs }: { project: ProjectDetail; docs: DocEntry[] }) {
  const { t } = useLocale();
  const [showPanel, setShowPanel] = useState(project.clone.status !== 'done');
  return (
    <div className="space-y-4">
      <Breadcrumbs items={[{ label: t('nav.projects'), href: '/projects' }, { label: project.name, href: `/projects/${project.id}` }, { label: t('project.docs') }]} />
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">{t('docs.title')}</h1>
          <p className="text-zinc-500 mt-1 text-sm">{project.name}</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => setShowPanel((v) => !v)}>
          {showPanel ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
          {t('clone.title')}
        </Button>
      </div>
      <ProjectNav id={project.id} />
      {showPanel && <ClonePanel project={project} />}
      <DocsView projectId={project.id} docs={docs} />
    </div>
  );
}
