import 'server-only';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

/** Expand a leading `~` to the user's home directory. */
export function expandHome(p: string): string {
  if (p === '~') return os.homedir();
  if (p.startsWith('~/')) return path.join(os.homedir(), p.slice(2));
  return p;
}

/** Where the pipeline writes project folders. */
export function projectsDir(): string {
  const env = process.env.UNBUBBLE_PROJECTS_DIR;
  return path.resolve(expandHome(env && env.trim() ? env : '~/UnBubble-Projects'));
}

/**
 * The UnBubble repo (the folder holding `skills/` and `.claude-plugin/plugin.json`).
 * Defaults to the parent of the `ui/` app, which is where this console lives.
 */
export function repoDir(): string {
  const env = process.env.UNBUBBLE_REPO_DIR;
  if (env && env.trim()) return path.resolve(expandHome(env));
  return path.resolve(/* turbopackIgnore: true */ process.cwd(), '..');
}

export function isRepoDir(dir: string): boolean {
  return (
    fs.existsSync(path.join(dir, 'skills', 'audit', 'SKILL.md')) &&
    fs.existsSync(path.join(dir, 'skills', 'clone', 'SKILL.md')) &&
    fs.existsSync(path.join(dir, 'skills', 'level-up', 'SKILL.md'))
  );
}

export function repoVersion(dir: string): string | undefined {
  try {
    const raw = fs.readFileSync(path.join(dir, '.claude-plugin', 'plugin.json'), 'utf8');
    const json = JSON.parse(raw) as { version?: string };
    return json.version;
  } catch {
    return undefined;
  }
}

/** Replace the home prefix with `~` for display. */
export function prettyPath(p: string): string {
  const home = os.homedir();
  return p.startsWith(home) ? '~' + p.slice(home.length) : p;
}

/**
 * Resolve a user-supplied relative path inside a project folder, refusing
 * traversal and the live secrets file. Returns null when not allowed.
 */
export function safeProjectPath(projectDir: string, rel: string): string | null {
  if (!rel || rel.includes('\0')) return null;
  const abs = path.resolve(projectDir, rel);
  const root = path.resolve(projectDir);
  if (abs !== root && !abs.startsWith(root + path.sep)) return null;
  const base = path.basename(abs);
  // The live credentials file is never served — names live in ENV-KEYS.md.
  if (base === '.env' || (base.startsWith('.env.') && base !== '.env.example')) return null;
  return abs;
}
