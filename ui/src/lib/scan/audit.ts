import 'server-only';
import fs from 'node:fs';
import path from 'node:path';
import { readJson, readText, statInfo } from '../fsx';
import type { AuditCategory, AuditProgress, AuditRound, AuditStage, Confidence, KeptItem, StageOverride } from '../types';

/** Anything the audit JSON stores per category: a list of findings or a bare number. */
function count(x: unknown): number {
  if (Array.isArray(x)) return x.length;
  if (typeof x === 'number' && Number.isFinite(x)) return x;
  return 0;
}

function num(x: unknown): number {
  return typeof x === 'number' && Number.isFinite(x) ? x : 0;
}

type Json = Record<string, unknown>;
const obj = (x: unknown): Json => (x && typeof x === 'object' && !Array.isArray(x) ? (x as Json) : {});

/** The ten sign-off sections of the HTML report (h2 anchors). */
export const REPORT_SECTIONS = ['p', 'r', 'b', 'o', 'pl', 's', 'd', 'w', 'ap', 'g'] as const;

/**
 * Category list mirrors the report sections of bubble_audit.py. Confidence follows the
 * skill's own framing: high = deterministic references, review = needs a human (pages,
 * plugins, mobile views), destructive = deleting also deletes data. `section` is the report
 * h2 the category is signed off with; `prefixes` are the item-key prefixes it owns.
 */
const CATEGORY_DEFS: { key: string; section: string; confidence: Confidence; prefixes: string[] }[] = [
  { key: 'pages', section: 'p', confidence: 'review', prefixes: ['page:'] },
  { key: 'reusables', section: 'r', confidence: 'high', prefixes: ['reusable:'] },
  { key: 'backend', section: 'b', confidence: 'high', prefixes: ['workflow:'] },
  { key: 'option_sets', section: 'o', confidence: 'high', prefixes: ['optionset:'] },
  { key: 'plugins', section: 'pl', confidence: 'review', prefixes: ['plugin:'] },
  { key: 'styles', section: 's', confidence: 'high', prefixes: ['style:'] },
  { key: 'variables', section: 's', confidence: 'high', prefixes: ['colorvar:', 'fontvar:'] },
  { key: 'data_tables', section: 'd', confidence: 'destructive', prefixes: ['datatype:'] },
  { key: 'data_fields', section: 'd', confidence: 'destructive', prefixes: ['field:'] },
  { key: 'workflow_audit', section: 'w', confidence: 'high', prefixes: ['customevent:', 'pagewf:', 'hiddenwf:'] },
  { key: 'api_connector', section: 'ap', confidence: 'high', prefixes: ['apicall:'] },
  { key: 'removed_plugin_refs', section: 'g', confidence: 'high', prefixes: ['ghostref:'] },
  { key: 'mobile_views', section: 'p', confidence: 'review', prefixes: ['mobileview:', 'mobilenav:'] },
];

function countsFromAuditJson(j: Json): Record<string, number> {
  const pages = obj(j.pages);
  const reus = obj(j.reusables);
  const backend = obj(j.backend);
  const os = obj(j.option_sets);
  const plugins = obj(j.plugins);
  const styles = obj(j.styles);
  const vars = obj(j.variables);
  const dt = obj(j.data_tables);
  const df = obj(j.data_fields);
  const wf = obj(j.workflow_audit);
  const api = obj(j.api_connector);
  const rp = obj(j.removed_plugin_refs);
  const mv = obj(j.mobile_views);
  return {
    pages: count(pages.unused),
    reusables: count(reus.unused_hard) + count(reus.unused_transitive),
    backend: count(backend.unused_hard) + count(backend.unused_transitive),
    option_sets: count(os.unused),
    plugins: count(plugins.orphaned) + count(plugins.configured_no_ui),
    styles: count(styles.unused),
    variables: count(obj(vars.colors).unused) + count(obj(vars.fonts).unused),
    data_tables: count(dt.unused),
    data_fields: count(df.unused),
    workflow_audit:
      count(wf.backend_custom_events_uncalled) +
      count(wf.page_custom_events_uncalled) +
      count(wf.triggers_on_missing_element) +
      count(wf.triggers_on_hidden_element_leads),
    api_connector: count(api.unused),
    removed_plugin_refs: count(rp.refs) || num(rp.total),
    mobile_views: count(mv.unused) + count(mv.broken_navigations),
  };
}

