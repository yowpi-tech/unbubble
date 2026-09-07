import { NextResponse } from 'next/server';
import { listDocs } from '@/lib/docs';
import { projectDirFor } from '@/lib/scan/project';

export const dynamic = 'force-dynamic';

export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const dir = projectDirFor(id);
  if (!dir) return NextResponse.json({ error: 'not found' }, { status: 404 });
  return NextResponse.json({ docs: listDocs(dir) });
}
