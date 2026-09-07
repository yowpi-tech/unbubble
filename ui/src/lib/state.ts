import 'server-only';
import fs from 'node:fs';
import path from 'node:path';
import { readJson } from './fsx';
import type { ProjectState, StageKey, StageOverride, StageStatus } from './types';

export const STATE_FILE = 'unbubble.json';

const STAGE_KEYS: StageKey[] = ['audit', 'clone', 'levelup_docs', 'levelup_impl'];

export function readState(projectDir: string): ProjectState {
  const raw = readJson<Partial<ProjectState>>(path.join(projectDir, STATE_FILE));
  return normalize(raw ?? {});
}

function normalize(raw: Partial<ProjectState>): ProjectState {
  const stages: ProjectState['stages'] = {};
  for (const k of STAGE_KEYS) {
    const s = raw.stages?.[k];
    if (s && typeof s === 'object') {
      const o: StageOverride = {};
      if (s.status === 'not_started' || s.status === 'in_progress' || s.status === 'done') o.status = s.status;
      if (typeof s.note === 'string' && s.note.trim()) o.note = s.note.trim();
      if (typeof s.updated_at === 'string') o.updated_at = s.updated_at;
      if (Object.keys(o).length) stages[k] = o;
    }
  }
  return {
    version: 1,
    name: typeof raw.name === 'string' && raw.name.trim() ? raw.name.trim() : undefined,
    stages,
    stories_done: Array.isArray(raw.stories_done)
      ? Array.from(new Set(raw.stories_done.filter((x): x is string => typeof x === 'string')))
      : [],
    links: raw.links && typeof raw.links === 'object' ? raw.links : {},
    notes: typeof raw.notes === 'string' ? raw.notes : undefined,
    updated_at: typeof raw.updated_at === 'string' ? raw.updated_at : undefined,
  };
}

export interface StatePatch {
  name?: string | null;
  stage?: { key: StageKey; status?: StageStatus | null; note?: string | null };
  storyToggle?: { id: string; done: boolean };
  storiesDone?: string[];
  links?: Partial<NonNullable<ProjectState['links']>>;
  notes?: string | null;
}

/** Merge a patch into the state file and write it back (pretty JSON, git-friendly). */
export function patchState(projectDir: string, patch: StatePatch): ProjectState {
  const cur = readState(projectDir);
  const now = new Date().toISOString();

  if (patch.name !== undefined) cur.name = patch.name ? patch.name.trim() : undefined;
  if (patch.stage) {
    const key = patch.stage.key;
    if (!STAGE_KEYS.includes(key)) throw new Error(`unknown stage: ${key}`);
    const existing = cur.stages?.[key] ?? {};
    const next: StageOverride = { ...existing };
    if (patch.stage.status === null) delete next.status;
    else if (patch.stage.status) next.status = patch.stage.status;
    if (patch.stage.note === null) delete next.note;
    else if (typeof patch.stage.note === 'string') next.note = patch.stage.note.trim() || undefined;
    next.updated_at = now;
    cur.stages = { ...(cur.stages ?? {}) };
    if (next.status || next.note) cur.stages[key] = next;
    else delete cur.stages[key];
  }
  if (patch.storyToggle) {
    const set = new Set(cur.stories_done ?? []);
    if (patch.storyToggle.done) set.add(patch.storyToggle.id);
    else set.delete(patch.storyToggle.id);
    cur.stories_done = Array.from(set).sort();
  }
  if (patch.storiesDone) cur.stories_done = Array.from(new Set(patch.storiesDone)).sort();
  if (patch.links) {
    cur.links = { ...(cur.links ?? {}) };
    for (const [k, v] of Object.entries(patch.links)) {
      const key = k as keyof NonNullable<ProjectState['links']>;
      if (v === null || v === undefined || (typeof v === 'string' && !v.trim())) delete cur.links[key];
      else if (typeof v === 'string') cur.links[key] = v.trim();
    }
  }
  if (patch.notes !== undefined) cur.notes = patch.notes ? patch.notes : undefined;
  cur.updated_at = now;

  const out: ProjectState = { version: 1 };
  if (cur.name) out.name = cur.name;
  if (cur.stages && Object.keys(cur.stages).length) out.stages = cur.stages;
  if (cur.stories_done && cur.stories_done.length) out.stories_done = cur.stories_done;
  if (cur.links && Object.keys(cur.links).length) out.links = cur.links;
  if (cur.notes) out.notes = cur.notes;
  out.updated_at = cur.updated_at;

  fs.writeFileSync(path.join(projectDir, STATE_FILE), JSON.stringify(out, null, 2) + '\n', 'utf8');
  return normalize(out);
}
