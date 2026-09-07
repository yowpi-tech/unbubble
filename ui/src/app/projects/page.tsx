import { ProjectsView } from '@/components/dashboard/projects-view';
import { listProjects } from '@/lib/scan/project';
import { prettyPath, projectsDir } from '@/lib/paths';

export const dynamic = 'force-dynamic';

export default function ProjectsPage() {
  return <ProjectsView projects={listProjects()} root={prettyPath(projectsDir())} />;
}
