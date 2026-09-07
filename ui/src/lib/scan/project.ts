import 'server-only';
import fs from 'node:fs';
import path from 'node:path';
import { firstHeading, latestMtime, listFiles, readText } from '../fsx';
import { projectsDir } from '../paths';
import { readState } from '../state';
import { scanAudit } from './audit';
import { scanClone } from './clone';
import { scanLevelUp } from './levelup';
import type { ProjectDetail, ProjectSummary, StageKey } from '../types';

const ID_RE = /^[a-z0-9][a-z0-9._-]*$/i;

export function listProjectIds(): string[] {
  const root = projectsDir();
  let entries: fs.Dirent[] = [];
  try {
    entries = fs.readdirSync(root, { withFileTypes: true });
  } catch {
    return [];
  }
  return entries
    .filter((e) => e.isDirectory() && !e.name.startsWith('.') && ID_RE.test(e.name))
    .map((e) => e.name)
    .sort();
}

export function projectDirFor(id: string): string | null {
  if (!ID_RE.test(id) || id.startsWith('.')) return null;
  const dir = path.join(projectsDir(), id);
  try {
    if (!fs.statSync(dir).isDirectory()) return null;
  } catch {
    return null;
  }
  return dir;
}

/** Display name: unbubble.json → 00-overview H1 ("00 · Visão geral — Acme Portal (as-is)") → app id. */
function displayName(dir: string, id: string, override?: string): string {
  if (override) return override;
  const overview = fs.existsSync(path.join(dir, 'docs'))
    ? (() => {
        try {
          const n = fs.readdirSync(path.join(dir, 'docs')).find((f) => /^00-/.test(f) && f.endsWith('.md'));
          return n ? readText(path.join(dir, 'docs', n), 200_000) : undefined;
        } catch {
          return undefined;
        }
      })()
    : undefined;
  if (overview) {
    const h = firstHeading(overview);
    if (h) {
      // "00 · Visão geral — Acme Portal (as-is)" → "Acme Portal"
      const m = h.match(/[—–-]\s*(.+?)\s*(?:\((?:as-is|AS-IS)\))?\s*$/);
      let candidate = (m ? m[1] : h).replace(/^\d+\s*[·.]\s*/, '').trim();
      // "Acme Portal (acme-portal)" → drop the app id when it is repeated in parentheses
      candidate = candidate.replace(new RegExp(`\\s*\\(${id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\)\\s*$`), '').trim();
      if (candidate && candidate.length <= 60) return candidate;
    }
  }
  return id;
}

function nextStep(s: ProjectSummary['stages']): ProjectSummary['nextStep'] {
  if (s.audit.status !== 'done') return 'audit';
  if (s.clone.status !== 'done') return 'clone';
  if (s.levelup_docs.status !== 'done') return 'levelup_docs';
  if (s.levelup_impl.status !== 'done') return 'levelup_impl';
  return 'rebuild_done';
}

export function getProject(id: string): ProjectDetail | null {
  const dir = projectDirFor(id);
  if (!dir) return null;
  const state = readState(dir);
  const audit = scanAudit(dir, state.stages?.audit);
  const clone = scanClone(dir, state.stages?.clone);
  const levelup = scanLevelUp(dir, state.stories_done ?? [], state.stages?.levelup_docs, state.stages?.levelup_impl);
  const files = listFiles(dir);

  const stages: ProjectSummary['stages'] = {
    audit: {
      status: audit.status,
      progress: audit.progress,
      detail: audit.latest
        ? audit.latest.totalFindings === null
          ? `${audit.rounds.length} round(s)`
          : `${audit.latest.label} · ${audit.latest.totalFindings} finding(s)` +
            (audit.progressFile && audit.sectionsWithFindings > 0
              ? ` · ${audit.sectionsResolved}/${audit.sectionsWithFindings} ✓${audit.progressFile.kept.length ? ` · ${audit.progressFile.kept.length} kept` : ''}`
              : '')
        : '',
    },
    clone: {
      status: clone.status,
      progress: clone.progress,
      detail: `${clone.docs.filter((d) => d.done).length}/${clone.docs.length} docs${clone.matrix ? ` · matrix ${clone.matrix.rows}` : ''}`,
    },
    levelup_docs: {
      status: levelup.docsStatus,
      progress: levelup.docsProgress,
      detail: `${levelup.docs.filter((d) => d.done).length}/${levelup.docs.length} docs${levelup.specCoverage ? ` · gate ${levelup.specCoverage.gate}` : ''}`,
    },
    levelup_impl: {
      status: levelup.implStatus,
      progress: levelup.implProgress,
      detail: levelup.backlog ? `${levelup.backlog.done}/${levelup.backlog.total} stories` : '',
    },
  };

  return {
    id,
    name: displayName(dir, id, state.name),
    dir,
    updatedAt: latestMtime(files),
    domain: clone.summary?.app_domain,
    counts: clone.summary?.counts ?? (audit.latest?.totals ? totalsToCounts(audit.latest.totals) : undefined),
    stages,
    nextStep: nextStep(stages),
    audit,
    clone,
    levelup,
    state,
    files,
  };
}

function totalsToCounts(t: NonNullable<ProjectSummary['counts']> | Record<string, number>): Record<string, number> {
  return {
    pages: t.pages ?? 0,
    data_types_active: t.dataTables ?? 0,
    backend_workflows: t.backend ?? 0,
    plugins_installed: t.plugins ?? 0,
    api_calls: t.apiCalls ?? 0,
    reusables: t.reusables ?? 0,
    option_sets: t.optionSets ?? 0,
  };
}

export function listProjects(): ProjectSummary[] {
  return listProjectIds()
    .map((id) => getProject(id))
    .filter((p): p is ProjectDetail => !!p)
    .map((p) => ({
      id: p.id,
      name: p.name,
      dir: p.dir,
      updatedAt: p.updatedAt,
      domain: p.domain,
      counts: p.counts,
      stages: p.stages,
      nextStep: p.nextStep,
    }))
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

export const STAGE_ORDER: StageKey[] = ['audit', 'clone', 'levelup_docs', 'levelup_impl'];
