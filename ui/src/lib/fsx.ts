import 'server-only';
import fs from 'node:fs';
import path from 'node:path';
import type { FileInfo } from './types';

const IGNORED_DIRS = new Set(['node_modules', '.git', '.impeccable', '__pycache__', '.next']);

export function exists(p: string): boolean {
  try {
    fs.accessSync(p);
    return true;
  } catch {
    return false;
  }
}

export function statInfo(projectDir: string, rel: string): FileInfo | undefined {
  try {
    const st = fs.statSync(path.join(projectDir, rel));
    if (!st.isFile()) return undefined;
    return { path: rel, size: st.size, mtime: st.mtime.toISOString() };
  } catch {
    return undefined;
  }
}

export function readText(p: string, maxBytes = 8 * 1024 * 1024): string | undefined {
  try {
    const st = fs.statSync(p);
    if (!st.isFile() || st.size > maxBytes) return undefined;
    return fs.readFileSync(p, 'utf8');
  } catch {
    return undefined;
  }
}

export function readJson<T = unknown>(p: string): T | undefined {
  const txt = readText(p);
  if (txt === undefined) return undefined;
  try {
    return JSON.parse(txt) as T;
  } catch {
    return undefined;
  }
}

/** List files (relative paths) under a project folder, skipping noise and secrets values. */
export function listFiles(projectDir: string, maxDepth = 4): FileInfo[] {
  const out: FileInfo[] = [];
  function walk(dir: string, depth: number) {
    if (depth > maxDepth) return;
    let entries: fs.Dirent[] = [];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const e of entries) {
      if (e.name === '.DS_Store') continue;
      const abs = path.join(dir, e.name);
      if (e.isDirectory()) {
        if (IGNORED_DIRS.has(e.name)) continue;
        walk(abs, depth + 1);
      } else if (e.isFile()) {
        if (e.name === '.env' || (e.name.startsWith('.env.') && e.name !== '.env.example')) continue;
        try {
          const st = fs.statSync(abs);
          out.push({
            path: path.relative(projectDir, abs).split(path.sep).join('/'),
            size: st.size,
            mtime: st.mtime.toISOString(),
          });
        } catch {
          /* ignore */
        }
      }
    }
  }
  walk(projectDir, 0);
  out.sort((a, b) => a.path.localeCompare(b.path));
  return out;
}

/** First markdown H1 of a file, without the leading hashes. */
export function firstHeading(text: string): string | undefined {
  const m = text.match(/^#\s+(.+?)\s*$/m);
  return m ? m[1].replace(/[*_`]/g, '').trim() : undefined;
}

export function latestMtime(files: FileInfo[]): string {
  let best = '';
  for (const f of files) if (f.mtime > best) best = f.mtime;
  return best;
}
