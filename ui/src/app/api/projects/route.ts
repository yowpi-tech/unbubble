import { NextResponse } from 'next/server';
import { listProjects } from '@/lib/scan/project';

export const dynamic = 'force-dynamic';

export async function GET() {
  return NextResponse.json(listProjects());
}
