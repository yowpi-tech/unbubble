import { NextResponse } from 'next/server';
import { connectedMode } from '@/lib/connect';
import { detectInstalls } from '@/lib/install';

export const dynamic = 'force-dynamic';

export async function GET() {
  return NextResponse.json({ ...detectInstalls(), connected: await connectedMode() });
}
