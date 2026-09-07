# UnBubble console (ui/)

A local web console for the UnBubble pipeline. It reads `~/UnBubble-Projects/<app-id>/` and
shows, per project, how far the three stages are:

| Stage | Derived from |
|---|---|
| **Audit** | `audit/<app>-vN_audit.json` (findings per category per round) + the HTML reports (embedded) + `audit/bubble_cleanup_progress__<app>.json` (deletions, per-section sign-offs and items kept on purpose — auto-saved by the embedded report through `PUT /api/projects/<app>/audit-progress`) |
| **Clone · docs** | `inventory/summary.json`, `secrets/ENV-KEYS.md` (+ `.env` existence only), `docs/00…08-*.md`, `PRD-clone.md`, `PARITY-MATRIX.md` (rows with/without disposition), `08-open-questions.md` (blocking / decisions) |
| **Level-up · docs** | the nine files of `levelup/` + `spec-coverage.json` (gate) + `parity-report.json` |
| **Level-up · implementation** | stories parsed from `levelup/BACKLOG.md` (same rules as `spec_coverage.py`) ticked off in the UI |

It also detects **where the skills are installed** (Claude Code, Codex/ChatGPT, `~/.agents`,
Cursor, Gemini, Copilot, OpenCode, Windsurf), whether each copy is in sync with this repo, and
walks a new user through a 4-step onboarding (`/setup`).

## Run

```bash
cd ui
npm install
npm run dev        # http://localhost:3333
```

`npm run build && npm start` for a production build. Node 20+.

Optional env vars (see `.env.example`): `UNBUBBLE_PROJECTS_DIR` (default `~/UnBubble-Projects`),
`UNBUBBLE_REPO_DIR` (default: the parent of `ui/`).

## Storage model — files are the source of truth

There is **no database**. Everything the console shows is derived, on every request, from the
files the skills already write. The only file the console writes is
**`<project>/unbubble.json`** (manual stage overrides + notes, ticked backlog stories, links,
display name). It is plain JSON, safe to commit, and safe to delete (the derived status comes
back).

```json
{
  "version": 1,
  "name": "My App",
  "stages": { "audit": { "status": "done", "note": "re-exported lean on 2026-07-15" } },
  "stories_done": ["H1-1", "H1-2"],
  "links": { "rebuild_repo": "~/Code/my-app-v2", "github": "https://github.com/…" }
}
```

The live secrets file (`secrets/.env`) is never read nor served; `ENV-KEYS.md` and
`.env.example` (names only) are.

## Layout

```
src/lib/scan/      audit.ts · clone.ts · levelup.ts · backlog.ts · project.ts  (derivation)
src/lib/install.ts skill-install detection across agent hosts
src/lib/state.ts   unbubble.json read/patch
src/app/api/       projects, projects/[id], …/docs, …/file, …/state, setup
src/components/    ui/ (shadcn base-nova, same kit as BubbleDocs), layout/, project/, docs/, setup/
```

UI kit, sidebar, breadcrumb, doc viewer with table of contents and the Mermaid renderer were
reused from BubbleDocs; Markdown is rendered with `react-markdown` (the skills emit plain
Markdown, not MDX).

## Adding a language

The console ships in English, Português (Brasil) and Español. Translations live in
`src/lib/i18n/locales/`, one file per language, registered in `src/lib/i18n/index.ts`; English is
the reference dictionary and anything a locale leaves out falls back to it. The step-by-step
recipe, written so an LLM can follow it, is the **Languages** chapter of the
[root README](../README.md#languages): copy `locales/en.ts`, translate the values (keep keys,
placeholders and product terms), append one entry to `LOCALES`, run `tsc` + `eslint`, check the
menu.

## Logo animation

`public/brand/unbubble.gif` (and the static `unbubble.png` + `src/app/icon.png` favicon) are rendered
by `scripts/make-logo.py`: a soap bubble grows, pops and frees the cube that was inside it. Regenerate
with `python3 scripts/make-logo.py --sheet` (needs Pillow; `--sheet` also writes a contact sheet of
key frames for review).

## Known build notice

`next build` prints a Turbopack warning ("Encountered unexpected file in NFT list … src/lib/install.ts").
It comes from the install detector walking home-directory paths at runtime; it only affects
`output: 'standalone'` file tracing, which this app does not use. Safe to ignore.
