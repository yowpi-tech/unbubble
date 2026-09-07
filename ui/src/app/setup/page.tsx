import { SetupView } from '@/components/setup/setup-view';
import { detectInstalls } from '@/lib/install';

export const dynamic = 'force-dynamic';

export default function SetupPage() {
  return <SetupView info={detectInstalls()} />;
}
