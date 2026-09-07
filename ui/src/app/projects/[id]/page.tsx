import { notFound } from 'next/navigation';
import { ProjectOverview } from '@/components/project/project-overview';
import { getProject } from '@/lib/scan/project';

export const dynamic = 'force-dynamic';

export default async function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const project = getProject(id);
  if (!project) notFound();
  return <ProjectOverview project={project} />;
}
