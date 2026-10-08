import { SetupView } from '@/components/setup/setup-view';
import { connectedMode } from '@/lib/connect';
import { detectInstalls } from '@/lib/install';

export const dynamic = 'force-dynamic';

export default async function SetupPage() {
  return <SetupView info={detectInstalls()} connected={await connectedMode()} />;
}
