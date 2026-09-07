import { DashboardView } from '@/components/dashboard/dashboard-view';
import { detectInstalls } from '@/lib/install';
import { listProjects } from '@/lib/scan/project';

export const dynamic = 'force-dynamic';

export default function DashboardPage() {
  const projects = listProjects();
  const setup = detectInstalls();
  return <DashboardView projects={projects} hosts={setup.hosts} />;
}
