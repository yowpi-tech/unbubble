import 'server-only';
import fs from 'node:fs';
import path from 'node:path';
import { readJson, readText, statInfo } from '../fsx';
import type { AuditCategory, AuditRound, AuditStage, Confidence, StageOverride } from '../types';

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

/**
 * Category list mirrors the report sections of bubble_audit.py. Confidence follows
 * the skill's own framing: high = deterministic references, review = needs a human
 * (pages, plugins, mobile views), destructive = deleting also deletes data.
 */
export function categoriesFromAuditJson(j: Json): AuditCategory[] {
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

  const cat = (key: string, n: number, confidence: Confidence): AuditCategory => ({ key, count: n, confidence });

  return [
    cat('pages', count(pages.unused), 'review'),
    cat('reusables', count(reus.unused_hard) + count(reus.unused_transitive), 'high'),
    cat('backend', count(backend.unused_hard) + count(backend.unused_transitive), 'high'),
    cat('option_sets', count(os.unused), 'high'),
    cat('plugins', count(plugins.orphaned) + count(plugins.configured_no_ui), 'review'),
    cat('styles', count(styles.unused), 'high'),
    cat('variables', count(obj(vars.colors).unused) + count(obj(vars.fonts).unused), 'high'),
    cat('data_tables', count(dt.unused), 'destructive'),
    cat('data_fields', count(df.unused), 'destructive'),
    cat(
      'workflow_audit',
      count(wf.backend_custom_events_uncalled) +
        count(wf.page_custom_events_uncalled) +
        count(wf.triggers_on_missing_element) +
        count(wf.triggers_on_hidden_element_leads),
      'high',
    ),
    cat('api_connector', count(api.unused), 'high'),
    cat('removed_plugin_refs', count(rp.refs) || num(rp.total), 'high'),
    cat('mobile_views', count(mv.unused) + count(mv.broken_navigations), 'review'),
  ];
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
    const m = head.match(/(?:Gerado|Generated)[^<]{0,40}?(\d{4}-\d{2}-\d{2})/);
    if (m) return m[1];
  }
  const info = statInfo(projectDir, rel);
  return info ? info.mtime.slice(0, 10) : '';
}

export function scanAudit(projectDir: string, override?: StageOverride): AuditStage {
  const auditDir = path.join(projectDir, 'audit');
  const rounds = new Map<string, AuditRound>();

  let names: string[] = [];
  try {
    names = fs.readdirSync(auditDir);
  } catch {
    names = [];
  }

  for (const name of names) {
    const m = name.match(ROUND_RE);
    if (!m) continue;
    const version = m[2] ? Number(m[2]) : null;
    const key = version === null ? 'none' : String(version);
    const rel = `audit/${name}`;
    let round = rounds.get(key);
    if (!round) {
      round = {
        version,
        label: version === null ? '—' : `v${version}`,
        date: '',
        totalFindings: null,
        categories: [],
      };
      rounds.set(key, round);
    }
    if (m[3].toLowerCase() === 'audit.json') {
      round.json = rel;
      const j = readJson<Json>(path.join(projectDir, rel));
      if (j) {
        round.categories = categoriesFromAuditJson(j);
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

  // Deletion-tracker export, when the owner saved it next to the reports.
  let progressFile: AuditStage['progressFile'];
  for (const name of names) {
    if (/^bubble_cleanup_progress__.*\.(md|json)$/i.test(name)) {
      const rel = `audit/${name}`;
      const txt = readText(path.join(projectDir, rel));
      let deleted = 0;
      if (txt) {
        if (name.toLowerCase().endsWith('.json')) {
          try {
            const j = JSON.parse(txt) as { deleted?: unknown[] } | unknown[];
            deleted = Array.isArray(j) ? j.length : count((j as { deleted?: unknown[] }).deleted);
          } catch {
            deleted = 0;
          }
        } else {
          deleted = (txt.match(/^- \[x\]/gim) ?? []).length;
        }
      }
      if (!progressFile || deleted > progressFile.deleted) progressFile = { path: rel, deleted };
    }
  }

  let derived: AuditStage['derivedStatus'] = 'not_started';
  if (latest) derived = latest.totalFindings === 0 ? 'done' : 'in_progress';

  const status = override?.status ?? derived;

  // Progress: 1 when clean; otherwise how far the latest round is from the first one.
  let progress = 0;
  if (latest) {
    const first = list.find((r) => r.totalFindings !== null);
    if (latest.totalFindings === 0) progress = 1;
    else if (first && first.totalFindings && latest.totalFindings !== null) {
      progress = Math.max(0.1, Math.min(0.95, 1 - latest.totalFindings / first.totalFindings));
    } else progress = 0.25;
  }
  if (status === 'done') progress = 1;

  return { status, derivedStatus: derived, override, rounds: list, latest, progressFile, progress };
}