export function categoriesFromAuditJson(j: Json, progress?: AuditProgress): AuditCategory[] {
  const counts = countsFromAuditJson(j);
  const done = new Set(progress?.sectionsDone ?? []);
  return CATEGORY_DEFS.map((d) => {
    const n = counts[d.key] ?? 0;
    const kept = (progress?.kept ?? []).filter((k) => d.prefixes.some((p) => k.key.startsWith(p)));
    return { key: d.key, count: n, confidence: d.confidence, section: d.section, resolved: n === 0 || done.has(d.section), kept };
  });
}

function totalsFromAuditJson(j: Json): AuditRound['totals'] {
  return {
    pages: num(obj(j.pages).total),
    reusables: num(obj(j.reusables).total),
    backend: num(obj(j.backend).total_apievents),
    optionSets: num(obj(j.option_sets).total),
    plugins: num(obj(j.plugins).total),
    styles: num(obj(j.styles).total),
    dataTables: num(obj(j.data_tables).active),
    dataFields: num(obj(j.data_fields).active),
    apiCalls: num(obj(j.api_connector).total_calls),
    mobileViews: num(obj(j.mobile_views).total),
  };
}

/** `<app>-v3_audit.json`, `<app>-v3_unused_report.html`, `<app>-v3_unused_report_EN.html`, `<app>_unused_report.html` */
const ROUND_RE = /^(.*?)(?:-v(\d+))?_(audit\.json|unused_report(_EN)?\.html)$/i;

function dateOfReport(projectDir: string, rel: string): string {
  // The HTML carries the --date stamp in its header; fall back to mtime.
  const txt = readText(path.join(projectDir, rel), 2 * 1024 * 1024);
  if (txt) {
    const head = txt.slice(0, 60_000);
    // "gerado em 2026-07-15" / "generated on 2026-07-15" (lowercase in the report header)
    const m = head.match(/(?:gerado|generated)[^<]{0,40}?(\d{4}-\d{2}-\d{2})/i);
    if (m) return m[1];
  }
  const info = statInfo(projectDir, rel);
  return info ? info.mtime.slice(0, 10) : '';
}

/**
 * Deletion-tracker progress file exported from the report (or auto-saved by the console).
 * JSON v2: { deleted[], sections_done[], kept[{key,label,section}] }. Older JSON: { deleted[] }.
 * Markdown: `- [x] \`section:b\`` lines mark a section done; unchecked items under a done
 * section are the kept ones.
 */
