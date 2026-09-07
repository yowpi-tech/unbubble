import { NextResponse } from 'next/server';
import { projectDirFor } from '@/lib/scan/project';
import { patchState, readState, type StatePatch } from '@/lib/state';

export const dynamic = 'force-dynamic';

export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const dir = projectDirFor(id);
  if (!dir) return NextResponse.json({ error: 'not found' }, { status: 404 });
  return NextResponse.json(readState(dir));
}

/** PATCH merges a StatePatch into <project>/unbubble.json — the only file this UI writes. */
export async function PATCH(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const dir = projectDirFor(id);
  if (!dir) return NextResponse.json({ error: 'not found' }, { status: 404 });
  let patch: StatePatch;
  try {
    patch = (await req.json()) as StatePatch;
  } catch {
    return NextResponse.json({ error: 'invalid json' }, { status: 400 });
  }
  try {
    const state = patchState(dir, patch);
    return NextResponse.json(state);
  } catch (e) {
    return NextResponse.json({ error: e instanceof Error ? e.message : 'failed' }, { status: 400 });
  }
}
