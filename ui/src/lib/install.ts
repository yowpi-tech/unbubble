import 'server-only';
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { isRepoDir, prettyPath, repoDir, repoVersion, projectsDir } from './paths';
import { listProjectIds } from './scan/project';
import type { HostInstall, HostKey, InstallLocation, SetupInfo, SkillPresence } from './types';

/** The core pipeline — "installed" means these three. */
const SKILLS: SkillPresence['skill'][] = ['audit', 'clone', 'level-up'];
/** Optional skills, reported when present (unbubble:connect needs the mcp/ install as well). */
const OPTIONAL_SKILLS: SkillPresence['skill'][] = ['connect'];
const ALL_SKILLS = [...SKILLS, ...OPTIONAL_SKILLS];

/**
 * Where each host looks for skills. Roots are relative to $HOME unless absolute.
 * `homeMarker` is the host's own folder — when it is missing, the host is not on this
 * machine at all (different from "installed, but without UnBubble").
 */
interface HostSpec {
  host: HostKey;
  label: string;
  vendor: string;
  homeMarker: string;
  roots: string[];
  envRoot?: string; // env var that relocates the host home (CODEX_HOME)
}

const HOSTS: HostSpec[] = [
  { host: 'claude', label: 'Claude Code', vendor: 'Anthropic', homeMarker: '.claude', roots: ['.claude/skills', '.claude/plugins'] },
  { host: 'codex', label: 'Codex (ChatGPT)', vendor: 'OpenAI', homeMarker: '.codex', roots: ['.codex/skills'], envRoot: 'CODEX_HOME' },
  { host: 'agents', label: 'Agent Skills (~/.agents)', vendor: 'cross-agent standard', homeMarker: '.agents', roots: ['.agents/skills'] },
  { host: 'cursor', label: 'Cursor', vendor: 'Anysphere', homeMarker: '.cursor', roots: ['.cursor/skills', '.cursor/skills-cursor'] },
  { host: 'gemini', label: 'Gemini CLI / Antigravity', vendor: 'Google', homeMarker: '.gemini', roots: ['.gemini/skills', '.gemini/antigravity/skills'] },
  { host: 'copilot', label: 'GitHub Copilot CLI', vendor: 'GitHub', homeMarker: '.copilot', roots: ['.copilot/skills'] },
  { host: 'opencode', label: 'OpenCode', vendor: 'SST', homeMarker: '.config/opencode', roots: ['.config/opencode/skills'] },
  { host: 'windsurf', label: 'Windsurf', vendor: 'Codeium', homeMarker: '.codeium/windsurf', roots: ['.codeium/windsurf/skills'] },
];

function sha(p: string): string | null {
  try {
    return crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
  } catch {
    return null;
  }
}

function realpath(p: string): string | null {
  try {
    return fs.realpathSync(p);
  } catch {
    return null;
  }
}

function isUnbubbleSkillMd(p: string): boolean {
  try {
    const head = fs.readFileSync(p, 'utf8').slice(0, 4000);
    return /unbubble/i.test(head);
  } catch {
    return false;
  }
}

/** Which UnBubble skills a folder provides, either nested (`skills/<s>/SKILL.md`) or directly (`SKILL.md`). */
function skillsIn(dir: string, repo: string): SkillPresence[] {
  const found: SkillPresence[] = [];
  for (const s of ALL_SKILLS) {
    const candidates = [path.join(dir, 'skills', s, 'SKILL.md'), path.basename(dir).endsWith(s) || path.basename(dir).includes(s) ? path.join(dir, 'SKILL.md') : ''].filter(Boolean);
    for (const c of candidates) {
      if (!fs.existsSync(c)) continue;
      if (!isUnbubbleSkillMd(c)) continue;
      const repoMd = path.join(repo, 'skills', s, 'SKILL.md');
      const a = sha(c);
      const b = sha(repoMd);
      found.push({ skill: s, path: c, inSync: a && b ? a === b : null });
      break;
    }
  }
  // A folder that IS a single skill without a recognizable name: read its frontmatter name.
  if (found.length === 0) {
    const direct = path.join(dir, 'SKILL.md');
    if (fs.existsSync(direct) && isUnbubbleSkillMd(direct)) {
      const m = fs.readFileSync(direct, 'utf8').match(/^name:\s*([\w-]+)/m);
      const s = m?.[1] as SkillPresence['skill'] | undefined;
      if (s && ALL_SKILLS.includes(s)) {
        const a = sha(direct);
        const b = sha(path.join(repo, 'skills', s, 'SKILL.md'));
        found.push({ skill: s, path: direct, inSync: a && b ? a === b : null });
      }
    }
  }
  return found;
}

