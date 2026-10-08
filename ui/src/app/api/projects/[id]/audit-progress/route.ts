import fs from 'node:fs';
import path from 'node:path';
import { NextResponse } from 'next/server';
import { readJson } from '@/lib/fsx';
import { readJournal } from '@/lib/scan/journal';
import { projectDirFor } from '@/lib/scan/project';

export const dynamic = 'force-dynamic';

/**
 * Deletion-tracker sync for the audit report. The report (served through /file) reads and
 * writes `audit/bubble_cleanup_progress__<app>.json` here, so ticking a box in the embedded
 * report lands on disk — the same file `bubble_audit.py --state` and the console read.
 *
 * GET  → { exists: false } when no file yet, else the stored payload + exists: true
 * PUT  → validates the v2 payload and writes it (pretty JSON)
 *
 * Deletions applied through the connected mode live in their own journal
 * (audit/cleanup-applied__<app>.json). GET merges the entries that count — applied to test, or on
 * a merged branch — into `deleted`, so the report ticks them; PUT drops those keys again before
 * writing, because the report sends back everything that is ticked: the progress file keeps only
 * what the owner marked by hand, the journal keeps what the MCP applied.
 */

const MAX_ITEMS = 50_000;

function progressPath(dir: string, id: string): string {
  return path.join(dir, 'audit', `bubble_cleanup_progress__${id}.json`);
}

function strings(x: unknown): string[] | null {
  if (!Array.isArray(x) || x.length > MAX_ITEMS) return null;
  return x.every((v) => typeof v === 'string' && v.length <= 300) ? (x as string[]) : null;
}

export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const dir = projectDirFor(id);
  if (!dir) return NextResponse.json({ error: 'not found' }, { status: 404 });
  const file = progressPath(dir, id);
  const json = readJson<Record<string, unknown>>(file);
  const applied = Array.from(readJournal(dir).appliedKeys).sort();
  if (!json && !applied.length) return NextResponse.json({ app: id, exists: false, deleted: [], sections_done: [], kept: [] });
  const stored = json ?? { app: id, version: 2, deleted: [], sections_done: [], kept: [] };
  const own = (strings(stored.deleted) ?? []).filter((k) => !applied.includes(k));
  return NextResponse.json({ ...stored, deleted: Array.from(new Set([...own, ...applied])).sort(), applied_via_connect: applied, exists: true });
}

export async function PUT(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const dir = projectDirFor(id);
  if (!dir) return NextResponse.json({ error: 'not found' }, { status: 404 });
  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: 'invalid json' }, { status: 400 });
  }
  if (body.app !== undefined && body.app !== id) return NextResponse.json({ error: 'app mismatch' }, { status: 400 });
  const deleted = strings(body.deleted ?? []);
  const sectionsDone = strings(body.sections_done ?? []);
  if (!deleted || !sectionsDone) return NextResponse.json({ error: 'invalid payload' }, { status: 400 });
  const keptRaw = Array.isArray(body.kept) ? body.kept.slice(0, MAX_ITEMS) : [];
  const kept = keptRaw
    .filter((k): k is Record<string, unknown> => !!k && typeof k === 'object')
    .map((k) => ({
      key: String(k.key ?? '').slice(0, 300),
      label: String(k.label ?? '').slice(0, 300),
      section: String(k.section ?? '').slice(0, 10),
    }))
    .filter((k) => k.key);
  const sections = body.sections && typeof body.sections === 'object' && !Array.isArray(body.sections) ? (body.sections as Record<string, unknown>) : {};

  const applied = readJournal(dir).appliedKeys;
  const payload = {
    app: id,
    version: 2,
    updated: new Date().toISOString().slice(0, 10),
    deleted: Array.from(new Set(deleted.filter((k) => !applied.has(k)))).sort(),
    sections_done: Array.from(new Set(sectionsDone)).sort(),
    sections,
    kept,
  };
  const file = progressPath(dir, id);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(payload, null, 1) + '\n', 'utf8');
  return NextResponse.json({ ok: true, path: path.relative(dir, file), exists: true, ...payload });
}
