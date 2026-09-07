import { notFound } from 'next/navigation';
import { LevelUpView } from '@/components/project/levelup-view';
import { getProject } from '@/lib/scan/project';

export const dynamic = 'force-dynamic';

export default async function LevelUpPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const project = getProject(id);
  if (!project) notFound();
  return <LevelUpView project={project} />;
}
