import 'server-only';
import fs from 'node:fs';
import path from 'node:path';
import { readJson, readText, statInfo } from '../fsx';
import { parseBacklog } from './backlog';
import type { ChecklistItem, FileInfo, LevelUpStage, ParityReportSummary, SpecCoverageSummary, StageOverride } from '../types';

/** The rebuild pack (level-up SKILL.md §5). */
export const LEVELUP_DOCS: { file: string; key: string; label: string }[] = [
  { file: 'ASSESSMENT.md', key: 'assessment', label: 'ASSESSMENT' },
  { file: 'TARGET-ARCHITECTURE.md', key: 'target', label: 'TARGET-ARCHITECTURE' },
  { file: 'FRONTEND-DESIGN.md', key: 'frontend', label: 'FRONTEND-DESIGN' },
  { file: 'DATA-MODEL.md', key: 'data-model', label: 'DATA-MODEL' },
  { file: 'MIGRATION-PLAN.md', key: 'migration', label: 'MIGRATION-PLAN' },
  { file: 'PRD-v2.md', key: 'prd-v2', label: 'PRD-v2' },
  { file: 'BACKLOG.md', key: 'backlog', label: 'BACKLOG' },
  { file: 'RISKS.md', key: 'risks', label: 'RISKS' },
  { file: 'EXECUTION-CONTRACT.md', key: 'contract', label: 'EXECUTION-CONTRACT' },
];

/** Known optional files, shown as extras with a friendlier order. */
export const LEVELUP_OPTIONAL = ['START-HERE.md', 'PARITY.md', 'spec-coverage.md', 'parity-report.md'];

export function scanLevelUp(
  projectDir: string,
  storiesDone: string[],
  docsOverride?: StageOverride,
  implOverride?: StageOverride,
): LevelUpStage {
  const dir = path.join(projectDir, 'levelup');
  let names: string[] = [];
  try {
    names = fs.readdirSync(dir);
  } catch {
    names = [];
  }
  const files = names
    .filter((n) => !n.startsWith('.'))
    .map((n) => statInfo(projectDir, `levelup/${n}`))
    .filter((f): f is FileInfo => !!f);

  const docs: ChecklistItem[] = LEVELUP_DOCS.map((d) => {
    const f = files.find((x) => path.basename(x.path).toLowerCase() === d.file.toLowerCase());
    return { key: d.key, label: d.label, done: !!f, file: f };
  });
  const extraDocs = files.filter(
    (f) => !LEVELUP_DOCS.some((d) => d.file.toLowerCase() === path.basename(f.path).toLowerCase()),
  );

  // spec coverage gate
  let specCoverage: SpecCoverageSummary | undefined;
  const scFile = statInfo(projectDir, 'levelup/spec-coverage.json');
  if (scFile) {
    const j = readJson<{ summary?: Record<string, unknown> }>(path.join(projectDir, scFile.path));
    const s = j?.summary ?? {};
    const n = (k: string) => (typeof s[k] === 'number' ? (s[k] as number) : 0);
    specCoverage = {
      file: scFile,
      gate: typeof s.gate === 'string' ? (s.gate as string) : 'UNKNOWN',
      coverage_pct: n('coverage_pct'),
      requirements_total: n('requirements_total'),
      requirements_covered: n('requirements_covered'),
      stories_total: n('stories_total'),
      orphan_stories: n('orphan_stories'),
      non_atomic_stories: n('non_atomic_stories'),
      requirements_missing_acceptance: n('requirements_missing_acceptance'),
      unknown_citations: n('unknown_citations'),
      strict_acceptance: s.strict_acceptance === true,
    };
  }

  // parity report (schema × code) — only exists once a rebuild has code
  let parityReport: ParityReportSummary | undefined;
  const prFile = statInfo(projectDir, 'levelup/parity-report.json');
  if (prFile) {
    const j = readJson<{ summary?: Record<string, unknown> }>(path.join(projectDir, prFile.path));
    const s = j?.summary ?? {};
    const n = (k: string) => (typeof s[k] === 'number' ? (s[k] as number) : 0);
    parityReport = {
      file: prFile,
      column_coverage_pct: n('column_coverage_pct'),
      tables_total: n('tables_total'),
      tables_orphaned: n('tables_orphaned'),
      columns_considered: n('columns_considered'),
      columns_orphaned_high_confidence: n('columns_orphaned_high_confidence'),
      columns_orphaned_low_signal: n('columns_orphaned_low_signal'),
      app_dir: typeof s.app_dir === 'string' ? (s.app_dir as string) : undefined,
    };
  }

  // backlog stories (implementation tracking)
  let backlog: LevelUpStage['backlog'];
  const blFile = docs.find((d) => d.key === 'backlog')?.file;
  if (blFile) {
    const txt = readText(path.join(projectDir, blFile.path));
    if (txt) {
      const epics = parseBacklog(txt);
      const all = epics.flatMap((e) => e.stories);
      const doneSet = new Set(storiesDone);
      backlog = {
        file: blFile,
        epics,
        total: all.length,
        done: all.filter((s) => doneSet.has(s.id)).length,
        infra: all.filter((s) => s.infra).length,
        nonAtomic: all.filter((s) => s.nonAtomic).length,
      };
    }
  }

  const docsDone = docs.filter((d) => d.done).length;
  const docsProgress = docs.length ? docsDone / docs.length : 0;
  let docsDerived: LevelUpStage['docsDerivedStatus'] = 'not_started';
  if (docsDone === docs.length && (!specCoverage || specCoverage.gate === 'PASS')) docsDerived = 'done';
  else if (docsDone > 0) docsDerived = 'in_progress';
  const docsStatus = docsOverride?.status ?? docsDerived;

  let implDerived: LevelUpStage['implDerivedStatus'] = 'not_started';
  let implProgress = 0;
  if (backlog && backlog.total > 0) {
    implProgress = backlog.done / backlog.total;
    if (backlog.done === backlog.total) implDerived = 'done';
    else if (backlog.done > 0) implDerived = 'in_progress';
  }
  if (implDerived === 'not_started' && parityReport) implDerived = 'in_progress';
  const implStatus = implOverride?.status ?? implDerived;

  return {
    docsStatus,
    docsDerivedStatus: docsDerived,
    docsOverride,
    docs,
    extraDocs,
    docsProgress: docsStatus === 'done' ? 1 : docsProgress,
    specCoverage,
    parityReport,
    implStatus,
    implDerivedStatus: implDerived,
    implOverride,
    backlog,
    implProgress: implStatus === 'done' ? 1 : implProgress,
  };
}
