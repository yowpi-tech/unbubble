import 'server-only';
import path from 'node:path';
import { firstHeading, listFiles, readText } from './fsx';
import { LEVELUP_DOCS, LEVELUP_OPTIONAL } from './scan/levelup';
import type { DocEntry } from './types';

export const DOC_GROUPS = [
  'clone-docs',
  'clone-prd',
  'levelup',
  'audit',
  'secrets',
  'inventory',
  'other',
] as const;
export type DocGroup = (typeof DOC_GROUPS)[number];

function kindOf(rel: string): DocEntry['kind'] {
  const ext = path.extname(rel).toLowerCase();
  if (ext === '.md' || ext === '.markdown') return 'md';
  if (ext === '.json') return 'json';
  if (ext === '.html' || ext === '.htm') return 'html';
  return 'text';
}

function groupOf(rel: string): DocGroup | null {
  const base = path.basename(rel);
  if (rel.startsWith('docs/') && kindOf(rel) === 'md') return 'clone-docs';
  if (!rel.includes('/') && (base === 'PRD-clone.md' || base === 'PARITY-MATRIX.md')) return 'clone-prd';
  if (rel.startsWith('levelup/') && (kindOf(rel) === 'md' || kindOf(rel) === 'json')) return 'levelup';
  if (rel.startsWith('audit/') && kindOf(rel) === 'html') return 'audit';
  if (rel.startsWith('secrets/') && (base === 'ENV-KEYS.md' || base === '.env.example')) return 'secrets';
  if (rel.startsWith('inventory/') && kindOf(rel) === 'json') return 'inventory';
  if (base === 'unbubble.json') return null;
  if (kindOf(rel) === 'md') return 'other';
  return null;
}

const LEVELUP_ORDER = ['START-HERE.md', 'EXECUTION-CONTRACT.md', ...LEVELUP_DOCS.map((d) => d.file), ...LEVELUP_OPTIONAL];

function levelupRank(rel: string): number {
  const base = path.basename(rel);
  const i = LEVELUP_ORDER.findIndex((n) => n.toLowerCase() === base.toLowerCase());
  return i === -1 ? 999 : i;
}

export function listDocs(projectDir: string): DocEntry[] {
  const files = listFiles(projectDir);
  const out: DocEntry[] = [];
  for (const f of files) {
    const group = groupOf(f.path);
    if (!group) continue;
    const kind = kindOf(f.path);
    let title = path.basename(f.path);
    if (kind === 'md') {
      const txt = readText(path.join(projectDir, f.path), 300_000);
      const h = txt ? firstHeading(txt) : undefined;
      if (h) title = h;
    }
    out.push({ path: f.path, group, title, size: f.size, mtime: f.mtime, kind });
  }
  out.sort((a, b) => {
    const ga = DOC_GROUPS.indexOf(a.group as DocGroup);
    const gb = DOC_GROUPS.indexOf(b.group as DocGroup);
    if (ga !== gb) return ga - gb;
    if (a.group === 'levelup') {
      const r = levelupRank(a.path) - levelupRank(b.path);
      if (r !== 0) return r;
    }
    return a.path.localeCompare(b.path);
  });
  return out;
}
