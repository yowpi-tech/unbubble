import fs from 'node:fs';
import path from 'node:path';
import { NextResponse } from 'next/server';
import { safeProjectPath } from '@/lib/paths';
import { projectDirFor } from '@/lib/scan/project';

export const dynamic = 'force-dynamic';

const TYPES: Record<string, string> = {
  '.html': 'text/html; charset=utf-8',
  '.htm': 'text/html; charset=utf-8',
  '.md': 'text/markdown; charset=utf-8',
  '.markdown': 'text/markdown; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.txt': 'text/plain; charset=utf-8',
  '.csv': 'text/csv; charset=utf-8',
  '.pdf': 'application/pdf',
  '.py': 'text/plain; charset=utf-8',
  '.example': 'text/plain; charset=utf-8',
};

/**
 * Serves one artifact of a project (report HTML, markdown, JSON). Path traversal and the
 * live secrets file are refused by safeProjectPath. Local tool: no auth by design.
 */
export async function GET(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const dir = projectDirFor(id);
  if (!dir) return NextResponse.json({ error: 'not found' }, { status: 404 });
  const rel = new URL(req.url).searchParams.get('path') ?? '';
  const abs = safeProjectPath(dir, rel);
  if (!abs) return NextResponse.json({ error: 'forbidden' }, { status: 403 });
  let st: fs.Stats;
  try {
    st = fs.statSync(abs);
  } catch {
    return NextResponse.json({ error: 'not found' }, { status: 404 });
  }
  if (!st.isFile()) return NextResponse.json({ error: 'not a file' }, { status: 400 });
  if (st.size > 64 * 1024 * 1024) return NextResponse.json({ error: 'too large' }, { status: 413 });
  const ext = path.extname(abs).toLowerCase();
  const type = TYPES[ext] ?? 'application/octet-stream';
  const body = fs.readFileSync(abs);
  return new NextResponse(body, {
    status: 200,
    headers: {
      'Content-Type': type,
      'Content-Length': String(st.size),
      'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff',
    },
  });
}
