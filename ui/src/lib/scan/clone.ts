import 'server-only';
import fs from 'node:fs';
import path from 'node:path';
import { readJson, readText, statInfo } from '../fsx';
import type {
  ChecklistItem,
  CloneStage,
  FileInfo,
  OpenQuestionsSummary,
  ParityMatrixSummary,
  StageOverride,
} from '../types';

/** The nine as-is docs the clone skill writes (SKILL.md §3). Matched by numeric prefix. */
export const CLONE_DOCS: { prefix: string; key: string; label: string }[] = [
  { prefix: '00', key: 'overview', label: '00 · Overview' },
  { prefix: '01', key: 'database', label: '01 · Database' },
  { prefix: '02', key: 'external-apis', label: '02 · External APIs' },
  { prefix: '03', key: 'plugins', label: '03 · Plugins' },
  { prefix: '04', key: 'data-api', label: '04 · Data API' },
  { prefix: '05', key: 'backend-workflows', label: '05 · Backend workflows' },
  { prefix: '06', key: 'pages', label: '06 · Pages & reusables' },
  { prefix: '07', key: 'business-rules', label: '07 · Business rules' },
  { prefix: '08', key: 'open-questions', label: '08 · Open questions' },
];

function listDocs(projectDir: string): FileInfo[] {
  const dir = path.join(projectDir, 'docs');
  let names: string[] = [];
  try {
    names = fs.readdirSync(dir);
  } catch {
    return [];
  }
  return names
    .filter((n) => n.toLowerCase().endsWith('.md'))
    .map((n) => statInfo(projectDir, `docs/${n}`))
    .filter((f): f is FileInfo => !!f)
    .sort((a, b) => a.path.localeCompare(b.path));
}

