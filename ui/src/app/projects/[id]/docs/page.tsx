import { Suspense } from 'react';
import { notFound } from 'next/navigation';
import { DocsPageView } from '@/components/docs/docs-page-view';
import { listDocs } from '@/lib/docs';
import { getProject } from '@/lib/scan/project';

export const dynamic = 'force-dynamic';

export default async function DocsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const project = getProject(id);
  if (!project) notFound();
  const docs = listDocs(project.dir);
  return (
    <Suspense fallback={null}>
      <DocsPageView project={project} docs={docs} />
    </Suspense>
  );
}
