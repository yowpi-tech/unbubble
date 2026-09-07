import { notFound } from 'next/navigation';
import { AuditView } from '@/components/project/audit-view';
import { getProject } from '@/lib/scan/project';

export const dynamic = 'force-dynamic';

export default async function AuditPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const project = getProject(id);
  if (!project) notFound();
  return <AuditView project={project} />;
}
