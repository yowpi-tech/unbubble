/**
 * BACKLOG.md story parser — mirrors the rules of skills/level-up/scripts/spec_coverage.py
 * (STORY_RE, INFRA_RE, NON_ATOMIC_*) so the console counts exactly what the gate counts.
 * Pure (no fs) so it can be unit-tested and reused client-side if needed.
 */
import type { BacklogEpic, BacklogStory } from '../types';

const STORY_RE = /^\s*[-*+]\s*\*\*([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*)\s*(?:\(([^)]*)\))?\s*\*\*/;
const INFRA_RE = /\[(infra|infraestrutura|infrastructure)\]/i;
const NON_ATOMIC_SIZE_RE = /^\s*G\b|\bG\s*(?:→|->|=>)/i;
const NON_ATOMIC_TEXT_RE = /\b(quebrar|decompor|break later|to split|split later)\b/i;
const ID_RE = /\b(?:BR-\d{2,4}|[A-Z]-[A-Z]{2,8}-\d{1,3})\b/g;

function stripMd(s: string): string {
  return s
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\s+/g, ' ')
    .trim();
}

export function parseBacklog(text: string): BacklogEpic[] {
  const lines = text.split('\n');
  const epics: BacklogEpic[] = [];
  let current: BacklogEpic | undefined;
  let story: BacklogStory | undefined;
  let buf: string[] = [];

  const flush = () => {
    if (!story) return;
    const full = buf.join(' ');
    story.text = stripMd(full.replace(STORY_RE, '')).slice(0, 400);
    story.infra = INFRA_RE.test(full);
    story.nonAtomic = (story.size ? NON_ATOMIC_SIZE_RE.test(story.size) : false) || NON_ATOMIC_TEXT_RE.test(full);
    story.cites = Array.from(new Set(full.match(ID_RE) ?? []));
    story = undefined;
    buf = [];
  };

  lines.forEach((line, idx) => {
    const h = line.match(/^(#{2,3})\s+(.*)$/);
    if (h) {
      flush();
      if (h[1] === '##') {
        current = { title: stripMd(h[2]), stories: [] };
        epics.push(current);
      } else if (current) {
        // ### sub-heading inside an epic: keep it as a sub-epic for readability
        current = { title: stripMd(h[2]), stories: [] };
        epics.push(current);
      }
      return;
    }
    const m = line.match(STORY_RE);
    if (m) {
      flush();
      if (!current) {
        current = { title: 'Backlog', stories: [] };
        epics.push(current);
      }
      story = {
        id: m[1],
        size: m[2]?.trim() || undefined,
        epic: current.title,
        text: '',
        infra: false,
        nonAtomic: false,
        cites: [],
        line: idx + 1,
      };
      current.stories.push(story);
      buf = [line];
      return;
    }
    if (story) {
      // continuation lines of a bullet (indented or plain text until the next bullet/blank)
      if (line.trim() === '' || /^\s*[-*+]\s/.test(line)) {
        flush();
      } else buf.push(line);
    }
  });
  flush();

  return epics.filter((e) => e.stories.length > 0);
}