/** Parse PARITY-MATRIX.md: every 2+-cell table row outside the summary table is an entity row. */
export function parseParityMatrix(text: string, file: FileInfo): ParityMatrixSummary {
  const lines = text.split('\n');
  let rows = 0;
  let withDisposition = 0;
  const byDisposition: Record<string, number> = {};
  let inSummary = false;
  let generatedOn: string | undefined;

  const gen = text.match(/(?:Gerada|Generated)[^\n]{0,40}?(\d{4}-\d{2}-\d{2})/i);
  if (gen) generatedOn = gen[1];

  for (const line of lines) {
    if (/^#{1,3}\s/.test(line)) {
      inSummary = false;
      continue;
    }
    if (/^\*\*Resumo de contagens|^\*\*Count summary|^\| *Classe *\||^\| *Class *\|/i.test(line)) {
      inSummary = true;
    }
    if (!line.startsWith('|')) continue;
    const cells = line
      .split('|')
      .slice(1, -1)
      .map((c) => c.trim());
    if (cells.length < 2) continue;
    if (cells.every((c) => /^:?-{2,}:?$/.test(c))) continue; // separator
    const first = cells[0].toLowerCase();
    if (first === 'entidade' || first === 'entity' || first === 'classe' || first === 'class') {
      if (first === 'classe' || first === 'class') inSummary = true;
      continue;
    }
    if (inSummary) continue;
    rows++;
    const disp = cells[1].replace(/`/g, '').trim();
    if (disp) {
      withDisposition++;
      const kind = disp.match(/^(REQ|BR-\d+|DESCOPED|UI-ONLY|INFRA)/i)?.[1]?.toUpperCase();
      const label = kind ? (kind.startsWith('BR-') ? 'BR' : kind) : 'OTHER';
      byDisposition[label] = (byDisposition[label] ?? 0) + 1;
    }
  }

  return { file, rows, withDisposition, blank: rows - withDisposition, byDisposition, generatedOn };
}

export function parseOpenQuestions(text: string, file: FileInfo): OpenQuestionsSummary {
  const lines = text.split('\n');
  let section: 'blocking' | 'non' | 'decisions' | 'other' = 'other';
  let blocking = 0;
  let nonBlocking = 0;
  const decisionDates: string[] = [];
  for (const line of lines) {
    const h = line.match(/^(#{2,3})\s+(.*)$/);
    if (h) {
      const title = h[2].toLowerCase();
      if (h[1] === '##') {
        if (/bloqueante|blocking/.test(title) && !/n[aã]o[- ]bloqueante|non[- ]blocking/.test(title)) section = 'blocking';
        else if (/n[aã]o[- ]bloqueante|non[- ]blocking/.test(title)) section = 'non';
        else if (/decis/.test(title)) section = 'decisions';
        else section = 'other';
      } else if (section === 'decisions') {
        const d = h[2].match(/\d{4}-\d{2}-\d{2}/);
        if (d) decisionDates.push(d[0]);
      }
      continue;
    }
    if (/^\s*(?:[-*+]|\d+\.)\s+\S/.test(line)) {
      if (section === 'blocking') blocking++;
      else if (section === 'non') nonBlocking++;
    }
  }
  return { file, blocking, nonBlocking, decisionDates, hasDecisions: decisionDates.length > 0 };
}

export function scanClone(projectDir: string, override?: StageOverride): CloneStage {
  const docs = listDocs(projectDir);
  const items: ChecklistItem[] = [];

  // inventory
  const summaryFile = statInfo(projectDir, 'inventory/summary.json');
  let summary: CloneStage['summary'];
  if (summaryFile) {
    const j = readJson<{ app_domain?: string; counts?: Record<string, number>; security_flags?: Record<string, string[]> }>(
      path.join(projectDir, 'inventory/summary.json'),
    );
    summary = { app_domain: j?.app_domain, counts: j?.counts, security_flags: j?.security_flags, file: summaryFile };
  }
  items.push({
    key: 'inventory',
    label: 'inventory/ (bubble_inventory.py)',
    done: !!summaryFile,
    file: summaryFile,
    detail: summary?.counts ? `${summary.counts.pages ?? 0} pages · ${summary.counts.data_types_active ?? 0} tables · ${summary.counts.backend_workflows ?? 0} backend WFs` : undefined,
  });

  // secrets — existence only; the .env is never read.
  const envPresent = fs.existsSync(path.join(projectDir, 'secrets', '.env'));
  const keysDoc = statInfo(projectDir, 'secrets/ENV-KEYS.md');
  const envExample = statInfo(projectDir, 'secrets/.env.example');
  let varCount: number | undefined;
  if (envExample) {
    const txt = readText(path.join(projectDir, 'secrets/.env.example'));
    if (txt) varCount = (txt.match(/^[A-Z][A-Z0-9_]*=/gm) ?? []).length;
  }
  items.push({
    key: 'secrets',
    label: 'secrets/.env + ENV-KEYS.md (bubble_secrets.py)',
    done: envPresent && !!keysDoc,
    file: keysDoc,
    detail: varCount !== undefined ? `${varCount} vars preserved` : undefined,
  });

  // the nine docs
  const docItems: ChecklistItem[] = CLONE_DOCS.map((d) => {
    const f = docs.find((x) => path.basename(x.path).startsWith(d.prefix + '-'));
    return { key: d.key, label: d.label, done: !!f, file: f };
  });
  const extraDocs = docs.filter((f) => !CLONE_DOCS.some((d) => path.basename(f.path).startsWith(d.prefix + '-')));

  // PRD + matrix
  const prd = statInfo(projectDir, 'PRD-clone.md');
  items.push({ key: 'prd', label: 'PRD-clone.md', done: !!prd, file: prd });

  const matrixFile = statInfo(projectDir, 'PARITY-MATRIX.md');
  let matrix: ParityMatrixSummary | undefined;
  if (matrixFile) {
    const txt = readText(path.join(projectDir, 'PARITY-MATRIX.md'));
    if (txt) matrix = parseParityMatrix(txt, matrixFile);
  }
  items.push({
    key: 'matrix',
    label: 'PARITY-MATRIX.md',
    done: !!matrixFile && (!matrix || matrix.blank === 0),
    file: matrixFile,
    detail: matrix ? `${matrix.rows} rows · ${matrix.blank} without disposition` : undefined,
  });

  // open questions
  let openQuestions: OpenQuestionsSummary | undefined;
  const oq = docItems.find((d) => d.key === 'open-questions')?.file;
  if (oq) {
    const txt = readText(path.join(projectDir, oq.path));
    if (txt) openQuestions = parseOpenQuestions(txt, oq);
  }

  const all = [...items.slice(0, 2), ...docItems, ...items.slice(2)];
  const done = all.filter((i) => i.done).length;
  const progress = all.length ? done / all.length : 0;

  let derived: CloneStage['derivedStatus'] = 'not_started';
  if (done === all.length) derived = 'done';
  else if (done > 0) derived = 'in_progress';
  const status = override?.status ?? derived;

  return {
    status,
    derivedStatus: derived,
    override,
    items,
    docs: docItems,
    extraDocs,
    progress: status === 'done' ? 1 : progress,
    summary,
    secrets: { envPresent, keysDoc, envExample, varCount },
    matrix,
    openQuestions,
  };
}