function inspectEntry(entryPath: string, repo: string): InstallLocation | null {
  let lst: fs.Stats;
  try {
    lst = fs.lstatSync(entryPath);
  } catch {
    return null;
  }
  const isLink = lst.isSymbolicLink();
  const real = realpath(entryPath);
  if (!real) return null; // dangling symlink
  let st: fs.Stats;
  try {
    st = fs.statSync(real);
  } catch {
    return null;
  }
  if (!st.isDirectory()) return null;

  const repoReal = realpath(repo) ?? repo;
  const insideRepo = real === repoReal || real.startsWith(repoReal + path.sep);
  const skills = skillsIn(real, repo);
  const named = /unbubble/i.test(path.basename(entryPath));
  if (skills.length === 0 && !insideRepo && !named) return null;

  let version: string | undefined;
  try {
    version = JSON.parse(fs.readFileSync(path.join(real, '.claude-plugin', 'plugin.json'), 'utf8')).version;
  } catch {
    version = undefined;
  }
  const inSync = skills.length ? (skills.every((s) => s.inSync === true) ? true : skills.some((s) => s.inSync === null) ? null : false) : null;
  return {
    path: entryPath,
    kind: isLink ? 'symlink' : 'copy',
    target: isLink ? real : undefined,
    version,
    skills,
    complete: SKILLS.every((s) => skills.some((x) => x.skill === s)),
    inSync: isLink && insideRepo ? true : inSync,
  };
}

function scanRoot(root: string, repo: string): InstallLocation[] {
  const out: InstallLocation[] = [];
  let entries: string[] = [];
  try {
    entries = fs.readdirSync(root);
  } catch {
    return out;
  }
  for (const name of entries) {
    if (name.startsWith('.')) continue;
    const loc = inspectEntry(path.join(root, name), repo);
    if (loc) out.push(loc);
  }
  return out;
}

/** Claude Code plugins installed from a marketplace (~/.claude/plugins/installed_plugins.json). */
function claudePlugins(home: string, repo: string): InstallLocation[] {
  const out: InstallLocation[] = [];
  try {
    const raw = JSON.parse(fs.readFileSync(path.join(home, '.claude', 'plugins', 'installed_plugins.json'), 'utf8')) as {
      plugins?: Record<string, { installPath?: string; version?: string }[]>;
    };
    for (const [key, list] of Object.entries(raw.plugins ?? {})) {
      if (!/^unbubble@/i.test(key)) continue;
      for (const inst of list ?? []) {
        if (!inst.installPath) continue;
        const skills = fs.existsSync(inst.installPath) ? skillsIn(inst.installPath, repo) : [];
        out.push({
          path: inst.installPath,
          kind: 'plugin',
          version: inst.version,
          skills,
          complete: SKILLS.every((s) => skills.some((x) => x.skill === s)),
          inSync: skills.length ? skills.every((s) => s.inSync === true) : null,
        });
      }
    }
  } catch {
    /* no plugins file */
  }
  return out;
}

export function detectInstalls(): SetupInfo {
  const home = os.homedir();
  const repo = repoDir();
  const hosts: HostInstall[] = HOSTS.map((spec) => {
    const hostHome = spec.envRoot && process.env[spec.envRoot] ? path.resolve(process.env[spec.envRoot] as string) : path.join(home, spec.homeMarker);
    const detectedOnMachine = fs.existsSync(hostHome);
    const roots = spec.roots.map((r) => {
      if (spec.envRoot && process.env[spec.envRoot]) return path.join(hostHome, r.replace(spec.homeMarker + '/', ''));
      return path.join(home, r);
    });
    let locations: InstallLocation[] = [];
    for (const root of roots) {
      if (root.endsWith(path.join('.claude', 'plugins'))) continue; // handled below
      locations = locations.concat(scanRoot(root, repo));
    }
    if (spec.host === 'claude') locations = locations.concat(claudePlugins(home, repo));

    let status: HostInstall['status'] = 'not_installed';
    if (!detectedOnMachine) status = 'host_absent';
    else if (locations.some((l) => l.complete)) status = 'installed';
    else if (locations.some((l) => l.skills.length > 0)) status = 'partial';

    return {
      host: spec.host,
      label: spec.label,
      vendor: spec.vendor,
      detectedOnMachine,
      roots: roots.map(prettyPath),
      locations: locations.map((l) => ({ ...l, path: prettyPath(l.path), target: l.target ? prettyPath(l.target) : undefined, skills: l.skills.map((s) => ({ ...s, path: prettyPath(s.path) })) })),
      status,
    };
  });

  const pdir = projectsDir();
  return {
    repoDir: prettyPath(repo),
    repoIsValid: isRepoDir(repo),
    repoVersion: repoVersion(repo),
    projectsDir: prettyPath(pdir),
    projectsDirExists: fs.existsSync(pdir),
    projectCount: listProjectIds().length,
    home: prettyPath(home),
    hosts,
    scannedAt: new Date().toISOString(),
  };
}
