import 'server-only';
import { execFile } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { promisify } from 'node:util';
import { readJson } from './fsx';
import { expandHome, prettyPath, repoDir } from './paths';
import type { ConnectedModeInfo, ConnectedProfile, ExportProvenance, ProjectConnection } from './types';

/**
 * Connected mode (unbubble:connect): the vendored befree-bubble-mcp driven through mcp/launch.py.
 *
 * The console never opens session material. The setup card asks the launcher itself
 * (`launch.py doctor --json`, which reports session existence and dates only); the project page
 * reads the profile list (settings.json), stats the session file of each profile and reads the
 * provenance sidecars of downloaded exports — files that carry no credentials.
 */

const run = promisify(execFile);

type Json = Record<string, unknown>;
const obj = (x: unknown): Json => (x && typeof x === 'object' && !Array.isArray(x) ? (x as Json) : {});
const str = (x: unknown): string | null => (typeof x === 'string' && x ? x : null);
const strs = (x: unknown): string[] => (Array.isArray(x) ? x.filter((v): v is string => typeof v === 'string') : []);

/** ~/.unbubble/mcp unless UNBUBBLE_MCP_HOME relocates it (same rule as mcp/launch.py). */
export function mcpHome(): string {
  const env = process.env.UNBUBBLE_MCP_HOME;
  return path.resolve(expandHome(env && env.trim() ? env : '~/.unbubble/mcp'));
}

/** Session file name of a profile, as the MCP stores it (sessions/<safe name>.json). */
function sessionFile(home: string, profile: string): string {
  return path.join(home, 'config', 'sessions', profile.replace(/[^A-Za-z0-9_-]/g, '_') + '.json');
}

function prettyDetail(detail: string): string {
  return detail.split(/(\s+)/).map((part) => (part.startsWith('/') ? prettyPath(part) : part)).join('');
}

function profileFrom(raw: Json): ConnectedProfile {
  return {
    name: String(raw.name ?? ''),
    appId: str(raw.app_id),
    appVersion: str(raw.app_version),
    sessionProfile: str(raw.session_profile),
    sessionCaptured: raw.session_captured === true,
    sessionUpdated: str(raw.session_updated),
    appSessions: strs(raw.app_sessions),
    rebuildSessions: strs(raw.rebuild_sessions),
  };
}

function provenanceFrom(file: string, raw: Json): ExportProvenance {
  return {
    file,
    appVersion: str(raw.app_version),
    fetchedAt: str(raw.fetched_at),
    sha256: str(raw.sha256),
    bytes: typeof raw.bytes === 'number' ? raw.bytes : null,
  };
}

async function doctorJson(launcher: string): Promise<{ stdout: string; error?: string }> {
  // The launcher needs only Python 3.8+; a GUI-started server may not have Homebrew on PATH.
  for (const python of ['python3', '/usr/bin/python3']) {
    try {
      const { stdout } = await run(python, [launcher, 'doctor', '--json'], { timeout: 30_000, maxBuffer: 1 << 20 });
      return { stdout };
    } catch (err) {
      const e = err as { code?: string; stdout?: string; message?: string };
      if (e.code === 'ENOENT') continue; // this python is not installed: try the next one
      // doctor exits 1 when a check fails, after printing its JSON report
      if (e.stdout) return { stdout: e.stdout };
      return { stdout: '', error: String(e.message ?? err).slice(0, 300) };
    }
  }
  return { stdout: '', error: 'python3 not found' };
}