function parseProgress(rel: string, txt: string, updated?: string): AuditProgress {
  if (rel.toLowerCase().endsWith('.json')) {
    try {
      const j = JSON.parse(txt) as unknown;
      if (Array.isArray(j)) return { path: rel, updated, deleted: j.length, sectionsDone: [], kept: [] };
      const o = obj(j);
      const kept = (Array.isArray(o.kept) ? o.kept : [])
        .map((k) => obj(k))
        .filter((k) => typeof k.key === 'string')
        .map<KeptItem>((k) => ({ key: String(k.key), label: String(k.label ?? ''), section: String(k.section ?? '') }));
      return {
        path: rel,
        updated: typeof o.updated === 'string' ? o.updated : updated,
        deleted: count(o.deleted),
        sectionsDone: (Array.isArray(o.sections_done) ? o.sections_done : []).map(String),
        kept,
      };
    } catch {
      return { path: rel, updated, deleted: 0, sectionsDone: [], kept: [] };
    }
  }
  let deleted = 0;
  const sectionsDone: string[] = [];
  const kept: KeptItem[] = [];
  let section = '';
  let sectionDone = false;
  for (const line of txt.split('\n')) {
    const m = line.match(/^- \[([ xX])\]\s*`([^`]+)`\s*(?:—\s*(.*))?$/);
    if (!m) continue;
    const checked = m[1] !== ' ';
    const key = m[2];
    if (key.startsWith('section:')) {
      section = key.slice('section:'.length);
      sectionDone = checked;
      if (checked) sectionsDone.push(section);
      continue;
    }
    if (checked) deleted++;
    else if (sectionDone) kept.push({ key, label: (m[3] ?? '').replace(/\s*·\s*[^·]*$/, '').trim(), section });
  }
  const upd = txt.match(/Updated:\s*(\d{4}-\d{2}-\d{2})/);
  return { path: rel, updated: upd ? upd[1] : updated, deleted, sectionsDone, kept };
}

export function scanAudit(projectDir: string, override?: StageOverride): AuditStage {
  const auditDir = path.join(projectDir, 'audit');
  let names: string[] = [];
  try {
    names = fs.readdirSync(auditDir);
  } catch {
    names = [];
  }

  // Progress file first — the categories of every round are annotated with it.
  let progressFile: AuditProgress | undefined;
  for (const name of names) {
    if (!/^bubble_cleanup_progress__.*\.(md|json)$/i.test(name)) continue;
    const rel = `audit/${name}`;
    const txt = readText(path.join(projectDir, rel));
    if (!txt) continue;
    const parsed = parseProgress(rel, txt, statInfo(projectDir, rel)?.mtime.slice(0, 10));
    // Prefer the JSON (what the console writes); otherwise the most informative file wins.
    if (!progressFile || rel.endsWith('.json') || parsed.sectionsDone.length > progressFile.sectionsDone.length) progressFile = parsed;
  }

  const rounds = new Map<string, AuditRound>();
  for (const name of names) {
    const m = name.match(ROUND_RE);
    if (!m) continue;
    const version = m[2] ? Number(m[2]) : null;
    const key = version === null ? 'none' : String(version);
    const rel = `audit/${name}`;
    let round = rounds.get(key);
    if (!round) {
      round = { version, label: version === null ? '—' : `v${version}`, date: '', totalFindings: null, categories: [] };
      rounds.set(key, round);
    }
    if (m[3].toLowerCase() === 'audit.json') {
      round.json = rel;
      const j = readJson<Json>(path.join(projectDir, rel));
      if (j) {
        round.categories = categoriesFromAuditJson(j, progressFile);
        round.totalFindings = round.categories.reduce((s, c) => s + c.count, 0);
        round.totals = totalsFromAuditJson(j);
      }
    } else if (m[4]) {
      round.htmlEn = rel;
    } else {
      round.html = rel;
    }
  }

  const list = Array.from(rounds.values());
  for (const r of list) {
    const src = r.html ?? r.htmlEn ?? r.json;
    r.date = src ? dateOfReport(projectDir, src) : '';
  }
  list.sort((a, b) => (a.version ?? -1) - (b.version ?? -1) || a.date.localeCompare(b.date));

  const latest = list.length ? list[list.length - 1] : undefined;

  // Section sign-off: a section counts as resolved when nothing was found in it or the owner
  // ticked "audit of this section complete" in the report (kept items are recorded).
  const withFindings = new Set<string>();
  const resolvedSections = new Set<string>();
  for (const c of latest?.categories ?? []) {
    if (c.count > 0) {
      withFindings.add(c.section);
      if (c.resolved) resolvedSections.add(c.section);
    }
  }
  // a section with several categories is resolved only if all of them are
  for (const sec of withFindings) {
    const cats = (latest?.categories ?? []).filter((c) => c.section === sec && c.count > 0);
    if (!cats.every((c) => c.resolved)) resolvedSections.delete(sec);
  }

  let derived: AuditStage['derivedStatus'] = 'not_started';
  if (latest) {
    if (latest.totalFindings === 0) derived = 'done';
    else if (latest.totalFindings !== null && withFindings.size > 0 && resolvedSections.size === withFindings.size) derived = 'done';
    else derived = 'in_progress';
  }
  const status = override?.status ?? derived;

  let progress = 0;
  if (latest) {
    if (derived === 'done') progress = 1;
    else if (withFindings.size > 0 && (progressFile?.sectionsDone.length ?? 0) > 0) {
      progress = Math.max(0.1, resolvedSections.size / withFindings.size);
    } else {
      const first = list.find((r) => r.totalFindings !== null);
      if (first && first.totalFindings && latest.totalFindings !== null) {
        progress = Math.max(0.1, Math.min(0.95, 1 - latest.totalFindings / first.totalFindings));
      } else progress = 0.25;
    }
  }
  if (status === 'done') progress = 1;

  return {
    status,
    derivedStatus: derived,
    override,
    rounds: list,
    latest,
    progressFile,
    sectionsTotal: REPORT_SECTIONS.length,
    sectionsResolved: resolvedSections.size,
    sectionsWithFindings: withFindings.size,
    progress,
  };
}
