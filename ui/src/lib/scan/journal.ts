import 'server-only';
import fs from 'node:fs';
import path from 'node:path';
import { readJson, statInfo } from '../fsx';
import type { CleanupJournalSummary } from '../types';

/**
 * Journal of deletions applied through the connected mode (unbubble:connect cleanup_journal.py):
 * audit/cleanup-applied__<app>.json, {"kind": "unbubble-cleanup-journal", "entries": [...]}.
 *
 * Same rule as bubble_audit.py --state: an entry counts as deleted in the app only when the call
 * succeeded and it was applied to `test` itself or to a branch the owner merged. Deletions on a
 * branch that is not merged (or was discarded) never count.
 */

type Json = Record<string, unknown>;
const obj = (x: unknown): Json => (x && typeof x === 'object' && !Array.isArray(x) ? (x as Json) : {});

const TEST_VERSIONS = new Set(['test', 'version-test']);

export function journalCounts(entry: Json): boolean {
  if (entry.ok === false) return false;
  return entry.merged === true || TEST_VERSIONS.has(String(entry.app_version ?? '').toLowerCase());
}

function journalFile(projectDir: string): string | undefined {
  try {
    const name = fs.readdirSync(path.join(projectDir, 'audit')).find((f) => /^cleanup-applied__.+\.json$/i.test(f));
    return name ? `audit/${name}` : undefined;
  } catch {
    return undefined;
  }
}

export interface Journal {
  summary?: CleanupJournalSummary;
  /** Keys that count as deleted (merged into the deletion tracker). */
  appliedKeys: Set<string>;
}

export function readJournal(projectDir: string): Journal {
  const rel = journalFile(projectDir);
  const data = rel ? obj(readJson(path.join(projectDir, rel))) : {};
  if (!rel || data.kind !== 'unbubble-cleanup-journal' || !Array.isArray(data.entries)) return { appliedKeys: new Set() };
  const appliedKeys = new Set<string>();
  const byVersion = new Map<string, CleanupJournalSummary['versions'][number]>();
  let applied = 0;
  let pending = 0;
  let failed = 0;
  let verified = 0;
  for (const raw of data.entries) {
    const e = obj(raw);
    if (typeof e.key !== 'string' || !e.key) continue;
    const version = String(e.app_version ?? '?');
    const v = byVersion.get(version) ?? { appVersion: version, applied: 0, pending: 0, failed: 0, verified: 0 };
    if (e.ok === false) {
      failed++;
      v.failed++;
    } else if (journalCounts(e)) {
      applied++;
      v.applied++;
      appliedKeys.add(e.key);
    } else {
      pending++;
      v.pending++;
    }
    if (e.verified === true) {
      verified++;
      v.verified++;
    }
    byVersion.set(version, v);
  }
  return {
    appliedKeys,
    summary: {
      path: rel,
      updated: typeof data.updated_at === 'string' ? data.updated_at : statInfo(projectDir, rel)?.mtime,
      entries: data.entries.length,
      applied,
      pending,
      failed,
      verified,
      versions: Array.from(byVersion.values()).sort((a, b) => a.appVersion.localeCompare(b.appVersion)),
    },
  };
}