export async function connectedMode(): Promise<ConnectedModeInfo> {
  const launcher = path.join(repoDir(), 'mcp', 'launch.py');
  const base: ConnectedModeInfo = {
    available: fs.existsSync(launcher),
    installed: false,
    launcher: prettyPath(launcher),
    home: prettyPath(mcpHome()),
    checks: [],
    hosts: {},
    profiles: [],
    exports: {},
    browsers: { shared: false, profiles: [], importable: [] },
  };
  if (!base.available) return base;
  const { stdout, error } = await doctorJson(launcher);
  let report: Json;
  try {
    report = obj(JSON.parse(stdout));
  } catch {
    return { ...base, error: error ?? 'launch.py doctor did not return JSON' };
  }
  const vend = obj(report.vendored);
  const exportsRaw = obj(report.exports);
  const exports: ConnectedModeInfo['exports'] = {};
  for (const [app, value] of Object.entries(exportsRaw)) {
    const v = obj(value);
    const latest = obj(v.latest);
    exports[app] = { count: typeof v.count === 'number' ? v.count : 0, latest: provenanceFrom(String(latest.file ?? ''), latest) };
  }
  return {
    ...base,
    installed: report.ok === true,
    vendored: typeof vend.commit === 'string' ? { commit: vend.commit, ref: String(vend.ref ?? ''), files: Number(vend.files ?? 0) } : undefined,
    checks: (Array.isArray(report.checks) ? report.checks : []).map((c) => {
      const o = obj(c);
      return { name: String(o.name ?? ''), ok: o.ok === true, detail: prettyDetail(String(o.detail ?? '')) };
    }),
    hosts: Object.fromEntries(Object.entries(obj(report.hosts)).map(([k, v]) => [k, v === true])),
    profiles: (Array.isArray(report.profiles) ? report.profiles : []).map((p) => profileFrom(obj(p))),
    exports,
    browsers: {
      shared: obj(report.browsers).shared === true,
      profiles: strs(obj(report.browsers).profiles),
      importable: strs(obj(report.browsers).importable),
    },
  };
}

function rolesFor(home: string, app: string): string[] {
  try {
    return fs
      .readdirSync(path.join(home, 'config', 'app-sessions', app.replace(/[^A-Za-z0-9._-]/g, '_')))
      .filter((f) => f.endsWith('.json') && !f.endsWith('.meta.json'))
      .map((f) => f.slice(0, -'.json'.length))
      .sort();
  } catch {
    return [];
  }
}

/** MCP profiles bound to this app and the newest export downloaded for it (no process spawned). */
export function projectConnection(appId: string): ProjectConnection | undefined {
  const home = mcpHome();
  const settings = obj(readJson(path.join(home, 'config', 'settings.json')));
  const profiles: ConnectedProfile[] = [];
  for (const [name, value] of Object.entries(obj(settings.profiles))) {
    const p = obj(value);
    if (p.app_id !== appId) continue;
    const owner = str(p.session_profile) ?? name;
    let updated: string | null = null;
    try {
      updated = fs.statSync(sessionFile(home, owner)).mtime.toISOString(); // existence and date only
    } catch {
      updated = null;
    }
    profiles.push({
      name,
      appId,
      appVersion: str(p.app_version),
      sessionProfile: str(p.session_profile),
      sessionCaptured: updated !== null,
      sessionUpdated: updated,
      appSessions: rolesFor(home, appId),
      rebuildSessions: rolesFor(home, `rebuild-${appId}`),
    });
  }
  profiles.sort((a, b) => a.name.localeCompare(b.name));

  let latestExport: ExportProvenance | undefined;
  let exportCount = 0;
  const folder = path.join(home, 'exports', appId);
  let names: string[] = [];
  try {
    names = fs.readdirSync(folder).filter((f) => f.endsWith('.bubble.meta.json'));
  } catch {
    names = [];
  }
  for (const name of names) {
    const meta = obj(readJson(path.join(folder, name)));
    if (!Object.keys(meta).length) continue;
    exportCount++;
    const prov = provenanceFrom(name.slice(0, -'.meta.json'.length), meta);
    if (!latestExport || (prov.fetchedAt ?? '') > (latestExport.fetchedAt ?? '')) latestExport = prov;
  }
  if (!profiles.length && !latestExport) return undefined;
  return { profiles, latestExport, exportCount };
}
